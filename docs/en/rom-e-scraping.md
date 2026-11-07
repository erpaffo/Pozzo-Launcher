# ROMs and Data Scraping

This chapter explains how the app finds ROMs on disk, how it identifies them, and where it downloads metadata and images from.
Everything is managed from **Settings › New Games** and **Settings › Sources**, or using the
**⟳ New Games** button at the top.

## Organizing Folders

The ROM folder (**Settings › New Games › ROM Folder: 📁 Change…**) contains one folder per
console. Folders are searched **recursively**, up to 4 levels deep:

```
D:/ROM/
  snes/                                                   *.sfc *.smc *.zip
  psx/                                                    *.chd *.cue *.m3u
  switch/<game>/                                          one folder per game
  Minerva_Myrient/No-Intro/Sega - Mega Drive - Genesis/   *.zip
  Minerva_Myrient/Redump/Nintendo - Wii U - WUX/          *.zip
```

The app recognizes:

- **short names** and aliases: `snes`, `psx`, `Mega Drive`, `genesis`…;
- **No-Intro and Redump set names**, even with suffixes:
  `Nintendo - GameCube - NKit RVZ [zstd-19-128k]` becomes GameCube.

For some consoles (Switch, PS3, PS Vita, Xbox, Xbox 360), each subfolder is a game. The complete list of
recognized consoles can be obtained with `python -m pozzo platforms`.

