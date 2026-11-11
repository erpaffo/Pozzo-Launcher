# Adding Online Stores and PC Stores

In addition to games you own, Pozzo Launcher can display games **available for download** read from web pages you
choose: **console catalogs** (online stores) and non-official **PC game directories** (repacks and
direct downloads). These games appear in the library marked as "available for download", with a button for each site that
offers them.

> **Legal Note.** The app does not include or import lists of websites: you add the addresses yourself. Only download what
> you have the legal right to download (games you own where backup copies are permitted, homebrew, freeware, demos,
> public domain titles): downloading copyrighted games without a license is illegal.

This chapter explains:

1. how to add a catalog to a console;
2. which page formats the app can parse and how to verify them;
3. how to add PC game directories;
4. how store updates work (queue, scheduling, logs);
5. the included plugins that add stores in bulk;
6. for developers: how to add a new page format or a new store.

## Online Store for a Console {: #store-online-di-una-console }

<a id="log-su-file"></a>
### Adding a Catalog

1. Open the console in the sidebar.
2. Click **Online Store** in the console header (the number in parentheses indicates how many catalogs exist).
3. Paste one or more URLs of **pages listing games** for that console, **one per line**.
4. Click **Save and Read**.

From each page, title, file size, download links, and magnet links are parsed. Games you do not own appear as
**available for download** in the console view, the **🛒 Store** view, and leaderboards. Games you already own
are not duplicated.

In the same window:

- the table displays the number of games parsed per URL, when it was last checked, and the detected format;
- **↻ Re-read** immediately rescans the directories;
- removing all addresses and saving unlinks the console from online stores.

![The Online Store window for a console: URLs, parsed games per page, and Re-read and Save and Read buttons](../images/store-online.jpg)

### How Games Appear

- Titles are **cleaned** of site-specific keywords: "Zumba World – The Marble Adventure Switch NSP (eShop)" becomes
  "Zumba World – The Marble Adventure". Words like "Switch" that form part of the actual game title are preserved ("1-2-Switch").
- **Same game from multiple sources**: if two sites offer the same game, even with slight spelling differences, the library
  displays **a single card** with pages for each source ("🌐 nxbrew.net ↗", "🌐 ziperto.com ↗") and the Torrent button
  when a magnet link exists **for the individual file**.
- **DLC and updates**: the store's declared item type, indications in title or filename, and (for Switch) the Title ID
  distinguish DLCs, updates, and base games. File size can confirm a DLC only if the catalog also contains the base game
  and the console supports downloadable content; updates are linked to the base game. On the **🛒 Store** page,
  **Exclude DLC** hides or displays recognized DLCs.
- **Non-game software**: Game Boy Advance **e-Reader** cards (including the reader itself) number in the
  thousands and end up listed as games: entries with "e-Reader" in the URL or title are categorized as
  **DLC** and can be hidden via **Hide DLC**.
- **⬇ Download** queues the files listed on the game's page, not the store catalog page itself. The details card
  displays all available links grouped by provider and categorized by type: **game** (including multi-part archives: "Part 2", "Part 3"),
  **update**, **DLC/expansions**, and any **localized language versions**. The main button queues
  one link per type all at once from the same source; each provider can also be queued individually. The
  downloads appear in the **⬇ Downloads** page like all others.
- **Bypassing ads and intermediate pages**: many hosters hide files behind shorteners (ouo.io) leading
  to file host landing pages (DataNodes, FileKeeper, KrakenFiles, 1Fichier, MegaUp); the actual file is one step further.
  Links are resolved **when the download starts**: via a standard HTTP request when the host has a form to submit,
  or inside the app's embedded browser window where it clicks the unlock button and captures the resulting download URL.
  That browser window remains hidden, except for hosts with countdown timers (FileKeeper): there it appears for a few seconds
  because Chromium pauses timers in background tabs. Ad popups are closed automatically inside that window: no extra tabs
  in your personal browser. Results are cached, making subsequent attempts instantaneous.
- **Real-time stage visibility**: on the **⬇ Downloads** page, the task row indicates the current pre-transfer stage —
  "⏳ Skipping advertisement (ouo.io)", "⏳ Locating file on datanodes.to", "⏳ Preparing download (name and
  size)" — before switching to progress and transfer speed. If a step fails, the stage remains logged beside
  the error ("⛔ stopped at: …"), making it immediately obvious whether the issue lies with the shortener, host page, or file.
