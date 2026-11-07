# Template per GitHub Release Notes
## Pozzo Launcher — Modello Ufficiale per Annunci di Release

Questo template markdown è progettato per massimizzare l'attrattiva, i download e le condivisioni sui social network (Reddit, Discord, X/Twitter, forum di gaming) di ogni nuova versione di **Pozzo Launcher**.

Può essere copiato e compilato direttamente nell'editor delle GitHub Releases (`Releases › Draft a new release`) o integrato in pipeline automatizzate.

---

```markdown
# 🚀 Pozzo Launcher v[X.Y.Z] — "[Nome in codice o Titolo Versione]"

[![Release](https://img.shields.io/github/v/release/erpaffo/Pozzo-Launcher?color=blue&label=version)](https://github.com/erpaffo/Pozzo-Launcher/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/erpaffo/Pozzo-Launcher/total?color=success&label=downloads)](https://github.com/erpaffo/Pozzo-Launcher/releases)
[![VirusTotal](https://img.shields.io/badge/VirusTotal-Clean%20(0%2F70)-brightgreen)](https://www.virustotal.com/gui/file/[INSERIRE_HASH_VT])
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Steam%20Deck%20%7C%20macOS-informational)](#-download-rapidi--installazione)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Riepilogo rapido / Quick Summary:**
> [Breve paragrafo di 2-3 righe che sintetizza l'aggiornamento. Es: "La versione 0.16 porta una nuovissima interfaccia Media Hub per film e serie TV, una dashboard con widget riordinabili con drag-and-drop, e piena compatibilità con Steam Deck in modalità Big Picture a 60 FPS stabili!"]

---

## 🌟 Novità in Primo Piano (Highlights)

### 1. [Nome Grande Novità 1 - es. Nuovo Media Hub Stile Cinema]
[Spiegazione coinvolgente della funzionalità in 2-3 frasi, evidenziando il vantaggio pratico per l'utente.]

<p align="center">
  <img src="https://raw.githubusercontent.com/erpaffo/Pozzo-Launcher/master/docs/img/[NOME_IMMAGINE_1].jpg" alt="Anteprima Funzionalità 1" width="85%" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
</p>

### 2. [Nome Grande Novità 2 - es. Dashboard con Widget Dinamici]
[Descrizione della novità, interazioni possibili, tasti rapidi o miglioramenti di comfort.]

<p align="center">
  <img src="https://raw.githubusercontent.com/erpaffo/Pozzo-Launcher/master/docs/img/[NOME_IMMAGINE_2].jpg" alt="Anteprima Funzionalità 2" width="85%" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
</p>

---

## 📋 Registro Modifiche Dettagliato (Full Changelog)

### ✨ Nuove Funzionalità (New Features)
- **[Componente/Modulo]**: [Descrizione chiara del miglioramento introdotto].
- **[Componente/Modulo]**: [Descrizione chiara del miglioramento introdotto].
- **[Componente/Modulo]**: [Descrizione chiara del miglioramento introdotto].

### ⚡ Miglioramenti & Prestazioni (Improvements & Performance)
- **[Componente/Modulo]**: [Ottimizzazioni memoria, fluidità interfaccia, tempi di caricamento scraper].
- **[Componente/Modulo]**: [Miglioramento compatibilità controller gamepad / Big Picture].

### 🐛 Correzioni di Bug (Bug Fixes)
- **[Modulo]**: [Risoluzione del problema X che impediva Y (#issue_number)].
- **[Modulo]**: [Corretto arresto anomalo su Linux / SteamOS durante l'avvio con determinate librerie].

### 🔧 Sotto il Cofano (Under the Hood)
- Aggiornate dipendenze principali (`pyside6`, `requests`, `pywebview`).
- Refactoring architetturale per velocizzare l'avvio a freddo.

---

## 💾 Download Rapidi & Installazione

### 🪟 Windows (10 / 11)
- **Installer raccomandato (Setup automatico)**: [`PozzoLauncher-[X.Y.Z]-windows-x64-setup.exe`](https://github.com/erpaffo/Pozzo-Launcher/releases/download/v[X.Y.Z]/PozzoLauncher-[X.Y.Z]-windows-x64-setup.exe)
- **Versione portatile (Nessuna installazione)**: [`PozzoLauncher-[X.Y.Z]-windows-x64.zip`](https://github.com/erpaffo/Pozzo-Launcher/releases/download/v[X.Y.Z]/PozzoLauncher-[X.Y.Z]-windows-x64.zip)

> **Installazione con un comando tramite Winget:**
> ```powershell
> winget install erpaffo.PozzoLauncher
> ```
> *(oppure con Scoop: `scoop install pozzo-launcher`)*

---

### 🎮 Steam Deck & Linux
- **Flathub (Consigliato per Steam Deck)**: Disponibile su Discover Software Center oppure:
  ```bash
  flatpak install flathub com.erpaffo.PozzoLauncher
  ```
- **Pacchetto Arch Linux / SteamOS (AUR)**:
  ```bash
  yay -S pozzo-launcher-bin
  ```
- **Pacchetto Debian / Ubuntu (.deb)**: [`pozzo_[X.Y.Z]_amd64.deb`](https://github.com/erpaffo/Pozzo-Launcher/releases/download/v[X.Y.Z]/pozzo_[X.Y.Z]_amd64.deb)
- **Archivio Linux portatile (.tar.gz)**: [`PozzoLauncher-[X.Y.Z]-linux-x64.tar.gz`](https://github.com/erpaffo/Pozzo-Launcher/releases/download/v[X.Y.Z]/PozzoLauncher-[X.Y.Z]-linux-x64.tar.gz)

---

### 🍎 macOS
- **Apple Silicon (M1/M2/M3/M4)**: [`PozzoLauncher-[X.Y.Z]-macos-arm64.dmg`](https://github.com/erpaffo/Pozzo-Launcher/releases/download/v[X.Y.Z]/PozzoLauncher-[X.Y.Z]-macos-arm64.dmg)

---

## 🛡️ Integrità, Sicurezza & SmartScreen

| File | Algoritmo | Impronta Crittografica (Checksum) |
|---|---|---|
| `PozzoLauncher-[X.Y.Z]-windows-x64-setup.exe` | SHA-256 | `[INSERIRE_SHA256]` |
| `PozzoLauncher-[X.Y.Z]-windows-x64.zip` | SHA-256 | `[INSERIRE_SHA256]` |
| `PozzoLauncher-[X.Y.Z]-linux-x64.tar.gz` | SHA-256 | `[INSERIRE_SHA256]` |
| `PozzoLauncher-[X.Y.Z]-macos-arm64.dmg` | SHA-256 | `[INSERIRE_SHA256]` |

> ℹ️ **Nota per utenti Windows (Microsoft Defender SmartScreen):**
> Essendo un software open-source libero e senza scopo di lucro, Pozzo Launcher non adotta certificati di firma commerciale EV da centinaia di euro l'anno. Se Windows mostra l'avviso a schermo blu *"PC protetto da Windows"*, clicca semplicemente su **"Ulteriori informazioni"** e poi su **"Esegui comunque"**.
> 
> Puoi verificare in qualsiasi momento:
> 1. Il report di scansione completo su [VirusTotal Report](https://www.virustotal.com/gui/file/[INSERIRE_HASH_VT]) (0/70 motori rilevati).
> 2. I registri pubblici di compilazione automatica su [GitHub Actions Workflow](https://github.com/erpaffo/Pozzo-Launcher/actions/workflows/release.yml).

---

## 💬 Community, Supporto & Come Aiutare

- 📖 **Manuale Completo Online**: [erpaffo.github.io/Pozzo-Launcher](https://erpaffo.github.io/Pozzo-Launcher/)
- 🐞 **Segnalazione Bug & Idee**: [GitHub Issues](https://github.com/erpaffo/Pozzo-Launcher/issues)
- ⭐ **Ti piace Pozzo Launcher?** Lascia una stella in alto a destra su GitHub! Aiuta il progetto a farsi conoscere ad altri appassionati di retrogaming e PC gaming.
- 📣 **Condividi l'aggiornamento**: Racconta la tua esperienza su [Reddit (r/SteamDeck, r/emulation)](https://reddit.com), nei canali Discord retro e con i tuoi amici videogiocatori!

**Grazie a tutti i tester e contributori di questa versione!** ❤️
```

---

## Linee Guida per la Pubblicazione

1. **Tag di versione**: Seguire rigorosamente il semantic versioning preceduto da `v` (es. `v0.16.0`).
2. **Immagini**: Usare link diretti a immagini già caricate su GitHub (`https://raw.githubusercontent.com/...`) o caricare screenshot trascinandoli direttamente nell'editor delle release di GitHub.
3. **Checksum**: I valori SHA-256 vengono calcolati in automatico dal workflow di rilascio (`release.yml`) nel file `SHA256SUMS.txt`. Copiare i valori direttamente da quel file.
4. **Condivisione**: Dopo la pubblicazione, pubblicare un breve post di annuncio con link alla release su:
   - Reddit (`r/SteamDeck`, `r/emulation`, `r/EmulationOnPC`, `r/pcgaming`)
   - Forum e canali Discord dedicati a emulatori e gaming open-source.