A console in the sidebar displays its games with the same library filters, the **🏆 Top 100** button,
and the **Online Store** button (see [Adding Stores](store-online.md#store-online-di-una-console)):

![The Game Boy Advance console: 5,013 games, Top 100 and Online Store in the console bar](../images/console.jpg)

### Unrecognized Folders

In the **⟳ New Games** window, unrecognized folders appear with a dropdown menu to associate them with a console.
Alternatively, you can map them in `config.toml`:

```toml
[platform_folders]
"Super Nintendo (PAL)" = "snes"
"Various/SNES Collection" = "snes"   # a path relative to the root is also valid
```

### Adding a New Console

**＋ Add Console** creates a console that the app does not recognize by default. You specify:

- **Name** and **Identifier** (short, without spaces);
- Game **File extensions**;
- Identifying **Folder names** (comma-separated);
- **Disc-based games** (ISO/CHD): skips checksum calculation, which is too slow on large files;
- **Each subfolder is a game**, for consoles with folder-based games;
- **IGDB Platform ID** (optional): improves metadata scraping.

### Additional ROM Folders

In **Settings › New Games › Additional ROM Folders**, you can add extra drives or directories. Each folder can contain console
folders or represent a console itself (for example `E:\Switch`). A disconnected drive is skipped and
reported without blocking the others.

### 📋 Paste a Folder for a Console

In the **⟳ New Games** table, each console has a **📋** button: it reads the path from the PC's **clipboard** and
adds it as a folder for that console; **📋 Paste PC Folder** does the same for a folder of PC games
(`.exe`). If the browser prevents reading the clipboard (which can happen outside the desktop app), the path can be pasted into a
prompt dialog.

The folder is saved and the app searches **only for new games** in the background: a notification shows how many were
found, while the progress bar handles the rest. There is no need to rescan everything.

## Scanning for New Games

**⟳ New Games** opens the scan window: for each console found on disk, it displays how many games are not yet
in the library, alongside the **Missing Data** and **Incomplete** columns. Choose what to do:

| Mode | What it queries |
|---|---|
| **Only new or never searched games** | Games that have never been searched before: fast even on large libraries |
| **Complete missing data** | Games with missing or incomplete data: retries only sources that failed previously |
| **Rescrape everything from scratch** | Everything, ignoring the cache (consumes a significant amount of online source quotas) |

Then click **⟳ Search New Games**. Progress can be tracked with a per-source progress bar, **■ Stop** halts
everything, and when finished the library updates automatically. **↻ Rescan Folders** re-reads the disk.

Execution **resumes where it left off**: every result is immediately saved to `cache/cache.db`. If you interrupt,
run out of quota, or lose network connection, simply relaunch.

Files tagged `[BIOS]` are never added to the library (unless `show_bios` is set) and are not counted as new.

### Automatically Added Games

If you copy a ROM into a console folder, it appears in your library **without clicking anything**. The app checks
folders every few seconds and waits about **10 seconds after copying finishes** (avoiding reading partially written files);
it then adds the games and shows an alert, for example "2 new games in SNES: …". It processes **one folder at a time**
and slows down during active gameplay sessions to avoid dropping framerates.

- Box art and descriptions arrive **shortly after**: the game entry appears first, followed by the metadata.
- Games **deleted from disk do not disappear** automatically: to remove them from the library, use **↻ Rescan Folders**.
- To disable this feature: **Settings → Library → New Games**, uncheck "Automatically add games copied to ROM folders". You can also view its status there (listening, last check, pending copy).

### Estimate Before Starting

**📊 Estimate** displays, for each source, how many games will be queried, the required number of requests, estimated
time, and how many days it will take within each source's rate limits.

## How Games Are Identified

Identification is performed **offline**:

1. **Name first**: the filename is matched against Libretro's No-Intro and Redump DAT files. If an exact match
   is found, CRC, MD5, and SHA1 are pulled directly from the DAT and **the file is not even read from disk**.
2. **Content second**, only for remaining files: the CRC of ZIP archives is read directly from the archive header index; files are read in
   8 MB chunks using an I/O strategy tailored for HDD vs SSD (`disk`, `io_workers`), and results are cached.
3. Files larger than `max_hash_mb` (512 MB by default) are not read: they are identified by name alone.

On a real-world collection of 14,782 games on an HDD, the amount of data read for Nintendo DS games dropped from 149 GB to just 3.6 GB.

### Scene-Style Release Names

PS4 folder names such as `Sekiro.Shadows.Die.Twice.PS4-CUSA12047` are cleaned to "Sekiro Shadows Die Twice";
bracketed codes such as `(PCSE00812)` are also stripped from the title.

### Nintendo Switch

Switch games (`.nsp`, `.xci`, `.nsz`, `.xcz`) are read directly from the file using your `prod.keys`, exactly as
emulators do: extracting title, publisher, version, and the 256×256 icon used as box art. Key files are automatically detected
in Ryujinx, Eden, and yuzu, or specified in `[paths] switch_keys`.

The game details card also displays the **installed update** and **DLCs** found in the folder. The base game
is identified by a Title ID ending in `000`. Truncated packages (for example, an NSP split across FAT32 4 GiB
boundaries) are flagged with a clear warning: the file must be re-downloaded or merged.

## Metadata Sources

Sources are prioritized and configured in **Settings › Sources**. Each source **only** queries games that are
still missing metadata it can provide.

| Source | Type | What it provides | Cost for services |
|---|---|---|---|
| **nsp** (Switch) | offline | Title, publisher, version, icon from file | None |
| **libretro** | offline | Identification via CRC/name, franchise, box art, screenshots, title screens | None (DATs refreshed every 30 days) |
| **LaunchBox** | offline | Community ratings, descriptions, genres, ESRB, videos, logos, 3D boxes, fanart | One download per week (~110 MB) |
| **TheGamesDB (full dump)** | offline | Descriptions, player count, box art | One download per month, no rate limit |
| **ArcadeDB** | online | Arcade games | 25 games per request |
| **IGDB** | online | Descriptions, user and critic ratings, franchise | 10 games per request |
| **ScreenScraper** | online | Checksums, multilingual descriptions, wheels, marquees, videos | Account quota |
| **RAWG** | online | User ratings and Metacritic | Free API key, 20,000 requests/month |
| **Wikipedia** | online | Descriptions, developers, publishers, genres, release year (Italian first, then English) | |
| **Steam Reviews** | online | Review score for Steam games | 1 request/sec, cached for 14 days |

**Local Databases** (LaunchBox, TheGamesDB) are downloaded completely once a week or month: after that, all
lookups occur locally on disk.

In **Settings › Sources**, each source has an on/off toggle, priority order (▲▼ arrows), request rate limit,
and daily/monthly quotas:

![Settings › Sources: source order, request rate, and daily/monthly limits](../images/impostazioni-fonti.jpg)

### The Cascade Pipeline

Sources work **in parallel**, each with its own queue: a game moves to the next source as soon as the previous
one finishes processing it, including media downloads. While ScreenScraper gradually uses its rate-limited quota, libretro
and IGDB are already working on other games. The configured priority order is strictly respected: a source only sees a
game after all preceding sources have had their turn.

For specific individual fields, priority can be overridden via `[field_priority]` (for instance, Italian descriptions, which
are predominantly available on ScreenScraper).

### Choosing Which Media to Download

The `media` setting in `config.toml` selects image assets to retrieve: `cover`, `screenshot`, `title`, `wheel`, `marquee`, `video`, `box3d`,
`fanart`. Wheels, marquees, videos, and 3D boxes are almost exclusively found on ScreenScraper: only request them if needed, because
doing so forces every game through ScreenScraper, making its daily quota the bottleneck.

## Protecting Online Services (Avoiding Bans)

- **Offline sources first**: online sources only receive games that are still missing metadata.
- **Per-source rate limits**: requests per second, day, and month, with safety headroom. These can be adjusted in the
  **Settings › Sources** table (*Rate/s*, *Max/day*, *Max/month* columns) or via `[limits.<source>]`. Request
  counters persist across app launches.
- **Circuit breaker**: after repeated errors (429, 5xx, timeouts), a source pauses temporarily; after 3 consecutive pauses, it
  disables itself until the next run.
- **Response caching**: identical queries are never re-requested. API keys are never stored in cache.
- ScreenScraper optimizations: threads and quotas are read directly from your account, restricted to primary versions (`only_primary`),
  with request buffers (`quota_reserve`, `ko_reserve`).

## Automatic Scraping

In **Settings › Sources › Automatic Scraping**, the app can run daily at a scheduled time to complete missing metadata within
source rate limits. If a daily quota is reached, it seamlessly resumes the next day.

## Missing Data for a Single Game

In the game details view, the **Missing: …** box lists fields and media that could not be found. **⟳ Search Missing Data**
retries all sources for that game and all its versions. From the command line:
`python -m pozzo scrape --missing`.

The **? Missing Data** view in the sidebar gathers all games that failed to be identified by any source, allowing
you to review them in bulk:

![Missing Data view: games for which no source found information](../images/libreria-senza-dati.jpg)

## Game Lengths (HowLongToBeat)

**Settings › Sources › Game Lengths** downloads game completion times from HowLongToBeat, powering duration-based sorting, Discover filters (*Short* and *Long*), and smart collections.
In game details, playtime duration appears in the modal layout (Cinema mode): if missing, it is queried on demand when opening the game and saved.

## Source Credentials

| Source | Required Credentials |
|---|---|
| ScreenScraper | Account username and password, plus developer `devid` and `devpassword` (requested via screenscraper.fr forums) |
| IGDB | A registered application on dev.twitch.tv: Client ID and Client Secret |
| RAWG | Free API key from rawg.io/apidocs |
| TheGamesDB | API key from TheGamesDB forums |

Credentials can be entered during the setup wizard, in **Settings › Sources**, or in `config.toml`;
alternatively, using environment variables: `SS_USER`, `SS_PASSWORD`, `SS_DEVID`, `SS_DEVPASSWORD`, `IGDB_CLIENT_ID`,
`IGDB_CLIENT_SECRET`, `TGDB_API_KEY`.

## Command-Line Scraping

Scraping can also be run headlessly from the terminal (see [Reference](riferimento.md#comandi-da-terminale)):

```powershell
python -m pozzo run                # all detected platforms
python -m pozzo run -p snes,psx    # specific platforms only
```

Output is saved to `output/<console>/`: `games.json` (all metadata with field provenance), `games.csv`
(compatible with Excel, `;` delimiter), `missing.txt` (unmatched ROMs), and `media/<type>/`.