- **DataNodes and FileKeeper**: the file only triggers as a real browser download following the countdown timer, and the final URL never
  appears in page markup. The app clicks the required buttons inside the browser window and intercepts the download URL, canceling
  the browser transfer: the file is downloaded by the manager, not the browser. Works on Windows (WebView2).
- **MegaUp cannot be completed**: the download requires an active session cookie tied to a popup, which cannot be passed cleanly
  to the download manager. If a file is only hosted on MegaUp, download it directly via your web browser.
- If a host redesigns its page or presents an impassable captcha, the download halts with a descriptive error message
  ("Link points to a webpage, not a file (host)"): it avoids saving an HTML document to disk, and the host page remains accessible
  via the provider button.
- **Torrent**: offered only for magnet links specifying an individual file (filename with extension); magnets that would
  download an entire romset do not get a download button and the card clarifies this, preventing accidental bulk downloads.
- Online-only games **do not count as owned**: they are excluded from console totals, "Local Multiplayer",
  and recommendations based on your collection.
- A console with an online store appears in the sidebar **even if you own zero games for it**: allowing you
  to browse its catalog freely.

### Box Art and Descriptions

Catalog pages contain only game titles. **🖼 Covers and descriptions** in the *Online Store* dialog completes
game cards, with two progress bars (covers and descriptions) and a stop button:

1. **GameTDB** (Switch only, offline): a database of ~24,000 games downloaded once (~4 MB, cached for
   30 days). Populates box art, description (Italian first, then fallback), publisher, and player count in seconds. Missing
   regional box art is automatically retrieved from other regions.
2. **Web scrapers**: for entries still lacking covers or descriptions, the app crawls the individual game page (capped at
   2 req/sec) to extract cover art, synopsis, Title ID, release date, publisher, genres, file size, and screenshots.
   Compatible with sites displaying "Genre: …" in body text as well as tabular layouts (`<dl>` with `<dt>`/`<dd>`,
   like superpsx); full text dates ("April 20, 2021") are parsed into `YYYY-MM-DD`.
3. **Title search** on sites supporting search queries, for items still missing covers (scoped to site platforms:
   e.g. Ziperto search only runs for Switch).

Completed lookups are cached (60 days): each run resumes seamlessly. Plain directory listings
(`filelist` format) are excluded: their metadata is handled through normal scraping.

### Offline Store Metadata

**Store Metadata** (LaunchBox and TheGamesDB, local dumps only: no API keys, no tokens) looks up descriptions, developers,
publishers, genres, player counts, release dates, and ratings for both PC store games and console online store items.
Queries stay scoped to the store platform (avoiding confusing Switch and PC titles), skip DLCs/updates, and only
populate empty fields: existing scraped data is never overwritten.

<a id="gestore-dei-download-integrato-coda-torrent-e-debrid"></a>
## Built-in Download Manager (Queue, Torrent, and Debrid)

Pozzo Launcher includes a **full-featured download manager**, engineered for downloading HTTP files from web hosters as well as managing torrents and magnets without requiring third-party clients like qBittorrent or JDownloader.

Open it by clicking **⬇ Downloads** in the sidebar (or via the counter next to the logo) or from the **Tasks** panel.

### The Queue Table

The queue gathers all active, paused, or completed downloads in a centered, responsive table view:

- **Sortable columns**: Click headers to sort by *Name*, *Host*, *Size*, *Progress*, *Speed*, *ETA*, *Status*, or *Priority*. Selected sorting persists across sessions.
- **Expanded progress bar**: Visually indicates transfer progress and dynamically expands with window width.
- **Bottom status bar**:
  - Instantaneous aggregate download and upload speeds;
  - Active download slots relative to maximum concurrent limit (configurable in *Settings › Downloads*);
  - **Slow Mode** indicator (bandwidth throttle activated manually or via scheduled time windows);
  - **🎮 Game Mode** indicator: when you launch a game, the launcher detects active gameplay and automatically lowers background download priority to safeguard CPU and latency.
- **Context menu and quick actions**: Right-click a row (or press keyboard `Menu` key) to adjust download priority, move to top/bottom of queue, pause or resume, force recheck, open containing directory, or copy source link.

