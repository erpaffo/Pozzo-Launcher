# Development and Technical Details

For those working from source, building executables, or curious about the inner workings of Pozzo Launcher.

## Quick Start from Source (Windows)

```powershell
python -m pip install -r requirements.txt
copy config.example.toml config.toml     # first time only, if you haven't run the exe yet: then edit roms = "..." and credentials
python -m pozzo app                      # opens the app at http://127.0.0.1:8765
```

## Building Executables

On GitHub, the workflow [`.github/workflows/release.yml`](https://github.com/erpaffo/Pozzo-Launcher/blob/main/.github/workflows/release.yml) builds them on every version tag (`git tag v0.1.0 && git push origin v0.1.0`): building across Windows, macOS, and Linux and publishing artifacts to the release. Locally (for the current operating system only):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller packaging/pozzo.spec --noconfirm     # output in dist/PozzoLauncher/
```

### Updates for Installed App

GitHub Releases provides download URLs for entire assets rather than individual files inside a ZIP. For this reason, the workflow keeps complete archives as a fallback while also publishing a manifest (`version`, `file` with `path`, `sha256`, and `size`) and a small tar asset for each file in portable packages. Asset filenames derive from their relative paths, allowing the updater to download only modified files without requiring Range requests or external services.

Differential updates are applied only if both the local and release manifests are valid and all hashes match; deletions, changed files, and integrity verifications occur in a staging folder on the same storage volume. Once checks pass, the updater renames the old folder and activates the new one, rolling back to the previous folder if an error occurs. Any invalid manifest, asset, or hash triggers the download and verification of the full archive fallback; update progress displays the expected transfer size in MB for both differential and full fallback methods.

## Codebase Structure

```
pozzo/
  cli.py          CLI commands and progress bars
  config.py       config.toml loading
  platforms.py    platforms: file extensions, ScreenScraper/IGDB/TGDB IDs, libretro systems, aliases
  scanner.py      folder scanning, parallel hashing, Game model
  cache.py        SQLite cache
  net.py          HTTP/2 client, rate limiter, retry logic, media downloads with validation
  matching.py     title matching (rapidfuzz)
  pipeline.py     cascading orchestration and per-field priority
  export.py       JSON/CSV/media per console
  api_client.py   local /api/v1 API client (used by pozzo-cli and scripts)
  sources/        libretro, arcadedb, igdb, screenscraper, thegamesdb
  app/            FastAPI server
    server.py       create_app(): shared components (config, library, launcher, events, jobs) + app
    routes/         /api endpoints, one module per domain (see below): build_router(ctx)
    apiv1.py        stable /api/v1 API
    apitoken.py     API token management
    themes/         bundled themes (chiaro, notte-blu, oled, retro)
    static/         desktop UI, Big Picture, and mobile phone app (see below)
tests/test_pipeline.py   end-to-end tests with mocked APIs (python tests/test_pipeline.py)
tests/perf/              startup and library memory/time budgets (test_perf_budget.py)
tests/e2e/               browser smoke tests via Playwright: startup, search, detail view, Big Picture (skipped without Playwright)
```

### Server: `server.py` and `routes/`

`create_app()` instantiates shared components once (config, library, active profile, launcher, events, background jobs, phone, plugins) and passes them to modules in `pozzo/app/routes/`, organized by domain: `library`, `stores`, `gameinfo`, `scan`, `saves`, `appsettings` (settings and themes), `system`, `wishlist`, `pages`… Each module exports `build_router(ctx) -> APIRouter` and pulls only what it needs from `ctx`:

```python
def build_router(ctx) -> APIRouter:
    cfg, lib, events, job = ctx.cfg, ctx.lib, ctx.events, ctx.job
    router = APIRouter()

    @router.get("/api/...")
    def ...:
        ...

    return router
```

Mount order is defined in `routes/__init__.py` (`ORDER`): any module consuming a function from another module is mounted later, and the function is attached to `ctx` via `vars(ctx).update(...)`. New endpoints belong in their respective domain module; newly shared utility functions should be registered on `ctx` inside `create_app()`.

This modular refactoring is **in progress**: endpoints are progressively migrated into `routes/` modules, while `create_app()` and core shared infrastructure remain in `server.py`.

### Frontend Architecture: `core.js`, `js/`, and `app.js`

No bundler is used: `index.html` loads **vanilla script tags** sequentially in file order, sharing a single global scope (`S`, `GS`, `api`, `esc`, `toast`…).

| File | Content |
|---|---|
| `core.js` | shared utilities (`api`, `esc`, `fold`, `store`), theme, experience, and plugin loading |
| `js/state.js` | library state management, data fetching, filters, sorting |
| `js/grid.js` | virtualized grid (only visible covers exist in the DOM) |
| `js/sidebar.js`, `js/home.js` | sidebar and collections; "For You" home view |
| `js/detail.js`, `js/actions.js` | game detail view; popovers, launch actions, context menus |
| `js/ports.js`, `js/pages.js` | free games and PC ports; wishlist, statistics, top games, screenshots |
| `js/stores.js`, `js/settings.js`, `js/emulators.js` | stores and sources; settings and toasts; emulators |
| `js/remote.js`, `js/events.js` | phone app and streaming; page-wide event `bind()` listeners |
| `app.js` | bootstrap: settings, extensions, library initialization, initial view, polling |
| `motion.js`, `motion-settings.js`, `skeleton.css` | animations and loading skeleton placeholders |
| `icons.js` | SVG icons |
| `bigpicture.js` + `bigpicture.html` | Big Picture mode (shared API, dedicated markup) |
| `m/` | mobile phone web app (`index.html`, `m.js`, `m.css`, `sw.js`) |

Practical guideline: modify the specific module file for that domain, and only expose functions to the global scope if genuinely required across multiple files—otherwise keep them module-local.

### Micro-animations

- `motion.css` defines motion design tokens (`--mo-fast`, `--mo-base`, `--mo-ease`, stagger distance and delays) and classes (`.mo-in` for cover entrance, `.mo-paused`). Only `transform` and `opacity` are animated—never layout properties.
- `motion.js` is view-agnostic: it observes the DOM, animates elements entering the viewport (staggered entrance, max 24 concurrently), and pauses when the tab is hidden or during scrolling.
- Intensity via `html[data-motion]`: `normal`, `reduced`, `off`. Selected in **Settings › Appearance › Animations** (`motion-settings.js`, persisted in `localStorage` as `gs.motion`); defaults to the system's `prefers-reduced-motion`. Themes or experiences may adjust motion temperament solely via tokens (`--mo-k`, `--mo-t`), not custom animations.
- Toasts, dialogs, and the settings view enter via `@starting-style` and exit using transitions to `[hidden]` / closed dialog (`display`/`overlay allow-discrete`): toggling `hidden` is sufficient without JS. Menus and popovers feature entrance transitions only.
- `GSMotion.enter(el)` (in `motion.js`) transitions a container using the Web Animations API (WAAPI); `setView` invokes this when switching views. Has no effect when animations are reduced or disabled.
- Infinite animations (skeletons) use exclusively `transform`/`opacity`, never `background-position`.
- `GSSkeleton.show(container, n)` / `.hide(container)` (in `motion-settings.js`) display `skeleton.css` placeholders during grid loading.

### Virtualized Lists

The library grid (`grid.js`) renders only visible rows. Long page views (Top games, wishlist, free games, ports, screenshots) employ the same approach via `vlist(box, host, items, cell, opt)` in `grid.js`: `cell(item)` returns HTML for an item, `opt.cols()` sets items per row (card grids), and `opt.gap` sets vertical spacing between rows. The DOM only keeps the current viewport rows plus one buffer screen above and below; unrendered rows are represented by spacers. Each row's height is measured after initial rendering. When adding a large list, delegate it to `vlist` rather than generating a monolithic `map().join()` string in the page template. Short lists (settings, stores, collections) remain standard DOM elements.

### Icons

All centralized in `icons.js`: 24×24 inline SVGs, 1.5px stroke width, rounded joins, styled with `currentColor` (matching theme colors automatically). Three ways to render them:

- `GS.icon("name", { size: 18, cls: "…" })` (aliased as `ic(...)`) in JS templates: returns the SVG markup string;
- `data-icon="name"` in static HTML;
- Recognized leading emojis in text ("⚙ Settings", "✕") are automatically swapped with SVGs in the DOM, including dynamically created content (`data-noicon` on an element opts out).

To add a new icon, add an entry to the `ICONS` dictionary: no external assets or sprites required.

### How to Add a Theme

A theme consists of two files, `theme.json` and `theme.css`, placed in `<data directory>/themes/<id>/` (alongside `config.toml`) or bundled within the app under `pozzo/app/themes/<id>/`. File specifications, required CSS variables, and attributes (`<html data-mode>`, `<html data-theme>`) are detailed in [Themes and Plugins](ESTENSIONI.md#temi), which also references the four built-in themes as examples.

On the codebase side, themes require no code changes:

- `pozzo/app/extensions.py` — `list_themes(cfg)` parses `theme.json` files (user folder prioritized over `pozzo/app/themes/`), `theme_file(cfg, id, rel)` resolves the requested asset file;
- `pozzo/app/routes/appsettings.py` — `GET /api/extensions` supplies themes, active theme, and experiences; `POST /api/app/theme` writes `app.theme` to `config.toml`; `GET /themes/<id>/<file>` serves static theme files;
- `core.js` (`loadExtensions`) — injects `<link data-ext="theme">` stylesheets (`desktop` or `bigpicture` according to active mode), waits for application before unhiding the window, and sets `document.documentElement.dataset.theme`.

The stable API for scripting and integrations is documented in [Reference › Local API](riferimento.md#api-locale): `/api/v1` endpoints maintain backward compatibility, while `/api` endpoints are internal to the web UI.

## Exporting the Library as a Web Page

`python -m pozzo export-frontend --format html --out C:\mylibrary` (or Settings › ▦ Library › *Export for other frontends* › **Web page**) produces:

```
index.html          the collection, with search, console filters, sorting, and game detail cards
covers/             cover art (local files)
```

It is **a self-contained single file plus images**, requiring no backend server or external dependencies: open it with a double click (including via `file://`), host it on a NAS, network share, or static website. The page handles thousands of games effortlessly (detail cards are rendered incrementally on scroll).

## Performance

| | Pozzo Launcher |
|---|---|
| Identification | **Offline**: CRC and filename matched against libretro No-Intro/Redump DATs |
| ROM Hashing | CRC/MD5/SHA1 computed once (ZIP CRC read from archive index, 8 MB chunk streaming, adaptive HDD/SSD strategy, results cached), then matching hashes first and filenames second against DATs. Subsequent runs reuse cached hashes. |
| Network | Asynchronous HTTP/2 client, rate limiting only where required |
| ScreenScraper | Media downloaded in parallel, downloading missing media only |
| IGDB | **10 games per batch request**, 4 requests/sec |
| ArcadeDB | **25 games per batch request** |
| Cache | SQLite with continuous write-through and automatic resume |
| Consoles | Processed concurrently across all platforms |
| Sources | **Pipelined chain**: all sources process different games simultaneously |

Benchmarked with 10,000 ROMs across 5 consoles in nested directories: 9,500 identified by name without reading file contents; scanning, hashing the remaining 500, identification, and export completed in **under 10 seconds** (excluding media downloads). On an actual test collection (14,782 games on an HDD), total NDS data read dropped from 149 GB to 3.6 GB. Libretro image downloads average roughly 16 per second (measured over 300 SNES covers, 84% hit rate): approximately 30 minutes to fetch covers, screenshots, and title screens for 10,000 games.

### How the Source Pipeline Cascade Works

Each source acts as a pipeline stage with its own queue. A game advances to the next source as soon as the previous source completes processing, including media downloads. Thus, while ScreenScraper steadily consumes its quota, libretro and IGDB are already actively processing other games concurrently. The established priority order is strictly preserved: a source only encounters a game after all upstream sources have finished with it.

1. **libretro**: Identifies ROMs offline and extracts title, developer, publisher, genre, release year, and player count. Downloads covers, screenshots, and title screens from thumbnails.libretro.com without quota constraints.
2. **arcadedb**: Arcade platforms only.
3. **igdb**: Descriptions, ratings, box art, and promotional artwork for remaining gaps. Leverages canonical names identified by libretro. Batches 10 games per exact-title request first, falling back to single queries only for unmatched items (IGDB multiquery does not support the `search` endpoint).
4. **screenscraper**: Wheel art, marquees, video snaps, localized descriptions, and previously unmatched games.
5. **thegamesdb**: Fallback resource of last resort (constrained by monthly API quota).

Each source receives **only** games missing metadata or media that the source can actually provide. To maximize scraping throughput, request `wheel`/`marquee`/`video` media only when needed: these exist almost exclusively on ScreenScraper, turning your account's daily allowance (e.g. 20,000 requests) into the bottleneck. For 10,000 games with these media types, roughly 10,000–12,000 ScreenScraper requests are required, representing approximately 1 day on a standard account. If your quota is exhausted, execution terminates cleanly and resumes seamlessly the following day.

## Source Caching

API responses from sources (RAWG, IGDB, ScreenScraper, TheGamesDB, ArcadeDB, Wikipedia) are cached in `cache.db` (`http_cache` table); HowLongToBeat completion times reside in `kv` (`hltb:<platform>:<normalized_title>`). The lookup key is the query URL without credentials or the normalized title, **never the profile**: all user profiles share a single unified cache entry.

- Expirations in `pozzo/cachepolicy.py`: `TTL[source] = (positive, negative)`. Negative hits (404 or empty result responses) expire sooner (7 days; HLTB 30 days) while preventing redundant searches for missing titles during subsequent scans.
- Triggered with `request(..., cache_source="rawg")`. Cache hits (`x-pozzo-cache: hit`) bypass rate limiters and consume zero API quota; ScreenScraper and TheGamesDB client counters refund the request.
- `HttpCache.stats()` (rows, bytes, expired count per source), `.invalidate(source=None, key=None)`, `.purge_expired()`. The `exp` expiration timestamp is computed on write.
- API endpoints: `GET /api/cache/sources`, `POST /api/cache/sources/clear {source?}`. Expired records are pruned in the background at startup once the UI is ready.
- "Re-download everything" bypasses cache reads while updating cache entries with fresh responses.

## Emulator Smoke Testing

`tests/smoke/test_emulator_smoke.py` launches RetroArch with the gambatte core and an open-source test ROM (Blargg's `cpu_instrs`, pinned commit URL with verified SHA256) using the execution plan generated by `launcher.plan()` along with null video and audio drivers, verifying that the process remains alive for several seconds.

- `smoke` pytest marker: excluded from standard test runs and from `packaging/run_tests.py` (which ignores `tests/smoke`). Run locally with: `RETROARCH_EXE=... RETROARCH_CORES_DIR=... python -m pytest -m smoke tests/smoke -rs`.
- If RetroArch is missing, network is unavailable, or ROM hashes mismatch, the test gracefully skips with an explanation.
- In CI, the `smoke` job runs nightly and on manual trigger (`workflow_dispatch`) on Linux, without gating standard pushes or pull requests.

## Omitted Features

- Image compositing: media assets are saved in their pristine original form.
- Dedicated scraper modules for MobyGames (commercial paywalled API), OpenRetro, and WorldOfSpectrum.

Should you need them, they can be implemented as modular providers under `pozzo/sources/` or `export.py`.

## Profiles and Game Ownership
`pozzo/profilecfg.py`: per-profile accounts and settings (`profiles/<id>.json`); `get`/`set` operate on the active profile derived from the `gs_profile` cookie (via `server.py` middleware, `profilecfg.override`) or defaulting to the server's configured profile (`cfg.app["profile"]`). To add a new setting: register it in `KEYS` and in `_legacy` (one-time migration tracked via `_done`). `pozzo/ownership.py` implements the game visibility model (`game_owners` table in `library.db`, `visible(game, profile)`); account-linked store lists reside in `store:<id>:<profile>` (`stores.snap_key`). The library catalog, metadata, and cache databases are never duplicated across profiles. Tests: `tests/test_profile_library.py`.

## Experience Presets
`GET/POST/DELETE /api/exp-profiles` list, save, and delete presets `{id, name, experience, theme, animations}`; `POST /api/exp-profiles/activate` applies the preset. The four default presets are Classic, Movie Night, TV Console, and Lightweight.
The active collection and motion preferences are stored in `profiles/<id>.json` per user profile (`profilecfg.set`); unavailable themes or experiences fall back to `default` and `catalog`.
The UI is handled in `pozzo/app/static/js/profiles-exp.js`: included in `index.html` after `motion-settings.js`; mounting targets `#experience-list` in `settings/aspetto.html`.
