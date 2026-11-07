# Pozzo Launcher

**English** · [Italiano](README.it.md)

[![Test](https://github.com/erpaffo/Pozzo-Launcher/actions/workflows/ci.yml/badge.svg)](https://github.com/erpaffo/Pozzo-Launcher/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/erpaffo/Pozzo-Launcher)](https://github.com/erpaffo/Pozzo-Launcher/releases/latest)
[![Manual](https://img.shields.io/badge/manual-online-blue)](https://erpaffo.github.io/Pozzo-Launcher/)

Pozzo Launcher brings together the ROMs of every console and the PC games from your stores. It fetches covers, descriptions, ratings and playtimes on its own. Then you play from the desktop, from Big Picture with a controller, from your phone, or by streaming.

**[Full manual](https://erpaffo.github.io/Pozzo-Launcher/)** · **[Download](https://github.com/erpaffo/Pozzo-Launcher/releases)** · **[Changelog](changelog.md)**

<p align="center">
  <img src="docs/img/libreria.jpg" width="49%" alt="The library">
  <img src="docs/img/dettaglio.jpg" width="49%" alt="A game's detail page">
</p>
<p align="center">
  <img src="docs/img/bigpicture.jpg" width="49%" alt="Big Picture, for the controller">
  <img src="docs/img/estensioni.jpg" width="49%" alt="Extensions store">
</p>
<p align="center"><sub>Sample library with made-up games.</sub></p>

### Layouts

A layout doesn't just change the colors but the way you browse the library. Pick one in **Settings › Appearance**.

<p align="center">
  <img src="docs/img/esp-catalogo.jpg" width="49%" alt="Catalog layout">
  <img src="docs/img/esp-scaffali.jpg" width="49%" alt="Shelves layout">
</p>
<p align="center">
  <img src="docs/img/esp-console.jpg" width="49%" alt="Console layout, with a narrow sidebar">
  <img src="docs/img/esp-dashboard.jpg" width="49%" alt="Dashboard layout">
</p>
<p align="center">
  <img src="docs/img/esp-cinema.jpg" width="49%" alt="Cinema layout">
  <img src="docs/img/esp-vetrina.jpg" width="49%" alt="Showcase layout">
</p>
<p align="center"><sub>Catalog · Shelves · Console · Dashboard · Cinema · Showcase (there's also Original, the classic view).</sub></p>

### Themes

Themes are independent of the layout and can be combined with it.

<p align="center">
  <img src="docs/img/tema-chiaro.jpg" width="49%" alt="Light theme">
  <img src="docs/img/tema-notte-blu.jpg" width="49%" alt="Midnight blue theme">
</p>
<p align="center">
  <img src="docs/img/tema-oled.jpg" width="49%" alt="OLED theme">
  <img src="docs/img/tema-retro.jpg" width="49%" alt="Retro theme">
</p>
<p align="center">
  <img src="docs/img/aspetto.jpg" width="60%" alt="Settings, Appearance section">
</p>

## What it does

- **Fast scraping**. ROMs are recognized offline (CRC and name against the No-Intro/Redump DATs), and online sources are queried only for what is missing, respecting their limits. If it is interrupted, it resumes where it left off.
- A Playnite-style library, with consoles and stores together. Regional versions are merged, and you get favorites (per console too), statuses, collections, search and filters; it copes with tens of thousands of games. A menu bar at the top gets you straight to the most-used actions and settings.
- **PC games** from Steam, Epic, GOG, Amazon, Battle.net, Xbox and others, next to your ROMs. You can add any `.exe`, game or application by hand: it shows up right away, and the cover and data follow. Each game can also launch other applications along with it, for example a deck tracker.
- **Big Picture**: a full-screen mode designed for the controller, even from the couch.
- From your phone you can browse and launch games, and the phone doubles as a controller (gyroscope included). For streaming there are Sunshine and Moonlight.
- **Online stores** are lists of games taken from other websites, which show up as a "store" of each console.
- Seven layouts (Catalog, Shelves, Console, Dashboard, Cinema, Showcase, Original) and the light, midnight blue, OLED and retro themes, to mix as you like.
- **Extensions** to install from the store inside the app: what to play tonight, achievements, release calendar, play diary…
- Plus the extras: free games, a wishlist with prices, PC ports, save backups, Discord (including mute, deafen and leave the call), Spotify and media keys, keyboard shortcuts, export for ES-DE and Pegasus.

## Download

The executables are on the **[Releases](https://github.com/erpaffo/Pozzo-Launcher/releases)** page:

| System | Installer | Portable |
|---|---|---|
| Windows 10/11 (64 bit) | `PozzoLauncher-<version>-windows-x64-setup.exe` | `…-windows-x64.zip`: extract and open `PozzoLauncher.exe` |
| macOS 11+ (Apple Silicon) | `…-macos-arm64.dmg`: drag the app to Applications | `…-macos-arm64.zip` |
| Linux (64 bit) | `pozzo_<version>_amd64.deb` (Debian, Ubuntu, Mint…) | `…-linux-x64.tar.gz` |

The executables are not signed: on Windows SmartScreen asks for confirmation (*More info › Run anyway*), on macOS the first time open the app with right click › Open.

When a new version is out a notice appears. Install it with one click from **Settings › About** (**⬇ Install and restart**) and your data stays where it is.

## Getting started

1. Open Pozzo Launcher and choose your ROM folder in **Settings › New games**.
2. Start the search: the library fills up, and covers and data arrive in the background.
3. For PC games, connect your stores from **Settings › Stores**.

Configuration, cache and library live in the user folder (`%LOCALAPPDATA%\PozzoLauncher` on Windows, `~/Library/Application Support/PozzoLauncher` on macOS, `~/.local/share/PozzoLauncher` on Linux). Everything else (source credentials, terminal commands, online stores, phone, extensions) is in the [manual](https://erpaffo.github.io/Pozzo-Launcher/). The manual is currently in Italian only.

## From source

```powershell
python -m pip install -r requirements.txt
python -m pozzo app          # opens the app
python -m pozzo run          # scan and scraping only, from the terminal
```

Code structure, how to build the executables and performance: [Development](docs/sviluppo.md). To contribute: [CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

Pozzo Launcher is a library manager: it **does not contain, host or distribute games, ROMs, BIOS files or keys**. Use it with games you legally own and in compliance with the laws of your country and the terms of the sites you connect to: you are responsible for the content you add.

The names and trademarks of consoles, games and stores mentioned belong to their respective owners. Pozzo Launcher is not affiliated with or endorsed by any of them.

[Privacy](PRIVACY.md) · [Security](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md) · [Third-party components](THIRD_PARTY_NOTICES.md)
