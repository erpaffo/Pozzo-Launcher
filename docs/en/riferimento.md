# Reference: Configuration and Commands

## Files and Folders

| Path | Content | Written by |
|---|---|---|
| `config.toml` | Base configuration (folders, sources, credentials) | You; the app never overwrites it |
| `settings.json` | Choices made in the app: emulators, stores, catalogs, theme, plugins, schedules | The app (alongside `config.toml`) |
| `cache/cache.db` | Source responses, scraping state, online store listings | The app |
| `cache/library.db` | The library prepared for the UI | The app, on every rebuild |
| `cache/userdata.db` | Favorites, playtime, statuses, notes, personal collections for the Primary profile; launch profiles and manually added games (common) | The app; never touched by rebuilds |
| `cache/profiles/<profile>.db` | The same personal data for other user profiles | The app |
| `cache/backups/` | Backups of your data | The app |
| `cache/saves/` | Copies of game saves | The app |
| `cache/logs/diagnostica.log` | Diagnostic log (with `--log`) | The app |
| `output/` | Terminal scraping results (JSON, CSV, images) | `pozzo run` / `export` |
| `themes/`, `plugins/` | Your custom themes and plugins | You |

The directory containing `config.toml` is located as described in
[Installation](installazione.md#dove-stanno-i-dati).

## config.toml

A complete and commented example is available in `config.example.toml` in the repository.

### [paths]

| Key | Meaning |
|---|---|
| `roms` | Root ROM folder (console folders are searched up to 4 levels deep) |
| `extra_roms` | Additional ROM folders, for example `["E:/Switch", "F:/Retro"]`. If configured through the app, the app's list overrides this |
| `cache` | Directory for downloaded data and media (default `cache`) |
| `output` | Output directory for terminal runs (default `output`) |
| `switch_keys` | Path to `prod.keys`; empty = automatically searched in Ryujinx, Eden, yuzu |

### [platform_folders]

Maps an unrecognized folder name to a console: `"Super Nintendo (PAL)" = "snes"`. Paths relative to the ROM root are also valid.

### [scrape]

| Key | Default | Meaning |
|---|---|---|
| `sources` | all | Priority order of sources |
| `fields` | title, description, developer, publisher, genres, date, players, rating | Desired text fields |
| `media` | `cover`, `screenshot`, `wheel` | Media types: `cover`, `screenshot`, `title`, `wheel`, `marquee`, `video`, `box3d`, `fanart` |
| `regions` | `eu`, `us`, `wor`, `jp` | Preferred region order for titles, images, dates |
| `languages` | `it`, `en` | Preferred language order for descriptions and genres |
| `min_match` | 70 | Minimum score (0–100) to accept a name match |
| `max_hash_mb` | 512 | Files larger than this are not hashed (identified by name) |
| `full_hash` | false | Also computes MD5 and SHA1 (slower; only useful for ScreenScraper) |
| `hash_workers` | 0 | Hashing worker processes (0 = all CPU cores) |
| `disk` | `auto` | `hdd` or `ssd`: on HDDs, large files are read sequentially |
| `io_workers` | 0 | Large files read in parallel (0 = 1 on HDD, all cores on SSD) |
| `link_media` | true | Hardlink media from cache to output: instant, zero extra disk space |

### [field_priority]

Source priority order for an individual field, for example `description = ["screenscraper", "igdb", "thegamesdb"]`.

### Online Sources

| Section | Keys |
|---|---|
| `[screenscraper]` | `user`, `password`, `devid`, `devpassword`, `threads` (0 = account maximum), `quota_reserve`, `ko_reserve`, `search_fallback` (`missing`, `true`, `false`), `only_primary`, `media_parallel` |
| `[igdb]` | `client_id`, `client_secret`, `rate` (max 4), `search_fallback` |
| `[rawg]` | `api_key` |
| `[thegamesdb]` | `api_key`, `rate`, `quota_reserve` |
| `[libretro]` | `refresh_days` (30), `download_threads` (24), `thumbs_by_filename` |
| `[limits.<source>]` | `rate` (requests/s), `daily`, `monthly`, `reserve` |

### [collections]

| Key | Meaning |
|---|---|
| `min_games` | An automatic collection is created with at least N games (default 3) |
| `exclude` | Franchises to exclude, for example `["Disney", "NBA"]` |
| `aliases` | Merges franchises with different names: `{ "Lara Croft" = "Tomb Raider" }` |
| `show_bios` | Also displays `[BIOS]` files in the library |

### [emulators] and [launch]

`[emulators]` contains the executable path for each emulator (`retroarch = "C:/Emulatori/RetroArch/retroarch.exe"`, …).
`[launch.<console>]` overrides the launch command for a console:

```toml
[launch.psx]
emulator = "retroarch"
core = "swanstation"
args = ["-L", "{core}", "{rom}", "-f"]
```

`{rom}` is the game file, `{core}` is the RetroArch core. The same settings can be configured via **Settings › Emulators**.

### [stores]

| Key | Meaning |
|---|---|
| `[stores.steam] api_key` | Steam Web API key, for uninstalled games |
| `[stores.steam] steamid` | Steam account ID; empty = most recently used account |
| `[stores.<store>] enabled` | `false` to disable a store |

### [app]

| Key | Meaning |
|---|---|
| `theme` | Theme (can also be selected in **Settings › Appearance**) |
| `exit_combo` | Holding Select + Start for 2 seconds exits the game (default `true`) |
| `save_backups` | Automatic game save backups (default `true`) |
| `skip_duplicates` | Show only a single version per game (default `true`) |
| `port` | Local server port (default 8765) |
| `notify` | Windows notifications for prices, free games, updated ports, and completed jobs (default `true` on Windows) |
| `after_jobs` | Action upon completion of long tasks: `none`, `sleep`, or `shutdown` (default `none`) |

### Environment Variables

| Variable | Meaning |
|---|---|
| `POZZO_CONFIG` | Path to the `config.toml` to use |
| `POZZO_LOG` | Enables diagnostic logging (`1` or a specific file path) |
| `SS_USER`, `SS_PASSWORD`, `SS_DEVID`, `SS_DEVPASSWORD` | ScreenScraper credentials |
| `IGDB_CLIENT_ID`, `IGDB_CLIENT_SECRET` | IGDB credentials |
| `TGDB_API_KEY` | TheGamesDB API key |

## settings.json

Written by the app; can be edited manually when the app is closed. Most useful sections to know:

| Section | Content |
|---|---|
| `catalogs` | Online console stores (see [Specifying the format manually](store-online.md#indicare-il-formato-a-mano)) |
| `pc_stores` | Other PC stores: `[{"url": …, "kind": "repack" or "direct"}]` |
| `emulators`, `launch` | Options configured in **Settings › Emulators** |
| `stores` | Active stores and linked accounts |
| `paths`, `platform_folders` | ROM folders and folder associations configured in the app |
| `custom_platforms` | Consoles added via **＋ Add console** |
| `screenscraper`, `igdb`, `rawg`, `thegamesdb`, `limits` | Source accounts and rate limits configured via the app |
| `app` | Theme, plugins, smart collections (`smart_collections`), schedules, and general app settings |
| `app.profiles`, `app.profile` | User profiles and currently active profile |
| `app.sync` | Synchronization: shared folder (`folder`), what to sync (`what`: `personal` or `all`), paired PCs, and this PC's identity |
| `app.phone` | Phone: `touchscreen` (secondary screen in DS and 3DS games), `screen_idle` (idle seconds before touch screen reverts to PC), `mouse`, `mic_device`, `public_url` (tunnel address for guests), `video_addr` (address for Moonlight), `pad` (appearance, sensitivity, and button layouts, shared across all phones) |
| `app.discord` | Discord Rich Presence: `enabled`, `client_id`, `show_time` |
| `app.notify` | Windows notifications (`false` to disable; active by default on Windows) |
| `app.merge_stores`, `app.store_order` | Merging the same game across stores (default `true`) and the preferred store order, e.g. `["steam", "gog", "epic"]` |
| `app.video_snap`, `app.video_max_mb` | Video snaps (off by default) and the per-clip cap in MB (default 30) |
| `app.libshare` | Shared library: shared consoles and games, invites and internet access (managed from Settings › Controller) |
| `app.archive_run` | `dir`: temporary folder for archives extracted at each launch (empty = default) |
| `app.after_jobs` | Action upon completion of long tasks: `none`, `sleep`, or `shutdown` |
| `app.save_dir` | Directory for save versions (empty = `<cache>/saves`); pointing to Ludusavi's folder enables shared backups |

<a id="comandi-da-terminale"></a>
## CLI Commands

When running from source, use `python -m pozzo <command>`. With the compiled executable, use `pozzo-cli <command>` located in the application directory; with the `.deb` package, the command is `pozzo <command>`.

| Command | Description |
|---|---|
| `app` | Launches the app. Options: `--browser`, `--bigpicture`, `--port N`, `--log [path]` |
| `bigpicture` | Fullscreen Big Picture mode (uses an already running instance if present) |
| `run` | Scan, scrape, and export (default command) |
| `scrape` | Scrape only (saves to cache); `--missing` populates missing data only |
| `export` | Regenerates output from cache, offline |
| `library` | Rebuilds the application library |
| `export-frontend` | Exports for ES-DE or Pegasus: `--format esde|pegasus`, `--out folder`, `-p console` |
| `relink` | Relinks renamed or moved games: preview mode, `--apply` to execute |
| `play --key <key>` | Launches a game and waits for it to exit (used by Sunshine/Moonlight) |
| `stats` | Cache statistics by console and source |
| `purge --source X -p Y` | Purges cached data for a source or console |
| `platforms` | Lists all supported consoles |

Common scraping options: `-c config.toml`, `-p snes,psx` (consoles), `-s libretro,igdb` (sources and order),
`-m cover,wheel` (media types; `none` = none), `--roms folder`, `--refresh` (re-queries previously searched games),
`--limit 50` (first N games only, useful for testing).

<a id="api-locale"></a>
## Local API

The application exposes an HTTP API at `127.0.0.1:8765` (port is configurable via `[app] port`). It serves scripts, Stream Deck,
Home Assistant, webhooks, and extensions.

**The server only responds to the local PC on which it runs** and must never be exposed directly to the Internet: endpoints include launching games and programs. To use it from another device, access it via a paired private network (similar to synchronization) or an on-demand tunnel, never through an open router port.

### The Four Endpoint Families

| Prefix | Target | Rule |
|---|---|---|
| `/api/v1/...` | Scripts, Stream Deck, Home Assistant, webhooks | **Stable**: endpoints persist and changes occur only after formal deprecation. Requires **token** |
| `/api/...` | App user interface | Internal: subject to change between versions. No token required because it binds locally (and browsers cannot query it cross-site) |
| `/plugin-api/<id>/...` | Plugins (see [Themes and Plugins](ESTENSIONI.md#server-backendpy)) | Defined by the plugin |
| `/m/api/...` | Mobile web app and guests | Requires **device-specific** token obtained during pairing (see [Phone and Streaming](telefono-streaming.md)) |

### The Token

A per-PC secret generated on first launch in `<cache>/api-token` (file permissions 0600 on Linux and macOS). It can be viewed and regenerated in **Settings › About › Local API** (**Copy** and **New token**); regenerating it invalidates scripts using the previous token.

Three equivalent ways to supply it:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/v1/games
curl -H "X-Api-Token: $TOKEN"             http://127.0.0.1:8765/api/v1/games
curl "http://127.0.0.1:8765/api/v1/games?token=$TOKEN"    # for EventSource, which does not send custom headers
```

This is not protection against other programs running under the same user (which can read the token file); its purpose is to prevent arbitrary software, malicious websites, or accidentally exposed tunnels from unauthorized API access.

### Stable Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/status` | App heartbeat: version, `api`, `library_built_at`. **The only endpoint without token** |
| `GET` | `/api/v1/games` | Lightweight game list: `q`, `platform`, `store`, `status`, `key`, `favorite`, `versions`, `limit` (max 1000), `offset`, `sort` (`title`, `year`, `rating`, `playtime`, `last_played`; `-` for descending) |
| `GET` | `/api/v1/games/{id}` | A single game with its versions, user data, and media |
| `POST` | `/api/v1/games/{id}/play` | Launches the game on the PC |
| `POST` | `/api/v1/games/{id}/favorite` | Toggles favorite status (`{"value": true}` or `false`), across all versions |
| `GET` | `/api/v1/running` | Currently running game, if any |
| `POST` | `/api/v1/running/stop` | Terminates the currently running game |
| `GET` | `/api/v1/platforms` | Consoles and stores with game counts and available filters |
| `GET` | `/api/v1/collections` | Automatic and custom collections with game counts |
| `GET` | `/api/v1/collections/{slug}` | Game IDs belonging to a collection |
| `GET` | `/api/v1/jobs` | Ongoing or recently completed jobs with percentage progress |
| `POST` | `/api/v1/jobs/{action}` | `stores`, `scan`, `rebuild`, `stop-scan`, `stop-game` |
| `GET` | `/api/v1/events` | Real-time events (SSE): `game_started`, `game_stopped`, `library_built`, `scrape_finished`, `stores_refreshed` |
| `GET` | `/api/v1/saves/{id}` | Save file versions for a game |
| `POST` | `/api/v1/saves/{id}` | Creates an immediate save version |
| `POST` | `/api/v1/saves/{id}/restore` | `{"name": "backup-..."}`; `409` if the game is running |
| `GET` | `/api/v1/backups` | Backups of personal data |
| `POST` | `/api/v1/backups` | Creates a new backup |
| `GET` | `/api/v1/wishlist` | Wishlist with prices |

The full and up-to-date OpenAPI schema is available at `http://127.0.0.1:8765/openapi.json` (and `/docs` for interactive browser testing).

### Errors

Always returned in a consistent JSON structure, so clients never have to guess:

```json
{"detail": "Gioco non trovato", "code": "not_found"}
```

`404` when an entity does not exist, `409` when present but state prevents the action (game already running, not installed, save operations while game is open), `422` for invalid parameters, `401` for missing or invalid token. `detail` is user-facing message text, `code` is the machine-readable error identifier for programmatic handling.

`POST` requests support an **`Idempotency-Key`** header: repeating the exact request (e.g., following a network timeout) within 5 minutes returns the original response without re-executing the action. Highly recommended for `play`, `jobs`, `saves`, and `backups`.

### Examples

With `curl`:

```bash
# the token is stored in <data directory>/cache/api-token, or can be copied from Settings › About
#   Windows: %LOCALAPPDATA%\PozzoLauncher\cache\api-token
#   macOS:   ~/Library/Application Support/PozzoLauncher/cache/api-token
#   Linux:   ~/.local/share/PozzoLauncher/cache/api-token
TOKEN="..."

curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/v1/games?q=zelda&limit=5"
curl -s -H "Authorization: Bearer $TOKEN" -X POST -H "Idempotency-Key: sera-1" \
     http://127.0.0.1:8765/api/v1/games/1234/play
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8765/api/v1/events"   # streaming events
```

In Python, using the bundled client (address and token are detected automatically):

```python
from pozzo import config
from pozzo.api_client import Client, ApiError

c = Client(cfg=config.load())            # or Client("http://127.0.0.1:8765", token="...")
for g in c.games(q="zelda", limit=5)["items"]:
    print(g["id"], g["title"], g["year"])
c.play(g["id"], idem="sera-1")           # idempotent: will not launch twice
c.wait_end()                             # wait for session to finish
for kind, data in c.events():
    print(kind, data)
```

`POZZO_URL` and `POZZO_API_TOKEN` configure address and token globally for scripts.
