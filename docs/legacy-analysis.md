# Legacy app analysis (`archive/`)

The code in `archive/` is a Django 1.8–1.11 era project on **Python 2**. It was kept in Mercurial and hosted on bitbucket.org/pi11/xxxflash.
It is **read-only reference material**. Do not modify it.

## Layout

| Path | What it is |
|---|---|
| `xxxflash/settings.py` | Base settings: paging sizes, thumb sizes, carrier IP ranges |
| `xxxflash/local_settings.py.example` | Per-deploy settings. `_PROJECT` picks the template, static and media set |
| `xxxflash/urls.py` | Mounts `flash.urls` plus Django admin at `/secret-admin-lol/` |
| `flash/models.py` | All models and two forms |
| `flash/views.py` | All views (~25) |
| `flash/templatetags/menu.py` | `get_themes`, `get_random_flashses`, `get_best_flashses` |
| `flash/templatetags/check_mobile.py` | Megafon/Beeline detection for carrier banners (**dropped**) |
| `flash/management/commands/` | `load_flash` (bulk SWF import), `update_games_count`, `updatehash`, `post-twit` |
| `flash/httputils.py` | memori.ru / b000.ru bookmark APIs (**dead, dropped**) |
| `templates/<site>/` | One template set per sister site (11 sets) |
| `static/<site>/` | CSS, images and JS per site |
| `sql_updates/*.sql` | Hand-written schema migrations from 2010–2013 |
| `data/megafon.txt`, `data/beeline.txt` | Carrier IP ranges (**dropped**) |
| `downloads/1.xml` | Alawar showroom export (downloadable games, unused) |

External dependencies came from the author's own bitbucket repos (now gone):
- `django-baner`: banner slots (`{% get_baner slot %}`)
- `django-email-auth` (`emailuser`): magic-link login
- `djangohelpers`: `scale()` thumbnails, `get_page_range`, `edge.is_mobile`

Search used Sphinx through `django-sphinx`.

## Sites

`_PROJECT` selects `templates/<_PROJECT>/`, `static/<_PROJECT>/` and `media/<_PROJECT>/`. All sites share the same code and differ only in templates, config and database.

Only these two are in scope for the rewrite:

| Site (`SITE`) | Legacy template set to port | Legacy data | Notes |
|---|---|---|---|
| `xxxflash` | `archive/templates/xxxflash/` + `archive/static/xxxflash/` | local DB `flashxxx`, schema `public` | Uses screenshots (1565 rows) |
| `flashsex` | `archive/templates/flashsex.ru/` + `archive/static/flashsex.ru/` | not restored yet | Game files live in `flashgames/` and `swf/all/`. No screenshots |

The other sets are ignored. That includes `xfg0.com`, a newer Bootstrap redesign of xxxflash.

## Data model (old)

```
Theme(id, name, url[slug], active, publication_date, count, order)        ordering -order, name
Flash(id, name, description, game_type{0 flash,1 downloadable}, user→User,
      flashfile, thumbfile, filesize(str), rate(int), views(int), active,
      publication_date(date), datahash(unique), is_posted, width, height, xrate(float))
Flash.theme  M2M Theme                (flash_flash_theme)
Screenshot(id, flash→Flash, image)
Mark(id, flash→Flash, mark)           denormalized total; duplicates Flash.rate
CMark(id, flash→Flash, ip, mark ±1, publication_date)   per-IP vote log
Comment(id, flash→Flash, user→User, text, ip, ua, publication_date(date))
Profile(id, user→User 1:1, score, avatar, site, about)  auto-created on user save
Ban(id, ip, publication_date)
BannedWord(id, word unique, publication_date)
Search(id, query, count)              search stats (not migrated)
MyFlash                               unused, 0 rows
```

Auth used `django.contrib.auth.User`, with `emailuser_emailuser` holding login tokens. A special user named `Anonymous` owns games that were bulk-loaded.

### Data volumes (dumps dated 2026-08-30)

| Table | flashxxx | flashsex |
|---|---:|---:|
| flash_flash | 3 422 | 3 412 |
| flash_flash_theme | 8 723 | 6 370 |
| flash_theme | 25 | 22 |
| flash_screenshot | 1 565 | 0 |
| flash_comment | 14 426 | 23 314 |
| flash_cmark (votes) | 231 765 | 54 118 |
| auth_user / flash_profile | 70 063 | 10 419 |
| flash_ban / bannedword | 5 / 44 | 26 / 16 |

In flashsex, about half the games are `active=f`. They were never moderated, or they were voted down.

## URLs and behaviour

The `?p=N` query parameter is the page number everywhere. An out-of-range page returns the **last** page (not 404). A non-integer page returns 404.