### Real-Time Details and Event Log

Double-clicking a download (or opening the resizable bottom pane) reveals three detail tabs:

1. **General**: Displays destination folder on disk, start date, elapsed time, connection type, and archive extraction status.
2. **Files**: For multi-file torrent downloads, lists all enclosed files, allowing you to uncheck unwanted items or set per-file priorities.
3. **Log**: Shows high-resolution timestamped logs of every operation. For protected links, records background browser events (buttons clicked, wait timers, anti-bot bypass attempts). Includes filter toggles for warnings/errors and buttons to copy or clear logs.

### Segmented HTTP Downloads and Link Resolver

- **Parallel segments**: HTTP files download using concurrent segments over HTTP/1.1 to saturate available host bandwidth. On Windows, partial files are created as "sparse files", avoiding pre-allocation zero-fills on disk.
- **Automatic link resolution**: Shorteners and file host pages (DataNodes, FileKeeper, KrakenFiles, 1Fichier, etc.) are resolved inside an embedded browser instance. If paused or interrupted, transfers resume from the exact byte offset without re-downloading completed chunks.
- **Show browser for Captchas**: If a host requires a manual captcha or Cloudflare check, enable **Settings › Downloads › Show browser while resolving links**: the window becomes visible so you can solve challenges on screen before downloading begins.

### Native Torrent and Magnet Support

- Magnet links and `.torrent` files are handled natively.
- Supports UDP and TCP trackers, DHT (Distributed Hash Table), PEX (Peer Exchange), LSD (Local Peer Discovery), and automatic UPnP router port forwarding.
- Configure a fixed port or allow the launcher to select a stable random port. Peer sessions persist to disk to resume swarms immediately upon startup.
- Supports **sequential downloading**, useful for organizing file segments and performing prompt integrity checks.

### Debrid Services (Multi-host)

If you subscribe to a Debrid multi-host service, configure your API key in **Settings › Downloads**:

- **Supported providers**: **Real-Debrid**, **AllDebrid**, **Premiumize**, **TorBox**, and **Debrid-Link**.
- **Strict privacy**: Your API key is stored strictly on your local PC and is never transmitted to external servers, telemetry, or crash reports.
- Supported hoster links unlock automatically at maximum account speed, bypassing free-tier wait queues and throttle caps.
- If a game is hosted on MultiUp, the card displays individual mirror hosts with dedicated buttons to pick your preferred server.

### Automatic Extraction and Folder Sorting

When a download finishes:

1. **Automatic extraction**: If the downloaded game is an archive (`.zip`, `.7z`, or `.rar`, including split multi-part archives), the launcher extracts it as soon as all volumes are present. RAR files require 7-Zip or UnRAR installed on the system. The source archive is automatically deleted after extraction.
2. **Smart console sorting**: The extracted game is moved directly to the appropriate console directory.
3. **Nintendo Switch intelligence**: Recognizes base games, updates, and DLCs by Title ID, neatly grouping them inside a single folder titled with the game's name.
4. **Instant library addition**: The new game appears in your library in fractions of a second (0.1 to 0.4s), triggering background metadata and cover art scraping.
5. **Automatic ROM hot-reload**: If you manually copy ROMs into console folders outside the download manager, Pozzo Launcher automatically detects them after a 10-second quiet period and integrates them into your library.

## Recognized Page Formats

The app can parse five page structures. Usually **there is no need to select them manually**: if no format is
specified, it is recognized automatically from the page markup.

| Format | Page Type | Pagination | Example Structure |
|---|---|---|---|
| `filelist` | File directory index (Apache, nginx) | No | Direct links to `.zip`, `.7z`, `.nsp`, … files with file sizes |
| `type_a` | Paginated card listing | `?lcp_page0=N` | `<ul class="lcp_catlist">` with one link per game |
| `type_b` | Single-page A–Z listing | No | `<div class="…-az-list">`, letter headers `<h2 id="letter-X">`, game items `<div class="…-game">` |
| `type_c` | Article archive (WordPress) | `/page/N/` | Each game is an `<article>` with `h2.entry-title` |
| `type_d` | Complete single-page A–Z index | No | `div.az-listing` with letter sections and link lists |

