# Rewrite plan: Django `archive/` → Sanic

Goal: one Sanic codebase that runs the **xxxflash** and **flashsex** sites (one site per process, chosen with `SITE` in `.env`). The legacy templates are ported faithfully to Jinja2, and SWF games play in modern browsers through self-hosted **Ruffle**.

Background: [docs/legacy-analysis.md](docs/legacy-analysis.md) · [docs/architecture.md](docs/architecture.md) · [docs/data-migration.md](docs/data-migration.md) · [docs/ruffle.md](docs/ruffle.md)

## Scope decisions (agreed 2026-09-30)

**Stack:** Sanic, Tortoise ORM + asyncpg with its built-in migrations, Jinja2, `.env` config, and the Resend API for email (`no-reply@authmail.click`).

**In scope**
- Two template sets ported: `archive/templates/xxxflash/` and `archive/templates/flashsex.ru/`.
- Catalog: index, best (`-rate`), top (`-xrate`), popular (`-views`), random, themes, game page with the Ruffle player, view counter.
- Voting: +/-, one vote per IP per game, auto-hide when `rate < -4`, xrate ranking.
- Users: magic-link email login, comments, scores, banned words, IP bans, staff delete.
- Search (Postgres FTS) and user SWF uploads with a moderation queue.
- A small built-in admin: moderation, edit game and themes, comments, bans, banned words.
- A copy tool that moves legacy data (`flashxxx.public`) into the new schema (`flashxxx.app`), including users, comments and the vote history.
- Analytics: Yandex Metrika ID from `.env`.

**Out of scope (dropped)**
- Domains and host-based routing
- Banner slots and the `baner` app
- Mobile-carrier banners
- Social share widgets
- cbox chat and ad scripts
- All other template sets (including xfg0.com)
- Legacy `/page/N/` redirects
- Search stats
- Twitter posting
- The bookmark APIs
- Downloadable game type

## Phases

### Phase 0: Skeleton
- [ ] `pyproject.toml` (uv) with sanic, tortoise-orm[asyncpg]>=1.1, jinja2, python-dotenv, httpx, itsdangerous, pillow, pytest, pytest-asyncio, sanic-testing and ruff
- [ ] `app/config.py`: a `Settings` object loaded from `.env`. `.env.example` is committed
- [ ] `app/server.py`: `create_app()`, Tortoise init/close on server start/stop with credential `schema=DB_SCHEMA` (asyncpg → `search_path`), a Jinja env for `SITE`, static and media routes (dev)
- [ ] `TORTOISE_ORM` dict in `app/config.py`, plus `[tool.tortoise]` in `pyproject.toml` so the `tortoise` CLI finds it
- [ ] `python -m app migrate`: `CREATE SCHEMA IF NOT EXISTS app`, then Tortoise `migrate`
- [ ] `python -m app serve` with a dev auto-reload flag
- [ ] Test harness: DB `flashxxx` (`flashxxx`/`123123`@localhost). Each pytest session creates schema `test_<rand>`, generates the schema there, and drops it afterwards. Tests never touch `public` or `app`

### Phase 1: Models and legacy copy
- [ ] `app/models.py`: the Tortoise models (see architecture doc); `tortoise makemigrations` → `app/migrations/0001_initial.py`
- [ ] `RunSQL` migration: a generated `tsvector` column with a GIN index, plus a `pg_trgm` index on `name`
- [ ] `python -m app copy-legacy [--truncate] [--media PATH]` following `docs/data-migration.md`
- [ ] Row-count report vs. the expected counts, plus sequence reset
- [ ] `update-counts` command (`Theme.game_count`)
- [ ] Thumbnail pre-generation (350² and 50²) from `MEDIA_ROOT` (dev: `./media/`); skip missing files. Media inventory: see `docs/data-migration.md` (158 SWFs and 230 thumbnails missing, 1 158 games with no thumbnail)
- [ ] Thumbnail fallback: first screenshot, then a static `noimage`
- [ ] (optional) Render the missing thumbnails with Ruffle `exporter`
- [ ] Tests: the copy tool against a small fixture of legacy tables in the test schema

