# Playing Games

## Configuring Emulators

Emulators are configured in **Settings › Emulators**, across two tables.

### Installing Emulators from the App

**Install Emulators**, at the top of the page, downloads with one click the latest official release of RetroArch, Dolphin,
PPSSPP, DuckStation, PCSX2, RPCS3, Vita3K, melonDS, Azahar, Cemu, Xenia Canary, xemu, Flycast, and shadPS4, setting them up
automatically. The version is pulled from each project's GitHub releases; RetroArch, Dolphin, and PPSSPP are downloaded from their
official websites. Emulators are placed in the folder specified below (otherwise in `Emulatori`, alongside settings).
**↻ Update** installs the new version over the old one: configuration and data inside the emulator folder are
preserved. **⬇ Download Cores** grabs RetroArch cores missing for consoles in the library from the libretro
buildbot. Ryujinx and Eden do not publish on GitHub: they must be installed manually. Windows only.

Emulators belong to their respective developers: Pozzo downloads the builds they publish without modifying them, and every row links
to the original project.

**Programs**: one path per emulator, shared by all consoles using it. **🔍 Find Emulators** searches a folder for
recognized executables: RetroArch, Ryujinx, Eden, melonDS, Dolphin, PCSX2, DuckStation, PPSSPP,
RPCS3, Vita3K, Azahar, Cemu, Xenia, xemu, Flycast, shadPS4, SharpEmu. **＋ Add Another Emulator** adds any arbitrary
program.

**Scan for Already Installed Emulators**: at the top of the page, this button performs a quick scan of the PC (taking about 4 seconds),
inspecting standard system locations (Program Files, Winget, Scoop, Steam libraries, and Windows Registry) to find
already present emulators. If found, it offers them with the **Use This** button: no settings are changed
without your confirmation. If an emulator is already installed, the **Install** button will not re-download it.

**Automatic Controller Mapping in Emulators**: for Dolphin, PCSX2, DuckStation, RPCS3, and RetroArch, the app
includes optimal mapping profiles for popular controllers (Xbox XInput, PlayStation DualSense and DualShock 4, Nintendo
Switch Pro). The profile is applied automatically when you install an emulator for the first time, or manually from
**Settings › Controllers › Map Keys in Emulators**. A backup copy of the original configuration file is created prior to
any write operations, and existing custom configurations are never overwritten without prompting.

**Per-Console Emulator**: for each console, choose:

- the **emulator**: *Automatic* uses the first installed among those recommended for that console; *Other…* allows
  any external emulator;
- the RetroArch **core**, if the console uses RetroArch;
- the **arguments**: `{rom}` is the game file, `{core}` is the RetroArch core.

The **Status** column shows what is missing (emulator not found, core missing…). Choices are saved to `settings.json`;
`config.toml` is never overwritten. In `config.toml`, you can specify the same paths under `[emulators]` and
override a console's command under `[launch.<console>]` (see [Reference](riferimento.md)).

![Settings › Emulators: one path per program and the per-console emulator table](../images/impostazioni-emulatori.jpg)

<a id="profilo-di-avvio-di-un-singolo-gioco"></a>
### Launch Profile for a Single Game

In the game details view, **⚙ Launch Profile** customizes how **only that specific game** launches (across all its
versions). Empty fields fall back to the console defaults:

- emulator and RetroArch core;
- alternative executable (e.g. a different version of the emulator);
- arguments replacing the default ones;
- extra arguments, prepended before the game file (e.g. `-f` for fullscreen);
- **pre-launch script** and **post-exit script** (see below);
- **companion app to launch alongside the game**: an executable with its arguments and the option **Close app when game
  exits**. Useful for programs that need to run alongside the game, such as a Hearthstone deck tracker or a stats
  overlay: it launches with the game and, if desired, closes when the game exits.

For PC games, the profile contains the two scripts and the companion app: the game always launches as handled by its
store.

<a id="script-prima-e-dopo-il-gioco"></a>
### Per-Game Automations

In the **⚙ Launch Profile**, the **Automations** section prepares the PC before the game and puts everything back at
the end, even after a crash. On Windows you can set:

