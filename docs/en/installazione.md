# Installation and updates

## Choosing the right file

Each release is published on the repository's **Releases** page, with two files per operating system:
an **installer** and a **portable** version.

| System | Installer | Portable |
|---|---|---|
| Windows 10/11 (64-bit) | `PozzoLauncher-<versione>-windows-x64-setup.exe` | `PozzoLauncher-<versione>-windows-x64.zip` |
| macOS 11+ (Apple Silicon) | `PozzoLauncher-<versione>-macos-arm64.dmg` | `PozzoLauncher-<versione>-macos-arm64.zip` |
| Linux (64-bit) | `pozzo_<versione>_amd64.deb` | `PozzoLauncher-<versione>-linux-x64.tar.gz` |

**Installer or portable?**

- The **installer** places the app in Program Files, creates a shortcut in the Start menu (and desktop, if you choose), and allows you to uninstall it via system settings. On Windows, it installs for the current user only (`%LOCALAPPDATA%\Programs\PozzoLauncher`) and **does not require administrator privileges**.
- The **portable** version is a folder you can extract anywhere, even onto an external drive. It does not install anything.

### Windows

- Installer: open `setup.exe` and follow the steps.
- Portable: extract the zip archive and run `PozzoLauncher.exe`.

Executables are not signed: SmartScreen will ask for confirmation (**More info › Run anyway**).

### macOS

- `.dmg`: open it and drag **Pozzo Launcher** into the **Applications** folder.
- `.zip`: extract and open `PozzoLauncher.app`.

The first time, open the app with **right-click › Open** (the app is not code-signed), or from Terminal:
`xattr -cr /Applications/PozzoLauncher.app`.

### Linux

- `.deb` (Debian, Ubuntu, Mint, and derivatives): `sudo apt install ./pozzo_<versione>_amd64.deb`. This also installs required system libraries, the application menu shortcut, and the `pozzo` command.
- `.tar.gz`: extract and run `PozzoLauncher/PozzoLauncher`. On minimal desktop installations, Qt window libraries may be required: `libegl1 libnss3 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-xkb1`.

If the native window cannot be opened, the app opens in your default browser.

## First launch: the setup wizard

On first launch, the **setup wizard** appears in five steps:

1. **Welcome**: shows where your data will be saved.
2. **ROM folder**: select the folder containing your console directories (for example `D:\ROM` containing `snes`, `psx`, `Nintendo - Game Boy Advance`…). **Verify** displays the recognized consoles. If you don't have ROMs, check *I don't have ROMs: I only want PC store games*.
3. **PC Stores**: stores detected on this PC ready to be imported. Accounts (Epic, GOG, Steam API key) can be linked later in **Settings › Stores**.
4. **Online sources**: optional accounts for data sources (ScreenScraper, IGDB, RAWG, TheGamesDB). Without accounts, the app still relies on offline sources.
5. **Summary**: **Start** saves everything, imports store games, builds the library, and launches background metadata retrieval for new games. The app opens as soon as the library is ready.

The setup wizard can be reopened at any time from **Settings › New games**.

<a id="dove-stanno-i-dati"></a>
## Where data is stored

Configuration, cache, library, and personal data reside in the user folder:

| System | Data folder |
|---|---|
| Windows | `%LOCALAPPDATA%\PozzoLauncher` |
| macOS | `~/Library/Application Support/PozzoLauncher` |
| Linux | `~/.local/share/PozzoLauncher` |

**If you used the previous version** (formerly named GameScraper): on first launch, the `GameScraper` folder is **copied** to `PozzoLauncher`, including library, favorites, saves, and settings. The old folder is untouched and can be safely deleted once you verify everything is working. This copy occurs only once (with large libraries it may take a few minutes), and if it fails, the app continues using the previous folder without losing anything.

The `config.toml` file is looked up in the following order:

1. `POZZO_CONFIG` environment variable (full path to a `config.toml`);
2. a `config.toml` **next to the executable**: this is **portable** mode, keeping all data in the same directory as the app;
3. the user data directory (table above).

The executable and source runs share the same data directory, so library, favorites, and settings are never split across two copies.

## Quick start

The app opens in about a second, even with tens of thousands of games:

1. your **own games** (ROMs and owned PC games) appear immediately in your selected theme with a *Loading your games…* progress bar;
2. right after, in the background, **online store games** arrive (*Loading store games…*), which can number in the hundreds of thousands.

In the meantime, you can already search, open, and play your games.

## Updating the app

On startup, the app checks GitHub for new versions (at most once every 12 hours; or instantly with **↻ Check for updates** in **Settings › About**). If an update is available, a small pop-up appears: **⬆ New version …**, once per release:

- clicking the pop-up downloads and installs the new version (if the app cannot install it automatically, e.g. when run from source, it opens the download page);
- **✕** dismisses it; the update remains accessible under **Settings › About**.

In **Settings › About**, when a new version is available, an **⬇ Install and restart** button is also present:

1. the app downloads the appropriate package for **how it was installed** and displays progress;
2. verifies the file integrity (SHA-256 checksum published on GitHub);
3. closes and reopens updated.

| Installation | What happens |
|---|---|
| Windows with installer | The installer runs silently and restarts the app upon completion |
| Windows, macOS, Linux portable | A helper script waits for the app to exit, overwrites old files with new ones, and restarts it |
| Linux `.deb` | The system package manager opens, asks for your password, and then you restart the app |
| Run from source | The button does not appear: update using `git pull` |

Updating the portable version **does not delete anything**: `config.toml`, cache, and your personal files beside the executable are preserved. If the application directory is read-only, the app will notify you to update manually.

![Settings › About: installed version, update check, downloaded data, and changelog](../images/impostazioni-info.jpg)

## Running from source

For development or testing the latest changes:

```powershell
python -m pip install -r requirements.txt
python -m pozzo app              # desktop window
python -m pozzo app --browser    # in browser (http://127.0.0.1:8765)
python -m pozzo app --bigpicture # directly into Big Picture
```

Executables are built with PyInstaller (`pyinstaller packaging/pozzo.spec --noconfirm`); on GitHub, they are generated by the release workflow on every version tag.
