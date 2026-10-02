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

Status as of 2026-09-30: phases 0–7 are implemented. 52 tests pass (`pytest`), and ruff is clean.
Both template sets were verified in headless Chromium: layout, the Ruffle player, a `parts/` loader
game, voting over POST+CSRF, and "load more comments".

### Phase 0: Skeleton
- [x] `pyproject.toml` with sanic, tortoise-orm[asyncpg]>=1.1, jinja2, python-dotenv, httpx, itsdangerous, pillow; dev extras: pytest, pytest-asyncio, sanic-testing, ruff
- [x] `app/config.py`: a `Settings` object loaded from `.env`; `.env.example` is committed
- [x] `app/server.py`: `create_app()`, Tortoise with `schema="app, ext"` (→ `search_path`), a Jinja env for `SITE`, static/vendor/media routes
- [x] `TORTOISE_ORM` in `app/config.py` and `[tool.tortoise]` in `pyproject.toml` for the `tortoise` CLI
- [x] `python -m app migrate`: creates the `app` and `ext` schemas and `pg_trgm` (in `ext`), then runs Tortoise `migrate`
- [x] `python -m app serve [--dev]` (Sanic AppLoader, multi-worker safe)
- [x] Test harness: each pytest session creates `test_<rand>`, applies the real migrations and drops it afterwards

### Phase 1: Models and legacy copy
- [x] `app/models.py`; `app/migrations/0001_initial.py` (generated)
- [x] `0002_search.py` (`RunSQL`): generated `tsvector` column with a GIN index, plus a trigram GIN index on `name`
- [x] `python -m app copy-legacy [--truncate] [--media PATH]` (asyncpg COPY; ~2 s for the whole flashxxx DB)
- [x] Row-count report (all 9 tables match the legacy counts), sequence reset
- [x] `update-counts` command
- [x] Thumbnail fallback: first screenshot, then a static `noimage.jpg`
- [ ] Thumbnail pre-generation (350² / 50² cache). Deferred: the originals are served as-is, as legacy did
- [ ] (optional) Render the ~1.4k missing thumbnails with Ruffle `exporter`
- [x] Test: the copy tool against a miniature legacy schema

### Phase 2: Ruffle and SWF audit
- [x] Ruffle self-hosted build pinned in `static/vendor/ruffle/VERSION` (`nightly-2026-09-29`), downloaded by `scripts/fetch_ruffle.sh` (the build itself is git-ignored)
- [x] `static/vendor/player.js`: sizes the player from the SWF aspect ratio (max 700px wide / 90vh) and shows an error fallback
- [x] `app/services/swf.py`: FWS/CWS/ZWS header parser (version, stage size, AS3 flag), with unit tests
- [x] `audit-swf`: dev result for active games: 1 461 ok, 139 as3, 74 missing; CSV in `var/`
- [x] `media/parts/*` served as `application/x-shockwave-flash`; Ruffle `base` = `MEDIA_URL`. Verified with `tsunade-and-horse` (loads `parts/tah-game`)
- [x] `HIDE_COMPAT` games hidden; AS3 note on game pages
- [ ] Manual play-through of ~20 games per site (AS2 and AS3) in real Chrome and Firefox

### Phase 3: Catalog pages and template port
- [x] Paginator (`?p=N`, clamps to the last page, 404 on a non-integer)
- [x] `/`, `/best/`, `/best2/`, `/popular/`, `/random/`, `/theme/<slug>/`, with the legacy filters and ordering
- [x] `/game/<id>/`: 404 for inactive games; views/xrate counted only with a Referer
- [x] `/get_comments/<id>/<page>/` ("load more" works again)
- [x] **xxxflash** templates → `templates/xxxflash/`
- [x] **flashsex.ru** templates → `templates/flashsex/` (the old `/page/N/` pagers now use `?p=`)
- [x] Shared partials in `templates/_shared/` (player, Metrika counter, login/upload bodies, staff actions, admin)
- [x] Static assets copied (banners, social icons and ad scripts dropped); jQuery 3.7.1 vendored
- [x] `<object>` → Ruffle; dropped widgets removed; `vote()` is a POST with CSRF
- [x] Visual check of both sets (headless Chromium screenshots)