- a **command before launch** and **after exit**, with a **working folder** and, if needed, **Wait for it to finish**;
  scripts receive `POZZO_GAME_ID`, `POZZO_TITLE`, `POZZO_PLATFORM`, `POZZO_EXE` and `POZZO_EVENT`;
- **resolution and refresh rate** of the screen;
- **Close these processes before launch** (for example a program that interferes with the game);
- a **power plan** (the plan GUID) and **HDR** on or off while playing (Win+Alt+B).

Scripts that apply to every game (game started, game closed, download finished) live in Settings, next to the ones
described further below.

#### Upscaling with Magpie

The **Upscaling with Magpie** menu enlarges the game running in a fullscreen window with **FSR**, **Anime4K**,
**Integer Scale** or **Lanczos**. It needs Windows 10 1903 or later; Magpie is downloaded from GitHub on first use.
When the game window comes to the foreground Pozzo prepares its profile and starts Magpie in the tray, and at the end
of the session it closes it only if Pozzo opened it.

#### Gamepad Remap

For PC games you can reassign buttons (for example `a=b, b=a, lb=lt`), set the stick deadzone (0-30%), swap the
sticks, invert the Y axis and enable **turbo** (`a:10` = button A at 10 Hz). Pozzo reads the physical pad and forwards
it to a virtual Xbox 360 controller: the **ViGEmBus** driver is required. Without **HidHide** the game may see two
controllers; with HidHide installed the physical pad is hidden during the game and always restored afterwards (if
HidHide is missing, a warning appears).

#### Archives Without a Fixed Extraction

For a PC game or a ROM in `.zip`, `.7z` or `.rar`, the archive option extracts it to a temporary folder on every
launch (after checking free space) and deletes it when the game ends. Files that are new or changed during play, such
as saves and settings, are kept and reapplied at the next launch. If they cannot be saved, the folder stays in place
and the app warns you.

## Pre-Launch and Post-Exit Scripts

In **Settings › Emulators › Game Launch**, you can define two scripts executed for **all games**, console and
PC:

- **Before launch**: for example, to change screen resolution or enable HDR;
- **After exit**: to restore settings to how they were.

A script can be a command or a `.bat` or `.ps1` file. It receives two environment variables: `POZZO_TITLE` (game title)
and `POZZO_KEY` (game key in library), allowing the same script to behave differently for different games.

Each game can also have its own scripts in the **⚙ Launch Profile**: they are executed **after** the global ones.

## Closing the Store Launcher

Also in **Settings › Emulators › Game Launch**, the option **Close store launcher** closes Steam, Epic, GOG Galaxy,
Battle.net, or Amazon Games when gameplay ends, **only if the launcher was opened by the game**: a launcher that was
already open beforehand remains running. The closure happens a few seconds after the game ends, allowing the launcher
to finish syncing cloud saves; Steam is shut down cleanly.

## Desktop Shortcut

In the game details view, **🖥 Desktop Shortcut** creates a desktop shortcut with the game's icon: from the
executable for PC games launched via `.exe`, or derived from the box art otherwise. The shortcut launches the game **via
Pozzo Launcher**: emulator, profile, and scripts still apply, and playtime is recorded just like when launching
from within the app. This is not available for online store games that are not installed.

## Launching a Game

**▶ Play**, `Enter`, or double-clicking the cover art. The app automatically chooses the correct file:

- **disc-based ZIP archives** (e.g. Myrient GameCube games) are extracted automatically before launching;
- for **folder-based games**, the correct file is launched (PS3 → `EBOOT.BIN`, PS5 → `eboot.bin` with SharpEmu,
  Switch → base game file, not an update or DLC);
- if an emulator is missing, the details card clearly indicates it, linking directly to settings.

During gameplay, the **Running** bar shows the active game and lets you terminate it.

### Closing the Game with a Controller

**Select + Start (View + Menu) held for 2 seconds** closes the running game, even while the game is focused in the
foreground, using XInput (Xbox) controllers. Can be disabled with `[app] exit_combo = false`.

