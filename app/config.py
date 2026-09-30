"""Settings loaded from `.env` (see `.env.example`)."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Extensions (pg_trgm) live in their own schema so the legacy `public` schema stays untouched.
EXT_SCHEMA = "ext"


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    site: str
    database_url: str
    db_schema: str
    legacy_schema: str
    media_root: Path
    media_url: str
    site_url: str
    secret_key: str
    resend_api_key: str
    email_from: str
    admin_emails: list[str]
    admin_prefix: str
    metrika_id: str
    games_per_page: int
    max_upload_mb: int
    trusted_proxies: list[str]
    hide_compat: list[str]
    debug: bool
    # Behind PgBouncer: no startup parameters (search_path comes from the role default set by
    # `python -m app migrate`) and no prepared-statement cache (breaks transaction pooling).
    db_pgbouncer: bool = False
    # UI language of the templates (ru | en) and whether comments are shown / accepted.
    language: str = "ru"
    show_comments: bool = True
    # Machine translation (adtr_client); see `python -m app translate`.
    adtr_user_id: int = 0
    adtr_api_key: str = ""
    translate_concurrency: int = 4
    comments_per_page: int = 20
    best_games_per_page: int = 20
    theme_games_per_page: int = 10
    search_games_per_page: int = 20
    page_links: int = 10
    extra: dict = field(default_factory=dict)

    @property
    def template_dir(self) -> Path:
        return BASE_DIR / "templates" / self.site

    @property
    def static_dir(self) -> Path:
        return BASE_DIR / "static" / self.site

    @property
    def vendor_dir(self) -> Path:
        return BASE_DIR / "static" / "vendor"


def load_settings(env_file: str | os.PathLike | None = None) -> Settings:
    load_dotenv(env_file or BASE_DIR / ".env", override=False)
    env = os.environ.get
    media_root = Path(env("MEDIA_ROOT", "./media"))
    if not media_root.is_absolute():
        media_root = BASE_DIR / media_root
    media_url = env("MEDIA_URL", "/media/")
    if not media_url.endswith("/"):
        media_url += "/"
    return Settings(
        site=env("SITE", "xxxflash"),
        database_url=env("DATABASE_URL", "postgres://flashxxx:123123@localhost:5432/flashxxx"),
        db_schema=env("DB_SCHEMA", "app"),
        legacy_schema=env("LEGACY_SCHEMA", "public"),
        media_root=media_root,
        media_url=media_url,
        site_url=env("SITE_URL", "http://localhost:8000").rstrip("/"),
        secret_key=env("SECRET_KEY", "dev-secret-change-me"),
        resend_api_key=env("RESEND_API_KEY", ""),
        email_from=env("EMAIL_FROM", "no-reply@authmail.click"),
        admin_emails=_list(env("ADMIN_EMAILS", "")),
        admin_prefix=env("ADMIN_PREFIX", "secret-admin").strip("/"),
        metrika_id=env("METRIKA_ID", ""),
        games_per_page=int(env("GAMES_PER_PAGE", "15")),
        max_upload_mb=int(env("MAX_UPLOAD_MB", "20")),
        trusted_proxies=_list(env("TRUSTED_PROXIES", "127.0.0.1")),
        hide_compat=_list(env("HIDE_COMPAT", "")),
        debug=_bool(env("DEBUG", "0")),
        db_pgbouncer=_bool(env("DB_PGBOUNCER", "0")),
        language=env("SITE_LANGUAGE", "ru").strip().lower(),
        show_comments=_bool(env("SHOW_COMMENTS", "1")),
        adtr_user_id=int(env("ADTR_USER_ID", "0") or 0),
        adtr_api_key=env("ADTR_API_KEY", ""),
        translate_concurrency=int(env("TRANSLATE_CONCURRENCY", "4")),
    )


def db_credentials(database_url: str) -> dict:
    url = urlparse(database_url)
    return {
        "host": url.hostname or "localhost",
        "port": url.port or 5432,
        "user": unquote(url.username or ""),
        "password": unquote(url.password or ""),
        "database": url.path.lstrip("/"),
    }


def search_path(schema: str) -> str:
    return f'"{schema}", {EXT_SCHEMA}'


def tortoise_config(settings: Settings, schema: str | None = None) -> dict:
    schema = schema or settings.db_schema
    credentials = db_credentials(settings.database_url)
    if settings.db_pgbouncer:
        # PgBouncer rejects the search_path startup parameter; the role default provides it.
        credentials["statement_cache_size"] = 0
    else:
        # asyncpg client turns this into the `search_path` startup parameter
        credentials["schema"] = search_path(schema)
    return {
        "connections": {
            "default": {"engine": "tortoise.backends.asyncpg", "credentials": credentials}
        },
        "apps": {
            "models": {
                "models": ["app.models"],
                "default_connection": "default",
                "migrations": "app.migrations",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


settings = load_settings()
# Used by the `tortoise` CLI ([tool.tortoise] in pyproject.toml).
TORTOISE_ORM = tortoise_config(settings)
