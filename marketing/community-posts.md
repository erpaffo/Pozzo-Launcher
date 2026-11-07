# Pozzo Launcher — Community Copywriting & Launch Kit

> **Guida d'uso per il team / maintainer**:  
> Questa cartella contiene tutti i testi pronti per la pubblicazione su community verticali, forum e directory software.  
> Il tono di voce adottato è **autentico, trasparente e da sviluppatore/appassionato open-source**. Nessun linguaggio commerciale o televendita: su Reddit, Hacker News e GBAtemp l'autopromozione aggressiva genera diffidenza e downvote immediati, mentre l'onestà tecnica e il rispetto del tempo degli utenti creano fiducia e passaparola organico.

---

## Indice dei Contenuti
1. [Reddit Posts](#1-reddit-posts)
   - 1.1 [r/emulation](#11-remulation--angolo-tecnico--integrità-dei-dati)
   - 1.2 [r/SteamDeck & r/ROGAlly](#12-rsteamdeck--rrogally--angolo-handheld--couch-gaming)
   - 1.3 [r/retrogaming & r/roms](#13-rretrogaming--rroms--angolo-collezionismo--accuratezza-metadata)
   - 1.4 [r/italygames](#14-ritalygames--angolo-sviluppo-indie-italiano--open-source)
2. [Hacker News (Show HN)](#2-hacker-news-show-hn)
   - 2.1 [Titolo & Testo del Post](#show-hn-post)
   - 2.2 [Risposte Preparate ai Commenti Tipici](#risposte-preparate-per-hacker-news)
3. [GBAtemp Thread](#3-gbatemp-thread)
   - 3.1 [Versione Markdown](#gbatemp-versione-markdown)
   - 3.2 [Versione BBCode per Editor XenForo](#gbatemp-versione-bbcode-pronta-al-copia-incolla)
4. [Product Hunt & AlternativeTo](#4-product-hunt--alternativeto)
   - 4.1 [Product Hunt Kit](#product-hunt-kit)
   - 4.2 [AlternativeTo Kit](#alternativeto-kit)

---

# 1. Reddit Posts

---

### 1.1 r/emulation — Angolo Tecnico & Integrità dei Dati

**Strategia di pubblicazione:**
- *Focus:* Nessuna chiamata API a vuoto, identificazione istantanea con DAT No-Intro / Redump offline, gestione multi-regione senza doppioni fittizi, rispetto dell'I/O su HDD di grandi dimensioni.
- *Tag/Flair raccomandato:* `Release` o `Software / Tool`.
- *Link diretti:* Solo GitHub Releases e Documentazione tecnica (nessun link tracking o monetizzato).

#### Titolo Raccomandato:
> **I got tired of scrapers hitting API limits on massive ROM sets, so I built an offline-first launcher that matches No-Intro/Redump DATs locally (Pozzo Launcher)**

*Titolo Alternativo:*
> **Pozzo Launcher: an open-source game & ROM frontend that identifies sets offline via No-Intro/Redump DATs before making a single web call**

#### Corpo del Post (Markdown):
```markdown
Hi r/emulation,

Like many of you, I have an extensive ROM collection spread across multiple platforms and storage drives. Every time I set up a new frontend or rebuilt my library, I ran into the same bottlenecks: scrapers taking dozens of hours, hitting ScreenScraper/IGDB hourly quotas, getting temporarily IP-banned, or thrashing mechanical hard drives reading gigabytes of ISOs and ZIPs just to calculate checksums.

Over the past months, I’ve been building **Pozzo Launcher**, an open-source, local-first game organizer and launcher designed to treat data integrity and scraper performance as first-class citizens.

Here is how the matching pipeline works under the hood:

### 1. Offline Identification Before Any Web Request
Instead of blind online scraping, Pozzo checks your ROM files against local No-Intro and Redump DATs first:
- **Exact File Name Match:** If your file name matches the official DAT entry, CRC, MD5, and SHA1 are pulled instantly from the offline database. **The physical file isn't even touched on disk.**
- **Fast ZIP Header Inspection:** For zipped ROMs not recognized by name alone, it reads the internal CRC directly from the ZIP central directory header without decompressing the payload.
- **Smart I/O Throttling:** For loose disk dumps or unfamiliar files, reads are performed in 8MB chunks with separate concurrency profiles optimized for SSDs vs HDDs (`disk`, `io_workers`). Files above 512MB skip byte-level hashing by default to prevent drive thrashing.
- **Real-world test:** On a real collection of 14,782 DS games on a mechanical HDD, the raw data read from disk dropped from **149 GB down to 3.6 GB**.

### 2. Cascading Pipeline & Quota Protection
When online metadata is genuinely needed (descriptions, reviews, community ratings):
- It supports **LibRetro DATs**, **LaunchBox Community offline database (~110MB weekly dump)**, and **TheGamesDB offline dump** locally on disk, completely eliminating network calls.
- For online APIs (IGDB, ScreenScraper, RAWG, ArcadeDB, Steam), queries run in asynchronous parallel queues with built-in token-bucket rate limiters.
- A **pre-scan estimator (`📊 Stima`)** calculates the exact number of HTTP requests, projected time, and daily quota consumption before you execute a scrape.
- Every state is persistently committed to a local SQLite database (`cache/cache.db`). If your network drops or you stop the scan, it resumes right where it left off with zero wasted quota.

### 3. Multi-Region Merging (1G1R without destructive filtering)
Rather than deleting or hiding your non-primary region ROMs, Pozzo groups regional variants (USA, Europe, Japan, World) into a single clean game entry. You can switch the active default launch version directly from the game's detail view without cluttering your library view with 4 duplicates of the same title.

### 4. Switch & Disk Formats
- Switch files (`.nsp`, `.xci`, `.nsz`, `.xcz`) are parsed directly via your local `prod.keys` (located automatically from Ryujinx, yuzu, or Eden directories). Title ID, version, DLC count, and embedded 256x256 icons are extracted in milliseconds without external scraping. Truncated FAT32 splits are detected and flagged.

### Specs & Privacy:
- **Zero telemetry**, zero account requirement, no central server.
- Built with Python (FastAPI local runtime + native lightweight webview frontend).
- Cross-platform: Standalone executables for Windows 10/11, Linux (.deb / tar.gz), and macOS (Apple Silicon).
- License: Open Source (MIT).

Code & Releases: https://github.com/erpaffo/Pozzo-Launcher  
Technical documentation: https://erpaffo.github.io/Pozzo-Launcher/

I'd love feedback from people with heavy collections. If you have custom naming schemes, weird DAT setups, or edge-case platform setups, let me know how it performs!
```

#### Primo Commento di Approfondimento (OP FAQ):
```markdown
A few quick answers to expected questions:

**Q: Does it replace retroarch / standalone emulators?**  
No, it's a frontend launcher. You map your preferred emulators (RetroArch cores, PCSX2, RPCS3, Dolphin, DuckStation, Ryujinx, etc.) or PC executables, and Pozzo launches them with proper command-line arguments. It also exports cleanly to ES-DE (EmulationStation-DE) and Pegasus if you ever want to sync metadata.

**Q: Where does the cache live?**  
Everything stays in `%LOCALAPPDATA%\PozzoLauncher` (Windows), `~/.local/share/PozzoLauncher` (Linux), or `~/Library/Application Support/PozzoLauncher` (macOS). The database is standard SQLite in WAL mode.

**Q: What about PC games?**  
It imports installed Steam, Epic, GOG, Amazon, Battle.net, and Xbox games side-by-side with your ROMs, plus any manual `.exe` or batch script.

**Q: How does it handle multi-disc games?**  
It recognizes `.m3u` playlists natively, as well as multi-disc CHD/cue sets (`(Disc 1)`, `(Disc 2)`), grouping them into a single playable item.
```

---

### 1.2 r/SteamDeck & r/ROGAlly — Angolo Handheld & Couch Gaming

**Strategia di pubblicazione:**
- *Focus:* Navigazione completa con controller (D-Pad / analogici), modalità Big Picture fluida, layout Cinema e Vetrina (Showcase), companion app su smartphone per telecomando e giroscopio, integrazione con PC streaming (Sunshine / Moonlight).
- *Tag/Flair raccomandato:* `Guide/Tips` o `Software`.

#### Titolo Raccomandato:
> **I created Pozzo Launcher: a lightweight, controller-first game frontend with Cinema/Showcase layouts and a phone companion app (remote control + gyro)**

*Titolo Alternativo:*
> **Looking for a clean Big Picture frontend for Steam Deck / ROG Ally? Pozzo Launcher combines ROMs & PC libraries with full gamepad navigation and remote launch**

#### Corpo del Post (Markdown):
```markdown
Hey everyone,

If you use your Steam Deck (in desktop/handheld mode) or ROG Ally / Legion Go docked to a TV or on the couch, you know the struggle: many frontend launchers are either too cluttered with micro-text, feel like desktop spreadsheets, or require cumbersome trackpad navigation to tweak settings.

I built **Pozzo Launcher**, an open-source library manager and frontend designed specifically to bridge high-density PC management with a 10-foot couch gaming experience.

Here are the features tailored for handhelds and TV setups:

### 🎮 Big Picture Mode & Controller-Native UI
- **Full Gamepad Navigation:** Navigate your entire catalog, filter by platform, search, and launch games using standard D-pad/analog stick and face buttons. No mouse emulation required.
- **Dedicated Layouts for Big Screens:**
  - **Cinema Layout:** Huge backdrop art, media previews, and prominent synopsis text readable from across the living room.
  - **Showcase (Vetrina):** An arcade/console style carousel that puts game cover art front and center with minimal interface distraction.
  - Plus 5 other desktop-friendly layouts (Catalog, Shelves, Console, Dashboard, Original) and themes including an authentic **OLED Black** theme to save battery on OLED displays.

### 📱 Phone Companion App (Zero Installation)
Pozzo has a built-in local companion server:
- Scan a QR code on your screen with your smartphone (Android or iOS).
- **Remote Library Browser:** Browse your entire library from the phone in your hand, view achievements and play times, and tap to launch directly on your Deck or handheld.
- **Virtual Controller & Gyroscope:** Use your smartphone screen as an extra controller or air-mouse, including hardware gyroscope forwarding.
- **Streaming Ready:** Deep integration with Sunshine and Moonlight if you stream heavier titles from your main desktop rig to your handheld.

### ⚡ Handheld-Friendly Resource Footprint
- Background file scanning automatically detects when a game process is running and idles its I/O threads so you never experience stutter or dropped frames during gameplay.
- Fast resume: SQLite WAL caching ensures immediate startup without 30-second parsing loops on 10,000+ item libraries.
- Supports Steam, Epic, GOG, and standalone emulators in one consolidated grid.

### Installation on Deck / Handheld:
- Linux: Standalone `.deb` package or portable `tar.gz` (runs easily in SteamOS Desktop mode, and you can add the executable to Steam as a Non-Steam Game with Proton turned off since it runs natively).
- Windows: Single portable `.zip` or setup installer for ROG Ally / Legion Go / Windows handhelds.
- 100% Free & Open Source under the MIT license, no telemetry, no subscription tiers.

GitHub: https://github.com/erpaffo/Pozzo-Launcher  
Screenshots & Docs: https://erpaffo.github.io/Pozzo-Launcher/

Feedback and suggestions for handheld-specific hotkeys or layout tweaks are very welcome!
```

#### Primo Commento di Approfondimento (OP FAQ):
```markdown
Adding a few practical setup tips for handheld users:

**How to add it to Steam on SteamOS (Steam Deck):**
1. Switch to Desktop Mode.
2. Download the Linux portable `.tar.gz` from GitHub Releases, extract to a folder (e.g. `~/Games/PozzoLauncher`).
3. Open Steam > *Add a Non-Steam Game* > Browse to `PozzoLauncher`.
4. Return to Gaming Mode. It runs natively on Linux without Proton compatibility layers.

**How does the phone pairing work?**
Go to Settings > Phone. It displays a local QR code with a self-signed HTTPS certificate (or local HTTP on your LAN). No external third-party cloud service or account creation is involved; your device communicates straight over your Wi-Fi network.

**Does it interfere with Steam Deck controls?**
In Game Mode, you can use the standard Gamepad template. In Desktop Mode or Windows handhelds, it supports direct XInput/DirectInput gamepad inputs.
```

---

### 1.3 r/retrogaming & r/roms — Angolo Collezionismo & Accuratezza Metadata

**Strategia di pubblicazione:**
- *Focus:* Scraping maniacale ma pulito, supporto a 3D boxart, wheel logos, marquee, manuali PDF, zero inquinamento di file fittizi, deduplicazione intelligente delle versioni regionali.
- *Tag/Flair raccomandato:* `Community Project` o `Resource`.

#### Titolo Raccomandato:
> **Built an open-source launcher for retro preservation: accurate offline No-Intro/Redump scraping, 3D boxes, multi-region grouping, and zero metadata clutter**

*Titolo Alternativo:*
> **Pozzo Launcher: an open-source ROM organizer built to respect retro collection integrity (offline DATs, high-res boxart, no duplicate region spam)**

#### Corpo del Post (Markdown):
```markdown
Hello fellow retro gamers and digital archivists,

If your retro collection looks like mine, you've likely spent years curating full No-Intro sets, Redump ISOs, and custom translations. The biggest pain point with modern game frontends is how they handle pristine collections:
- They flood your visual grid with 5 regional clones of the same cartridge (USA, Europe, Japan, Revision 1, Revision 2).
- They pollute folders with weird `.nfo` files or miss titles entirely because the online scraper relies on fuzzy search against crowd-sourced web APIs.
- They choke on large disk-based platforms (PSX, PS2, Saturn, Dreamcast).

I created **Pozzo Launcher** with a strong focus on retro preservation and metadata fidelity.

### What makes it tailored for collectors:
1. **Accurate DAT-First Identification:**
   Games are matched against verified No-Intro and Redump DAT files. If you have clean dumps, they are recognized with 100% precision with zero false matches. BIOS files (`[BIOS]`) are automatically detected and kept hidden so they don't pollute your game catalog.

2. **Unified Multi-Region Entries:**
   Instead of viewing *Super Mario World (USA)*, *Super Mario World (Europe)*, and *Super Mario World (Japan)* as three separate catalog items, Pozzo consolidates them into a single primary entry. You can pick your preferred primary region (e.g., Europe for 50Hz/languages or USA for 60Hz), and access all alternative dumps from a neat drop-down on the game's page.

3. **High-Fidelity Media & Artwork:**
   - 3D Boxart, front covers, spine art, cartridges/discs, marquee banners, and arcade wheels.
   - Sources include LibRetro databases, LaunchBox Community dumps, ScreenScraper, TheGamesDB, and ArcadeDB.
   - You can define strict field-level priorities (e.g. use European cover art when available, but English synopsis, and community rating from LaunchBox).
   - Support for game manuals, release notes, and community play logs.

4. **100% Local, Offline & Exportable:**
   Your collection stays yours. All metadata, cover art, and play stats are stored in an unencrypted, locally-accessible SQLite database and media cache folder. Need to export your curated setup to a handheld running EmulationStation-DE or Pegasus? Pozzo includes one-click export utilities.

5. **Seven Visual Layouts:**
   From a virtual retro game store shelf view to a clean minimalist catalog, and an authentic 90s CRT-styled Retro theme.

It is completely free, open-source (MIT), and contains zero telemetry or tracking code.

- Project Repository: https://github.com/erpaffo/Pozzo-Launcher  
- User Manual: https://erpaffo.github.io/Pozzo-Launcher/

Would love to hear your thoughts and suggestions for any niche retro platforms you'd like to see better supported!
```

#### Primo Commento di Approfondimento (OP FAQ):
```markdown
Quick note on supported media types and sources:

- **LaunchBox Local DB & TheGamesDB Local DB:** Pozzo supports downloading full offline metadata packages (LaunchBox is ~110MB updated weekly). Once downloaded, thousands of games can be scraped in seconds entirely offline without querying internet servers.
- **Arcade Games:** Arcade ROMs (`.zip` / `.7z` MAME/FBNeo sets) are verified against ArcadeDB and DAT signatures, properly displaying canonical cabinet marquee, flyer art, and title screens.
- **Game Manuals & Guides:** You can bind local game manuals (PDF) directly to game cards for instant viewing before jumping into complex retro RPGs or flight sims.
```

---

### 1.4 r/italygames — Angolo Sviluppo Indie Italiano & Open Source

**Strategia di pubblicazione:**
- *Focus:* Progetto open-source indipendente italiano, zero pubblicità, privacy assoluta (nessun dato inviato), manuale utente completo in italiano, interfaccia multilingue curata, integrazione tra retrogame e PC store.
- *Tag/Flair raccomandato:* `Sviluppo / Indie` o `Discussione`.

#### Titolo Raccomandato:
> **Ho creato Pozzo Launcher: un frontend open source per organizzare ROM di ogni console e giochi PC (Steam, Epic, GOG) con manuale completo in italiano**

*Titolo Alternativo:*
> **Stanco dei frontend complessi o pesanti, ho sviluppato Pozzo Launcher: local-first, zero telemetria, scraping super veloce e interfaccia personalizzabile**

#### Corpo del Post (Markdown):
```markdown
Ciao a tutti!

Da grande appassionato di retrogaming e videogiochi PC, mi sono sempre trovato a fare compromessi con i launcher esistenti: alcuni sono eccellenti ma macchinosi da configurare, altri dipendono interamente da servizi cloud esterni, e altri ancora rallentano vistosamente quando la libreria supera le migliaia di giochi.

Negli ultimi mesi ho sviluppato e rilasciato **Pozzo Launcher**, un software open-source (licenza MIT) pensato per unire in un'unica interfaccia pulita sia la propria collezione di ROM (dalle console storiche fino a quelle più recenti) sia i giochi PC da Steam, Epic Games, GOG, Amazon Games, Battle.net ed eseguibili singoli.

### Cosa fa Pozzo Launcher:
- 🚀 **Scraping velocissimo e intelligente:** Riconosce le ROM offline tramite i DAT No-Intro e Redump. Non bombarda le API esterne di richieste: prima verifica il file in locale, poi scarica copertine, descrizioni, voti e durata (HowLongToBeat) solo per ciò che manca realmente. Se la scansione si interrompe, riprende esattamente da dove era rimasta.
- 🗂️ **Gestione Multi-Regione:** Niente più liste intasate da 4 versioni dello stesso gioco (USA, Europa, Giappone). Le unifica in un'unica scheda con selettore rapido della versione da avviare.
- 🎮 **Modalità Big Picture:** Interfaccia a schermo intero navigabile interamente con controller, perfetta per chi gioca dal divano su TV o su handheld tipo Steam Deck e ROG Ally.
- 📱 **App per smartphone senza installazione:** Scansionando un semplice QR code sullo schermo, il telefono diventa un telecomando per sfogliare la libreria, lanciare i giochi a distanza o usarlo come controller d'emergenza con giroscopio.
- 🎨 **Layout e Temi:** 7 modalità di visualizzazione (Catalogo, Scaffali, Console, Dashboard, Cinema, Vetrina, Originale) e temi personalizzabili (compreso un tema OLED puro e un tema Retrò).
- 🔒 **Privacy e Local-First:** Zero telemetria, nessun account richiesto, nessun dato inviato a server terzi. Tutto rimane salvato sul vostro PC in un comune database SQLite locale.
- 📖 **Manuale completo in italiano:** Tutta la documentazione, la guida alla configurazione e i dettagli tecnici sono scritti e manutenuti nativamente in italiano.

### Come provarlo:
Il progetto è liberamente scaricabile dalla pagina Releases di GitHub, disponibile sia con installer che in versione portatile (senza installazione) per Windows, macOS (Apple Silicon) e Linux (pacchetto `.deb` o archivio `.tar.gz`).

- Repository GitHub: https://github.com/erpaffo/Pozzo-Launcher
- Manuale online: https://erpaffo.github.io/Pozzo-Launcher/
- Changelog: https://github.com/erpaffo/Pozzo-Launcher/blob/main/changelog.md

Essendo un progetto open source indipendente, mi farebbe davvero piacere ricevere feedback da chi ha librerie grandi o configurazioni particolari. Se avete domande, curiosità tecniche su come è sviluppato o suggerimenti su funzionalità da aggiungere, parliamone nei commenti!
```

#### Primo Commento di Approfondimento (OP FAQ):
```markdown
Lascio un paio di dettagli tecnici utili per chi volesse dare un'occhiata al codice o provarlo da sorgenti:

- **Stack tecnologico:** Il backend è realizzato in Python (con FastAPI/uvicorn e SQLite in modalità WAL per garantire letture concorrenti velocissime). L'interfaccia frontend usa tecnologie web moderne racchiuse in una webview nativa ultra-leggera, evitando il pesante consumo di memoria tipico dei framework Electron monolitici.
- **Esecuzione dai sorgenti:**
  ```powershell
  python -m pip install -r requirements.txt
  python -m pozzo app
  ```
- **Contributi:** Se qualcuno vuole contribuire con temi CSS personalizzati, nuove estensioni o integrazioni emulatori, i contributi e le Issue su GitHub sono i benvenuti!
```

---

# 2. Hacker News (Show HN)

---

### Show HN Post

#### Titolo Regolamentare HN:
> **Show HN: Pozzo Launcher – Local-first, open-source game and ROM library manager**

*(Nota su HN: Le regole di Show HN vietano tassativamente aggettivi promozionali come "The ultimate...", "Fastest", "Best". Il titolo deve essere sobrio, descrittivo e rispettare rigorosamente il prefisso `Show HN:`).*

#### Testo del Post (Submission Text):
```text
Hey HN,

I built Pozzo Launcher (https://github.com/erpaffo/Pozzo-Launcher), an open-source, local-first organizer and launcher for emulation ROMs and PC games (Steam, GOG, Epic, etc.).

Most existing game organizers in the retro space either rely heavily on cloud APIs that throttle users after a few hundred requests, or they run on heavyweight Electron runtimes that consume 600MB+ RAM just idling. On the other end, traditional frontends often struggle with multi-region deduplication or require manual file-by-file configuration.

Here are the technical decisions behind Pozzo Launcher:

1. Offline-First Scrape Architecture:
Instead of querying web endpoints on discovery, Pozzo matches ROMs against local No-Intro and Redump DAT databases. If a file name matches canonical DAT naming, cryptographic hashes (CRC32, MD5, SHA1) are fetched straight from memory without touching the disk payload. For unknown ZIP files, CRC32 is read directly from the ZIP central directory header.
For collections on magnetic HDDs, disk I/O uses 8MB block sizes and concurrency pools tailored to storage drive type. Real-world result: indexing 14,780 Nintendo DS titles reduced raw disk read volume from 149 GB to 3.6 GB.

2. Cascaded Asynchronous Metadata Pipeline:
When metadata is absent, the fetch pipeline uses local offline dumps (LaunchBox community db dump ~110MB, TheGamesDB monthly dump) before hitting external APIs (IGDB, ScreenScraper, RAWG). Network calls run via HTTP/2 connection pooling with token-bucket rate limiters respecting third-party rate limits. An estimator utility simulates projected API requests and daily quota consumption prior to running. All scrape transactions commit directly to SQLite in WAL mode, guaranteeing instant restart/resume capability without data loss.

3. Architecture & Footprint:
- Backend: Python 3 with FastAPI and Uvicorn running on an internal loopback.
- Data layer: SQLite with WAL (Write-Ahead Logging) and `rapidfuzz` for sub-millisecond fuzzy title matching.
- Frontend: Lightweight native webview layer (via pywebview) rather than a bundled multi-process Chromium distribution, maintaining low memory overhead.
- Remote Control: An internal lightweight server serves a local PWA companion to smartphones over LAN (with auto-generated local HTTPS certificates for web gyro and touch APIs).

4. Data Privacy:
Zero telemetry, zero user accounts, zero pingbacks. Configuration and cache live entirely in user-space directory paths (`%LOCALAPPDATA%`, `~/.local/share`, `~/Library/Application Support`).

Binaries are built via PyInstaller with a custom differential manifest-based updater that downloads changed assets rather than re-downloading entire release archives.

Code: https://github.com/erpaffo/Pozzo-Launcher  
Documentation: https://erpaffo.github.io/Pozzo-Launcher/

I would love to hear thoughts on the offline identification pipeline, concurrency handling, or general architecture.
```

---

### Risposte Preparate per Hacker News

#### Domanda 1: Sicurezza e gestione dei segreti (API keys, credenziali store)
> *"How do you handle credentials for store integrations (Steam, GOG, Epic) and API keys? Are they stored in OS keychains?"*

**Risposta:**
```text
Credentials and API keys (e.g. IGDB client secrets, ScreenScraper logins) are stored locally in plain-text inside `config.toml` and `settings.json` located within the user's local application data directory (`%LOCALAPPDATA%\PozzoLauncher` on Windows, `~/.local/share/PozzoLauncher` on Linux, `~/Library/Application Support/PozzoLauncher` on macOS).

We chose explicit flat files over OS keychains (such as Windows Credential Manager or SecretService) for three deliberate reasons:
1. Portability: Users can run Pozzo in true portable mode on external SSDs or flash drives between machines without losing configuration.
2. Full Transparency: The user has complete, unabstracted ownership over their data. You can inspect, version-control via git, or wipe your keys with standard text tools.
3. No IPC dependencies: Avoiding complex C-bindings or external daemon dependencies that frequently break across headless Linux environments or minimal SteamOS containers.

We document this explicitly in our PRIVACY.md: the config folder must be treated with the same permissions as your SSH directory.
```

#### Domanda 2: Licenza, Filosofia Open Source e Monetizzazione
> *"What is your licensing model, and are there any plans to paywall features or introduce a cloud sync subscription?"*

**Risposta:**
```text
Pozzo Launcher is licensed under the MIT License and will remain 100% free software. 

There are no plans for hosted proprietary services, premium tiers, or telemetry-driven features. Multi-device sync is designed around user-controlled infrastructure: you can sync your library between PCs via local network pairing or by pointing the data directory to a shared folder (e.g. Syncthing, Nextcloud, or a local NAS). The goal is to provide a durable utility that continues working 20 years from now even if the original project repository went offline.
```

#### Domanda 3: Packaging, Distribuzione e scelta dello stack Python
> *"Why Python and PyInstaller instead of Rust/Go or Electron? Doesn't PyInstaller create large startup binaries?"*

**Risposta:**
```text
Python allowed us to leverage mature ecosystem libraries for retro computing (libtorrent bindings, 7z/rar archive handlers, rapidfuzz C-extensions, and PIL/Pillow for image processing) without reinventing parsing wheels.

To address the typical PyInstaller cold-start and update size issues:
1. Startup Performance: We use `pywebview` binding to the OS's native web engine (WebView2 on Windows, WebKit on macOS/Linux). This avoids packing a full Chromium browser instance, keeping the memory baseline around 80-120MB rather than 500MB+.
2. Differential Auto-Updater: Standard PyInstaller apps require re-downloading 100MB+ executables on every release. Our GitHub Actions build generates a granular release manifest containing file-level SHA256 hashes and small tarballs. The in-app updater inspects the manifest and downloads only the modified modules and static assets, reducing minor version updates from ~90MB down to ~3-8MB over the wire.
```

#### Domanda 4: Performance su cataloghi enormi (50k+ ROM)
> *"How does the UI and SQLite perform when querying 50,000+ items with complex filters?"*

**Risposta:**
```text
The SQLite database runs with PRAGMA journal_mode = WAL and synchronous = NORMAL, with indexes on `platform_id`, `canonical_title`, `favorite`, and `play_status`.

On the UI layer, rather than rendering 50,000 DOM nodes simultaneously, all collection layouts (Catalog, Shelves, Console, Big Picture) utilize virtualized scrolling: only the items visible inside the current viewport (plus a 200px buffer) are mounted to the DOM. Search filtering uses `rapidfuzz` running in background Python worker threads with cached token arrays, delivering sub-20ms response times on typical full No-Intro sets.
```

---

# 3. GBAtemp Thread

---

### GBAtemp: Versione Markdown

#### Titolo del Thread:
> **[RELEASE] Pozzo Launcher – Free, Open-Source Game & ROM Frontend (Offline No-Intro/Redump Scraper, Big Picture, Handheld/Phone Support)**

```markdown
Hello GBAtemp community!

I'd like to share **Pozzo Launcher**, an all-in-one open source frontend designed to organize, scrape, and launch your entire retro and modern gaming library with zero hassle.

Whether you're managing full retro romsets on an external drive, a curated handheld library on your Steam Deck/ROG Ally, or combining your PC games from Steam and GOG in one place, Pozzo was built to do it quickly, cleanly, and without API headache.

---

### 🌟 Key Features

- **Blazing Fast Offline Scraping:**
  Matches your ROMs against local No-Intro and Redump DATs first. If your file names match standard sets, it doesn't even need to read the disk. No more getting blocked by ScreenScraper or IGDB rate limits!
- **Unified Multi-Region System (1G1R Made Right):**
  Doesn't clutter your screen with 5 regional clones. Automatically consolidates USA, EUR, and JPN versions into a single game card with a drop-down to pick which one to launch.
- **Full Gamepad & Big Picture Mode:**
  Designed from scratch for couch gaming. Navigate your collection, change views, and launch games using your controller.
- **7 Switchable Layouts & Themes:**
  Catalog, Shelves, Console view, Dashboard, Cinema view, Showcase carousel, and Classic Original. Includes OLED Black, Retro CRT, Light, and Midnight Blue themes.
- **Smartphone Companion (No app install needed):**
  Scan the QR code from the app and control your launcher from your phone browser: browse your library, launch games, and use your phone as a virtual touchpad/gamepad with gyro!
- **Consoles + PC Stores in One Place:**
  Seamlessly integrates Steam, Epic, GOG, Amazon, Battle.net, Xbox, and standalone `.exe` games alongside your emulated consoles.
- **Switch & Disc Preservation:**
  Directly parses Switch titles (`.nsp`, `.xci`, `.nsz`) using your `prod.keys` to pull title, update version, DLCs, and icons instantly.
- **100% Free & Open Source:**
  No ads, no paid tiers, no cloud account required, and absolute zero telemetry.

---

### 📸 Screenshots & Layouts

- **The Main Library & Shelves:** Clean visual browsing with high-res 3D boxart, logos, and metadata.
- **Game Details Page:** Playtime tracking, synopsis, screenshot galleries, and multi-region selectors.
- **Big Picture Mode:** Tailored for 10-foot TV experience and handheld displays.
- **Phone Remote App:** Scan the QR code to search your library and launch games from your phone.

*(Screenshots and GIFs available on the GitHub repository: https://github.com/erpaffo/Pozzo-Launcher)*

---

### 📥 Download & Installation

Binaries are compiled and ready to download on GitHub Releases:
- **Windows (10/11 64-bit):** Available as a standard Installer (`setup.exe`) or a Portable `.zip` (extract and run `PozzoLauncher.exe`).
- **Linux (64-bit / SteamOS):** Native `.deb` package or portable `.tar.gz`.
- **macOS (Apple Silicon):** Native `.dmg` or `.zip`.

👉 **Download latest release:** [GitHub Releases](https://github.com/erpaffo/Pozzo-Launcher/releases)  
👉 **Full Documentation / Manual:** [Online Manual](https://erpaffo.github.io/Pozzo-Launcher/)

---

### 📝 Condensed Changelog

- **v1.0.x Release Highlights:**
  - Added fast offline DAT hashing engine for No-Intro and Redump sets.
  - Implemented 7 distinct UI layouts including Cinema and Showcase.
  - Added smartphone companion server with WebRTC/WebSocket gyro controller support.
  - Added multi-source scrape pipeline: LaunchBox local DB, ScreenScraper, TheGamesDB, IGDB, ArcadeDB, and RAWG.
  - Added multi-region game consolidation.
  - Added export modules for EmulationStation-DE and Pegasus Frontend.
  - Implemented auto-updater with differential file-level patching.

---

### 💬 Feedback, Bug Reports & Feature Requests

This is an active open-source project created by and for gamers. If you have custom platform structures, obscure file extensions, or feature ideas you'd love to see, please drop a comment here or open an Issue on GitHub!

Looking forward to your impressions!
```

---

### GBAtemp: Versione BBCode (Pronta al copia-incolla)

```bbcode
[B][SIZE=6][COLOR=#0080ff]Pozzo Launcher[/COLOR] – Open-Source Game & ROM Frontend[/SIZE][/B]
[I]Offline No-Intro/Redump Scraper, Full Big Picture, Handheld & Phone Companion[/I]

Hello GBAtemp community!

I would like to present [B]Pozzo Launcher[/B], an open-source, local-first game organizer and launcher designed to manage massive retro ROM collections alongside modern PC titles without the usual scraper headaches or bloat.

[HR][/HR]
[SIZE=5][B]🚀 Key Features[/B][/SIZE]

[LIST]
[*][B]Fast Offline Scraping:[/B] Compares file names and hashes against local No-Intro and Redump DATs first. Zero unnecessary API calls, no IP bans, and no waiting hours on hourly limits.
[*][B]Smart Multi-Region Grouping:[/B] Consolidates USA, EUR, and JPN versions of the same title into one clean entry with an in-card version selector.
[*][B]Big Picture & Handheld Ready:[/B] Full controller navigation designed for TV couch gaming and handhelds like the Steam Deck and ROG Ally.
[*][B]7 Layouts & Custom Themes:[/B] Switch between Catalog, Shelves, Console, Dashboard, Cinema, Showcase, and Original views. Includes an authentic OLED black theme.
[*][B]Phone Companion Mode:[/B] Scan a local QR code on your TV to browse your library and launch games from your phone, or use it as an emergency controller with gyro.
[*][B]PC Games + Emulators:[/B] Consolidates Steam, Epic, GOG, Amazon, Battle.net, and standalone executables next to your retro platforms.
[*][B]Privacy & Local First:[/B] Zero telemetry, no user accounts, no cloud servers. All your data stays on your machine.
[/LIST]

[HR][/HR]
[SIZE=5][B]📦 Downloads & Source Code[/B][/SIZE]

Executables are available for Windows (Installer & Portable), Linux (.deb & portable tar.gz), and macOS:

[URL='https://github.com/erpaffo/Pozzo-Launcher/releases'][B]⬇ Download Pozzo Launcher (GitHub Releases)[/B][/URL]
[URL='https://github.com/erpaffo/Pozzo-Launcher'][B]⭐ GitHub Source Repository[/B][/URL]
[URL='https://erpaffo.github.io/Pozzo-Launcher/'][B]📖 Official Online Manual[/B][/URL]

[HR][/HR]
[SIZE=5][B]💬 Feedback & Discussion[/B][/SIZE]

The project is completely free and open-source (MIT License). I'd love to get feedback from fellow collectors and handheld users on performance, scraping accuracy, and feature suggestions!
```

---

# 4. Product Hunt & AlternativeTo

---

### Product Hunt Kit

#### Product Name:
**Pozzo Launcher**

#### Tagline (58 caratteri):
> **Open-source, local-first game organizer for ROMs and PC**

*(Rientra nel limite stringente di 60 caratteri).*

#### Short Description (248 caratteri):
> **Pozzo Launcher brings together your retro ROMs and PC games into one beautiful interface. Fast offline No-Intro/Redump scraping, Big Picture controller mode, 7 layouts, zero telemetry, and a phone companion app to launch games from your couch.**

*(Rientra nel limite di 260 caratteri).*

#### Full Description (Product Hunt Markdown):
```markdown
Pozzo Launcher is a lightweight, open-source game launcher that consolidates your emulation collection and PC games (Steam, Epic, GOG, Amazon, etc.) into a single, cohesive library.

Built with a local-first philosophy, Pozzo doesn't require an account, has zero telemetry, and keeps all your data strictly on your computer.

### Highlights:
- **Offline-First Scraping Engine:** Matches your ROMs against local No-Intro and Redump DATs before touching any web API. Fast, accurate, and immune to scraper bans or rate limits.
- **No Duplicate Region Spam:** Groups USA, European, and Japanese dumps into a unified game card with an instant region switcher.
- **Big Picture & Handheld Friendly:** Navigate your library from the couch with full controller support on TV screens, Steam Deck, or ROG Ally.
- **Phone Companion App:** Scan a local QR code to turn your smartphone into a remote library browser, remote game launcher, or motion controller with gyro support.
- **7 Flexible Layouts:** Choose between Showcase, Cinema, Shelves, Catalog, Console, Dashboard, and Original styles, paired with OLED Black, Midnight Blue, and Retro themes.
- **100% Free & Open Source:** Released under the MIT license for Windows, macOS, and Linux.
```

#### Categorie e Tag Raccomandati:
- `Gaming`
- `Open Source`
- `Video Games`
- `Productivity / Organization`
- `Handheld Gaming / Steam Deck`

#### Commento di Lancio del Maker (First Comment):
```markdown
Hi Product Hunt! 👋

I created Pozzo Launcher because I was frustrated with the current state of game frontends. You usually have to choose between clunky desktop tools that require hours of setup, or proprietary frontends that lock your metadata into cloud accounts and telemetry.

Pozzo Launcher was built around three guiding principles:
1. **Speed & Data Integrity:** Offline identification against verified DATs so scraping thousands of games takes minutes, not days.
2. **Couch & Handheld Comfort:** Dedicated Big Picture and Cinema views, with a handy companion phone app to browse and launch games without getting off the couch.
3. **Total Privacy:** 100% local-first, zero analytics, open-source (MIT).

Would love to hear your feedback, thoughts on the layouts, and any ideas for new integrations!
```

---

### AlternativeTo Kit

#### Tagline / Breve Presentazione:
> **A fast, local-first, open-source game launcher and ROM manager with offline DAT scraping, Big Picture controller mode, and phone remote control.**

#### Piattaforme Supportate:
- Windows (10, 11)
- Linux (SteamOS, Debian, Ubuntu, Mint, Arch)
- macOS (Apple Silicon)

#### Licenza:
- **Open Source / Free (MIT License)**

#### Tag / Caratteristiche Consigliate:
- `Game Launcher`
- `ROM Manager`
- `Retro Gaming`
- `Local First`
- `Zero Telemetry / Privacy Focused`
- `Gamepad Support / Big Picture`
- `Emulation Frontend`
- `Self-Hosted / Offline Scraping`
- `Steam Deck Compatible`

---

### Proposta di Valore vs Competitor Diretti

#### Pozzo Launcher vs. Playnite
| Caratteristica | Pozzo Launcher | Playnite |
|---|---|---|
| **Ecosistema & Scopo** | Specializzato sia per ROM retro sia per store PC nativi in un'unica architettura bilanciata | Focalizzato principalmente su PC gaming, supporto ROM tramite plugin terzi |
| **Scraping ROM** | **Offline nativo via DAT No-Intro/Redump**, download batch di LaunchBox e TheGamesDB in locale senza limiti API | Basato su plugin ed estensioni online che consumano API ed espongono a rate-limit |
| **Deduplicazione Regionale** | Raggruppamento automatico multi-regione (1G1R non distruttivo con switch integrato) | Tratta ogni file regionale come titolo separato o richiede script di unione complessi |
| **Cross-Platform** | **Windows, Linux (nativo / SteamOS) e macOS (Apple Silicon)** | Solo Windows |
| **Handheld & Couch** | Big Picture nativo + **Companion app su telefono via LAN** (telecomando e giroscopio) | Big Picture eccellente su Windows, nessuna companion mobile nativa senza software terzi |
| **Impronta Risorse** | Backend asincrono in Python + Webview nativa (basso consumo RAM) | Applicazione WPF .NET (ottima su desktop potenti, ma più pesante su dispositivi compatti) |

#### Pozzo Launcher vs. LaunchBox (e Big Box)
| Caratteristica | Pozzo Launcher | LaunchBox / Big Box |
|---|---|---|
| **Costo & Licenza** | **100% Gratuito e Open Source (MIT)** | Freemium (Desktop base gratis, modalità Big Box per controller a pagamento / licenza perpetua) |
| **Supporto Piattaforme** | Windows, Linux nativo, macOS | Solo Windows (versione Android separata) |
| **Scraping & Quota** | Combina database offline e fonti multiple (ScreenScraper, IGDB, LibRetro, LaunchBox DB) con regolazione priorità per singolo campo | Centrato sul database proprietario LaunchBox |
| **Funzionalità Companion** | App mobile web su rete locale inclusa con telecomando e controlli touch/giro | Richiede app o configurazioni aggiuntive |

#### Pozzo Launcher vs. RetroBat / EmulationStation-DE (ES-DE)
| Caratteristica | Pozzo Launcher | RetroBat / ES-DE |
|---|---|---|
| **Gestione Giochi PC** | Integrazione nativa automatica di Steam, Epic, GOG, Amazon, Battle.net ed eseguibili singoli | Pensato quasi esclusivamente per ROM ed emulatori (integrare giochi PC richiede scorciatoie e script manuali) |
| **Interfaccia Desktop & Editing** | Doppia anima: interfaccia desktop completa per gestione/metadati + Big Picture per controller | Interfaccia unicamente full-screen a menù console (modifica metadati poco pratica su PC desktop) |
| **Interoperabilità** | **Esporta verso ES-DE e Pegasus** con un clic per condividere i dati raschiati | Formato XML proprietario non esportabile nativamente verso altri launcher |

---

### Matrice Riepilogativa delle Funzionalità Chiave (per la scheda AlternativeTo)

- **Local-First & Offline:** Funziona completamente offline, nessun account o server proprietario.
- **Zero Telemetry:** Nessuna raccolta dati di utilizzo o tracciamento degli utenti.
- **Smart No-Intro/Redump Scraper:** Calcolo hash istantaneo da DAT senza I/O non necessario su disco.
- **7 Layout Flessibili:** Catalogo, Scaffali, Console, Dashboard, Cinema, Vetrina (Showcase), Originale.
- **Phone Remote & Controller:** PWA locale su smartphone per telecomando da divano, avvio giochi e giroscopio.
- **Multi-Store PC:** Steam, Epic Games, GOG Galaxy, Amazon Prime Games, Battle.net, Xbox.
- **Differential Updates:** Aggiornamenti software leggeri tramite manifest che scaricano solo i file modificati.
- **Multi-Region Merging:** Riconoscimento intelligente delle versioni regionali dello stesso gioco.
