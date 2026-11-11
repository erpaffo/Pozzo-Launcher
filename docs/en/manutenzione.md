# Data, Backups, and Health

<a id="sincronizzazione-tra-pc"></a>
## Cross-PC Synchronization

With two PCs (for example a desktop and a laptop), **Settings › Library › Cross-PC Synchronization** keeps personal data aligned for each profile: favorites, hidden games, statuses, notes, ratings, primary version, playtime and play sessions, personal collections and collection changes, and wishlist. Synchronization happens automatically at startup and every 5 minutes, or immediately with **⟳ Sync now**.

![Settings › Library: cross-PC synchronization, export for other frontends, and backups](../images/impostazioni-libreria.jpg)

### What to Synchronize

| Choice | What transfers between PCs |
|---|---|
| **Personal data only** | The data listed above |
| **Personal data and app settings** | Additionally: online stores and other PC stores, sources and their limits and accounts, added consoles, theme, disabled plugins, smart collections, wishlist and RetroAchievements settings |

The following **always remain local to the individual PC**: ROM folders, emulators and launch profiles, manually added games, PC store accounts (Steam, Epic, GOG…), phone, and streaming. The choice must match on both PCs.

### Two Methods, Even Together

**Shared folder**: choose a folder synced by OneDrive, Dropbox, Google Drive, a NAS, or Syncthing—the **same** on both PCs—and click **Save**. Each PC only writes its own file (`PozzoLauncher-sync/<profile>/<pc>.json`), so the sync service will not create conflicts. This works even if the PCs are never turned on at the same time.

**Local network**, without external services:

1. On the first PC, click **🔑 Show code for another PC**: a 6-digit code appears (valid for 10 minutes, single use) along with the PC's address;
2. On the second PC, enter the address and code, then click **Pair**.

From that point on, the second PC exchanges data with the first **bidirectionally** whenever both are powered on within the same network. Communication is encrypted (HTTPS) and the first PC's certificate is remembered during pairing: if it changes, data exchange stops and pairing must be repeated. A paired PC can only exchange synchronization data, nothing else. Paired PCs can be disconnected from the same section. Windows may prompt to allow the app on private networks.

### How Data is Merged

- For each data point, the **most recent change** wins: if you remove a favorite on your laptop, it disappears from your desktop as well.
- On first connection, data from both PCs is **merged**: favorites from both remain favorites.
- **Playtime** is summed: each play session is recorded only once, even if synchronization is repeated.
- **Deletions** (collections, wishlist games) also propagate to the other PC.
- The same game is identified across both PCs even if stored in different folders (ROMs by content, PC games by store code).

## Backups of Your Data

In **Settings › Library › Data Backups**, favorites, playtime, statuses, notes, personal collections (across all profiles), play session history, wishlist, launch profiles, manually added games, browser saves, `settings.json`, user profile files and custom themes are saved into a zip archive. Backups reside in `<cache>/backups`, with a `manifest.json` listing the contents.

- **Automatic weekly backup** at startup: off by default, enable it in the same section. The last N backups are kept (10 by default, 1 to 50).
- **Credentials**: "Include credentials" is on by default. If you turn it off, API keys and tokens stay out of the zip (safe to keep in the cloud) and a restore leaves the current ones in place.
- **Restore preview**: before confirming you see which files will be overwritten or created and, for data, how many rows exist now versus in the backup. If the backup contains before/after-game scripts, a warning is shown.
- Not included: caches, metadata, images, screenshot files, the download queue, `config.toml` and emulators.
- **Hot restore**: works while the app is running. Before restoring, a copy of the current data is saved so the restore operation can be undone.

There is no need to back up the library database (`library.db`): it rebuilds itself automatically. For game saves, see [Playing](giocare.md#salvataggi).

## The Health Page

**Settings › 🩺 Health** monitors everything that needs fixing in a single place:

- unreachable ROM folders (for example, a disconnected drive);
- consoles without a configured emulator;
- missing `prod.keys` for Switch games;
- games missing data or covers;
- games whose files were not found;
- non-responsive online sources;
- Sunshine stopped or set to manual startup;
- age of the latest backup of your data.

Each issue includes a button that resolves it or navigates to the relevant setting. The check performs no network requests.

![The Health page: issues to fix and successful checks](../images/impostazioni-salute.jpg)

## Renamed or Moved Folders

If you rename or move game folders, the library sees old games as "files not found" and new ones as newly discovered games. In **Settings › New Games**, the app detects this automatically and displays **⟲ N games appear renamed or moved**: it pairs games with missing files to the new folders (same console and file size, or similar name) and **Relink selected** updates them in a single click. Downloaded data, playtime, favorites, and collections are transferred to the new location.

Before relinking, a backup copy of the databases (`*.bak`) is saved. This works as long as the library still contains games with the old paths, meaning **prior** to a rebuild. From the terminal:

```powershell
python -m pozzo relink            # preview
python -m pozzo relink --apply    # apply
```

## Exporting to Other Frontends

**Settings › Library › Export for other frontends** exports metadata and images for:

| Frontend | Output |
|---|---|
| **ES-DE** | `gamelist.xml` plus the `downloaded_media` folder |
| **Pegasus** | `metadata.pegasus.txt` plus images |
| **Web page** | `index.html` plus the `covers` folder |

From terminal: `pozzo export-frontend --format esde`, `--format pegasus` or `--format html`.

### The Web Page

The web page is **a single file plus covers**, requiring no server and no external resources: it opens with a double-click (even via `file://`), from a NAS, from a network drive, or hosted on a static website. It features search, console filtering, sorting, and game detail cards; cards are rendered on the fly as you scroll, so it performs smoothly even with thousands of games. The page title can be chosen in the field next to the format selector.

## Downloaded Data

**Settings › About › Downloaded Data › ⟳ Calculate** shows where data is located and how much space it uses: broken down by folder, by console (images and videos, database metadata, online store listings), by metadata source, by other data, and by individual database.

## Rebuilding the Library

The library rebuilds itself automatically after every scan, store refresh, or import. Manually: `python -m pozzo library`. Rebuilding never touches your personal data (`userdata.db`, `settings.json`).

## Logs

- Standard executable logging without a terminal is located at `<data directory>/logs/pozzo.log`.
- Detailed diagnostic logging (stores, scheduler, errors) is enabled via `--log` or `POZZO_LOG` (see [Logging to file](store-online.md#log-su-file)).