### Phase 4: Users and interaction
- [x] Resend mail service (the link is logged when there is no key or DEBUG=1)
- [x] Magic-link login, logout, user panel; tokens are single-use, expire after 24h and are stored as sha256
- [x] Signed session cookie (itsdangerous) + double-submit CSRF
- [x] `POST /mark/` with the legacy score rules (the voter's +1 only counts real votes now)
- [x] `/add-comment` (ban → 403, honeypot, banned words, +3)
- [x] Staff-only `/del-comment/<id>` (author −10) and `/ban/<id>/`, both POST
- [x] Login-email rate limit (5/hour per IP and per address, in-process)
- [ ] Comment rate limit per IP

### Phase 5: Search and upload
- [x] `/search/?q=` → `/search/<q>` (FTS `russian` + trigram + substring), 20 per page
- [x] `/upload/`: SWF magic bytes + header, size limit, sha512 dedupe, Pillow thumbnail (350² JPEG), `active=false`, admin email, +10

### Phase 6: Admin (`/<ADMIN_PREFIX>/`, staff only)
- [x] Dashboard; moderation queue with a Ruffle preview; approve / delete
- [x] Edit game (name, description, themes, thumbnail, active, date); themes CRUD
- [x] Comments list with search, delete and ban-IP; bans and banned words CRUD
- [x] `python -m app create-staff <email>`

### Phase 8: Redesign and English site (2026-09-30)
- [x] xxxflash redesign ("velvet stage" theme, self-hosted Unbounded + Golos Text, no external links)
- [x] English version of xxxflash via a translation catalog (`SITE_LANGUAGE=en`), comments hidden and disabled (`SHOW_COMMENTS=0`)
- [x] English game titles/descriptions: machine translation (Phase 9)

### Phase 9: Fully translatable content (agreed 2026-09-30)
Translator: `adtr_client` (sync `requests`, one text per call, max 300 chars, raises
`requests.HTTPError` / `ValueError`, no batching or retries). Credentials `ADTR_USER_ID`,
`ADTR_API_KEY` in `.env`.

Decisions: a translation table (not per-language columns); the English site **hides** games
without an English translation; translate **all** games (3 422, ~6.9k API calls); ship ru + en
now, with a design ready for more languages.

- [x] Models + migration: `game_translations(game_id, language, name, description, source_hash,
      status: machine|edited|failed, error, translated_at)`, unique (game_id, language);
      `theme_translations(theme_id, language, name)` (genre names move out of `en.json`, seeded from it)
- [x] English FTS: generated `tsvector` (`english` config) + trigram index on the translated name
- [x] `app/services/translate.py`: wraps `adtr_client` in a thread pool (`TRANSLATE_CONCURRENCY`,
      default 4), retries with backoff on 429/5xx/timeouts, splits text > 300 chars at sentence
      boundaries, copies Latin-only titles as-is (190 titles), language code → API name map
- [x] `python -m app translate --lang en [--limit N] [--force] [--dry-run]`: idempotent via
      `source_hash` (sha256 of Russian name + description); new or changed games only; never touches
      `edited` rows; failures recorded and retried next run; progress + summary report
- [x] Cron example: `translate --lang en` every 10 min (new uploads, approvals, admin edits)
- [x] Queries: `SITE_LANGUAGE != ru` → catalog, search, random, best, theme counts use the translated
      name/description and exclude games without a translation
- [x] Templates: game name/description come from the translation (a `g.title` / `g.text`
      attribute set by the query layer), so templates stay language-agnostic
- [x] Admin: English title/description fields on the game edit page (saving marks `edited`),
      translation status per game, and a "re-translate" button
- [x] Tests with a fake translator (no network): chunking, Latin passthrough, idempotency, edited
      protection, failure retry, hide-untranslated on the English site

- [ ] Production: first full run `python -m app translate --lang en` (~6.9k calls, ~2 h), then enable the cron
- [ ] (optional) English URL slugs for games

### Phase 7: Ops
- [x] `deploy/nginx.conf.example` (static/media, `parts/` MIME type, CSP with `wasm-unsafe-eval`)
- [x] `deploy/flash@.service` (one instance per site / env file) and `deploy/flash-counts.cron.example`
- [x] `docs/deploy.md` (install, env files, nginx + Cloudflare real IP, cron, updates, troubleshooting)

## Resolved defaults (change if needed)
- AS3 games stay visible with a warning.
- Legacy accounts keep working: the user enters their email and gets a link.
- Inactive legacy games are copied as inactive and show up in the moderation queue.

## Production-only (provided by the user at deploy time)
- The real media directory for `MEDIA_ROOT`. Dev uses `./media/`, already populated with the flashxxx media.
- `RESEND_API_KEY` in `.env`. Dev logs magic links instead of sending them.

## Waiting on the user
- The legacy flashsex DB restored somewhere, for the flashsex site's data.
