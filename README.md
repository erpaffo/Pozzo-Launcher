# Pozzo Launcher

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

- **Scraping veloce**. Le ROM vengono riconosciute offline (CRC e nome sui DAT No-Intro/Redump), e le fonti online si interrogano solo per quello che manca, rispettando i loro limiti. Se si interrompe, riprende da dove era rimasto.
- Una libreria in stile Playnite, con console e store insieme. Le versioni regionali vengono unite, ci sono preferiti (anche per console), stati, collezioni, ricerca e filtri, e regge anche decine di migliaia di giochi. In alto c'è una barra dei menu per arrivare subito alle azioni e alle impostazioni più usate.
- **Giochi PC** da Steam, Epic, GOG, Amazon, Battle.net, Xbox e altri, accanto alle ROM. Puoi aggiungere a mano qualsiasi `.exe`, gioco o applicazione che sia: compare subito, copertina e dati arrivano dopo. Ogni gioco può anche avviare altre applicazioni insieme a sé, per esempio un deck tracker.
- **Big Picture**: schermo intero pensato per il controller, anche dal divano.
- Dal telefono sfogli e avvii i giochi, e il telefono fa anche da controller (giroscopio compreso). Per lo streaming ci sono Sunshine e Moonlight.
- Gli **store online** sono elenchi di giochi presi da altri siti, che compaiono come «store» di ogni console.
- Sette grafiche (Catalogo, Scaffali, Console, Dashboard, Cinema, Vetrina, Originale) e i temi chiaro, notte blu, OLED e retrò, da combinare come vuoi.
- **Estensioni** da installare dallo store dentro l'app: cosa gioco stasera, obiettivi, calendario uscite, diario di gioco…
- Poi gli extra: giochi gratis, lista desideri con prezzi, port PC, copie dei salvataggi, Discord (anche muto, sordo ed esci dalla chiamata), Spotify e tasti multimediali, scorciatoie da tastiera, esportazione per ES-DE e Pegasus.

## Download

Gli eseguibili sono nella pagina **[Releases](https://github.com/erpaffo/Pozzo-Launcher/releases)**:

| Sistema | Installer | Portatile |
|---|---|---|
| Windows 10/11 (64 bit) | `PozzoLauncher-<versione>-windows-x64-setup.exe` | `…-windows-x64.zip`: estrai e apri `PozzoLauncher.exe` |
| macOS 11+ (Apple Silicon) | `…-macos-arm64.dmg`: trascina l'app in Applicazioni | `…-macos-arm64.zip` |
| Linux (64 bit) | `pozzo_<versione>_amd64.deb` (Debian, Ubuntu, Mint…) | `…-linux-x64.tar.gz` |

Gli eseguibili non sono firmati: su Windows SmartScreen chiede conferma (*Ulteriori informazioni › Esegui comunque*), su macOS la prima volta apri l'app con clic destro › Apri.

Quando esce una versione nuova compare un avviso. La installi con un clic da **Impostazioni › Info** (**⬇ Installa e riavvia**) e i tuoi dati restano dove sono.

## Per iniziare

1. Apri Pozzo Launcher e scegli la cartella delle ROM in **Impostazioni › Nuovi giochi**.
2. Avvia la ricerca: la libreria si riempie, e copertine e dati arrivano in sottofondo.
3. Per i giochi PC, collega gli store da **Impostazioni › Store**.

Configurazione, cache e libreria stanno nella cartella dell'utente (`%LOCALAPPDATA%\PozzoLauncher` su Windows, `~/Library/Application Support/PozzoLauncher` su macOS, `~/.local/share/PozzoLauncher` su Linux). Tutto il resto (credenziali delle fonti, comandi da terminale, store online, telefono, estensioni) è nel [manuale](https://erpaffo.github.io/Pozzo-Launcher/).

## Dai sorgenti

```powershell
python -m pip install -r requirements.txt
python -m pozzo app          # apre l'app
python -m pozzo run          # solo scansione e scraping, da terminale
```

Struttura del codice, come creare gli eseguibili e prestazioni: [Sviluppo](docs/sviluppo.md). Per contribuire: [CONTRIBUTING.md](CONTRIBUTING.md).

## Avvertenze

Pozzo Launcher è un gestore di librerie: **non contiene, non ospita e non distribuisce giochi, ROM, BIOS o chiavi**. Usalo con giochi che possiedi legalmente e nel rispetto delle leggi del tuo paese e dei termini dei siti a cui ti colleghi: la responsabilità dei contenuti che aggiungi è tua.

I nomi e i marchi di console, giochi e store citati appartengono ai rispettivi proprietari. Pozzo Launcher non è affiliato né approvato da nessuno di loro.

[Privacy](PRIVACY.md) · [Sicurezza](SECURITY.md) · [Codice di condotta](CODE_OF_CONDUCT.md) · [Componenti di terze parti](THIRD_PARTY_NOTICES.md)