Useful details:

- **filelist** filters links by file extension: retains only valid game archives and console-specific extensions. It is the
  classic directory format and acts as the fallback when no other pattern matches.
- **type_a** and **type_c** read page 1, extract total page count from pagination controls, and crawl
  subsequent pages sequentially with randomized delays. If pagination only offers "Next", links are
  followed until exhausted.
- **type_a, type_b, type_c, type_d** link to the game's **detail page**, not direct files: no extension
  filtering is applied.
- If a paginated listing shrinks or its format changes, obsolete entries are pruned: no ghost titles linger in
  your library.

<a id="indicare-il-formato-a-mano"></a>
### Specifying the Format Manually

If automatic detection fails, the format can be explicitly configured in `settings.json` under `catalogs`:

```json
{
  "catalogs": {
    "snes": ["https://example.test/roms/"],
    "nds":  { "urls": ["https://example-a.test/all/"], "type": "type_a" },
    "gba":  { "urls": ["https://example-b.test/all"], "type": "type_b",
              "css": { "az_list": "mysite-az-list", "game": "mysite-game" } }
  }
}
```

- The **list of URLs** format uses auto-detection (or `filelist`).
- The **object** format contains `urls` and options: `type` and, specifically for `type_b`, `css` specifying the classes
  of both page containers (`az_list` for wrapper, `game` for each item).
- Editing URLs via the *Online Store* GUI preserves custom `type` and CSS options.

### Testing an Address Before Adding

A common mistake is pasting an address that does not list the **entire** catalog (a single category, a partial archive,
a single page): resulting in few or no games found. The **🔍 Test** button (in *Other PC Stores*) inspects only that
single page and reports format, game count on page, total pages, and initial titles:

```
✅ Format type_c: 10 games on this page, across 1,373 pages. Examples: …
⚠️ Format filelist: 0 games on this page, single page.
```

- Multiple pages: the URL is a complete master index; the app will crawl all pages.
- Few games and single page: likely not a master index. Look for the site's "all games" directory,
  often labeled *All*, *Archive*, *A–Z*, or *Index*.

## Other PC Stores {: #altri-store-pc }

In **Settings › Stores › Other PC Stores (Unofficial)**, you can add directories of PC games that are not official
stores, categorized into:

| Category | Description |
|---|---|
| **📦 Repack** | Highly compressed games: faster downloads, longer installation time. Ideal for bandwidth-constrained connections |
| **⬇ Direct Download** | Unaltered standalone game installations |

To add one:

1. paste the **directory URL** and choose the **category**;
2. click **🔍 Test** to verify format and game count;
3. click **Add**;
4. click **↻ Read Lists** to parse all directories and rebuild the library.

Directories use the same formats as consoles, with automatic structure detection. Games appear as PC games
available for download: listed in the PC section, filters, and game details cards. Cards display the
category ("📦 Repack (fast download, longer install)" or "⬇ Direct Download") and a button per source.
Identical games across multiple sites are merged into a single card.

### Repack Sources

Repack pages do not link to the file directly: they list multiple host mirrors for the same title. The game card
displays each mirror in order of reliability: first **torrent** (almost always available and ad-free),
followed by **FuckingFast**, **DataNodes**, **FileKeeper**, and third-party mirrors.

| Button | Action |
|---|---|
| 🧲 **Torrent** | queues the magnet link: full game, no ads, no browser |
| ↗ **site** | opens the torrent listing page (1337x, RuTor, Tapochek…) in your browser |
| 📄 **Filehoster** | parses the hidden paste bin (MultiUP, PixelDrain, DataNodes…) and displays links |
| ⬇ **Download all N parts** | queues all archive volumes (`.part01.rar`, …): extracts automatically when all arrive in folder |

The **⬇ Download** button at the top of the card automatically selects the primary direct source (FuckingFast, then
DataNodes, FileKeeper, etc.) and queues all parts; **🧲 Torrent** sits alongside when listed.

Only true download links are retained: developer websites, forums, screenshots, and promo landing pages are
stripped; ".torrent file only" is omitted when magnet links exist. If the page lists an
**update**, it appears as a distinct "Update" row with its own mirrors: **⬇ Download** fetches the base game, while
**⬇ Download Game + Update** queues both.

