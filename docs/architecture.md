# Target architecture (Sanic rewrite)

## Stack

| Concern | Choice |
|---|---|
| Runtime | Python 3.12+ (dev: 3.14) in a project `.venv`, `pip install -e ".[dev]"` |
| Web | Sanic 25.x |
| ORM | **Tortoise ORM** on the **asyncpg** backend (`asyncpg://…`) |
| Migrations | **Tortoise ORM built-in migrations** (tortoise-orm ≥ 1.0): `tortoise makemigrations` / `tortoise migrate` / `tortoise downgrade`. Configured through `[tool.tortoise] tortoise_orm = "app.config.TORTOISE_ORM"` in `pyproject.toml`. Migration files live in `app/migrations/`, set by `apps.models.migrations = "app.migrations"`. Postgres-specific SQL goes in `RunSQL` operations |
| Config | **`.env`**, loaded with `python-dotenv` into a typed `Settings` object (`app/config.py`). `.env` is never committed; `.env.example` is |
| Templates | Jinja2 (autoescape on), one template dir per site |
| Search | Postgres full-text search (`russian` config) on name + description through a raw query, with a `pg_trgm` fallback |
| Sessions | Signed cookie (`itsdangerous`) that holds only the user id |
| Email | **Resend HTTP API** (`POST https://api.resend.com/emails` via `httpx`), `from: no-reply@authmail.click`, key in `RESEND_API_KEY`. In dev with no key set, the link is logged instead of sent |
| Images | Pillow |
| Flash | Self-hosted Ruffle (see `ruffle.md`) |
| Tests | pytest + `sanic-testing`, run against the dev Postgres in a throwaway schema |

## Sites and config

There are two template sets: **`xxxflash`** and **`flashsex`**. Each running process serves **one** site, selected by `SITE` in `.env`. This mirrors the old `_PROJECT` setting. To run both sites, start two processes with different env files (`--env .env.flashsex`). There is no host-based routing and no domain handling in the app.

`.env` keys:

```dotenv
SITE=xxxflash                       # template/static set: xxxflash | flashsex
DATABASE_URL=postgres://flashxxx:123123@localhost:5432/flashxxx
DB_SCHEMA=app                       # new app tables live here
LEGACY_SCHEMA=public                # legacy Django tables (copy-tool source)
MEDIA_ROOT=./media                  # swf/, th/, screenshots/, cache/ (git-ignored; real path set in production)
MEDIA_URL=/media/
SITE_URL=http://localhost:8000      # used in magic links / emails
SECRET_KEY=change-me
RESEND_API_KEY=
EMAIL_FROM=no-reply@authmail.click
ADMIN_EMAILS=                       # comma separated, moderation notices
ADMIN_PREFIX=secret-admin
METRIKA_ID=
GAMES_PER_PAGE=15
MAX_UPLOAD_MB=20
TRUSTED_PROXIES=127.0.0.1
HIDE_COMPAT=                         # dev: empty (no media locally); production: missing,broken
```

Per-site text (titles, recommended links, info blocks) lives in the site's templates, not in config.

## Database layout

The dev DB `flashxxx` (user `flashxxx`, password `123123`, localhost) holds the **restored legacy flashxxx dump** in `public`. The role cannot create databases but can create schemas, so:

- `public`: legacy Django tables. **Read-only**, used only by the copy tool.
- `app`: the new schema. Tortoise connects with the credential `schema: DB_SCHEMA`, which the asyncpg client turns into `search_path`. Tortoise does not create schemas itself, so `python -m app migrate` runs `CREATE SCHEMA IF NOT EXISTS <DB_SCHEMA>` first and then calls Tortoise `migrate`. The migration history table also lives in `app`.
- `test_<random>`: created per pytest session and dropped at the end.

The flashsex site needs its own DB (or schema) with the legacy flashsex dump restored the same way. Then the same copy tool runs against it.

### Languages and the English site

The xxxflash templates are translated rather than duplicated. Every UI string is Russian source
wrapped in `_()` (or `plural(n, "игра|игры|игр")`), and `app/locales/en.json` maps it to English.
A missing entry falls back to the Russian source. `tests/test_i18n.py` fails if any template or
view string lacks an English entry.

The English site is the same code and database started with a different env file:

```dotenv
SITE=xxxflash
SITE_LANGUAGE=en
SHOW_COMMENTS=0
```

With `SHOW_COMMENTS=0`, no comments are rendered (game page, "latest comments") and
`/get_comments/…` and `/add-comment` return 404. Genre names are translated through the same
catalog. Game titles and descriptions are data and exist only in Russian.

### Behind PgBouncer (`DB_PGBOUNCER=1`)

PgBouncer rejects the `search_path` startup parameter (`unsupported startup parameter:
search_path`), and asyncpg's prepared-statement cache breaks under transaction pooling. With
`DB_PGBOUNCER=1`:

- The app and the Tortoise CLI send no startup parameters and use `statement_cache_size=0`.
- `python -m app migrate` stores the search path as the role default:
  `ALTER ROLE CURRENT_USER IN DATABASE <db> SET search_path = "app", ext, public`
  (`public` stays last so anything else on this role still finds its tables).
