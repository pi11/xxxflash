"""Schema bootstrap, migrations and connection helpers."""

import asyncio
import contextlib
import logging

import asyncpg
from tortoise import Tortoise, connections
from tortoise.migrations.api import migrate as tortoise_migrate

from app.config import EXT_SCHEMA, Settings, search_path, tortoise_config

log = logging.getLogger("app.db")


async def connect(settings: Settings) -> asyncpg.Connection:
    """Plain asyncpg connection (no startup parameters, PgBouncer-safe)."""
    kwargs = {"statement_cache_size": 0} if settings.db_pgbouncer else {}
    return await asyncpg.connect(settings.database_url, **kwargs)


async def ensure_schemas(settings: Settings, schema: str | None = None) -> None:
    """Create the app and extension schemas (Tortoise does not create schemas).

    Behind PgBouncer the search_path cannot be sent on connect, so it is stored as the role's
    default for this database instead. It applies to *new* server connections only.
    """
    schema = schema or settings.db_schema
    conn = await connect(settings)
    try:
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{EXT_SCHEMA}"')
        await conn.execute(f'CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA "{EXT_SCHEMA}"')
        if settings.db_pgbouncer:
            dbname = await conn.fetchval("SELECT current_database()")
            # `public` stays last so anything else using this role still finds its tables.
            await conn.execute(
                f'ALTER ROLE CURRENT_USER IN DATABASE "{dbname}" '
                f"SET search_path = {search_path(schema)}, public"
            )
    finally:
        await conn.close()
    if settings.db_pgbouncer:
        await refresh_pooled_sessions(settings, schema)


_CONN_ERRORS = (OSError, asyncpg.PostgresError, asyncpg.InterfaceError)

# Idle server sessions of this role in this database; PgBouncer replaces them on demand.
_TERMINATE_IDLE_SQL = """
SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
WHERE usename = current_user AND datname = current_database()
  AND state = 'idle' AND pid <> pg_backend_pid()
"""


async def refresh_pooled_sessions(settings: Settings, schema: str, attempts: int = 10) -> bool:
    """Make PgBouncer drop server sessions that predate the role's search_path default.

    PgBouncer keeps server connections open, and those still use the old search_path (our own
    connect in ensure_schemas has just opened one). Terminating idle backends of this role is
    harmless under transaction pooling: PgBouncer opens fresh ones, which pick up the default.
    """
    for _ in range(attempts):
        try:
            conn = await connect(settings)
        except _CONN_ERRORS:
            await asyncio.sleep(0.3)
            continue
        try:
            if await conn.fetchval("SELECT current_schema()") == schema:
                return True
            killed = await conn.fetchval(_TERMINATE_IDLE_SQL)
            log.warning("search_path is stale on pooled sessions; terminated %s idle", killed)
            # The session serving this query is stale too: end it as well.
            await conn.execute("SELECT pg_terminate_backend(pg_backend_pid())")
        except _CONN_ERRORS:
            pass  # expected: we just terminated this session
        finally:
            with contextlib.suppress(*_CONN_ERRORS):
                await conn.close()
        await asyncio.sleep(0.3)
    return False


async def drop_schema(settings: Settings, schema: str) -> None:
    if schema in ("public", EXT_SCHEMA, settings.legacy_schema):
        raise ValueError(f"refusing to drop schema {schema!r}")
    conn = await connect(settings)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await conn.close()


class SearchPathError(RuntimeError):
    pass


async def check_search_path(settings: Settings, schema: str | None = None) -> None:
    """Fail fast if the ORM connection would not resolve tables in the app schema."""
    schema = schema or settings.db_schema
    rows = await connections.get("default").execute_query_dict("SELECT current_schema() AS s")
    current = rows[0]["s"] if rows else None
    if current != schema:
        hint = (
            "Behind PgBouncer the role default applies to new server connections only. "
            "`python -m app migrate` replaces idle ones; if this persists, run `RECONNECT` on "
            "the PgBouncer admin console (or restart PgBouncer) and run migrate again."
            if settings.db_pgbouncer
            else "Check DB_SCHEMA and that `python -m app migrate` has run."
        )
        raise SearchPathError(f"current_schema() is {current!r}, expected {schema!r}. {hint}")


async def run_migrations(settings: Settings, schema: str | None = None, quiet=False) -> None:
    await ensure_schemas(settings, schema)
    config = tortoise_config(settings, schema)
    progress = None if quiet else _progress
    try:
        await Tortoise.init(config=config)
        # Never let migrations create tables in the wrong schema.
        await check_search_path(settings, schema)
        await tortoise_migrate(config=config, progress=progress)
    finally:
        await Tortoise.close_connections()


def _progress(event: str, app_label: str, name: str) -> None:
    if event == "apply_done":
        print(f"  applied {app_label}.{name}")