### Close Game, Job Object and Pause

On Windows, games started directly by Pozzo are tracked with a **Job Object**: the session ends when the last child
process closes too, so playtime is correct even with executables that relaunch another one, and **Close game**
terminates every process of the game.

**Pause** freezes the running game (like Nyrna) and frees CPU and GPU even for games without their own pause. Use
**Ctrl+Shift+P** (configurable in the screenshot settings), **Select + L1** on the controller, or the **Pause** button
in the game bar, in Big Picture and from the phone. Paused time does not count as playtime, and the game always
resumes at the end of the session. Pause and Job Object are Windows only.

### Splash Screen on Launch

When you press **Play**, the game's image appears at once in fullscreen with the logo and a small loading indicator,
also in Big Picture. It disappears as soon as the game window comes to the foreground (or after 60 seconds, or if the
launch fails). Turn it off in **Settings › Emulators** with **Show a splash screen when games start**. On Windows,
while the game is in the foreground, the Pozzo interface goes idle (animations stopped, audio and video previews
paused) and wakes up when you return to Pozzo.

## Play from Fast Storage

If your library resides on a slow drive (HDD), the game can be copied to an SSD and launched from there for faster
loading times.

In the game details view, **⚡ Play from Fast Storage** is located next to **▶ Play**. The app copies the game (percentage
progress is visible in the **Running** bar), then automatically launches it.

