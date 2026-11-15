# Pozzo Launcher

[English](README.md) · **Italiano**

[![Test](https://github.com/erpaffo/Pozzo-Launcher/actions/workflows/ci.yml/badge.svg)](https://github.com/erpaffo/Pozzo-Launcher/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/erpaffo/Pozzo-Launcher)](https://github.com/erpaffo/Pozzo-Launcher/releases/latest)
[![Manuale](https://img.shields.io/badge/manuale-online-blue)](https://erpaffo.github.io/Pozzo-Launcher/)

Pozzo Launcher mette insieme le ROM di ogni console e i giochi PC degli store. Copertine, descrizioni, valutazioni e durate le recupera da solo. Poi giochi dal desktop, da Big Picture con il controller, dal telefono o in streaming.

**[Manuale completo](https://erpaffo.github.io/Pozzo-Launcher/)** · **[Download](https://github.com/erpaffo/Pozzo-Launcher/releases)** · **[Changelog](changelog.md)**

<p align="center">
  <img src="docs/img/libreria.jpg" width="49%" alt="La libreria">
  <img src="docs/img/dettaglio.jpg" width="49%" alt="Scheda di un gioco">
</p>
<p align="center">
  <img src="docs/img/bigpicture.jpg" width="49%" alt="Big Picture, per il controller">
  <img src="docs/img/estensioni.jpg" width="49%" alt="Store delle estensioni">
</p>
<p align="center"><sub>Libreria di esempio con giochi di fantasia.</sub></p>

### Grafiche

Una grafica non cambia solo i colori ma il modo in cui sfogli la libreria. Si sceglie da **Impostazioni › Aspetto**.

<p align="center">
  <img src="docs/img/esp-catalogo.jpg" width="49%" alt="Grafica Catalogo">
  <img src="docs/img/esp-scaffali.jpg" width="49%" alt="Grafica Scaffali">
</p>
<p align="center">
  <img src="docs/img/esp-console.jpg" width="49%" alt="Grafica Console, con barra laterale stretta">
  <img src="docs/img/esp-dashboard.jpg" width="49%" alt="Grafica Dashboard">
</p>
<p align="center">
  <img src="docs/img/esp-cinema.jpg" width="49%" alt="Grafica Cinema">
  <img src="docs/img/esp-vetrina.jpg" width="49%" alt="Grafica Vetrina">
</p>
<p align="center"><sub>Catalogo · Scaffali · Console · Dashboard · Cinema · Vetrina (c'è anche Originale, la vista storica).</sub></p>

### Temi

I temi sono indipendenti dalla grafica e si possono combinare.

<p align="center">
  <img src="docs/img/tema-chiaro.jpg" width="49%" alt="Tema Chiaro">
  <img src="docs/img/tema-notte-blu.jpg" width="49%" alt="Tema Notte blu">
</p>
<p align="center">
  <img src="docs/img/tema-oled.jpg" width="49%" alt="Tema OLED">
  <img src="docs/img/tema-retro.jpg" width="49%" alt="Tema Retrò">
</p>
<p align="center">
  <img src="docs/img/aspetto.jpg" width="60%" alt="Impostazioni, sezione Aspetto">
</p>

## Cosa fa

- **Scraping veloce e importatori**. Le ROM vengono riconosciute offline (CRC e nome sui DAT No-Intro/Redump, più supporto Nintendo Switch 2 / Eglantine `.nup`/NSP/cartelle), e le fonti online si interrogano solo per quello che manca, rispettando i loro limiti. Se si interrompe, riprende da dove era rimasto. Puoi anche importare playlist di Steam ROM Manager e RetroArch con anteprima.
- Una libreria in stile Playnite, con console e store insieme. Le versioni regionali vengono unite, ci sono preferiti (anche per console), stati, collezioni, filtri salvati, ricerca e **3 layout per la scheda gioco** (Classico, Cockpit a 2 colonne, Editoriale + pannello laterale); regge anche decine di migliaia di giochi. In alto c'è la barra dei menu e la palette comandi (`Ctrl+K`) per arrivare subito ad azioni e impostazioni.
- **Giochi PC** da Steam, Epic, GOG, Amazon, Battle.net, Xbox, Riot, Minecraft, Cartella di rete e librerie condivise **Pozzo remoto**, accanto alle ROM — anche senza client tramite SteamCMD, `legendary`, `gogdl` e `nile`. Aggiungi a mano qualsiasi `.exe` o gioco web, con automazioni per singolo gioco (script prima/dopo, estrazione temporanea archivi, risoluzione/HDR/energia, upscaling Magpie, remap controller ViGEmBus/HidHide, batteria e barra LED DualSense/DS4).
- **Gioca ovunque**: desktop, **Big Picture** per il controller, **Gioca nel browser** (EmulatorJS per console retro e Ruffle per Flash), installazione emulatori e core RetroArch in un clic (con bezel, shader e trucchi) e **Overlay in partita** multipiattaforma (`Ctrl+Shift+O` / `Select+R3`) con notifiche obiettivi in tempo reale.
- Dal telefono sfogli e avvii i giochi, lo usi come controller (giroscopio compreso) o ascolti l'audio. Per giocare a distanza ci sono Sunshine e Moonlight, oltre a **Partita con un amico** (RetroArch Netplay / Eden).
- **Store online e gestore download integrato**: sfogli elenchi di giochi da siti esterni e scarichi tramite HTTP multi-segmento, Torrent/Magnet nativo o servizi debrid/hoster — con categorie, filtri automatici RSS, cartella `.torrent` osservata, interfaccia VPN con kill switch, Click'n'Load e pausa automatica su disco pieno.
- **Sette grafiche** (Catalogo, Scaffali, Console, Dashboard, Cinema, Vetrina, Originale), **5 temi integrati** (Predefinito, Chiaro, Notte blu, OLED, Retrò), **Preset esperienza** e **Editor dei temi** integrato (cursori HSL, controllo contrasto WCAG, importa/esporta `.pozzo-theme.json`).
- **22 Estensioni** nello store dentro l'app: statistiche, cosa gioco stasera, anniversari retro, pulizia libreria, diario di gioco, limite di tempo, obiettivi personali, riepilogo annuale, SteamGridDB, calendario uscite, notizie videogiochi, il mio PC ce la fa?, recensioni e punteggi, sconti e bundle, media locale, ricette web, media server Jellyfin/Plex, Twitch e YouTube, eventi e fiere, speedrun…
- **Guidato e sicuro**: tour iniziale, **30 tutorial interattivi**, **61 suggerimenti contestuali**, **6 lingue dell'interfaccia** (italiano, inglese, francese, spagnolo, portoghese, tedesco), backup automatici a rotazione, verifica Ed25519/SHA-256 sugli aggiornamenti, API locale `/api/v1`, più giochi gratis, lista desideri con prezzi, port PC, Discord (muto/sordo/esci dalla chiamata), Spotify, scorciatoie da tastiera ed esportazione per ES-DE, Pegasus e Steam.

## Download

Gli eseguibili sono nella pagina **[Releases](https://github.com/erpaffo/Pozzo-Launcher/releases)**:

| Sistema | Installer | Portatile |
|---|---|---|
| Windows 10/11 (64 bit) | `PozzoLauncher-<versione>-windows-x64-setup.exe` | `…-windows-x64.zip`: estrai e apri `PozzoLauncher.exe` |
| macOS 11+ (Apple Silicon) | `…-macos-arm64.dmg`: trascina l'app in Applicazioni | `…-macos-arm64.zip` |
| Linux (64 bit) | `pozzo_<versione>_amd64.deb` (Debian, Ubuntu, Mint…) | `…-linux-x64.tar.gz` |

Gli eseguibili non sono firmati: su Windows SmartScreen chiede conferma (*Ulteriori informazioni › Esegui comunque*), su macOS la prima volta apri l'app con clic destro › Apri.

Quando esce una versione nuova compare un avviso. La installi con un clic da **Impostazioni › Sistema** (**⬇ Installa e riavvia**) e i tuoi dati restano dove sono.

## Per iniziare

1. Apri Pozzo Launcher e scegli la cartella delle ROM in **Impostazioni › Libreria**.
2. Avvia la ricerca: la libreria si riempie, e copertine e dati arrivano in sottofondo.
3. Per i giochi PC, collega gli store da **Impostazioni › Store e account**.

Configurazione, cache e libreria stanno nella cartella dell'utente (`%LOCALAPPDATA%\PozzoLauncher` su Windows, `~/Library/Application Support/PozzoLauncher` su macOS, `~/.local/share/PozzoLauncher` su Linux). Tutto il resto (credenziali delle fonti, comandi da terminale, store online, telefono, estensioni) è nel [manuale](https://erpaffo.github.io/Pozzo-Launcher/) (disponibile in italiano e inglese; l'interfaccia dell'app è tradotta in 6 lingue).

## Dai sorgenti

```powershell
python -m pip install -r requirements.txt
python -m pozzo app          # apre l'app
python -m pozzo run          # solo scansione e scraping, da terminale
```

Struttura del codice, come creare gli eseguibili e prestazioni: [Sviluppo](docs/sviluppo.md). Per contribuire: [CONTRIBUTING.md](CONTRIBUTING.it.md).

## Avvertenze

Pozzo Launcher è un gestore di librerie: **non contiene, non ospita e non distribuisce giochi, ROM, BIOS o chiavi**. Usalo con giochi che possiedi legalmente e nel rispetto delle leggi del tuo paese e dei termini dei siti a cui ti colleghi: la responsabilità dei contenuti che aggiungi è tua.

I nomi e i marchi di console, giochi e store citati appartengono ai rispettivi proprietari. Pozzo Launcher non è affiliato né approvato da nessuno di loro.

[Privacy](PRIVACY.it.md) · [Sicurezza](SECURITY.it.md) · [Codice di condotta](CODE_OF_CONDUCT.md) · [Componenti di terze parti](THIRD_PARTY_NOTICES.md)