| URL | View | Behaviour |
|---|---|---|
| `/` | `index` | New games paginated (`GAMES_PER_PAGE` = 15, or 10 via local_settings). Filter: `active`, `rate > -2`, `publication_date <= now`. Ordered by `-publication_date, -rate, -views, -id`. Also shows: top 5 by `-rate` ("best"), 7 random games, active themes with count > 0, the last 5 comments (first page only), and the top 5 profiles by score (flashsex only) |
| `/best/` | `best_games` | Ordered by `-rate`, 20 per page |
| `/best2/` | `best_games2` | Ordered by `-xrate` ("Top"), 20 per page |
| `/popular/` | `popular_games` | Ordered by `-views`, 20 per page |
| `/random/` | `random_games` | 15 random games, rendered with `index.html` |
| `/theme/<slug>/` | `theme` | Games in the theme, ordered by `-xrate`, 10 per page |
| `/game/<id>/` | `game` | Game page (see below). Never cached |
| `/get_comments/<game>/<page>/` | `get_comments` | AJAX HTML fragment of comments (20 per page), used for "load more" |
| `/mark/?pk=&vote=up\|down` | `mark` | AJAX vote, JSON `{"success": <new rate or message>}` |
| `/add-comment` POST | `add_comment` | Login required |
| `/del-comment/<id>` | `del_comment` | Staff only |
| `/ban/<id>/` | `ban` | Bans the comment's IP. **The old code has no auth check. This is a bug** |
| `/upload/` | `upload` | Login required. SWF + thumbnail upload |
| `/search/?q=` → `/search/<q>` | `search` | Sphinx query, 20 per page. Logs the query when the referrer is our own site |
| `/login/` | `login_view` | Email form. Auto-creates the user and emails a magic link |
| `/auth/<uid>/<token>/` | `auth` | Consumes the token and logs in |
| `/logout/` | `logout_view` | |
| `/get-user-panel/` | `get_user_panel` | HTML fragment "Hi, user \| score \| logout" loaded by AJAX |
| `/page/N/`, `/theme/x/N/`, `/best/page/N/` … | `*_old` | Redirects to `?p=N` (**dropped**) |
| `/secret-admin-lol/` | Django admin | Moderation (**replaced by a small built-in admin**) |

### Business rules to preserve

**Game view counting** (`game`)
- A missing or inactive game returns 404.
- Views increment **only when `Referer` is non-empty**, which serves as the bot filter.
- On each counted view, `xrate` is recomputed:
  `xrate = rate * 10000 / views` when `rate > 0`, else `xrate = rate`.
  This uses `views` from before the increment, treating 0 as 1.
- Player size: width is `DEFAULT_WIDTH` (700) and height comes from the DB, falling back to 700.
  The new app derives the aspect ratio from the SWF header instead.

**Voting** (`mark`)
- `vote=up` → +1, `vote=down` → −1.
- Each IP gets one vote per game, checked against `CMark`. Staff can vote repeatedly.
  A repeat vote returns `{"success": "Вы уже голосовали"}`.
- A logged-in voter gets `profile.score += 1`.
- The uploader gets `profile.score += mark`.
- `flash.rate += mark`, and if `rate < -4` the game is set to `active = False` (auto-hide).
- The response is `{"success": new_rate}`, and the JS writes it into `#mark-<id>`.

**Comments** (`add_comment`)
- If the client IP is in `Ban`, the old code redirected away. The new app returns 403.
- There is a honeypot: a hidden `email` field. If it is non-empty, the comment is silently dropped.
- If the text contains any `BannedWord` (case-insensitive substring), it is silently dropped.
  The form also rejects the literal text "апиши этот коммент".
- The commenter gets `profile.score += 3`.
- The comment stores `ip` and `ua` (truncated to 250 characters).
- On success the user is redirected to `/game/<id>/?new`.
- Staff delete: removes the comment, and the old code deducts 10 points from the **staff user's** own score. That is almost certainly a bug. The new app deducts from the author instead (see plan).

**Upload** (`upload`)
- Fields: name, description (max 2000), themes (multi), SWF file, thumbnail image.
- The content type must be `application/x-shockwave-flash`. The new app checks the magic bytes `FWS`/`CWS`/`ZWS` instead.
- Dedupe uses `datahash` = sha512(file) + sha512(b"") (the old code has a quirky double hash). A duplicate is rejected with "This game already loaded".
- New games are saved with `active=False`. Admins get an email with the moderation link, and the uploader gets `score += 10`.
- The thumbnail is resized to 350×350 RGB when it is saved.
- Quirk: `Flash.save()` forces `user = Anonymous` on create, which overrides the uploader. The new app keeps the real uploader.

**Magic-link login**
- The user enters an email. If no user exists, one is created with a username derived from the email's local part plus a random suffix on collision.
- A token is generated and a link `SITE_URL/auth/<uid>/<token>/` is emailed.
- Hitting the link authenticates the user.

**Theme counts**: the cron job `update_games_count` sets `theme.count` to the number of active, published games. The menu shows only themes with `count > 0`.

## Templates (per set, same names)

`base.html`, `index.html`, `game.html`, `theme.html`, `best_and_popular.html`, `search.html`, `upload-flash.html`, `flash-list.html`, `game-list-item.html` (xfg0), `flash-best.html`, `flash-random.html`, `menu.html`, `paginator.html` / `pages.html`, `comments.html`, `comments_list.html`, `comment-item.html`, `counters.html` (xfg0), `404.html`, `500.html`, `user/login.html`, `user/auth.html`, `user/panel.html`.

Content removed in the port:
- `{% get_baner … %}` banner slots
- carrier banners
- VK/Facebook/Twitter share widgets
- the cbox.ws chat iframe
- teasernet/palandan ad scripts
- LiveInternet
- the old GA `_gaq`
- `/save/` JS, which pointed to a non-existent endpoint

Content kept:
- the Yandex Metrika counter, with its ID moved to site config
- the "recommended" outbound links in the menu, moved to site config

## Known bugs and quirks (do not port)

- `/ban/<id>/` has no permission check.
- `del_comment` penalizes the staff member instead of the comment author.
- Votes use GET, with no CSRF protection.
- `get_best_flashses` filters `publication_date__gt=now`. That is inverted, so it returns only future-dated games.
- `datahash` hashes the data plus an empty slice, so the second half of the hash is always the sha512 of empty bytes.
- `Mark` duplicates `Flash.rate`. The old code cleaned up duplicate `Mark` rows while reading.
- `Flash.save()` overwrote the uploader with `Anonymous`.
- The `flash:get_comments` URL name is namespaced in the templates but not in `urls.py`, so "load more comments" was broken.