- The default applies to **new** server connections only. After the first `migrate`, run
  `RECONNECT` on the PgBouncer admin console (or restart PgBouncer).
- A guard checks `current_schema()` before migrating and at app start. It refuses to run
  instead of creating tables in `public`.
- The copy tool always uses `SET LOCAL search_path` inside its single transaction, so it works
  either way.

Alternatively, point `DATABASE_URL` straight at Postgres (port 5432) and leave the flag off.

## Package layout

```
app/
  __main__.py        CLI: serve | copy-legacy | audit-swf | update-counts | create-staff
  server.py          create_app(): Sanic app, Tortoise init/close listeners, middleware, blueprints
  config.py          Settings from .env; TORTOISE_ORM dict built from DATABASE_URL + DB_SCHEMA
  models.py          Tortoise models (below)
  views/
    catalog.py       / /best/ /best2/ /popular/ /random/ /theme/<slug>/ /search/
    game.py          /game/<id>/ /get_comments/<id>/<page>/
    vote.py          POST /mark/
    comments.py      POST /add-comment, /del-comment/<id>, /ban/<id>/
    upload.py        /upload/
    auth.py          /login/ /auth/<uid>/<token>/ /logout/ /get-user-panel/
    admin.py         /<ADMIN_PREFIX>/ moderation UI
  services/
    rules.py         vote scoring, xrate, auto-hide, comment filters (pure, unit-tested)
    swf.py           SWF header parse (sig, version, w/h, AS3 flag), hashing
    thumbs.py        resize/scale
    mail.py          Resend client: magic link, moderation notice
    paging.py        Paginator + page range (port of get_page_range)
  templating.py      Jinja env for SITE; globals (url_for, static, media, csrf_token, user, settings)
  copy_legacy.py     legacy public.* → app.* (`python -m app copy-legacy`)
  audit.py           `python -m app audit-swf`
  maintenance.py     `python -m app update-counts`
  queries.py         visible_games / random / best / search SQL
  web.py             session cookie, CSRF, client IP, auth decorators
scripts/fetch_ruffle.sh  downloads the pinned Ruffle build
app/migrations/          tortoise built-in migrations (0001_initial.py, 0002_search.py with RunSQL …)
templates/xxxflash/  templates/flashsex/
static/xxxflash/  static/flashsex/     served at /static/ (legacy CSS uses absolute /static/images/…)
static/vendor/                         served at /vendor/: jquery.min.js, site.js, site.css, player.js,
                                       ruffle/ (VERSION committed, build fetched by the script)
deploy/                                nginx, systemd and cron examples
tests/
```

## Tortoise models (schema `app`)

```python
class User(Model):        id, username(unique), email(unique, lowercased), is_staff, is_active,
                          score:int, avatar:str|None, created_at, last_login, legacy_id:int|None
class LoginToken(Model):  token_hash(pk), user→User, expires_at, used_at|None
class Theme(Model):       id, name, slug(unique), active, sort_order, game_count
class Game(Model):        id, name, description, user→User, swf_path, thumb_path, filesize:int,
                          rate:int, views:int, xrate:float, active:bool, published_at:date,
                          sha512(unique), swf_version:int|None, is_as3:bool, width:int, height:int,
                          compat:CharEnum(ok|as3|broken|missing|unknown)
                          themes = M2M(Theme, through="game_themes")
class Screenshot(Model):  id, game→Game, image_path
class Vote(Model):        id, game→Game, ip:str, value:int(±1), user→User|None, created_at
                          index (game_id, ip)
class Comment(Model):     id, game→Game, user→User, text, ip:str|None, ua:str|None, created_at
class Ban(Model):         ip(pk), created_at
class BannedWord(Model):  word(pk), created_at
```

Legacy IDs are preserved, so `/game/<id>/` URLs stay valid. Sequences are reset after the copy.
Full-text search uses a `RunSQL` migration that adds a generated `tsvector` column with a GIN index and a `pg_trgm` index. Views call it with `Game.raw(...)` / `connection.execute_query`.

Atomic counters (`views`, `rate`, `score`) use `F()` expressions (`Game.filter(id=…).update(views=F("views") + 1)`), not read-modify-write.

## Security and behaviour changes vs legacy

- Voting moves to `POST /mark/` with CSRF. The JSON shape `{"success": …}` is unchanged.
- `/ban/`, `/del-comment/` and the admin require `is_staff`.
- All state-changing forms carry a CSRF token: double-submit cookie plus a hidden field.
- The client IP comes from `X-Forwarded-For` only when the request comes from a `TRUSTED_PROXIES` address.
- Magic-link tokens are single-use, expire after 24h, and are stored hashed.
- Uploads are capped at `MAX_UPLOAD_MB` and validated by magic bytes. Files are stored under a random name.
- SWF responses are served with `Content-Type: application/x-shockwave-flash`, and `.wasm` with `application/wasm`.
