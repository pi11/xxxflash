# Running the SWF games with Ruffle

Browsers removed the Flash plugin in 2021. [Ruffle](https://ruffle.rs) is a Flash Player emulator written in Rust and compiled to WebAssembly. It runs SWFs in modern browsers with no plugin.

## Support level

| Content | Ruffle status |
|---|---|
| AS1/AS2 (SWF ≤ 8, most 2005–2010 games) | Very good. Most of this catalog falls here |
| AS3 (SWF 9+ with the `ActionScript3` flag set) | Good and improving, but some games break |
| Games that call external URLs, `loadMovie` from dead hosts, or sitelocks | Partly broken (sitelocks can be spoofed) |

A one-off scan of the legacy media on 2026-09-30 read the header and the `FileAttributes` AS3 flag of each file:

| Media dir | SWF files | AS3 | Most common versions |
|---|---:|---:|---|
| xxxflash | 3 306 | ~224 (7%) | v6–v9, some v10 |
| flashsex | 7 251 (incl. duplicates in `flashgames/` and `swf/all/`) | ~323 (4%) | v4–v9 |

More than 90% of the catalog is AS1/AS2, so Ruffle should run most games. Run `python -m app audit-swf` to get the exact per-game result. It writes to `Game.compat`.

## Integration

1. **Vendor** a pinned self-hosted build, for example `ruffle-nightly-YYYY_MM_DD-web-selfhosted.zip`, into `static/ruffle/<version>/`. The files are `ruffle.js` plus `*.wasm` and chunk files.
   Record the version in `static/ruffle/VERSION`. Update it deliberately, never from a CDN at runtime.
2. The game page renders a container instead of `<object>`:

   ```html
   <div id="game" class="game-player"
        data-swf="{{ media_url(g.swf_path) }}"
        data-width="{{ g.width or 700 }}" data-height="{{ g.height or 700 }}"></div>
   <script>window.RufflePlayer = window.RufflePlayer || {};
     window.RufflePlayer.config = {
       publicPath: "{{ static_url('ruffle/' ~ ruffle_version ~ '/') }}",
       autoplay: "on", unmuteOverlay: "visible", splashScreen: false,
       letterbox: "on", warnOnUnsupportedContent: true,
       contextMenu: "rightClickOnly", allowScriptAccess: false,
       base: "{{ settings.MEDIA_URL }}",     // media root: loader games request "parts/<name>"
       openUrlMode: "confirm", allowNetworking: "internal"
     };</script>
   <script src="{{ static_url('ruffle/' ~ ruffle_version ~ '/ruffle.js') }}"></script>
   <script src="{{ static_url('_shared/player.js') }}"></script>
   ```

   `player.js` calls `RufflePlayer.newest().createPlayer()`, sets its size, and appends it to the container. The size follows the SWF aspect ratio: width is capped at the container width (700px on desktop) and scales down on mobile.
   It then calls `player.ruffle().load({ url })` and shows a fallback message and link if loading fails.
3. Show the player only on the game page. Listings use thumbnails only.
4. The Content-Security-Policy must allow `script-src 'self' 'wasm-unsafe-eval'`. Add `mc.yandex.ru` for Metrika.
5. Serve `.wasm` as `application/wasm`, or loading is slow or fails. Serve `.swf` as `application/x-shockwave-flash`.
   The extensionless files in `media/parts/` also need `application/x-shockwave-flash`. Add an nginx `location /media/parts/ { default_type application/x-shockwave-flash; }` and the matching dev route.
6. **Loader games:** at least 13 SWF v7 games (e.g. `swf/2013/10/01/tsunade-and-horse.swf` → `parts/tah-game`, `swf/all/game-134.swf` → `parts/mb2-game`) call `loadMovie("parts/<name>")` with a relative path. Ruffle resolves that against `base`, so `base` is the media root (`MEDIA_URL`) and `media/parts/` must be kept. Include one of these games in the manual test list.
7. Admin preview reuses the same `player.js` in place of the legacy `<object>` toggle.

## Compatibility audit (`python -m app audit-swf`)

For every game the script:

1. Checks that the file exists. If not, it sets `compat='missing'`. It never changes `active`: hiding is done at query time through `HIDE_COMPAT`, so an empty dev `./media/` doesn't deactivate the catalog.
2. Parses the header, decompressing with zlib for `CWS` and LZMA for `ZWS`. It reads the version, the frame rectangle (width and height in twips / 20) and the `FileAttributes` tag.
   `is_as3` is true when the `0x08` flag is set.
3. Sets `compat` to one of:
   - `ok`: AS1/2
   - `as3`: needs a manual check
   - `broken`: the header does not parse or the file is truncated
4. Fills in `width`, `height`, `swf_version` and `filesize` when they are missing. Legacy width and height are 0 for most rows.
5. Prints a summary table and writes a CSV to `var/audit-<SITE>.csv`.

Policy comes from `.env` as `HIDE_COMPAT=missing,broken`:
- Hidden games are excluded from listings and return 404.
- `as3` games stay visible, and the game page shows a small note: "Игра может работать некорректно".

### Optional phase 2: headless smoke test
A Playwright script loads each `as3` game with Ruffle in headless Chromium for about 5 seconds. It watches the console for Ruffle panics or `unsupported` warnings and marks failures as `broken`. This is slow (about 3.4k games × 5 s), so it runs only as a batch job.
