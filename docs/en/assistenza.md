# Help Center and Frequently Asked Questions (FAQ)

Welcome to the **Pozzo Launcher Help Center**. This guide is designed to quickly address your questions, walk you step-by-step through troubleshooting common issues, and help you get the most out of every feature in the application.

---

## 🔍 What are you looking to do?

Select the topic you need help with:

| Category | Description |
|---|---|
| [📁 ROMs, Folders, and Covers](#roms-folders-and-covers) | Configure ROM folders, identify games, and fix missing artwork or titles |
| [🎮 Launching Games and Emulators](#launching-games-and-emulators) | Troubleshoot game launches, configure emulators, and set custom parameters |
| [⬇️ Downloads, Torrents, and Debrid](#downloads-torrents-and-debrid) | Integrated download manager, protected link resolver, torrents, and Debrid accounts |
| [👥 Multiplayer and Play with a Friend](#multiplayer-and-play-with-a-friend) | Online netplay with RetroArch, Eden Switch private rooms, and port configuration |
| [📱 Phone, Remote, and Dual Screen](#phone-remote-and-dual-screen) | Pairing your smartphone, HTTPS certificate, DS/3DS touchscreen, and controller |
| [💾 Saves, Versions, and Backups](#saves-versions-and-backups) | Restoring previous save states, syncing across two PCs, and using Ludusavi |
| [💻 PC Games, Stores, and Web Games](#pc-games-stores-and-web-games) | Integrating Steam, Epic, GOG, Riot, Battle.net, and adding browser or .exe games |
| [🎨 Appearance, Themes, and Big Picture](#appearance-themes-and-big-picture) | Selecting themes, switching experience profiles, and couch gaming on TV |
| [🛠️ Diagnostics, Ports, and Error Troubleshooting](#diagnostics-ports-and-error-troubleshooting) | Health screen, occupied ports 8765/8766, and locked files |

---

## 📁 ROMs, Folders, and Covers

![The Game Boy Advance console with over 5,000 organized games and complete metadata](../images/console.jpg)

### Where should I put my ROMs to make them appear in the app?
**Answer:** You don't need to move your ROMs if you already have them organized!  
1. Go to **Settings › Library › ROM Folders**.
2. Click **＋ Add folder** and select the root folder containing your game collections (e.g. `E:\Roms`).
3. Pozzo Launcher automatically recognizes subfolders matching standard console names (e.g. `gba`, `snes`, `psx`, `switch`, `nds`, `n64`, `megadrive`, etc.).
4. Alternatively, you can add a dedicated folder for an individual console by mapping it directly from the dropdown menu.
5. Click **⟳ Scan for new games** at the top: newly detected games will appear instantly in the corresponding console's sidebar!

If you copy a ROM into a console folder while the app is open, it appears automatically within about ten seconds (can be toggled in **Settings › Library › New Games**; deleted files can be purged with **↻ Recheck folders**).

---

### Why is a ROM not recognized or missing its cover art?
**Answer:** Pozzo Launcher identifies games using a combination of digital checksums (CRC32, MD5, SHA-1 of the file or partition) and intelligent filename cleaning:
- **Check the filename**: Clean filenames such as `Pokemon - FireRed Version.gba` or No-Intro scene conventions are identified immediately. Names with unusual characters or cryptic abbreviations may fail to match.
- **Compressed archives**: `.zip` and `.7z` archives are supported for classic consoles. For Nintendo Switch, `.nsp`, `.xci`, and `.nsz` formats are supported.
- **Try manual search**: Right-click on the game and select **🖼 Game Images…**: you can upload an image from your PC, pick one from SteamGridDB, or paste an image URL from the web.
- **Check the ? Missing Data view**: In the sidebar, click **? Missing Data** to view all games requiring verification and run **⟳ Search missing data** exclusively for them.

![The Missing Data view: groups all games requiring attention or manual metadata](../images/libreria-senza-dati.jpg)

---

### How does offline scraping work for Nintendo Switch?
**Answer:** If you own a Nintendo Switch and have configured your `prod.keys` file in `config.toml` (key `switch_keys = "C:/path/to/prod.keys"`), Pozzo Launcher reads official metadata (title, publisher, game version, and native-resolution icon) **directly from inside the `.nsp` or `.xci` file**, without requiring any Internet connection!

---

## 🎮 Launching Games and Emulators

![Settings › Emulators: executable paths and console association table](../images/impostazioni-emulatori.jpg)

### I click "Play" but the game or emulator does not open: what should I do?
**Quick answer:** In 95% of cases, the emulator has not yet been configured or the executable path is incorrect.

Follow this troubleshooting checklist:
1. Open **Settings › Emulators**.
2. Check whether the row for the emulator you intend to use (e.g. *DuckStation*, *PCSX2*, *Dolphin*, *Ryujinx*, *RetroArch*, *melonDS*) displays a green checkmark with the path to the executable filled in (e.g. `C:\Emulators\Duckstation\duckstation-qt-x64-ReleaseLTCG.exe`).
3. If the path is empty, click **Search PC**: Pozzo Launcher will scan standard Windows paths, registry entries, and user folders.
4. If you use a portable build, click **Browse…** and select the `.exe` file directly.
5. In the table below, verify that the console (e.g. `psx`) is assigned to the desired emulator (*DuckStation*).

---

### Can I use special launch arguments or run pre/post-game scripts?
**Answer:** Absolutely!
- **Globally per emulator**: In **Settings › Emulators › Game Launching**, you can specify pre-game and post-game commands (e.g., enabling an HDR color profile, turning on ambient LED lighting, or disabling secondary monitors).
- **Per game**: Open the game detail card, click the **⚙ Launch Profile** icon, and configure title-specific parameters (such as an alternate RetroArch core or custom resolutions).

---

## 📱 Phone, Remote, and Dual Screen

![The mobile web app: Home, PC games, remote control, and virtual gamepad](../images/telefono.jpg)

### How do I connect my smartphone to the application?
**Answer:** No app download from the Google Play Store or Apple App Store is required: Pozzo Launcher features a high-performance Progressive Web App (PWA):
1. On your PC, navigate to **Settings › 📱 Phone and Streaming**.
2. Toggle on **Phone Access**.
3. Scan the **Pairing QR Code** displayed on screen using your smartphone's camera.
4. The 6-digit code securely pairs your phone to your PC without exposing it externally.
5. Tap **Add to Home Screen** (or Install) to run it like a native full-screen app!

![Settings › Phone and Streaming: certificate, QR code, and paired device management](../images/impostazioni-telefono.jpg)

---

### Why does the mobile browser show "Connection is not private" or prevent installing the app?
**Answer:** This is completely normal: your PC generates a local self-signed HTTPS security certificate (required to enable gyroscope motion sensors and haptic feedback without routing through third-party servers).

**How to resolve in 1 minute:**
- **On Android**: Scan the **🔒 PC Certificate** QR code in *Settings › Phone and Streaming* (or download `PozzoLauncher-CA.crt`), open it in *Settings › Security › Encryption & credentials › Install a certificate › CA Certificate*, and tap "Install anyway".
- **On iPhone/iPad (Safari required)**: Download the certificate, open *Settings › Profile Downloaded › Install*. Then navigate to *Settings › General › About › Certificate Trust Settings* and toggle on "Pozzo Launcher CA". Return to Safari, and the security warning will be permanently resolved!

---

### How does "Dual Screen" work for Nintendo DS and Nintendo 3DS?
**Answer:** This is one of Pozzo Launcher's standout features:
- When you launch a Nintendo DS game (via *melonDS*) or Nintendo 3DS game (via *Citra* or *Azahar*), if your smartphone is connected:
  - **On your PC**, you see the primary top screen in full high-definition.
  - **On your phone**, you see the lower screen and can interact with touch gestures just like the console's physical touchscreen!
- If your phone disconnects or goes to sleep, the app instantly restores the secondary screen on the PC in Picture-in-Picture mode without interrupting gameplay.

---

## 💾 Saves, Versions, and Backups

![Settings › Library: cross-PC synchronization, export, and backups](../images/impostazioni-libreria.jpg)

### The game crashed or I accidentally overwrote my save: can I recover it?
**Answer:** **Yes, in a single click!**  
Pozzo Launcher automatically creates timestamped backups of your save files **before** each launch and **after** each session closes:
1. Open the game card in your library.
2. Scroll to the **Saves** section.
3. Click **⏮ Undo last session**: the app will instantly revert your save files to their state prior to launching the last session.
4. You can also view the version history log, pin a favorite version with a note (e.g. *"Before final boss"*), or diff files.

---

### How do I sync games between a desktop and laptop without paid cloud services?
**Answer:** You can choose between two built-in synchronization modes:
1. **Shared folder**: If you use OneDrive, Google Drive, Syncthing, Dropbox, or a network NAS folder, select that folder in *Settings › Library › Cross-PC Synchronization*. Favorites, playtime (merged without overwriting), ratings, and collections will stay synchronized in the background.
2. **Direct local network (Zero Cloud)**: If both PCs are connected to the same local Wi-Fi or LAN, click **Generate pairing code** on PC A and enter the code on PC B. The two computers will communicate directly via local HTTPS secured by SHA-256 fingerprint validation!

---

## 💻 PC Games, Stores, and Web Games

![PC games from official stores: Steam, Epic, GOG, Riot, and Battle.net](../images/store-pc.jpg)

### Which PC stores are natively supported?
**Answer:** Pozzo Launcher discovers and catalogs installed and owned games in real time from:
- **Steam** (including multi-account support, manifest reading, and VDF parsing)
- **Epic Games Store**
- **GOG Galaxy**
- **Riot Games** (League of Legends, Valorant, Teamfight Tactics, Runeterra)
- **Battle.net** (Hearthstone, Overwatch 2, Diablo, WoW with fast client monitoring)
- **Amazon Games** and **Xbox / Game Pass**
- **Minecraft**

---

### Can I add a browser game via URL (e.g. Chess.com, Wordle)?
**Answer:** Absolutely!
1. Click **＋ Add game** in the top navigation bar or menu.
2. Choose **Web Browser Game (URL)**.
3. Paste the URL (e.g. `https://www.chess.com/play/online`).
4. Pozzo Launcher automatically fetches the title, description, and Open Graph banner image from the page, validating and protecting against unsafe local addresses.
5. The game appears in your PC library and launches in your default browser in full-screen mode!

---

### DLCs or updates appear as separate entries: how can I group them?
**Answer:**
- In the top bar of the console or store view, toggle the **Hide DLC** checkbox: all supplemental content will be filtered out from the main grid and neatly grouped inside the base game's detail view under **Installable DLC and updates**!

---

## 🎨 Appearance, Themes, and Big Picture

![Settings › Appearance: theme selection and experience profile gallery](../images/impostazioni-aspetto.jpg)

### What graphical themes are available?
**Answer:** In **Settings › Appearance**, you can choose between 4 meticulously crafted color palettes:
1. **OLED (Absolute Black)**: High contrast, ideal for OLED displays and late-night sessions.
2. **Night Blue**: Relaxing indigo and dark navy tones for optimal visual comfort.
3. **Retro**: Warm nostalgic tones inspired by 80s and 90s arcade cabinets.
4. **Light**: Modern, clean, and bright styling perfect for well-lit rooms and offices.

---

### What are the 6 desktop "Experience Profiles"?
**Answer:** Unlike themes (which only adjust colors), an experience profile reorganizes the layout and flow of the desktop UI to suit your preferred gaming style:
- **Shelves**: Streaming-style horizontal rows for jumping right back into recently played titles.
- **Cinema**: Immersive layout featuring dynamic background art and cinematic details.
- **Console**: Fullscreen arrow-key driven layout designed for lean-back navigation.
- **Dashboard**: Compact view packed with widgets, statistics, and quick recommendations.
- **Showcase**: Highlights the most prestigious cover art in your collection.
- **Catalog / Original**: Classic high-density grid view with sidebar navigation for dedicated collectors.

---

### How do I play on my TV using a controller (Big Picture Mode)?
**Answer:**
- Press `F11` or click the **Fullscreen / Big Picture** icon in the header bar.
- The interface adapts instantly to 16:9 and 4K displays with large typography, responsive controller D-Pad navigation, and tactile UI audio for couch gaming comfort!

![Big Picture: TV mode for controller navigation from the couch](../images/bigpicture.jpg)

---

## ⬇️ Downloads, Torrents, and Debrid

### How does the integrated download queue work?
**Answer:** Clicking on **⬇ Downloads** in the sidebar or Activity panel opens a comprehensive management table to monitor transfers:
- Click table headers to sort by name, size, download speed, or estimated time of arrival (ETA).
- Right-click any row to pause, force resume, or adjust file priority.
- Double-click a row to open the inspector panel with real-time logs for each resolution step and headless browser stage.
- When launching a game, **Game Mode** automatically throttles or suspends downloads to ensure lag-free gaming performance.

---

### What should I do if a download stalls or the host requires a captcha?
**Answer:** Many hosting services (FileKeeper, DataNodes, etc.) employ countdown gates or challenge protections that the integrated browser handles automatically. If a host requires manual verification (such as a Cloudflare Turnstile or captcha challenge):
1. Navigate to **Settings › Downloads**.
2. Enable the **"Show browser while resolving links"** toggle.
3. Retry the download: a visible browser window will appear, allowing you to complete the captcha or click required verification buttons. Once resolved, the launcher captures the final link, launches multi-segmented downloads, and closes the browser window.

---

### How do I configure a Debrid service (Real-Debrid, AllDebrid, TorBox, etc.)?
**Answer:**
1. Navigate to **Settings › Downloads › Debrid Services**.
2. Enter your API key or account token (Real-Debrid, AllDebrid, Premiumize, TorBox, Debrid-Link).
3. Click **Verify**: the launcher verifies key validity and securely saves it encrypted on your machine.
4. From that point on, supported filehost and torrent links are unrestrictedly downloaded at maximum line speed through Debrid cloud servers, bypassing free host wait times and speed limits.

---

## 👥 Multiplayer and Play with a Friend

### How do I play online multiplayer with a friend using RetroArch or Eden Switch?
**Answer:** Pozzo Launcher features native out-of-the-box support for **"Play with a Friend"** without requiring dedicated server setups or account registrations:
1. In the game card, click **👥 Play with a friend**: Pozzo generates an invite code and shareable link ready to paste into Discord, WhatsApp, or Telegram.
2. Your friend opens Pozzo on their PC, clicks **👥 I have an invite**, and pastes the code.
3. **RetroArch**: Launches a peer-to-peer 2-player netplay session (requires matching ROM and core). With Discord open, Rich Presence displays the match as "(1 of 2)".
4. **Eden (Nintendo Switch)**: The app launches Eden's private room daemon (eden-room, UDP port 24872) in the background with a random room password, automatically prepopulating the connection parameters under *Multiplayer › Direct Connect* on your friend's PC. They simply click *Connect*.
5. **Other emulators**: If an emulator lacks native netplay, Pozzo provides **Share Play** via Sunshine and Moonlight to stream the game from your PC and assign a virtual second controller to your friend!

---

### What network ports need to be forwarded on my router to play over the Internet?
**Answer:**
- **On a local network (same house or Wi-Fi)**: Zero port forwarding is required.
- **Using a free virtual LAN (Recommended)**: Install **Tailscale** or **ZeroTier** on both PCs. No router configuration is necessary, and all traffic is end-to-end encrypted.
- **Direct Internet connection (Port Forwarding)**:
  - For **RetroArch**: Forward **TCP 55435** to your local PC IP address;
  - For **Eden Switch**: Forward **UDP 24872** to your local PC IP address;
  - Use the **"Detect my public IP"** button in the app before sending the invite.

---

## 🛠️ Diagnostics, Ports, and Error Troubleshooting

![The Health page: automatic diagnostics for paths, databases, and services](../images/impostazioni-salute.jpg)

### What should I do if I see "Port 8765 or 8766 already in use"?
**Answer:** This occurs if a previous instance of Pozzo Launcher remained running in the background or another application is bound to those ports.
1. Check the Windows notification area / system tray near the clock: if the Pozzo Launcher icon is present, right-click and select Quit.
2. If necessary, open Windows Task Manager (`Ctrl + Shift + Esc`), check for remaining `pozzo.exe` or `python.exe` processes, and select *End task*.
3. Alternatively, you can change the default server port in `config.toml` (e.g. `port = 8780`).

---

### How can I check overall app health using the "Health" screen?
**Answer:** Open **Settings › 🩺 Health**:
- Pozzo Launcher executes real-time system diagnostics:
  - Integrity of SQLite databases (`library.db` and `userdata.db`)
  - Validity of configured ROM directories and emulator executables
  - Service status of the local desktop server and mobile companion server
  - Sunshine streaming service and ViGEmBus virtual controller driver status
- If an issue is discovered, an actionable green **Resolve** button is displayed with clear steps to fix it in a single click.

---

### What do the descriptive error messages mean?
**Answer:** Recent versions of Pozzo Launcher replace vague errors like "Internal Server Error" or "Failed to fetch" with contextual root-cause diagnoses and immediate solutions:
- **Database schema version mismatch**: Advises opening Settings and clicking *Rebuild library*.
- **File or folder not found**: Highlights the exact missing storage path.
- **Permission denied or disk full**: Warns of insufficient storage capacity or missing write permissions on directories.
- **Network unreachable**: Clearly differentiates between lack of Internet connection, host timeout, or firewall blocks.

> [!TIP]
> Have a question not answered in this guide? Check the [Full Command Reference](riferimento.md) or visit the official community on the Pozzo Launcher GitHub repository!
