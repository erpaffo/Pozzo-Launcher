# 🎮 Pozzo Launcher — Press Kit & Media Kit

> **Il launcher open-source, local-first e ad altissime prestazioni per ROM retro e giochi PC.**  
> Nessun account, nessuna telemetria, scraping istantaneo offline con database No-Intro/Redump, 7 layout intercambiabili al volo e una companion app per smartphone con giroscopio integrato e supporto secondo schermo.

---

## 📌 Indice dei Contenuti

1. [Elevator Pitch](#-elevator-pitch)
   - [Versione in 1 Frase](#1-versione-in-1-frase-one-liner)
   - [Versione in 1 Paragrafo](#2-versione-in-1-paragrafo-short-pitch)
   - [Versione in 3 Paragrafi](#3-versione-in-3-paragrafi-executive-summary)
2. [Why Pozzo? — Analisi Comparativa](#-why-pozzo--analisi-comparativa)
   - [Pozzo vs Playnite](#pozzo-vs-playnite)
   - [Pozzo vs LaunchBox / BigBox](#pozzo-vs-launchbox--bigbox)
   - [Pozzo vs RetroBat](#pozzo-vs-retrobat)
   - [Pozzo vs ES-DE (EmulationStation Desktop Edition)](#pozzo-vs-es-de)
   - [Tabella di Confronto Rapido](#tabella-di-confronto-rapido)
3. [Scheda Tecnica](#-scheda-tecnica)
4. [Killer Features Dettagliate](#-killer-features-dettagliate)
   - [1. Scraping Offline Istantaneo con DAT No-Intro / Redump](#1-scraping-offline-istantaneo-con-dat-no-intro--redump)
   - [2. Switch Dinamico tra 7 Layout & Temi Indipendenti](#2-switch-dinamico-tra-7-layout--temi-indipendenti)
   - [3. Smartphone Companion: Controller Virtuale, Giroscopio e Schermo DS](#3-smartphone-companion-controller-virtuale-giroscopio-e-schermo-ds)
   - [4. Big Picture Nativo da Divano](#4-big-picture-nativo-da-divano)
   - [5. Zero-Config per Store PC ed Eseguibili Custom](#5-zero-config-per-store-pc-ed-eseguibili-custom)
   - [6. Ecosistema Extra: Giochi Gratis, Radar Saldi, PC Ports e Discord](#6-ecosistema-extra-giochi-gratis-radar-saldi-pc-ports-e-discord)
5. [Galleria Asset & Schermate Ufficiali](#-galleria-asset--schermate-ufficiali)
6. [FAQ per Recensori e Giornalisti](#-faq-per-recensori-e-giornalisti)
7. [Bio del Creatore & Contatti](#-bio-del-creatore--contatti)

---

## 🚀 Elevator Pitch

### 1. Versione in 1 Frase (One-Liner)
**Pozzo Launcher è un launcher unificato open-source per giochi PC e decine di migliaia di ROM, con scraping istantaneo offline tramite hash DAT, 7 layout grafici intercambiabili al volo e una web app per smartphone che si trasforma in controller con giroscopio e secondo schermo touch.**

### 2. Versione in 1 Paragrafo (Short Pitch)
I videogiocatori moderni si dividono quotidianamente tra librerie PC frammentate (Steam, Epic, GOG, Game Pass) e immense collezioni di ROM emulate difficili da organizzare senza ore di scraping lento e rate-limited. **Pozzo Launcher** risolve questo caos unendo entrambi i mondi in un'unica interfaccia elegante, local-first e priva di telemetria. Riconosce i giochi retro in pochi secondi grazie all'hash matching offline con i cataloghi No-Intro e Redump, passa fluidamente tra 7 layout e 4 temi cromatici, offre una modalità Big Picture ottimizzata per controller e permette di usare qualsiasi smartphone come gamepad virtuale avanzato — completo di puntamento giroscopico e visualizzazione a doppio schermo per Nintendo DS/3DS.

### 3. Versione in 3 Paragrafi (Executive Summary)
**Il Problema:** Con il moltiplicarsi dei negozi digitali per PC e l'espansione del retrogaming, gestire la propria collezione è diventato un incubo di launcher separati, configurazioni complesse e frontend pesanti. I launcher esistenti costringono l'utente a scegliere tra tool lenti che consumano centinaia di megabyte di memoria, software a pagamento per sbloccare la modalità TV, o scraper online che si bloccano per limiti di traffico dopo aver processato una manciata di titoli.

**La Soluzione Pozzo:** Pozzo Launcher è stato costruito da zero secondo una filosofia locale, minimalista ed efficiente. Il suo motore di scansione adotta una pipeline a cascata: calcola l'hash delle ROM verificandole istantaneamente contro i cataloghi ufficiali No-Intro e Redump già memorizzati localmente, interrogando il web solo per arricchimenti estetici e rispettando in modo trasparente i server comunitari. Parallelamente rileva in automatico i giochi installati da Steam, Epic Games, GOG, Battle.net, Amazon Games e Xbox. Il risultato è una libreria unificata capace di navigare decine di migliaia di titoli con zero ritardi.

**L'Esperienza da Salotto e Mobile:** Oltre all'esperienza desktop arricchita da 7 layout (Catalogo, Scaffali, Console, Dashboard, Cinema, Vetrina e Originale) e supporto alle estensioni, Pozzo include una modalità Big Picture nativa da divano e un'innovativa PWA locale per smartphone. Senza scaricare app da store terzi, il cellulare diventa telecomando, controller Xbox virtuale per 4 giocatori con supporto DSU motion (per Cemu, Dolphin, Ryujinx), e persino schermo touch inferiore per gli emulatori di Nintendo DS e 3DS con streaming ultra-basso ritardo.

---

## ⚔️ Why Pozzo? — Analisi Comparativa

Perché un recensore o un giocatore appassionato dovrebbe preferire Pozzo Launcher rispetto ai pesi massimi del settore? Ecco un'analisi trasparente e rigorosa:

### Pozzo vs Playnite
- **Architettura & Performance:** Playnite si basa sull'ecosistema .NET/WPF, storicamente legato a Windows e incline a consumare ingenti risorse RAM con librerie che superano i 20.000 elementi. Pozzo combina un backend ultrarapido in Python/FastAPI con un frontend web reattivo moderno, riducendo l'impronta di sistema e garantendo compatibilità multipiattaforma (Windows, macOS Apple Silicon e Linux).
- **Gestione ROM & Scraping:** Su Playnite l'aggiunta di ROM richiede spesso plugin ed estensioni di terze parti, con scraping online sequenziale soggetto a frequenti blocchi per rate-limit. Pozzo include il riconoscimento offline istantaneo tramite hash No-Intro/Redump e pipeline a cascata nativa.
- **Funzionalità Smartphone:** Playnite non offre un sistema integrato out-of-the-box per trasformare lo smartphone in controller fisico virtuale (ViGEmBus) con giroscopio DSU o secondo display per DS.

### Pozzo vs LaunchBox / BigBox
- **Costi & Licenza:** LaunchBox riserva la sua celebre interfaccia "BigBox" (da divano/controller) a un modello a pagamento con licenza annuale o a vita ($30–$75). Pozzo Launcher è **100% Free and Open Source Software (FOSS)** con licenza MIT: la modalità Big Picture è gratuita per tutti, per sempre.
- **Peso e Requisiti:** BigBox richiede hardware grafico moderno e pesa svariati gigabyte con installazioni ricche. Pozzo genera eseguibili compatti (portatili o installer) che girano fluidamente anche su mini PC da salotto economici, Raspberry/Linux o macchine datate.

### Pozzo vs RetroBat
- **Focus del Software:** RetroBat è una distribuzione Windows incentrata quasi esclusivamente sull'emulazione (wrapper attorno a EmulationStation e RetroArch). Non gestisce nativamente i moderni negozi PC (Steam, Epic, GOG, Xbox) come libreria integrata unificata.
- **Personalizzazione al Volo:** In RetroBat il cambio tema richiede spesso il riavvio o lunghe navigazioni nei menu XML. Pozzo consente di passare tra 7 modalità d'uso completamente differenti (dallo scaffale 3D alla visuale console compatta) con un solo clic o con il controller.

### Pozzo vs ES-DE (EmulationStation Desktop Edition)
- **Flessibilità e Dinamismo:** ES-DE è fantastico per postazioni dedicate, ma è rigido per un uso desktop ibrido e richiede configurazioni manuali complesse per lanciare file `.exe` o giochi moderni.
- **Esperienza Mobile:** ES-DE non espone server web locali PWA protetti con profili crittografici, telecomando remoto, gestione attività in background o supporto a giroscopi di rete.
- **Interoperabilità:** Pozzo non si isola: include nativamente l'opzione di esportazione verso i formati compatibili con ES-DE e Pegasus Frontend, consentendo agli utenti di generare librerie per i propri dispositivi portatili (Anbernic, Miyoo, Steam Deck).

---

### Tabella di Confronto Rapido

| Caratteristica | Pozzo Launcher | Playnite | LaunchBox | RetroBat | ES-DE |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Licenza & Prezzo** | **100% Open Source (MIT)** | Open Source (BSD) | Commerciale / Freemium ($30-$75) | Open Source (GPL) | Donazione / FOSS |
| **Piattaforme** | **Windows, macOS, Linux** | Solo Windows | Solo Windows (Android parziale) | Solo Windows | Windows, macOS, Linux, Android |
| **Big Picture (Controller UI)** | **Incluso & Gratuito** | Incluso | A pagamento (BigBox) | Incluso | Incluso |
| **Scraping Offline (DAT CRC)** | **Nativo (No-Intro/Redump)** | Solo via plugin | No (solo online) | Limitato | No (solo online) |
| **Librerie PC (Steam/Epic/GOG)** | **Zero-Config Integrato** | Nativo | Nativo | Limitato / Manuale | Molto Complesso |
| **Layout Intercambiabili** | **7 Layout + 4 Temi al volo** | 3 Viste | Pochi temi liberi | Temi XML | Temi XML |
| **Smartphone Controller + Gyro** | **Nativo (PWA + ViGEm + DSU)** | Assente | Assente | Assente | Assente |
| **Schermo Touch DS su Smartphone** | **Nativo Integrato** | Assente | Assente | Assente | Assente |
| **Privacy (No Telemetria)** | **100% Local-First** | Ottima | Buona | Ottima | Ottima |

---

## 🛠 Scheda Tecnica

- **Nome Prodotto:** Pozzo Launcher
- **Versione Attuale:** 0.16.x (in costante aggiornamento)
- **Autore & Lead Developer:** Francesco (`@erpaffo` / `sassoanarchico`)
- **Repository Ufficiale:** [github.com/erpaffo/Pozzo-Launcher](https://github.com/erpaffo/Pozzo-Launcher)
- **Documentazione Online:** [erpaffo.github.io/Pozzo-Launcher](https://erpaffo.github.io/Pozzo-Launcher/)
- **Licenza:** MIT License (Permissiva, libera per qualsiasi uso e modifica)
- **Linguaggio Core:** Python 3.10+ (Server asincrono ad alta efficienza)
- **Architettura Server:** FastAPI, HTTP/2 asincrono (`httpx`), SQLite3 ad altissima indicizzazione
- **Interfaccia Grafica:** SPA Web ad altissima reattività (HTML5 moderno, CSS Grid/Flexbox dinamico, Vanilla JavaScript senza overhead di framework pesanti)
- **Piattaforme Supportate:**
  - **Windows:** 10 / 11 (64-bit) — Installer con autoupdater differenziale o archivio zip portatile
  - **macOS:** 11+ Big Sur, Monterey, Ventura, Sonoma (Apple Silicon arm64 .dmg e .zip)
  - **Linux:** Distribuzioni x86_64 basate su Debian/Ubuntu/Mint (.deb) e archivio generico (.tar.gz)
- **Integrazioni Esterne:** Steam, Epic Games, GOG Galaxy, Amazon Games, Battle.net, Xbox App, RetroAchievements, Discord RPC, Spotify, Sunshine / Moonlight, ViGEmBus, DSU Cemuhook Protocol.
- **Privacy Policy:** 100% Local-First. Zero server proprietari, zero login di terze parti per usare il software, zero telemetria o statistiche di utilizzo trasmesse. Database e configurazioni salvati esclusivamente sul disco locale.

---

## 💎 Killer Features Dettagliate

### 1. Scraping Offline Istantaneo con DAT No-Intro / Redump
Mentre i frontend tradizionali interrogano i server web per ogni singolo file — esaurendo rapidamente i limiti orari delle API di ScreenScraper o IGDB — Pozzo Launcher calcola in parallelo l'hash CRC32/SHA1 della ROM e lo confronta istantaneamente con i database No-Intro e Redump inclusi localmente. Riconosce il 90%+ della libreria in pochi secondi senza connessione internet. I servizi cloud vengono contattati a velocità controllata solo per copertine e dettagli mancanti, salvando tutto nella cache SQLite locale.

### 2. Switch Dinamico tra 7 Layout & Temi Indipendenti
Pozzo non impone un unico modo di vedere i giochi. Attraverso il pannello Aspetto o con comandi rapidi è possibile passare istantaneamente tra:
- **Catalogo:** Schede dettagliate con copertina, trame e metadati in primo piano.
- **Scaffali:** Prospettiva visiva a mensola che richiama la collezione fisica.
- **Console:** Barra laterale pulita e griglia ultra-compatta ottimizzata per l'esplorazione veloce.
- **Dashboard:** Schermata riassuntiva con statistiche, giochi recenti e scorciatoie preferite.
- **Cinema:** Visualizzazione ad alto impatto con video-anteprime, sfondi a tutto schermo e colonne sonore.
- **Vetrina:** Focus elegante sul gioco selezionato con carousel animato.
- **Originale:** La visuale classica solida e funzionale.  
I layout possono essere combinati liberamente con 4 temi indipendenti (**Chiaro**, **Notte Blu**, **OLED High-Contrast** e **Retrò Vintage**).

### 3. Smartphone Companion: Controller Virtuale, Giroscopio e Schermo DS
Una delle innovazioni più sorprendenti di Pozzo. Inquadrando un QR code sulla rete locale con qualsiasi smartphone (iOS o Android), il telefono installa una Progressive Web App (PWA) protetta da certificato locale emesso dal PC:
- **Virtual Gamepad Xbox:** Fino a 4 smartphone contemporanei si collegano tramite il driver ViGEmBus, diventando gamepad a latenza bassissima per sfide multiplayer immediate.
- **Skin Adattive:** Il layout dei tasti si trasforma automaticamente a seconda del gioco avviato (PlayStation, Nintendo Switch, GameCube, Arcade 6 tasti, telecomando Buzz!, chitarra Rock Band o volante inclinabile).
- **Giroscopio & Puntamento DSU:** I sensori di movimento dello smartphone vengono trasmessi in protocollo DSU/cemuhook a emulatori come Cemu, Dolphin, Ryujinx e Citra, abilitando il motion-aiming e i minigiochi basati sul movimento.
- **Doppio Schermo per Nintendo DS e 3DS:** Il telefono si trasforma nel touchscreen inferiore di melonDS o Citra/Lime3DS! Mentre il monitor del PC mostra lo schermo superiore in glorioso 4K, lo smartphone gestisce comandi touch e visuale secondaria senza ingombrare la visuale principale.

### 4. Big Picture Nativo da Divano
Nessun costo aggiuntivo, nessun plugin instabile: premendo il pulsante Guida o premendo F11 / scorciatoia dedicata, Pozzo Launcher si trasforma in una gloriosa interfaccia Fullscreen navigabile al 100% tramite qualsiasi gamepad (Xbox, PlayStation, Switch Pro o generico DirectInput). Grafica fluida a 60/120 FPS, testi ad alta leggibilità pensati per TV da 55-75 pollici, e menu rapidi per sospendere, chiudere o cambiare gioco senza toccare mouse o tastiera.

### 5. Zero-Config per Store PC ed Eseguibili Custom
Pozzo unifica il PC gaming moderno e il retrogaming:
- Riconoscimento automatico delle librerie installate di **Steam, Epic Games, GOG, Amazon Games, Battle.net e Xbox**.
- Aggiunta manuale di qualsiasi file `.exe`, script o applicazione con ricerca automatica delle copertine e metadati.
- Possibilità di configurare **companion apps** per ogni gioco (es. avviare automaticamente un deck-tracker per giochi di carte, un software di modding o software di rimappatura controller e chiuderli insieme al gioco).

### 6. Ecosistema Extra: Giochi Gratis, Radar Saldi, PC Ports e Discord
Pozzo Launcher include strumenti che nessun altro launcher integra di base:
- **Radar Giochi Gratis & Offerte:** Notifiche automatiche sui titoli regalati settimanalmente da Epic Games, Steam, GOG e offerte monitorate su IsThereAnyDeal e GG.deals.
- **Database PC Ports:** Trova e installa con un clic i porting nativi su PC di classici per console (es. Super Mario 64 PC Port, Ship of Harkinian per Ocarina of Time, ecc.).
- **Discord & Spotify Integration:** Presenza ricca su Discord (con tasti rapidi a schermo per mutare o silenziare il microfono senza aprire l'overlay Discord) e comandi multimediali per controllare Spotify in background mentre si gioca.

---

## 📸 Galleria Asset & Schermate Ufficiali

Tutti gli asset grafici in alta risoluzione sono disponibili all'interno del repository ufficiale nella cartella [`docs/img/`](file:///c:/Users/paffe/OneDrive/Desktop/GameScraper/docs/img) e [`docs/images/`](file:///c:/Users/paffe/OneDrive/Desktop/GameScraper/docs/images):

- **Interfaccia Principale & Dettaglio Gioco:**
  - `docs/img/libreria.jpg` — Panoramica della libreria unificata con copertine e filtri.
  - `docs/img/dettaglio.jpg` — Scheda informativa del gioco con screenshot, valutazioni, tempi e salvataggi.
- **Big Picture Mode:**
  - `docs/img/bigpicture.jpg` — Interfaccia navigabile a controller a schermo intero per TV da salotto.
- **I 7 Layout a Confronto:**
  - `docs/img/esp-catalogo.jpg` — Layout Catalogo.
  - `docs/img/esp-scaffali.jpg` — Layout Scaffali.
  - `docs/img/esp-console.jpg` — Layout Console.
  - `docs/img/esp-dashboard.jpg` — Layout Dashboard.
  - `docs/img/esp-cinema.jpg` — Layout Cinema.
  - `docs/img/esp-vetrina.jpg` — Layout Vetrina.
- **I 4 Temi Visivi:**
  - `docs/img/tema-chiaro.jpg` — Tema Chiaro pulito.
  - `docs/img/tema-notte-blu.jpg` — Tema Notte Blu riposante.
  - `docs/img/tema-oled.jpg` — Tema Nero Assoluto per pannelli OLED.
  - `docs/img/tema-retro.jpg` — Tema Retrò Vintage ad atmosfera anni '90.
- **Mobile Companion & Innovazioni:**
  - `docs/images/telefono.jpg` — Web app responsive sul telefono con interfaccia e controller.
  - `docs/images/impostazioni-telefono.jpg` — Procedura di pairing con QR code e certificati sicuri.
  - `docs/img/estensioni.jpg` — Store interno per estensioni e plugin della community.
- **Logo Ufficiale:**
  - `docs/images/icon.png` — Logo vettoriale / PNG ad alta risoluzione di Pozzo Launcher.

---

## ❓ FAQ per Recensori e Giornalisti

#### 1. Pozzo Launcher include o distribuisce giochi, ROM o file BIOS?
**Assolutamente no.** Pozzo Launcher è un software di gestione catalogo e frontend. Non contiene, non ospita e non distribuisce materiale protetto da copyright. Gli utenti importano le proprie collezioni legittime e configurano i propri emulatori ed eseguibili in totale conformità con le leggi locali.

#### 2. Come fa Pozzo a scansionare 20.000 ROM in pochissimi minuti senza blocchi API?
La maggior parte dei launcher invia richieste HTTP per ogni singolo file a database comunitari online, incappando rapidamente nei rate-limit orari (o costringendo a pagare abbonamenti API premium). Pozzo calcola l'hash CRC locale dei file e lo confronta istantaneamente in locale con gli indici ufficiali No-Intro e Redump inclusi nel software. Il 90%+ dei file viene riconosciuto a velocità di disco SSD; solo i dati grafici non presenti vengono scaricati in modo scaglionato e rispettoso delle policy di rete.

#### 3. È davvero necessario installare un'app nativa dallo store sul telefono per il controller?
No, ed è uno dei maggiori punti di forza. Pozzo Launcher crea un server locale HTTPS sicuro. Qualsiasi smartphone moderno (iOS o Android) inquadra il QR code generato dal PC e apre istantaneamente una Progressive Web App (PWA) che può essere salvata sulla home screen. Grazie alle Web API standard e alla crittografia locale certificata, l'app accede ai sensori del giroscopio e al touch a 60 FPS senza dover passare da App Store o Google Play.

#### 4. È davvero 100% gratuito o ci sono feature bloccate dietro "Paywall"?
Pozzo Launcher è rilasciato sotto licenza permissiva **MIT**. L'intero codice sorgente è pubblico su GitHub. Non esistono abbonamenti, acquisti in-app, versioni "Pro" o telemetrie pubblicitarie. Ogni funzionalità — inclusa la modalità Big Picture e il controller mobile — è accessibile liberamente a tutti gli utenti.

#### 5. Funziona su Steam Deck, ROG Ally e Legion Go?
Sì. Essendo compatibile sia con Linux che con Windows e disponendo di build dedicate per controller e scorciatoie per tastiere virtuali, Pozzo si presta perfettamente all'installazione su dispositivi portatili come Steam Deck (in modalità Desktop o aggiunta come gioco non-Steam) e handheld basati su Windows 11.

#### 6. In che modo Pozzo garantisce la privacy dei miei account Steam ed Epic?
Pozzo è un'applicazione **100% local-first**. Rileva i giochi installati leggendo i file manifest e di registro locali presenti sul computer. Non richiede l'inserimento di password personali su server remoti di terze parti e non invia alcun dato a server esterni proprietari. I dati di gioco rimangono unicamente all'interno della cartella dell'applicazione sul disco dell'utente.

---

## 👤 Bio del Creatore & Contatti

### Informazioni sullo Sviluppatore
**Pozzo Launcher** è stato ideato e sviluppato da **Francesco** (`erpaffo` su GitHub), sviluppatore indipendente appassionato di software libero, conservazione del videogioco e design dell'interfaccia utente. Il progetto nasce dalla volontà di superare la frammentazione e la lentezza dei frontend tradizionali, offrendo alla community una soluzione rapida, solida, senza abbonamenti a pagamento e capace di sfruttare in modo intelligente i dispositivi già presenti nelle case dei giocatori (come lo smartphone).

### Canali Ufficiali & Riferimenti Stampa
- **GitHub Repository:** [https://github.com/erpaffo/Pozzo-Launcher](https://github.com/erpaffo/Pozzo-Launcher)
- **Documentazione Completa:** [https://erpaffo.github.io/Pozzo-Launcher/](https://erpaffo.github.io/Pozzo-Launcher/)
- **Release & Download:** [https://github.com/erpaffo/Pozzo-Launcher/releases](https://github.com/erpaffo/Pozzo-Launcher/releases)
- **Segnalazione Bug & Feature Request:** [Issue Tracker Ufficiale](https://github.com/erpaffo/Pozzo-Launcher/issues)
- **Richieste Stampa, Interviste e Supporto Media:** Contattare l'autore tramite il profilo GitHub ufficiale o via issue dedicate con etichetta `[press/media]`.
