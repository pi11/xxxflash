# AGENTS.md

This is a Sanic rewrite of an old Django 1.x / Python 2 Flash-games site. One codebase runs two sites, **xxxflash** and **flashsex**, one site per process, selected by `SITE` in `.env`. SWF games are played with self-hosted **Ruffle**, since browsers no longer ship Flash.

Read these first:
- `plan.md`: phased task list and scope decisions. Tick boxes as you finish items.
- `docs/legacy-analysis.md`: what the old app did, including the business rules to preserve and the bugs not to port.
- `docs/architecture.md`: stack, `.env` keys, models and DB layout.
- `docs/data-migration.md`: the legacy → new copy tool.
- `docs/ruffle.md`: player integration and SWF compatibility audit.

## Ground rules

- **Stay inside this project directory.** Do not scan or read paths outside it (backups, other projects, `/`) unless the user explicitly says to or gives the path.
- `archive/` is the **legacy Django app, read-only reference**. Never edit it, import from it, or run it.
  Port only `archive/templates/xxxflash/` and `archive/templates/flashsex.ru/`, plus their `archive/static/` counterparts. Ignore the other sets.
- The legacy tables in the `public` schema of DB `flashxxx` are **read-only**. Only the copy tool reads them.

## Stack

Sanic · Tortoise ORM (asyncpg backend) · Tortoise built-in migrations (`tortoise` CLI) · Jinja2 · python-dotenv (`.env`) · httpx for the Resend email API · Pillow · pytest.

## Database

- Dev DB: `postgres://flashxxx:123123@localhost:5432/flashxxx`
  - `public`: the legacy Django dump (read-only)
  - `app`: the new Tortoise schema (`DB_SCHEMA`)
  - `ext`: `pg_trgm` (kept out of `public`); `search_path` is `app, ext`
  - `test_<rand>`: created and dropped by each pytest session
- The role cannot create databases, only schemas.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
./scripts/fetch_ruffle.sh                     # pinned Ruffle build -> static/vendor/ruffle/
cp .env.example .env                          # set SECRET_KEY; RESEND_API_KEY only in production
.venv/bin/python -m app migrate               # schemas app+ext, pg_trgm, tortoise migrations
.venv/bin/tortoise makemigrations             # after changing app/models.py
.venv/bin/python -m app copy-legacy --truncate
.venv/bin/python -m app audit-swf
.venv/bin/python -m app serve --dev           # http://127.0.0.1:8000  (SITE=flashsex for the other set)
.venv/bin/python -m app create-staff you@example.com
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format .
```

## Conventions

- Python 3.12+ with async everywhere. Tortoise models live in `app/models.py`. Use `F()` expressions for counters (`views`, `rate`, `score`), never read-modify-write.
- Views are thin. Business rules (vote scoring, xrate, auto-hide, comment filters) are pure functions in `app/services/rules.py` and have unit tests.
- Keep legacy URL shapes (`/game/<id>/`, `/theme/<slug>/`, `?p=N`) and the `/mark/` JSON shape `{"success": ...}`.
- UI text in `templates/xxxflash/` (and `_shared/player.html`, `_shared/403.html`) is Russian source wrapped in `_()` / `plural()`; add the English entry to `app/locales/en.json` in the same change (`tests/test_i18n.py` enforces it). The English site runs with `SITE_LANGUAGE=en SHOW_COMMENTS=0`.
- Templates: Jinja2 with autoescape on. Port markup faithfully and change only what's required: Django → Jinja syntax, `<object>` → Ruffle player, removed widgets, CSRF tokens. User-facing text stays in Russian.
- All config comes from `.env` through `app/config.py`. Nothing environment-specific is hard-coded. `.env` is never committed; `.env.example` is.
- Email goes only through the Resend API, from `no-reply@authmail.click`, with the key in `RESEND_API_KEY`.
- Never commit DB dumps, media, or SWF files. In dev, media lives in `./media/` (git-ignored).
- Schema changes go through Tortoise migrations (`tortoise makemigrations`), never through hand-edited tables. Use `RunSQL` for Postgres-specific bits (FTS, trigram).
- State-changing endpoints are POST with CSRF, and staff-only actions check `is_staff`.
- Add or adjust tests with every behaviour change. Tests run against real Postgres, in a throwaway schema.
