# Legacy data copy

## Sources

| What | Where |
|---|---|
| Legacy flashxxx DB (for the xxxflash site) | Already restored in the local DB **`flashxxx`**, schema `public` (`postgres://flashxxx:123123@localhost/flashxxx`) |
| Legacy flashsex DB (for the flashsex site) | Not restored yet. The user will provide it |
| Media (SWF, thumbs, screenshots, avatars) | Dev: `./media/` in the project (git-ignored, may be empty or hold a sample). Production: the real path is set in `MEDIA_ROOT`. Do not go looking for it outside the project |

Do not commit dumps or media.

## Tool: `python -m app copy-legacy`

```bash
.venv/bin/python -m app copy-legacy [--truncate] [--media PATH]
```

- Reads legacy tables from `LEGACY_SCHEMA` (default `public`) and writes Tortoise models into `DB_SCHEMA` (default `app`), both in `DATABASE_URL`.
- It requires an up-to-date schema: run `python -m app migrate` first (it creates the `app` schema and applies Tortoise migrations).
- It is idempotent: `--truncate` clears the `app.*` tables, then reloads them.
- It reads legacy rows **by column name** (`SELECT col AS …`), because column order differs between the flashxxx and flashsex dumps.
- It writes every table with asyncpg `copy_records_to_table` in one transaction (about 2 s for the whole flashxxx DB). COPY bypasses Tortoise defaults, so every NOT NULL column must be supplied explicitly.
- At the end it resets sequences, prints a row-count report (legacy vs. new), and recomputes `Theme.game_count`.

Then run `python -m app audit-swf` to fill in `compat`, `width` and `height` from the SWF files.

## Mapping

| Legacy (`public`) | New (`app`) | Notes |
|---|---|---|
| `auth_user` + `flash_profile` | `User` | Import users with a non-empty email, plus any user referenced by a game, comment or vote. Carry over `is_staff`, `is_active`, `profile.score` and `profile.avatar`. Passwords are dropped (login is by magic link). `legacy_id` = old id. Duplicate emails, compared case-insensitively, are merged into the lowest id |
| user `Anonymous` | `User(username='Anonymous')` | Owns bulk-loaded games |
| `flash_theme` | `Theme` | `url`→`slug`, `order`→`sort_order` |
| `flash_flash` | `Game` | Same `id`. `flashfile`→`swf_path`, `thumbfile`→`thumb_path`, `publication_date`→`published_at`, `datahash`→`sha512`. `game_type=1` rows are imported as inactive |
| `flash_flash_theme` | `Game.themes` | |
| `flash_screenshot` | `Screenshot` | |
| `flash_cmark` | `Vote` | `mark`→`value`, `publication_date`→`created_at` |
| `flash_mark` | — | Dropped. `Game.rate` is the source of truth |
| `flash_comment` | `Comment` | |
| `flash_ban` | `Ban` | Deduplicated |
| `flash_bannedword` | `BannedWord` | Lowercased and deduplicated |
| `flash_search`, `flash_myflash`, `emailuser_*`, `social_auth_*`, `registration_*`, `baner_*`, `django_*`, `admin_tools_*`, `south_*` | — | Not copied |

Expected counts for flashxxx: 3 422 games, 25 themes, 8 723 game-theme links, 1 565 screenshots, 14 426 comments, 231 765 votes, 5 bans, 44 banned words.

## Media

### Dev media inventory (`./media/`, flashxxx data, checked 2026-09-30)

| Dir | Files | DB references | Missing on disk |
|---|---:|---|---:|
| `swf/` (by year, plus `swf/all/`) | 3 442 (3 426 `.swf`) | `flash_flash.flashfile`: 3 422 | **158** (74 of them active games) |
| `th/` | 2 247 | `flash_flash.thumbfile`: 2 264 non-empty. 1 158 games have **no** thumbnail | **230** |
| `screenshots/` | 1 587 | `flash_screenshot.image`: 1 565 | 0 |
| `avatars/` | 36 | `flash_profile.avatar`: 75 | 46 |
| `parts/` | 213 | none. These are extensionless SWFs (e.g. `ae-mainmenu`, Flash v9) that some games load at runtime | — |
| `flashgames/flash.zip` | 1 (500 MB) | none. **Password-protected**, 527 SWFs, no file name matches a missing game | — |
| `css/`, `js/`, `images/` | 7 | old static leftovers (`style.css`, `jquery.min.js`, `favicon.png`, `star.png`…) | — |

Copy-tool consequences:
- A missing SWF is copied anyway. `audit-swf` sets `compat='missing'`, and `HIDE_COMPAT=missing` hides it in production.
- A missing or empty thumbnail gets `thumb_path=NULL`. The templates fall back to the first screenshot if there is one, then to a static `noimage` placeholder.
- A missing avatar gets `avatar=NULL`.
- `parts/` and `flash.zip` are not referenced by the DB and are left as they are. `parts/` must stay served under `MEDIA_URL`, because games may request those files by relative URL (see `ruffle.md`).
- Optional later step: generate the ~1.4k missing thumbnails by rendering a frame with Ruffle's desktop `exporter` tool.

- `MEDIA_ROOT` keeps the legacy relative paths (`swf/…`, `th/…`, `screenshots/…`), so `swf_path` resolves as `MEDIA_ROOT / swf_path`.
- A missing media file is not an error during the copy (dev has no media). `audit-swf` flags it later.
- Thumbnails: the copy tool pre-generates the `350x350` and `50x50` (screenshot) variants into `MEDIA_ROOT/cache/`.