Filehoster pastes (often encrypted via PrivateBin) are decrypted locally to extract file URLs (cached for 7 days).
If a layout changes, the **↗** button remains to open the page manually. Direct download URLs resolve at transfer start:
FuckingFast and DataNodes execute via the background browser (Cloudflare, timer, captcha), while standard hosts use
direct form submission.

The directory table includes a filter *All / 📦 Repack / ⬇ Direct Download*, allowing you to re-categorize or remove entries.
In `settings.json`, entries reside in `pc_stores`:

```json
{ "pc_stores": [ { "url": "https://example.test/games/", "kind": "repack" },
                 { "url": "https://other.test/a-z/", "kind": "direct" } ] }
```

### Installing a Repack

A repack is not a pre-installed game: it is an archive containing the installation **setup wizard**. Once downloaded
and extracted, the task row in **Downloads** displays **📦 Install**: the launcher launches the repack's `setup.exe`
(requesting administrator rights if needed) in its own window, allowing you to select destination path and installer components.

When the installer window closes, the launcher scans for the newly installed game — in the Windows Apps registry
or in newly created folders under *Program Files* and storage drives — and adds it to the library as an installed PC game,
appearing immediately without requiring a full rescan. The *available for download* entry for that game is dismissed.

In **Tasks**, installation progress is listed as **Installing · *game*** with elapsed time: installer internals
cannot be monitored from outside, so the progress bar remains indeterminate until the setup window exits.

## Store Updates

Parsed listings are cached locally: store games appear **instantly** on startup, and background updates
run silently without locking the UI. In **Settings › Stores › 🔄 Store Updates**, configure update frequency:

| Mode | Behavior |
|---|---|
| **On app startup** (default) | Refreshes all directories shortly after launch |
| **Daily at** | Runs once per day at the scheduled time while app is open |
| **Manual only** | Never updates automatically: triggered via **⟳ Update All** |

![Settings › Stores: store status, connected accounts, and directory updates](../images/impostazioni-store.jpg)

### The Queue Pipeline

- **Parallel crawls**: up to the concurrency limit set in *in parallel* (default 4, range 1–8), **never crawling
  two directories from the same host simultaneously** to prevent rate-limiting.
- Clicking **⟳** on multiple stores puts each into the **queue**, starting as slots become free. **⟳ Update All**
  queues all configured stores. Adding a store while a crawl is running enqueues it rather than rejecting it;
  this unified queue serves the ⟳ button, *Read Lists*, the console *Online Store* window, and the
  Link → Store plugin.
- Once the queue clears, the library rebuilds **exactly once**.
- **■ Stop** cleanly terminates page crawling at the end of the current page (even mid-way through hundreds of pages)
  and empties the queue. The button vanishes when idle.
- Unreachable domains do not halt the process: failed rows display error badges and cached catalogs remain
  active.

### Store Status Table

The table always reflects all configured stores:

| Column | Description |
|---|---|
| Status | `·` unread, ⏳ in progress, ✓ finished, ✕ error, ⏭ skipped |
| Queue | Position in queue |
| Progress | Current page / total pages, seconds per page, estimated time remaining |
| Log | Most recent log message; **📄** opens full log for that store |
| ⟳ | Queues only this store |

### File Logging

To diagnose why a site is slow or failing, start the app with file logging:

```bat
python -m pozzo app --log                   :: <cache>\logs\diagnostica.log
python -m pozzo app --log C:\temp\gs.log    :: custom path
set POZZO_LOG=1 && python -m pozzo app
```

The log file records timestamps, scheduler decisions (mode, time, deferred launches and reasons),
opening/closing of catalogs, **each page crawled** (`… page 51/147 — 50 games`), and errors with
exceptions and descriptions. Files exceeding 8 MB rotate automatically (older records move to `.log.old`).
The active log path is displayed in **Settings › Stores**.

## Plugins Adding Stores

### Link → Store

Many index sites aggregate **lists of other download sites**. The **Link → Store** plugin (enabled in **Settings ›
Appearance › Plugins**, found under *Link → Store* in the sidebar) parses such curator pages:

1. paste the page URL and click **Parse Links**;
2. links are **grouped by heading** (h2/h3 page sections) and filterable;
3. assign each link to its target: a **console** (becomes an online store) or **PC store** with category
   (📦 Repack or ⬇ Direct Download);
