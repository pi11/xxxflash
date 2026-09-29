"""Schema bootstrap and migration helpers."""

import asyncpg
from tortoise import Tortoise
from tortoise.migrations.api import migrate as tortoise_migrate

from app.config import EXT_SCHEMA, Settings, tortoise_config


async def ensure_schemas(settings: Settings, schema: str | None = None) -> None:
    """Create the app schema and the extension schema (Tortoise does not create schemas)."""
    schema = schema or settings.db_schema
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{EXT_SCHEMA}"')
        await conn.execute(f'CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA "{EXT_SCHEMA}"')
    finally:
        await conn.close()


async def drop_schema(settings: Settings, schema: str) -> None:
    if schema in ("public", EXT_SCHEMA, settings.legacy_schema):
        raise ValueError(f"refusing to drop schema {schema!r}")
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await conn.close()


async def run_migrations(settings: Settings, schema: str | None = None, quiet=False) -> None:
    await ensure_schemas(settings, schema)
    config = tortoise_config(settings, schema)
    progress = None if quiet else _progress
    try:
        await tortoise_migrate(config=config, progress=progress)
    finally:
        await Tortoise.close_connections()


def _progress(event: str, app_label: str, name: str) -> None:
    if event == "apply_done":
        print(f"  applied {app_label}.{name}")
