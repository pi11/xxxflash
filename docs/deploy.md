# Deployment

This guide runs production on one Linux host with nginx (optionally behind Cloudflare), systemd, Postgres and optionally PgBouncer.

Each site is its own app process with its own env file:

| Instance          | Env file            | What it is                                          |
|-------------------|---------------------|-----------------------------------------------------|
| `xxxflash`        | `.env.xxxflash`     | Russian xxxflash                                    |
| `xxxflash-en`     | `.env.xxxflash-en`  | English xxxflash: same DB schema and media, `SITE_LANGUAGE=en`, `SHOW_COMMENTS=0` |
| `flashsex`        | `.env.flashsex`     | flashsex.ru: its **own** `DB_SCHEMA` and `MEDIA_ROOT` |

Paths below assume the checkout lives in `/srv/xxxflash` and media in `/srv/media/<site>`. Adjust them to your layout, for example `/var/www/...`. The same paths appear in `deploy/flash@.service`, `deploy/nginx.conf.example` and `deploy/flash-counts.cron.example`.

## 1. Requirements

- Python 3.11+ with `venv` (Debian 12's 3.11 works), plus `git`, `curl` and `unzip` (for `scripts/fetch_ruffle.sh`).
- Postgres with the contrib package (`pg_trgm`). The app role needs `CREATE` on the database, because it creates the schemas `app` and `ext` and the `pg_trgm` extension, a trusted extension since PG 13. It does not need to create databases.
- nginx, whose `mime.types` must map `application/wasm wasm` (recent versions do).
- A Resend API key for login emails. The sender is always `no-reply@authmail.click`.
- An adtr API user and key, only for the English site's machine translation.

## 2. First install

```bash
cd /srv
git clone <repo> xxxflash && cd xxxflash
python3 -m venv .venv && .venv/bin/pip install -e .
./scripts/fetch_ruffle.sh          # pinned Ruffle build (VERSION) -> static/vendor/ruffle/, ~30 MB
```

### Env files

Copy `.env.example` once per instance (`cp .env.example .env.xxxflash`, and so on), then set:

| Key | Notes |
|-----|-------|
| `PORT` | Used only by systemd. Give each instance its own port, e.g. 8001 / 8002 / 8003. |
| `SITE` | `xxxflash` or `flashsex`. |
| `SITE_LANGUAGE`, `SHOW_COMMENTS` | `ru`/`1` normally; `en`/`0` for the English site. |
| `DATABASE_URL` | The production DSN. Point it at PgBouncer (e.g. `:6432`) and set `DB_PGBOUNCER=1` if you use it; see [architecture.md](architecture.md#behind-pgbouncer-db_pgbouncer1). |
| `DB_SCHEMA` | `app` for xxxflash **and** xxxflash-en, which share the same data; use another schema for flashsex. |
| `MEDIA_ROOT`, `MEDIA_URL` | Absolute path, e.g. `/srv/media/xxxflash`, and `/media/`. |
| `SITE_URL` | Public `https://` URL, used in magic-link emails. |
| `SECRET_KEY` | Long and random (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`). Keep it stable, because changing it logs everyone out. The EN and RU instances may differ. |
| `RESEND_API_KEY`, `ADMIN_EMAILS` | Without the key, emails are only logged and nobody can log in. |
| `ADMIN_PREFIX` | Admin lives at `/<ADMIN_PREFIX>/`. Pick something non-obvious. |
| `TRUSTED_PROXIES` | `127.0.0.1` (nginx). See the Cloudflare section. |
| `HIDE_COMPAT` | `missing,broken` once media is in place (empty while it is not). |
| `METRIKA_ID` | Yandex Metrika counter; leave empty for none. |
| `ADTR_USER_ID`, `ADTR_API_KEY` | In the env file the translate cron sources. |

Keys from systemd's `EnvironmentFile` win. A plain `.env` in the checkout, if present, only fills keys the instance file lacks. Keep the files readable only by the service user (`chmod 640`, owner `root:www-data`).

### Media

Put the legacy media tree (`swf/`, `th/`, `parts/`, `screenshots/`) in `MEDIA_ROOT`. The service user must be able to **write** to it, because uploads, new thumbnails and `cache/` go there:

```bash
chown -R www-data:www-data /srv/media/xxxflash
```

### Database

```bash
set -a; . ./.env.xxxflash; set +a
.venv/bin/python -m app migrate                    # schemas app+ext, pg_trgm, migrations
.venv/bin/python -m app copy-legacy --truncate     # legacy `public` tables -> app (once)
.venv/bin/python -m app audit-swf                  # SWF compat / sizes; needs MEDIA_ROOT
.venv/bin/python -m app update-counts
.venv/bin/python -m app create-staff you@example.com
```

`copy-legacy --truncate` **empties the app tables first**, so run it only on the first install or for a deliberate re-import. [data-migration.md](data-migration.md) describes it.

The English site needs translations, otherwise it shows no games. Start with a dry run:

```bash
.venv/bin/python -m app translate --lang en --dry-run
.venv/bin/python -m app translate --lang en --limit 50     # most viewed first; billed per call
.venv/bin/python -m app translate --lang en                # everything (about 3–5 s per text)
```

A full run takes hours. Run it in `tmux` or `screen`; it is idempotent and safe to stop and restart.

## 3. systemd

```bash
cp deploy/flash@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now flash@xxxflash flash@xxxflash-en
journalctl -u flash@xxxflash -f
```

The unit runs `python -m app serve --host 127.0.0.1 --port $PORT --workers 2` from the instance's env file. Raise `--workers` for more CPU.

## 4. nginx

Start from `deploy/nginx.conf.example`, using one `server` block per site:

- `/static/` → `static/<SITE>/`, `/vendor/` → `static/vendor/` (Ruffle, player, admin scripts).
- `/media/` → `MEDIA_ROOT`. `/media/parts/` is served as `application/x-shockwave-flash`, because loader games fetch extensionless files there.
- The CSP must keep `'wasm-unsafe-eval'`, or Ruffle cannot start.
- `client_max_body_size` must be at least `MAX_UPLOAD_MB` plus some margin.

The English site is a second `server` block. Its `server_name` and `upstream` point to the `xxxflash-en` port; the `static`, `vendor` and `media` paths are the same as for xxxflash.

```nginx
upstream flash_xxxflash_en { server 127.0.0.1:8002; }
server {
    server_name example-en.com;
    # ... same locations as the xxxflash block ...
    location / { proxy_pass http://flash_xxxflash_en; ... }
}
```

### Behind Cloudflare

**Real client IP.** Without this, Sanic sees Cloudflare's edge IPs, which breaks per-IP vote limits, IP bans and comment checks. Generate a real-IP include and refresh it now and then:

```bash
{ for u in ips-v4 ips-v6; do curl -fsS https://www.cloudflare.com/$u | sed 's/.*/set_real_ip_from &;/'; done
  echo 'real_ip_header CF-Connecting-IP;'; } > /etc/nginx/cloudflare-realip.conf
```

Then `include /etc/nginx/cloudflare-realip.conf;` in each server block and pass `proxy_set_header X-Forwarded-For $remote_addr;`, as in the example.

**Caching.** `vendor()` URLs carry `?v=<content hash>`, so a deploy never pairs a stale cached `ruffle.js` with new `.wasm` files. Keep Cloudflare's default caching level, which includes the query string in the cache key. Never cache HTML: pages carry session and CSRF cookies. If Ruffle reports `failed to fetch Wasm: 404`, purge `/vendor/*` ([ruffle.md](ruffle.md)).

## 5. Cron

`deploy/flash-counts.cron.example` → `/etc/cron.d/flash`:

- `update-counts` runs daily and recomputes genre game counts.
- `translate --lang en` runs every 10 minutes under `flock`. It translates new and changed games and retries failed ones. Enable it **after** the initial full run. Its log (`/var/log/flash-translate.log`) must be writable by `www-data`:
  `touch /var/log/flash-translate.log && chown www-data /var/log/flash-translate.log`.

## 6. Updating

```bash
cd /srv/xxxflash
git pull
.venv/bin/pip install -e .                        # if pyproject.toml changed
set -a; . ./.env.xxxflash; set +a
pg_dump -n app "$DATABASE_URL" > ~/app-$(date +%F).sql   # before migrations; they only go forward
.venv/bin/python -m app migrate                   # no-op when nothing is new
./scripts/fetch_ruffle.sh                         # only if static/vendor/ruffle/VERSION changed
systemctl restart 'flash@*'
```

With PgBouncer, `migrate` sets the role's `search_path` default and replaces stale pooled sessions itself, logging "search_path is stale on pooled sessions" the first time ([architecture.md](architecture.md#behind-pgbouncer-db_pgbouncer1)).

Always restart, even for template, CSS or JS-only changes: each process computes the `/vendor/` cache-busting hashes once, at first use.

## 7. Checks after a deploy

- `/` and a game page load, and the game starts. Check the browser console for Ruffle errors.
- `/<ADMIN_PREFIX>/` opens for a staff user, and login emails arrive (check Resend's logs).
- On the English site, genres and games show English text and comments are absent.
- `journalctl -u 'flash@*' --since -10min` shows no tracebacks.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `unsupported startup parameter: search_path` | Behind PgBouncer: set `DB_PGBOUNCER=1` and run `migrate`. |
| `current_schema() is 'public', expected 'app'` | The role's `search_path` default isn't active on pooled sessions. Run `migrate` (it replaces idle ones); if it persists, `RECONNECT` or restart PgBouncer and run `migrate` again. |
| `failed to fetch Wasm: 404` | A stale `ruffle.js` cached by the CDN or browser. Purge `/vendor/*`; current builds hash the URLs. |
| Every visitor has the same IP; one vote blocks all | Cloudflare real IP isn't configured (see above). |
| English site shows no games | No translations yet. Run `translate --lang en`. |
| Games list shrinks after `audit-swf` | `HIDE_COMPAT` hides `missing`/`broken`. Check `MEDIA_ROOT` and the dashboard counts. |
| Login email never arrives | `RESEND_API_KEY` is unset (the log says "email … not sent"), or the sender domain isn't verified in Resend. |
| Uploads fail with permission errors | `MEDIA_ROOT` isn't writable by the service user. |
