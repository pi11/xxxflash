"""Test harness: every session gets its own throwaway schema in the dev DB.

The schema (test_<random>) is created, migrated with the real Tortoise migrations and dropped
at the end. `public` (legacy) and `app` are never touched.
"""

import os
import secrets
import tempfile
from pathlib import Path

# Must happen before app.config is imported anywhere.
_SCHEMA = f"test_{secrets.token_hex(4)}"
_MEDIA = tempfile.mkdtemp(prefix="flash-media-")
os.environ.update(
    DB_SCHEMA=_SCHEMA,
    MEDIA_ROOT=_MEDIA,
    HIDE_COMPAT="missing,broken",
    RESEND_API_KEY="",
    SITE="xxxflash",
    SITE_URL="http://testserver",
    SECRET_KEY="test-secret",
    ADMIN_PREFIX="admin-test",
    DEBUG="0",
    # the ASGI test client reports its peer as "mockserver"; treat it as the reverse proxy
    TRUSTED_PROXIES="mockserver",
)

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from sanic import Sanic  # noqa: E402
from tortoise import Tortoise  # noqa: E402

from app.config import EXT_SCHEMA, settings, tortoise_config  # noqa: E402
from app.db import drop_schema, run_migrations  # noqa: E402

TABLES = [
    "game_translations",
    "theme_translations",
    "login_tokens",
    "votes",
    "comments",
    "screenshots",
    "game_themes",
    "games",
    "themes",
    "users",
    "bans",
    "banned_words",
]

Sanic.test_mode = True


@pytest.fixture(scope="session")
def media_root() -> Path:
    return Path(_MEDIA)


@pytest.fixture(scope="session", autouse=True)
async def database():
    await run_migrations(settings, _SCHEMA, quiet=True)
    await Tortoise.init(config=tortoise_config(settings, _SCHEMA))
    yield _SCHEMA
    await Tortoise.close_connections()
    await drop_schema(settings, _SCHEMA)


@pytest.fixture(autouse=True)
async def clean_tables(database):
    yield
    conn = await asyncpg.connect(
        settings.database_url, server_settings={"search_path": f"{_SCHEMA}, {EXT_SCHEMA}"}
    )
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


@pytest.fixture
def app():
    from app.server import create_app

    return create_app(settings, name=f"test_{secrets.token_hex(4)}", init_orm=False)


@pytest.fixture
def client(app):
    return app.asgi_client
