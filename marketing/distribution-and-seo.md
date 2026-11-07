# Guida alla Distribuzione, Package Managers & GitHub SEO
## Pozzo Launcher — Strategia di Crescita, Canali di Installazione e Visibilità

Questo documento raccoglie le istruzioni operative, i file di configurazione pronti all'uso e le migliori pratiche per distribuire **Pozzo Launcher** sui principali package manager (Windows, Linux, Steam Deck), ottimizzare la visibilità su GitHub e gestire in modo professionale la fiducia dell'utente (antivirus, falsi positivi, SmartScreen).

---

## Indice

1. [Distribuzione Windows: Winget & Scoop](#1-distribuzione-windows-winget--scoop)
   - [Winget (Windows Package Manager)](#winget-windows-package-manager)
   - [Manifest YAML Winget per Pozzo Launcher](#manifest-yaml-winget-per-pozzo-launcher)
   - [Automazione Release con WingetReleaser](#automazione-release-con-wingetreleaser)
   - [Scoop (Community Bucket & Manifest)](#scoop-community-bucket--manifest)
2. [Distribuzione Linux & SteamOS: Flathub & AUR](#2-distribuzione-linux--steamos-flathub--aur)
   - [Flathub (Flatpak) — 1-Click Install per Steam Deck Discover Store](#flathub-flatpak--1-click-install-per-steam-deck-discover-store)
   - [Manifest Flatpak (`com.erpaffo.PozzoLauncher.yaml`)](#manifest-flatpak-comerpaffopozzolauncheryaml)
   - [File AppStream Metainfo e Desktop](#file-appstream-metainfo-e-desktop)
   - [Procedura di Sottomissione su Flathub](#procedura-di-sottomissione-su-flathub)
   - [Arch Linux / SteamOS: Pacchetto AUR (`pozzo-launcher-bin`)](#arch-linux--steamos-pacchetto-aur-pozzo-launcher-bin)
3. [GitHub SEO, Profiling & Social Preview](#3-github-seo-profiling--social-preview)
   - [GitHub Topics & Tag Strategici](#github-topics--tag-strategici)
   - [About Box: Descrizione & Link Ottimizzati](#about-box-descrizione--link-ottimizzati)
   - [Social Preview Card (1280x640px)](#social-preview-card-1280x640px)
4. [Gestione della Fiducia, SmartScreen & Falsi Positivi](#4-gestione-della-fiducia-smartscreen--falsi-positivi)
   - [Perché compare Windows SmartScreen?](#perché-compare-windows-smartscreen)
   - [Trasparenza e Build Riproducibili su GitHub Actions](#trasparenza-e-build-riproducibili-su-github-actions)
   - [Scansione VirusTotal Automatizzata nel Workflow](#scansione-virustotal-automatizzata-nel-workflow)
   - [Procedura Ufficiale Sottomissione Falsi Positivi (Microsoft WDSI)](#procedura-ufficiale-sottomissione-falsi-positivi-microsoft-wdsi)

---

## 1. Distribuzione Windows: Winget & Scoop

### Winget (Windows Package Manager)

**Winget** è il gestore pacchetti ufficiale di Microsoft preinstallato su Windows 10 e Windows 11. Permette agli utenti di installare Pozzo Launcher da PowerShell con un singolo comando:

```powershell
winget install erpaffo.PozzoLauncher
```

I pacchetti sono ospitati nel repository pubblico [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).

#### Procedura Passo-Passo per la Pubblicazione

1. **Installare lo strumento ufficiale `wingetcreate`**:
   ```powershell
   winget install Microsoft.WingetCreate
   ```

2. **Generare il manifest per una nuova versione**:
   Lanciare il comando puntando all'installer Windows (.exe generato da Inno Setup su GitHub Releases):
   ```powershell
   wingetcreate new https://github.com/erpaffo/Pozzo-Launcher/releases/download/v0.16.0/PozzoLauncher-0.16.0-windows-x64-setup.exe
   ```

3. **Verifica automatica**:
   `wingetcreate` scaricherà il binario, calcolerà l'impronta crittografica SHA-256 e guiderà la compilazione interattiva dei metadati mancanti.

4. **Invio della Pull Request**:
   È possibile inviare automaticamente la PR configurando un GitHub Personal Access Token (PAT):
   ```powershell
   wingetcreate token <tuo_github_pat>
   wingetcreate submit
   ```

---

### Manifest YAML Winget per Pozzo Launcher

Il repository `winget-pkgs` accetta manifest multi-file o formato singleton. Di seguito è riportato il set di manifest multi-file standard per Pozzo Launcher nella cartella `manifests/e/erpaffo/PozzoLauncher/<versione>/`:

#### 1. Manifest di Versione: `erpaffo.PozzoLauncher.yaml`
```yaml
# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.1.6.0.schema.json
PackageIdentifier: erpaffo.PozzoLauncher
PackageVersion: 0.16.0
DefaultLocale: en-US
ManifestType: version
ManifestVersion: 1.6.0
```

#### 2. Manifest Installatore: `erpaffo.PozzoLauncher.installer.yaml`
```yaml
# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.1.6.0.schema.json
PackageIdentifier: erpaffo.PozzoLauncher
PackageVersion: 0.16.0
MinimumOSVersion: 10.0.17763.0
InstallerType: inno
Scope: user
InstallModes:
  - interactive
  - silent
  - silentWithProgress
InstallerSwitches:
  Silent: /SILENT
  SilentWithProgress: /VERYSILENT
  Custom: /ALLUSERS=0
UpgradeBehavior: install
ReleaseDate: 2026-11-06
Installers:
  - Architecture: x64
    InstallerUrl: https://github.com/erpaffo/Pozzo-Launcher/releases/download/v0.16.0/PozzoLauncher-0.16.0-windows-x64-setup.exe
    InstallerSha256: <INSERIRE_SHA256_SETUP_EXE>
    ProductCode: '{CE2FB0F8-58F8-4638-8A8C-AE32627832CE}'
ManifestType: installer
ManifestVersion: 1.6.0
```

#### 3. Manifest Metadati: `erpaffo.PozzoLauncher.locale.en-US.yaml`
```yaml
# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.6.0.schema.json
PackageIdentifier: erpaffo.PozzoLauncher
PackageVersion: 0.16.0
PackageLocale: en-US
Publisher: erpaffo
PublisherUrl: https://github.com/erpaffo
PublisherSupportUrl: https://github.com/erpaffo/Pozzo-Launcher/issues
Author: erpaffo
PackageName: Pozzo Launcher
PackageUrl: https://erpaffo.github.io/Pozzo-Launcher/
License: MIT
LicenseUrl: https://raw.githubusercontent.com/erpaffo/Pozzo-Launcher/master/LICENSE
Copyright: Copyright (c) 2026 Francesco (erpaffo)
ShortDescription: Unified game launcher and retro emulator frontend with automated scrapers, Big Picture mode and web streaming.
Description: |-
  Pozzo Launcher brings together the ROMs of every console and your PC games from all stores.
  It automatically fetches covers, descriptions, ratings and playtimes without manual configuration.
  Play from desktop, controller Big Picture mode, or stream to your phone and browser.
Moniker: pozzo
Tags:
  - game-launcher
  - retrogaming
  - emulation
  - emulation-frontend
  - rom-manager
  - playnite-alternative
  - retroarch
  - steam-deck
ReleaseNotesUrl: https://github.com/erpaffo/Pozzo-Launcher/releases/tag/v0.16.0
ManifestType: defaultLocale
ManifestVersion: 1.6.0
```

---

### Automazione Release con WingetReleaser

Per evitare di inviare manualmente la PR ad ogni nuova release, è possibile aggiungere questo job al file `.github/workflows/release.yml`:

```yaml
  winget:
    name: Publish to Winget
    needs: release
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: windows-latest
    steps:
      - name: Submit to Windows Package Manager
        uses: vedantmgoyal2009/winget-releaser@v2
        with:
          identifier: erpaffo.PozzoLauncher
          version: ${{ github.ref_name }}
          token: ${{ secrets.WINGET_PAT }}
```

*(Nota: `WINGET_PAT` è un GitHub Personal Access Token con permessi di fork e push verso `microsoft/winget-pkgs`).*

---

### Scoop (Community Bucket & Manifest)

**Scoop** è il gestore preferito da sviluppatori e power user di Windows perché installa applicazioni portatili nello spazio utente (`%USERPROFILE%\scoop\apps`) senza richiedere UAC né sporcare il registro di sistema.

#### Manifest Scoop: `pozzo-launcher.json`

Questo manifest può essere sottomesso al bucket `extras` di Scoop ([ScoopInstaller/Extras](https://github.com/ScoopInstaller/Extras)) oppure distribuito tramite bucket personale:

```json
{
  "version": "0.16.0",
  "description": "Unified game launcher and emulator frontend for PC and retro consoles",
  "homepage": "https://erpaffo.github.io/Pozzo-Launcher/",
  "license": "MIT",
  "architecture": {
    "64bit": {
      "url": "https://github.com/erpaffo/Pozzo-Launcher/releases/download/v0.16.0/PozzoLauncher-0.16.0-windows-x64.zip",
      "hash": "<INSERIRE_SHA256_ZIP>"
    }
  },
  "extract_dir": "PozzoLauncher",
  "bin": [
    ["PozzoLauncher.exe", "pozzo"]
  ],
  "shortcuts": [
    ["PozzoLauncher.exe", "Pozzo Launcher"]
  ],
  "persist": [
    "profiles",
    "cache",
    "settings.json"
  ],
  "checkver": {
    "github": "https://github.com/erpaffo/Pozzo-Launcher"
  },
  "autoupdate": {
    "architecture": {
      "64bit": {
        "url": "https://github.com/erpaffo/Pozzo-Launcher/releases/download/v$version/PozzoLauncher-$version-windows-x64.zip"
      }
    }
  }
}
```

#### Installazione per l'utente finale:
```powershell
# Nel caso di bucket dedicato erpaffo:
scoop bucket add erpaffo https://github.com/erpaffo/scoop-bucket
scoop install pozzo-launcher
```

---

## 2. Distribuzione Linux & SteamOS: Flathub & AUR

### Flathub (Flatpak) — 1-Click Install per Steam Deck Discover Store

Su **SteamOS** (il sistema operativo immutabile di Steam Deck) il filesystem di sistema `/` è in sola lettura. L'unico modo supportato e raccomandato da Valve per installare applicazioni senza alterare il sistema è **Flatpak** tramite il centro software **KDE Discover**.

Essere presenti su **Flathub** garantisce:
1. **Installazione con 1 clic** dalla modalità Desktop di Steam Deck.
2. Aggiornamenti automatici e sicuri tramite Discover.
3. Possibilità di aggiungere l'applicazione a Steam Gaming Mode (tramite "Add a Non-Steam Game" o tool automatici come BoilR).

---

### Manifest Flatpak (`com.erpaffo.PozzoLauncher.yaml`)

```yaml
app-id: com.erpaffo.PozzoLauncher
runtime: org.freedesktop.Platform
runtime-version: '23.08'
sdk: org.freedesktop.Sdk
command: pozzo

finish-args:
  # Finestra grafica: supporto nativo X11 e Wayland
  - --socket=x11
  - --socket=wayland
  - --share=ipc

  # Audio (effetti, trailer, audio frontend)
  - --socket=pulseaudio

  # Accesso di rete (scraper metadati IGDB/ScreenScraper, aggiornamenti, web streaming)
  - --share=network

  # Accesso controller e joystick (Steam Controller, gamepad Xbox/PS5, Steam Deck controls)
  - --device=all

  # Permessi Filesystem:
  # 1. Home utente per librerie ROM predefinite e configurazioni
  - --filesystem=home:ro
  # 2. Accesso a schede MicroSD e storage esterno su Steam Deck (/run/media)
  - --filesystem=/run/media:rw
  # 3. Accesso alle directory emulatori e Steam
  - --filesystem=~/.var/app:ro
  - --filesystem=~/.local/share/Steam:ro

  # Notifiche desktop
  - --talk-name=org.freedesktop.Notifications

modules:
  - name: python3-dependencies
    buildsystem: simple
    build-commands:
      - pip3 install --verbose --exists-action=i --no-index --find-links="file://${PWD}" --prefix=${FLATPAK_DEST} -r requirements.txt
    sources:
      - type: file
        path: requirements.txt

  - name: pozzo-launcher
    buildsystem: simple
    build-commands:
      # Installazione binari precompilati per Linux
      - install -dm755 /app/opt/PozzoLauncher
      - cp -r * /app/opt/PozzoLauncher/
      - install -dm755 /app/bin
      - ln -s /app/opt/PozzoLauncher/PozzoLauncher /app/bin/pozzo

      # File Desktop & Icone di sistema
      - install -Dm644 packaging/icon.png /app/share/icons/hicolor/256x256/apps/com.erpaffo.PozzoLauncher.png
      - install -Dm644 packaging/com.erpaffo.PozzoLauncher.desktop /app/share/applications/com.erpaffo.PozzoLauncher.desktop
      - install -Dm644 packaging/com.erpaffo.PozzoLauncher.metainfo.xml /app/share/metainfo/com.erpaffo.PozzoLauncher.metainfo.xml
    sources:
      - type: archive
        url: https://github.com/erpaffo/Pozzo-Launcher/releases/download/v0.16.0/PozzoLauncher-0.16.0-linux-x64.tar.gz
        sha256: <INSERIRE_SHA256_TAR_GZ>
```

---

### File AppStream Metainfo e Desktop

Per superare la validazione Flathub, sono necessari i file `.desktop` e `.metainfo.xml`:

#### `packaging/com.erpaffo.PozzoLauncher.desktop`
```ini
[Desktop Entry]
Type=Application
Name=Pozzo Launcher
Comment=Unified game library and retro emulation frontend
Exec=pozzo
Icon=com.erpaffo.PozzoLauncher
Terminal=false
Categories=Game;Emulator;Utility;
Keywords=game;launcher;emulator;retro;steamdeck;roms;frontend;
StartupWMClass=PozzoLauncher
```

#### `packaging/com.erpaffo.PozzoLauncher.metainfo.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.erpaffo.PozzoLauncher</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <name>Pozzo Launcher</name>
  <summary>Unified game library and retro emulation frontend</summary>
  
  <description>
    <p>
      Pozzo Launcher brings together your retro console ROMs and PC games in a single modern,
      responsive interface designed for desktops, laptops, and the Steam Deck.
    </p>
    <ul>
      <li>Automated scraping of covers, descriptions, and ratings from ScreenScraper and web providers.</li>
      <li>Big Picture mode with full gamepad and controller navigation.</li>
      <li>Local media hub and game streaming to your phone or web browser.</li>
      <li>Optimized performance with low memory and CPU footprint.</li>
    </ul>
  </description>

  <launchable type="desktop-id">com.erpaffo.PozzoLauncher.desktop</launchable>

  <screenshots>
    <screenshot type="default">
      <caption>Catalog and library view</caption>
      <image>https://raw.githubusercontent.com/erpaffo/Pozzo-Launcher/master/docs/img/libreria.jpg</image>
    </screenshot>
    <screenshot>
      <caption>Big Picture controller mode</caption>
      <image>https://raw.githubusercontent.com/erpaffo/Pozzo-Launcher/master/docs/img/bigpicture.jpg</image>
    </screenshot>
  </screenshots>

  <url type="homepage">https://erpaffo.github.io/Pozzo-Launcher/</url>
  <url type="bugtracker">https://github.com/erpaffo/Pozzo-Launcher/issues</url>
  <url type="vcs-browser">https://github.com/erpaffo/Pozzo-Launcher</url>

  <releases>
    <release version="0.16.0" date="2026-11-06" />
  </releases>

  <content_rating type="oars-1.1" />
</component>
```

#### Procedura di Sottomissione su Flathub
1. Creare un fork del repository [flathub/flathub](https://github.com/flathub/flathub).
2. Creare un branch chiamato `new-pr/com.erpaffo.PozzoLauncher`.
3. Inserire `com.erpaffo.PozzoLauncher.yaml` e gli asset metainfo.
4. Testare la build in locale con `flatpak-builder --force-clean build-dir com.erpaffo.PozzoLauncher.yaml`.
5. Aprire una Pull Request verso `flathub/flathub:new-pr`. Il team di Flathub effettua la review e crea automaticamente il repo `flathub/com.erpaffo.PozzoLauncher`.

---

### Arch Linux / SteamOS: Pacchetto AUR (`pozzo-launcher-bin`)

Gli utenti Arch Linux, Manjaro e gli utenti avanzati di Steam Deck con pacman o AUR helper (`yay`, `paru`) possono installare Pozzo Launcher direttamente dall'AUR.

#### `PKGBUILD` per `pozzo-launcher-bin`

```bash
# Maintainer: Francesco (erpaffo) <https://github.com/erpaffo>
pkgname=pozzo-launcher-bin
pkgver=0.16.0
pkgrel=1
pkgdesc="Unified game launcher and retro emulation frontend with scraping and Big Picture mode (binary package)"
arch=('x86_64')
url="https://erpaffo.github.io/Pozzo-Launcher/"
license=('MIT')
depends=(
  'libegl'
  'nss'
  'libxkbcommon-x11'
  'xcb-util-cursor'
  'xcb-util-image'
  'xcb-util-keysyms'
  'xcb-util-renderutil'
  'xcb-util-wm'
)
provides=('pozzo-launcher')
conflicts=('pozzo-launcher')
source=("https://github.com/erpaffo/Pozzo-Launcher/releases/download/v${pkgver}/PozzoLauncher-${pkgver}-linux-x64.tar.gz"
        "pozzo.desktop")
sha256sums=('<INSERIRE_SHA256_TAR_GZ>'
            'SKIP')

package() {
  # Cartella applicazione
  install -dm755 "${pkgdir}/opt/PozzoLauncher"
  cp -r "${srcdir}/PozzoLauncher/"* "${pkgdir}/opt/PozzoLauncher/"

  # Eseguibile globale nel PATH
  install -dm755 "${pkgdir}/usr/bin"
  ln -s /opt/PozzoLauncher/PozzoLauncher "${pkgdir}/usr/bin/pozzo"

  # Icona
  install -Dm644 "${srcdir}/PozzoLauncher/_internal/packaging/icon.png" \
    "${pkgdir}/usr/share/pixmaps/pozzo.png" 2>/dev/null || \
  install -Dm644 "${srcdir}/PozzoLauncher/packaging/icon.png" \
    "${pkgdir}/usr/share/pixmaps/pozzo.png" 2>/dev/null || true

  # Desktop Entry
  install -Dm644 "${srcdir}/pozzo.desktop" \
    "${pkgdir}/usr/share/applications/pozzo.desktop"

  # Licenza
  install -dm755 "${pkgdir}/usr/share/licenses/${pkgname}"
  echo "MIT License - Copyright (c) 2026 erpaffo" > "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
```

#### Pubblicazione su AUR:
```bash
git clone ssh://aur@aur.archlinux.org/pozzo-launcher-bin.git
cd pozzo-launcher-bin
# Copiare PKGBUILD e pozzo.desktop
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO pozzo.desktop
git commit -m "Release v0.16.0"
git push origin master
```

---

## 3. GitHub SEO, Profiling & Social Preview

### GitHub Topics & Tag Strategici

L'algoritmo di raccomandazione di GitHub (Explore, Trending e Topics search) indicizza i repository in base ai tag inseriti nelle impostazioni del repository.

#### Set di Topics raccomandati (Massimo 20 tag):

| Categoria | Tag GitHub | Obiettivo SEO |
|---|---|---|
| **Core Functions** | `game-launcher` `emulation-frontend` `rom-manager` `game-library` `metadata-scraper` | Essere trovati da chi cerca un gestore giochi/ROM |
| **Alternative & Confronti** | `playnite-alternative` `launchbox-alternative` `retroarch-frontend` `steam-alternative` | Intercettare utenti in cerca di alternative open/leggere |
| **Piattaforme & Hardware** | `steam-deck` `steamos` `retrogaming` `emulation` `pc-gaming` | Coinvolgere la community Steam Deck e retrocomputing |
| **Tech Stack & Feature** | `python` `pyside6` `qt6` `big-picture` `game-streaming` `media-center` | Attrarre sviluppatori Python/Qt e appassionati di UI |

> **Istruzioni operative**: Andare nella homepage del repo su GitHub (`https://github.com/erpaffo/Pozzo-Launcher`), cliccare sull'icona a forma di ingranaggio accanto a "About" e incollare tutti i tag sopra indicati separati da spazio.

---

### About Box: Descrizione & Link Ottimizzati

Il box "About" è il primo elemento mostrato da Google nei risultati di ricerca e da GitHub nelle card del catalogo. Ha un limite consigliato di 350 caratteri.

#### Testo in Inglese (Consigliato per il repo principale):
```text
🎮 Modern, lightweight and beautiful game launcher & retro ROM frontend for PC and Steam Deck. Auto-scrapes box art, descriptions & playtimes. Includes controller Big Picture mode, web streaming & zero bloat.
```

#### Testo in Italiano (Alternativa):
```text
🎮 Launcher giochi e frontend retrogaming moderno e leggero per PC e Steam Deck. Recupero automatico di copertine, trame e ore di gioco. Modalità Big Picture per controller e streaming web.
```

#### Website Link Configurato:
Impostare il campo **Website** su:
`https://erpaffo.github.io/Pozzo-Launcher/`

---

### Social Preview Card (1280x640px)

La Social Preview Card (Open Graph Image) viene visualizzata quando il link di GitHub viene condiviso su Discord, Reddit, Telegram, X/Twitter e WhatsApp. Un'immagine curata aumenta il Click-Through-Rate (CTR) di oltre il 300%.

#### Specifiche Tecniche:
- **Dimensioni**: Esattamente `1280 × 640 pixel` (rapporto d'aspetto `2:1`).
- **Formato**: PNG o JPEG ottimizzato (sotto 1 MB).
- **Safe Zone**: Mantenere testi, logo e mockup a una distanza di almeno **60px** dai bordi per evitare tagli sui display mobili.

#### Composizione Grafica Ideale:
1. **Sfondo**: Tema dark OLED elegante (`#0f141c` / `#161b22`) con sfumature sottili blu/viola.
2. **Elemento Centrale / Sinistro**:
   - Logo vettoriale di Pozzo ad alta risoluzione.
   - Titolo: **POZZO LAUNCHER** (Font bold sans-serif, es. Inter o Montserrat).
   - Payoff: *"Your Games. Every Console. One Beautiful Library."*
3. **Elemento Destro**:
   - Mockup inclinato 3D di uno **Steam Deck** con a schermo l'interfaccia Big Picture.
   - Screenshot fluttuante del **Layout Scaffali** o **Cinema** con copertine colorate.
4. **Footer Card**:
   - Pillole visive: `Windows` • `Linux` • `Steam Deck` • `Open Source (MIT)`.

> **Come caricarla**: Su GitHub, andare in **Settings › General › Social preview** e cliccare su **Edit › Upload an image**.

---

## 4. Gestione della Fiducia, SmartScreen & Falsi Positivi

### Perché compare Windows SmartScreen?

Gli eseguibili generati con PyInstaller / Inno Setup che non dispongono di un certificato di firma digitale commerciale **EV (Extended Validation)** — dal costo di diverse centinaia di euro all'anno — vengono bloccati da Microsoft SmartScreen con l'avviso:
> *"Windows ha protetto il tuo PC. Microsoft Defender SmartScreen ha impedito l'avvio di un'app non riconosciuta."*

Questo accade **non perché il file contenga malware**, ma perché l'eseguibile ha "zero reputazione crittografica" nei database Microsoft finché non viene scaricato ed eseguito da migliaia di utenti.

---

### Trasparenza e Build Riproducibili su GitHub Actions

Per rassicurare al 100% utenti, recensori e community:

1. **Compilazione su server pubblici GitHub**:
   Tutti gli eseguibili in `release/` sono compilati direttamente da GitHub Actions (`.github/workflows/release.yml`) su macchine virtuali Microsoft pulite (`windows-latest`).
   Chiunque può consultare il log di build pubblico passo dopo passo.

2. **Verifica Checksum SHA-256**:
   Ogni release include il file `SHA256SUMS.txt`. Gli utenti possono verificare che il file scaricato sia identico a quello prodotto dal server di build:
   ```powershell
   Get-FileHash .\PozzoLauncher-0.16.0-windows-x64-setup.exe -Algorithm SHA256
   ```

3. **Sezione "È sicuro?" nel README e nella Documentazione**:
   Inserire un chiarimento esplicito:
   > **Nota su Windows SmartScreen**: Essendo un progetto open-source senza scopo di lucro, Pozzo Launcher non utilizza un certificato EV a pagamento. Per avviare l'installer: clicca su **"Ulteriori informazioni"** e poi su **"Esegui comunque"**. Il codice sorgente è verificabile al 100% su GitHub.

---

### Scansione VirusTotal Automatizzata nel Workflow

È buona norma automatizzare l'analisi VirusTotal su GitHub Actions dopo ogni compilazione per allegare il report direttamente nelle note di rilascio.

Aggiungere al file `.github/workflows/release.yml` il seguente step:

```yaml
      - name: VirusTotal Scan (Automated)
        uses: crazy-max/ghaction-virustotal@v4
        with:
          vt_api_key: ${{ secrets.VIRUSTOTAL_API_KEY }}
          files: |
            release/*.exe
            release/*.zip
        continue-on-error: true
```

Il link al report pubblico dimostra all'utente che 70+ motori antivirus hanno analizzato e certificato il binario come pulito.

---

### Procedura Ufficiale Sottomissione Falsi Positivi (Microsoft WDSI)

Quando una nuova release fa scattare un falso positivo su Microsoft Defender, Microsoft mette a disposizione un portale dedicato agli sviluppatori per rimuovere il flag entro 24-48 ore.

#### Procedura Operativa:

1. Accedere al portale: **[Microsoft Defender Security Intelligence (WDSI) File Submission](https://www.microsoft.com/en-us/wdsi/filesubmission)**.
2. Effettuare il login con un account Microsoft.
3. Selezionare l'opzione **"Software Developer"**.
4. Compilare i dati richiesti:
   - **File to submit**: Caricare il file `PozzoLauncher-x.x.x-windows-x64-setup.exe`.
   - **Product Name**: `Pozzo Launcher`
   - **Company / Publisher**: `erpaffo`
   - **Application Version**: Es. `0.16.0`
   - **Detection Name**: Es. `Trojan:Win32/Wacatac...` o `Unrecognized Application`
   - **Comments**:
     ```text
     False positive detection. Pozzo Launcher is a verified open-source game launcher frontend built in Python and packaged with PyInstaller and Inno Setup.
     Full source code, build scripts and public GitHub Actions workflows are available at: https://github.com/erpaffo/Pozzo-Launcher
     No malicious code is present. Please analyze and whitelist this installer.
     ```
5. Inviare la richiesta. Microsoft assegnerà un ID ticket (es. `SUB-XXXXXX`).
6. Solitamente entro 12-24 ore i sistemi automatici di analisi cloud di Microsoft confermano il falso positivo e rilasciano un aggiornamento delle definizioni antivirus per Defender.