### Phase 2: Ruffle and SWF audit
- [ ] Vendor a pinned Ruffle self-hosted build into `static/ruffle/<ver>/`
- [ ] `static/_shared/player.js`: create the player, size it from the aspect ratio, show an error fallback
- [ ] `app/services/swf.py`: header parser (FWS/CWS/ZWS, version, rect, AS3 flag) and sha512, with unit tests
- [ ] `audit-swf` command: fills `compat`, `width`, `height`, `swf_version` and `filesize`, and writes a CSV report
- [ ] Manually test about 20 games per site (AS2 and AS3) in Chrome and Firefox, including a `parts/` loader game (`tsunade-and-horse`)
- [ ] Serve `media/parts/*` (no extension) as `application/x-shockwave-flash`. Ruffle `base` = `MEDIA_URL`
- [ ] Hide `HIDE_COMPAT` games. Add a note on `as3` game pages

### Phase 3: Catalog pages and template port (main focus)
- [ ] Paginator and page range (port of `get_page_range`, 10 links). Out-of-range pages clamp to the last page, and a non-integer `p` returns 404
- [ ] `/`, `/best/`, `/best2/`, `/popular/`, `/random/`, `/theme/<slug>/`, with the same filters and order as legacy
- [ ] `/game/<id>/`: 404 for inactive games; count views and recompute xrate only when a Referer is present; 7 random games; themes; first comment page
- [ ] `/get_comments/<id>/<page>/` fragment (fixes the broken "load more")
- [ ] Port **xxxflash** templates → `templates/xxxflash/`: base, index, game, theme, best_and_popular, search, upload-flash, flash-list, game-list-item, flash-best, flash-random, menu, paginator, comments, comments_list, comment-item, counters (Metrika only), banner-foot (drop), error, 404, 500, user/login, user/auth, user/panel
- [ ] Port **flashsex.ru** templates → `templates/flashsex/`: base, index, game, theme, best_and_popular, search, upload-flash, flash-list, flash-best, flash-random, menu, pages/pages_theme (as `?p=`), paginator, comments*, comment-item, 404, 500, user/*
- [ ] Copy the needed static assets from `archive/static/xxxflash/` and `archive/static/flashsex.ru/`. Vendor jQuery instead of loading it from a CDN
- [ ] Replace `<object>` with the Ruffle player. Remove dropped widgets. Change the `vote()` JS to POST with CSRF
- [ ] Visual check of every page in both sets against the legacy markup

### Phase 4: Users and interaction
- [ ] Resend mail service (`httpx` → `https://api.resend.com/emails`, `Authorization: Bearer $RESEND_API_KEY`, from `EMAIL_FROM`). With no key, log the link instead
- [ ] Magic-link login: `/login/`, `/auth/<uid>/<token>/`, `/logout/`, `/get-user-panel/`. Tokens are single-use, expire after 24h and are stored hashed
- [ ] Signed session cookie and CSRF (double-submit)
- [ ] `POST /mark/` voting with all the score rules
- [ ] `/add-comment`: ban check (403), honeypot, banned words, `score += 3`, redirect to `?new`
- [ ] Staff: `/del-comment/<id>` (penalize the **author** by −10) and `/ban/<id>/` (**staff only**)
- [ ] Rate limit for login emails and comments per IP

### Phase 5: Search and upload
- [ ] `/search/?q=` → `/search/<q>`, FTS + trigram, 20 per page
- [ ] `/upload/`: login required. Validate the SWF magic bytes and the size limit, dedupe by sha512, check the thumbnail with Pillow (350² RGB), parse the SWF header and store `active=false`. Email the admins through Resend and give the uploader `score += 10`

### Phase 6: Admin
- [ ] `/<ADMIN_PREFIX>/`, staff only
- [ ] Moderation queue of inactive games, with a Ruffle preview and approve/reject
- [ ] Edit a game (name, description, themes, thumbnail, active, date), plus CRUD for themes
- [ ] Comments list with search, delete and ban-IP actions. CRUD for bans and banned words

### Phase 7: Ops
- [ ] nginx example: media and static served directly, `application/wasm` MIME type, CSP header
- [ ] systemd unit per site (separate env file); a daily cron job for `update-counts`

## Resolved defaults (change if needed)
- AS3 games stay visible with a warning.
- Legacy accounts keep working: the user enters their email and gets a link.
- Inactive legacy games are copied as inactive and show up in the moderation queue.

## Production-only (provided by the user at deploy time)
- The real media directory for `MEDIA_ROOT`. Dev uses `./media/`, already populated with the flashxxx media.
- `RESEND_API_KEY` in `.env`. Dev logs magic links instead of sending them.

## Waiting on the user
- The legacy flashsex DB restored somewhere, for the flashsex site's data.