**Where the copy goes**: into the temporary directory chosen in **Settings › Emulators and Launch**, under the **Fast Storage** section; if none is
selected, into the app's cache folder. It is recommended to use an SSD with sufficient free space: at least the size of
the game is required (for PC games, the entire installation folder). If space is insufficient, the app warns you and aborts the copy.
For safety, selecting risky paths like the drive root (`C:\`), the user home folder, or the library folder is blocked.

**After gameplay**: by default, the copy is deleted when you close the game. Disable **Delete copy when closing
game** to reuse it next time without re-copying (if the game changes in the meantime, it will be re-copied).

Warnings:

- for PC games, saves written inside the game folder will be lost with the deleted copy; saves in standard Windows
  locations or managed by the app are safe;
- not available for games launched via an external store or launcher;
- clicking **Close Game** during the copy process cancels it immediately;
- leftover copies on disk after a PC or emulator crash are automatically cleaned up on next launcher launch;
- the mode remains active even after selecting the window in which to launch the game.

## Play in the Browser

Light consoles can be played inside Pozzo with **EmulatorJS**, and Flash games (`.swf`) with **Ruffle**: **Play in
browser** is in the game details, in the right-click menu, in Big Picture and on the phone. The consoles are NES, SNES,
Game Boy, GBA, Mega Drive, Master System, Game Gear, PC Engine, PlayStation, Atari 2600, N64, DS and arcade. The
emulator is downloaded on the first game; saves and states are stored in the user data and included in the backup.
PlayStation needs your own BIOS.

## RetroArch: Bezel, Shader and Cheats

In the details of a RetroArch game, the **RetroArch: bezel, shader, cheats** section lets you pick a **bezel** (from
the libretro overlay-borders repository, downloaded and cached), a **shader** preset among those already in RetroArch,
and **cheats** from the libretro-database with one switch each (**Find cheats**). Choices apply to the game or as the
core default. Pozzo writes only its own keys in the override files and makes a `.pozzo-bak` copy first.

## Reducing PC Game Size

For a PC game installed on Windows, **🗜 Reduce disk space** (right-click menu) compresses the files with Windows
compression. Pick the **algorithm** and press **Compress** (**Decompress** to undo); if the game is in the CompactGUI
database you see an estimate of the savings. If the game uses DirectStorage, it may fail to start or run slower on
compressed files, and Pozzo asks for explicit confirmation.

## Playtime and Sessions

For every game, the app tracks **playtime**, **last played**, and **play count**. A session immediately appears in
*Recently Played* and in *In Progress* state as soon as it starts, from any device (PC, phone, Moonlight); the PC
app detects it within a few seconds.

For PC games launched via a launcher (Steam, Epic…), playtime is recorded by identifying the game process running
in its directory. Steam also supplies its own total playtime, displayed separately.

<a id="mostrare-su-discord-cosa-stai-giocando"></a>
## Showing What You're Playing on Discord

In **Settings › 🧩 Integrations**, you can enable **Discord Rich Presence**: your profile will display *«Playing …»*
with title, console, and session time. All that is required is the **Application ID** — free from
`discord.com/developers/applications` › *New Application* — and the Discord desktop client running.

It uses Discord's **local channel** (`named pipe`): no data leaves your PC, no servers, no secret keys. Images
cannot be displayed because Discord only accepts assets uploaded directly to the developer application and not external web URLs.

![Settings › Integrations: Windows notifications and Discord Rich Presence](../images/impostazioni-integrazioni.jpg)

<a id="partita-con-un-amico"></a>
## Play with a Friend

You can play with a friend without an account and without external servers: create an **invite** (a code or link) and send it to your friend
over Discord, WhatsApp, or any preferred channel.

Supported by **RetroArch** and **Eden**. For other games, use Discord or the store.

- **👥 Play with a Friend**, in the game details: generates the invite to send.
- **👥 I Have an Invite**, at the top: paste the received code and join the game.

### The Invite Message

The **Copy Invite** button copies a ready-to-send message containing the game name, requirements, the `pozzo://join/…` link, and the code. Send it to your friend: they can paste the entire message into **I Have an Invite**. The link opens Pozzo on their PC, but the game never starts automatically without confirmation.

### Where Do You Play?

- **Same network** (home Wi-Fi or LAN cable): no setup required, the app selects the appropriate IP.
- **Over the Internet**: your friend must be able to reach your PC. Open the port on your router: **TCP 55435** for RetroArch, **UDP 24872** for Eden (how to open depends on your router: search "port forwarding" + model). In the app, click **Detect My Public IP**.
- **Free VPN** (Tailscale or ZeroTier): install on both PCs, use the IP assigned by the VPN to your PC; no ports to open.

If unsure, use a VPN.

Warnings:

- the Eden room password is embedded in the invite code: anyone with the code can join while the room is open;
- an opened router port remains exposed: close it when you finish playing;
- your friend must have the exact same version of the game and emulator.

## Playing with a Friend (RetroArch Netplay)

With RetroArch, you can play online with a friend in the same game (netplay, two players). Pozzo requires no external server:
it generates an invite as described in "Play with a Friend".

### Creating the Invite

In the details card of a RetroArch game, **👥 Play with a Friend** asks for your nickname and host PC IP, then launches the game
as host. The code (`POZZO-…`) can be copied and sent as described in "Play with a Friend".

### Joining via Invite

Paste the code into **I Have an Invite**. Upon confirmation, Pozzo launches the same game and RetroArch connects
to the host.

### Requirements

- **Same game, exact same ROM, and same RetroArch core** on both PCs. The game must also be present in the library on the friend's
  PC. If the core differs, Pozzo warns you; if the ROM differs, RetroArch will fail to connect.
- Port is **55435**.
- **In LAN** (same home network), it works directly with the suggested local IP.
- **Over the Internet**: as in "Play with a Friend", on port **55435** (port forwarding to host PC, or
  VPN with the VPN-assigned IP entered instead of the home IP).

### Limitations and Other Platforms

- Works with **RetroArch** and **Eden** (see below). For other emulators, Pozzo suggests **Share Play**
  (streaming via Sunshine and Moonlight), where your friend plays your session remotely.
- With the Discord client running and Rich Presence active (**Settings › 🧩 Integrations**), your profile shows the session
  as "(1 of 2)", since RetroArch netplay handles two players.

### Multiplayer Room with Eden (Nintendo Switch)

For Nintendo Switch games supporting wireless or local multiplayer:

1. **Host**: in game details, click **👥 Play with a Friend**. Pozzo Launcher launches a private room in the background (`eden-room` next to the Eden executable, or `eden --room`) on port **UDP 24872** with a secure random password, then starts the game.
2. **Joining player**: click **👥 I Have an Invite** and paste the code received. Pozzo opens Eden with the *Multiplayer › Direct Connect* tab pre-filled (host IP address, port 24872, and player nickname): simply click **Connect** to join the room instantly.
3. **Close Room**: the host can click **Close Room** at any time to shut down the room server without closing the game.
4. *Requirements*: both players must have the same Eden version and the same Switch game version (including updates).

## Downloading While Playing

In **Settings › Downloads › While Playing**, you can choose how downloads behave when a game launches:
**Continue normally** (default), **Throttle bandwidth** (global download speed drops to the specified KB/s limit,
upload untouched), or **Pause torrents** (an accompanying option also pauses HTTP downloads).

When the game closes, **only** downloads paused by this feature are resumed: downloads paused manually remain
paused. The launcher automatically detects when you are playing, even with PC games started via Steam or Epic.

An individual download can also be scheduled for a specific time: in the row's **⋯** menu, **⏰ Start at…** prompts for the time (`23:30`).
The download remains queued — showing ⏰ with the time — and begins automatically, even across app restarts; the same
menu item becomes **⏰ Cancel Schedule** to remove it. The same optional field exists in the **＋ Add** dialog.

<a id="salvataggi"></a>
## Save Management

In the game details view, **💾 Saves** keeps a **version before and after every play session** (as long as saves do not
exceed 1 GB; beyond that, manual only to avoid filling the disk silently), plus:

- **Backup Now** to create a manual backup;
- **↶ Undo Last Session**, which reverts saves to their pre-session state;
- **Restore** to any version: it backs up current saves first, so you can always revert; restoration replaces
  files from the backup without deleting newer files created since. While a game is running, restoring is locked
  to prevent the emulator from overwriting its files;
- **★** pins a version (never deleted automatically), **✎** adds a note (e.g. "before boss"),
  **Compare** shows which files would change compared to current saves.

The last **20 versions** are kept per game; pinned versions do not count against this limit. Versions are stored in the folder chosen
in **Settings › Library › Game Saves** (default: `<cache>/saves`), in a dedicated folder per game.

When a game shares **files with other games** — such as shared memory cards in PCSX2, DuckStation, Dolphin, or VMUs in
Flycast — the app alerts you: restoring also rolls back saves for the other games sharing that card.

### Where Saves Are Located

Saves are identified per game so backups do not get mixed up:

| Emulator | How saves are identified |
|---|---|
| Eden, yuzu (and suyu, citron) | Title ID in path: `nand/user/save/…/<TITLEID>` |
| Ryujinx | Title ID in first bytes of `ExtraData0` |
| RetroArch | `.srm` and `.state*` matching the ROM name, even in core subfolders |
| Dolphin | `.gci` memory cards (`GC/<region>/Card ?`) and `Wii/title/00010000/<ID>`, plus `StateSaves/` |
| PCSX2 | states `sstates/<serial> (<crc>)`; `.ps2` memory cards are shared |
| DuckStation | memory cards and states named after the game title or serial; `shared_card_*` is shared |
| PPSSPP | `PSP/SAVEDATA/<serial>*` and `PSP/PPSSPP_STATE/<serial>*` |
| RPCS3 | `dev_hdd0/home/00000001/savedata/<TITLEID>*` |
| Vita3K | `ux0/user/00/savedata/<TITLEID>` |
| melonDS | `<ROM>.sav` and `<ROM>.ml*` alongside the ROM |
| Azahar, Lime3DS, Citra | `sdmc/Nintendo 3DS/…/title/00040000/<id>/data` and `states/<TITLEID>.*` |
| Cemu | `mlc01/usr/save/00050000/<id>` |
| Flycast | `<ROM>_vmu_save_*.bin`, `<ROM>.nvmem*` (`vmu_save_*.bin` are shared) |
| shadPS4 | `user/savedata/1/<CUSA…>` |

For **xemu** (single disk image) and **Xenia** (ID cannot be extracted from file), the path must be configured manually.

### Manually Added Paths

If the app does not find the saves, in the **💾 Saves** section you can enter the directory (or file) where the
game keeps them, e.g. `%APPDATA%\Game\Saves`; `%VARIABLE%` environment variables work across Windows, Linux, and
macOS. This applies to **PC games** as well.

After a session, if save paths were unknown, the app prompts you with directories modified while playing:
**These are saves** adds them, **Ignore** dismisses the suggestion.

### PC Games: Ludusavi Manifest Locations

For PC games, save locations are sourced from the **Ludusavi manifest** (over 50,000 games, updated weekly, downloaded
in background once a week). The app identifies games by Steam or GOG ID, title, or install directory, and only backs
up files marked by the manifest as game saves. Windows Registry keys are not managed: in such cases, the path must be added manually.

### Backup Format: Ludusavi Compatible

Versions are stored in **Ludusavi format**: each game has a folder containing `mapping.yaml` and `backup-<date>.zip`
files, containing original paths, SHA-1 hashes, and file sizes. By choosing the **same folder** as Ludusavi
(*Backup mode › Backup target*) in **Settings › Library › Game Saves**, both applications can view and restore each
other's backups. Only **complete** backups are displayed (Ludusavi differential backups are not supported). Backups made
in the previous format are automatically converted on first launch.

For PC ports, files in the port directory that do not originate from the release are backed up. Save backups can be
disabled with `[app] save_backups = false`.

## Screenshots

After each session, the app imports screenshots captured by the emulator (Ryujinx, Eden and forks, and other
supported emulators). For Eden, it searches the default `%APPDATA%\eden\screenshots`, the portable
`user\screenshots` next to the exe, and custom paths read from `qt-config.ini`. Screenshots can be browsed
in the **📷 Screenshots** view and can also be triggered from your phone.

### In-game overlay

During a session (Windows) **Ctrl+Shift+O** or **Select + R3** on the controller open an overlay on top of the game with
the session timer, screenshot, pause, "Close game", achievements, notes from the Diary extension (if installed) and music
controls. Close it with the same key, **Esc** or **B**; focus returns to the game. Change the shortcut in the screenshot
settings. The overlay works with windowed and borderless-fullscreen games: **it cannot be drawn over exclusive fullscreen games**.

### Live achievements

For Steam games run with a Steam emulator, Pozzo watches the achievement files of Goldberg/GSE
(`%APPDATA%\Goldberg SteamEmu Saves`), EMPRESS, CODEX and RUNE during the session and shows an alert for each new unlock.
Name and icon come from the Steam schema if you set an API key; otherwise the cleaned-up id is used. Alerts and sound are set
in the screenshot settings (⚙). RPCS3, SmartSteamEmu and CreamAPI are not supported.

## RetroAchievements

In **Settings › Stores › RetroAchievements**, enter your username and Web API key. Retro game details cards will display
**unlocked achievements**, completion percentage, and icons.

Game matching:

1. by **hash**: the MD5 is already known from the No-Intro DAT, working even for `.zip` ROMs and localized
   versions (which have English titles on RetroAchievements);
2. otherwise by title, canonical name, or filename.

Cache: catalog 7 days, matches 30 days, progress 30 minutes.

### Eden (Switch)

With Eden, multiplayer sessions run through Eden's **rooms**: local wireless Switch gameplay travels over the Internet, so
it only works with games supporting local wireless play. The invite code is identical.

- **Host**: in **👥 Play with a Friend → Create Invite**, Pozzo launches the room (private, with password embedded in code,
  port **UDP 24872**) and the game, closing them together with Pozzo. **Close Room** stops it without closing the game.
  The room requires `eden-room.exe` next to `eden.exe` (or an Eden version supporting `eden --room`).
- **Friend**: paste code as in "Play with a Friend". Pozzo populates **Multiplayer › Direct Connect** with address,
  port, and nickname, and launches the game: in Eden, simply click **Multiplayer › Direct Connect › Connect**, then enter the game's local multiplayer mode.
- Port **UDP 24872** (outside local network: port forwarding or VPN, as in "Play with a Friend"). Requires the identical
  game on both PCs. Close Eden before joining, otherwise Pozzo cannot prefill fields.