4. the plugin saves it to settings immediately without restarting, indicating if it was already present;
5. **↻ Read Added Stores** queues scraping: progress is tracked in **Settings › Stores**.

### Minerva Store

The **Minerva Store** plugin (sidebar entry) adds minerva-archive.org directories curated on r-roms.github.io to each
console's online store, then crawls game listings. **Import from r-roms** displays the import log; existing links
are preserved and **not re-read**: only newly added stores for that console are read (plus existing unread stores,
e.g. after adding a new platform). Upon completion, the library updates.

For **Switch**, it preconfigures three complete catalogs: NXBrew index (`type_b`), Ziperto NSP (`type_c`), and
Ziperto XCI (`type_d`). For **Switch 2**, it preconfigures the NXBrew Switch 2 category archive (`type_c`,
paginated). For **PS4** and **PS5**, it preconfigures the superpsx archive (`type_c`). When a
console has multiple directories with different layouts, the plugin clears hardcoded type declarations in `settings.json`,
allowing auto-detection to handle each page.

## Developer Guide

### Adding a New Page Format

Parsers are registered in `pozzo/catalog.py`:

```python
PARSERS = {
    "filelist": _parse_filelist,
    "type_a": parse_type_a_index,
    "type_b": parse_type_b,
    "type_c": parse_type_c_index,
    "type_d": parse_type_d_index,
}
```

To add a new format:

1. implement `parse_type_x(page, base_url, exts=None, config=None)` returning a list of dicts
   `{"name", "size", "url", "magnet"}` (or `(items, total_pages)` if paginated);
2. register it in `PARSERS`;
3. if applicable, add auto-detection heuristics in `detect_kind()`.

Fetching, caching, pruning stale items, library integration, and APIs work out of the box. Tests reside in
`tests/catalog/` and mock HTTP network boundaries (`catalog._get_page`): zero live network requests.

### Adding a New Store (Library Provider)

A new store, such as an unsupported game launcher, is added via a **plugin** (see [Themes and Plugins](ESTENSIONI.md)).
The plugin backend registers a subclass of `StoreProvider` whose `fetch()` method yields games as `StoreGame`:

```python
# plugins/mio-launcher/backend.py
import json
from pathlib import Path

from pozzo.stores.base import StoreGame, StoreProvider


class MioLauncher(StoreProvider):
    id = "miolauncher"
    name = "Mio Launcher"

    LIBRARY = Path.home() / "MioLauncher" / "library.json"

    def detected(self) -> bool:
        return self.LIBRARY.exists()  # store appears only if launcher is installed

    async def fetch(self) -> list[StoreGame]:
        games = []
        for g in json.loads(self.LIBRARY.read_text(encoding="utf-8")):
            games.append(StoreGame(
                store=self.id, id=str(g["id"]), title=g["name"],
                installed=bool(g.get("path")), install_dir=g.get("path", ""),
                launch={"type": "uri", "target": f"miolauncher://run/{g['id']}"},
                install_uri=f"miolauncher://install/{g['id']}",
            ))
        return games


def register(gs):
    gs.add_store(MioLauncher)
```

Key fields of `StoreGame`:

| Field | Meaning |
|---|---|
| `store`, `id`, `title` | Store ID, game ID in store, game title |
| `installed`, `install_dir` | Installation state and directory |
| `launch` | Launch configuration: `{"type": "uri", "target": "…"}` or `{"type": "exe", "target": path, "args": [], "cwd": ""}` |
| `install_uri` | URI opening the store client to the installation page |
| `page` | Web storefront URL |
| `playtime`, `last_played` | Playtime (seconds) and last played timestamp, if provided by store |
| `images` | Images by type (`cover`, `hero`, `logo`, `icon`, `header`) → URL |
| `genres`, `description`, `developer`, `publisher`, `release_date`, `size`, `reviews` | Optional metadata |

The new store appears in **Settings › Stores** and its games appear in the PC section, with launching, playtime
tracking, and multi-store deduplication working identically to built-in stores. Built-in stores (`pozzo/stores/`)
serve as references: `manual.py` is the simplest, while `steam.py` and `epic.py` showcase account authentication
and uninstalled game handling.
