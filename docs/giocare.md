# Giocare

## Configurare gli emulatori

Gli emulatori si configurano in **Impostazioni › Emulatori**, in due tabelle.

### Installare gli emulatori dall'app

**Installa emulatori**, in cima alla pagina, scarica con un clic l'ultima versione ufficiale di RetroArch, Dolphin,
PPSSPP, DuckStation, PCSX2, RPCS3, Vita3K, melonDS, Azahar, Cemu, Xenia Canary, xemu, Flycast e shadPS4 e la imposta da
sola. La versione viene dalle release GitHub di ogni progetto; RetroArch, Dolphin e PPSSPP si scaricano dal loro sito
ufficiale. Gli emulatori vanno nella cartella indicata sotto (altrimenti in `Emulatori`, accanto alle impostazioni).
**↻ Aggiorna** installa la versione nuova sopra quella vecchia: configurazione e dati nella cartella dell'emulatore
restano. **⬇ Scarica i core** prende dal buildbot di libretro i core di RetroArch che mancano alle console della
libreria. Ryujinx ed Eden non pubblicano su GitHub: si installano a mano. Solo Windows.

Gli emulatori sono dei loro sviluppatori: Pozzo scarica le build che pubblicano, senza modificarle, e ogni riga porta
al progetto originale.

**Programmi**: un percorso per emulatore, valido per tutte le console che lo usano. **🔍 Trova emulatori** cerca in
una cartella gli eseguibili conosciuti: RetroArch, Ryujinx, Eden, melonDS, Dolphin, PCSX2, DuckStation, PPSSPP,
RPCS3, Vita3K, Azahar, Cemu, Xenia, xemu, Flycast, shadPS4, SharpEmu. **＋ Aggiungi un altro emulatore** aggiunge un programma
qualsiasi.

**Cerca emulatori già installati**: in cima alla pagina, questo pulsante esegue una scansione rapida del PC (circa 4 secondi)
ispezionando le cartelle di sistema standard (Programmi, Winget, Scoop, librerie di Steam e registro di Windows) per trovare
gli emulatori già presenti. Se ne trova uno, lo propone con il pulsante **Usa questo**: nessuna impostazione viene cambiata
senza la tua conferma. Se un emulatore è già installato, il pulsante **Installa** non lo riscarica.

**Mappatura automatica del controller negli emulatori**: per Dolphin, PCSX2, DuckStation, RPCS3 e RetroArch, l'app
include profili di mappatura ottimali per i controller più diffusi (Xbox XInput, PlayStation DualSense e DualShock 4, Nintendo
Switch Pro). Il profilo si applica automaticamente quando installi un emulatore per la prima volta, oppure a mano da
**Impostazioni › Controller › Mappa i tasti negli emulatori**. Prima di qualsiasi scrittura viene creata una copia di backup
del file di configurazione originale, e le impostazioni personalizzate già esistenti non vengono mai sovrascritte senza richiesta.

**Emulatore per console**: per ogni console scegli

- l'**emulatore**: *Automatico* usa il primo installato tra quelli consigliati per quella console; *Altro…* permette
  qualsiasi emulatore esterno;
- il **core** di RetroArch, se la console usa RetroArch;
- gli **argomenti**: `{rom}` è il file del gioco, `{core}` il core di RetroArch.

La colonna **Stato** dice cosa manca (emulatore non trovato, core assente…). Le scelte vanno in `settings.json`; il
`config.toml` non viene mai riscritto. In `config.toml` si possono indicare gli stessi percorsi in `[emulators]` e
sovrascrivere il comando di una console in `[launch.<console>]` (vedi [Riferimento](riferimento.md)).

![Impostazioni › Emulatori: un percorso per programma e la tabella emulatore per console](images/impostazioni-emulatori.jpg)

### Profilo di avvio di un singolo gioco

Nel dettaglio di un gioco, **⚙ Profilo di avvio** cambia il modo di avviare **solo quel gioco** (tutte le sue
versioni). I campi vuoti usano le impostazioni della console:

- emulatore e core RetroArch;
- eseguibile diverso (per esempio un'altra versione dell'emulatore);
- argomenti al posto di quelli predefiniti;
- argomenti aggiuntivi, messi prima del file del gioco (per esempio `-f` per lo schermo intero);
- **script prima dell'avvio** e **script dopo la chiusura** (vedi sotto);
- **app da avviare insieme al gioco**: un eseguibile con i suoi argomenti e l'opzione **Chiudi l'app quando il gioco
  finisce**. Serve per i programmi che devono girare accanto al gioco, per esempio un deck tracker su Hearthstone o un
  overlay di statistiche: si avvia con il gioco e, se vuoi, si chiude con lui.

Per i giochi PC il profilo contiene i due script e l'app di accompagnamento: il gioco si avvia sempre come prevede il
suo store.

### Automazioni per gioco

Nel **⚙ Profilo di avvio** la sezione **Automazioni** prepara il PC prima della partita e rimette tutto a posto alla
fine, anche dopo un crash del gioco. Su Windows puoi impostare:

- **Comando prima dell'avvio** e **dopo la chiusura**, con **cartella di lavoro** e, se serve, **Aspetta che finisca**;
  gli script ricevono `POZZO_GAME_ID`, `POZZO_TITLE`, `POZZO_PLATFORM`, `POZZO_EXE` e `POZZO_EVENT`;
- **Risoluzione e frequenza** dello schermo;
- **Chiudi questi processi prima dell'avvio** (per esempio un programma che dà fastidio al gioco);
- **Piano energetico** (il GUID del piano) e **HDR** acceso o spento durante il gioco (Win+Alt+B).

Gli script che valgono per tutti i giochi (gioco avviato, gioco chiuso, download finito) stanno nelle Impostazioni,
vicino a quelli descritti più sotto.

#### Upscaling con Magpie

Il menu **Upscaling con Magpie** ingrandisce il gioco in finestra a schermo intero con **FSR**, **Anime4K**,
**Integer Scale** o **Lanczos**. Serve Windows 10 1903 o successivo; Magpie si scarica da GitHub al primo utilizzo.
Quando la finestra del gioco passa in primo piano Pozzo prepara il profilo e avvia Magpie nella tray, e a fine partita
lo chiude solo se l'aveva aperto lui.

#### Remap del pad

Per i giochi PC puoi riassegnare i tasti (per esempio `a=b, b=a, lb=lt`), impostare la zona morta degli stick
(0-30%), scambiare gli stick, invertire l'asse Y e attivare il **turbo** (`a:10` = tasto A a 10 Hz). Pozzo legge il
pad fisico e lo inoltra a un controller Xbox 360 virtuale: serve il driver **ViGEmBus**. Senza **HidHide** il gioco
può vedere due controller; con HidHide installato il pad fisico viene nascosto durante la partita e sempre ripristinato
dopo (se HidHide manca, compare un avviso).

#### Archivi senza estrazione fissa

Per un gioco PC o una ROM in `.zip`, `.7z` o `.rar`, l'opzione dell'archivio lo estrae in una cartella temporanea a
ogni avvio (dopo aver controllato lo spazio libero) e la cancella a fine partita. I file nuovi o cambiati durante il
gioco, come salvataggi e configurazioni, si conservano e si riapplicano all'avvio successivo. Se non si riescono a
salvare, la cartella resta dov'è e l'app avvisa.

## Script prima e dopo il gioco

In **Impostazioni › Emulatori › Avvio dei giochi** si indicano due script eseguiti per **tutti i giochi**, console e
PC:

- **Prima dell'avvio**: per esempio per cambiare la risoluzione dello schermo o attivare l'HDR;
- **Dopo la chiusura**: per rimettere le cose com'erano.

Uno script è un comando oppure un file `.bat` o `.ps1`. Riceve due variabili d'ambiente: `POZZO_TITLE` (titolo
del gioco) e `POZZO_KEY` (chiave del gioco nella libreria), così lo stesso script può comportarsi diversamente
per giochi diversi.

Ogni gioco può avere i suoi script nel **⚙ Profilo di avvio**: vengono eseguiti **dopo** quelli di tutti i giochi.

**Conferma degli script.** Se salvi uno script nuovo o modificato (per tutti i giochi, per un gioco o per gli eventi come «gioco avviato»), Pozzo mostra i comandi e chiede conferma: senza il tuo «sì» non viene salvato nulla. Gli script invariati non chiedono niente. Importando da un altro launcher gli script non vengono copiati (compare un avviso). Ripristinando una copia di sicurezza gli script che contiene tornano attivi, e Pozzo ti avvisa prima.

## Chiudere il launcher dello store

Sempre in **Impostazioni › Emulatori › Avvio dei giochi**, l'opzione **Chiudi il launcher dello store** chiude a fine
partita Steam, Epic, GOG Galaxy, Battle.net o Amazon Games, **solo se l'aveva aperto il gioco**: un launcher che era
già aperto prima resta aperto. La chiusura avviene qualche secondo dopo la fine della partita, così il launcher
finisce di sincronizzare i salvataggi; Steam viene chiuso in modo pulito.

## Collegamento sul desktop

Nel dettaglio di un gioco, **🖥 Collegamento sul desktop** crea un collegamento con l'icona del gioco: quella
dell'eseguibile per i giochi PC avviati da un `.exe`, altrimenti ricavata dalla copertina. Il collegamento avvia il gioco **tramite
Pozzo Launcher**: valgono emulatore, profilo e script, e il tempo di gioco viene registrato come quando lo avvii
dall'app. Non è disponibile per i giochi degli store online, che non sono installati.

## Avviare un gioco

**▶ Gioca**, `Invio` o un doppio clic sulla copertina. L'app sceglie da sola il file giusto:

- gli **ZIP di dischi** (per esempio i GameCube di Myrient) vengono estratti automaticamente prima dell'avvio;
- per i **giochi a cartella** si avvia il file corretto (PS3 → `EBOOT.BIN`, PS5 → `eboot.bin` con SharpEmu,
  Switch → il file del gioco base, non un aggiornamento o un DLC);
- con un emulatore mancante il dettaglio lo dice chiaramente, con il collegamento alle impostazioni.

Durante la partita la barra **In esecuzione** mostra il gioco in corso e permette di chiuderlo.

### Chiudere il gioco con il controller

**Select + Start (View + Menu) tenuti premuti per 2 secondi** chiudono il gioco in esecuzione, anche mentre il gioco
è in primo piano, con i controller XInput (Xbox). Si disattiva con `[app] exit_combo = false`.

### Chiudi gioco, Job Object e pausa

Su Windows i giochi avviati direttamente da Pozzo sono tracciati con un **Job Object**: la partita finisce quando
si chiude anche l'ultimo processo figlio, quindi il tempo di gioco è corretto anche con gli eseguibili che ne
rilanciano un altro, e **Chiudi gioco** termina tutti i processi del gioco.

La **Pausa** congela il gioco in corso (come Nyrna) e libera CPU e GPU anche nei giochi senza pausa propria. Si attiva
con **Ctrl+Shift+P** (cambiabile nelle impostazioni delle schermate), con **Select + L1** sul controller o dal pulsante
**Pausa** nella barra del gioco, in Big Picture e dal telefono. Il tempo in pausa non conta nel tempo di gioco e a
fine sessione il gioco riprende sempre. Pausa e Job Object sono solo per Windows.

### Splash all'avvio

Premendo **Gioca** compare subito a tutto schermo l'immagine del gioco con il logo e un piccolo indicatore di
caricamento, anche in Big Picture. Sparisce appena la finestra del gioco passa in primo piano (o dopo 60 secondi, o se
l'avvio fallisce). Si disattiva da **Impostazioni › Emulatori** con **Mostra uno splash all'avvio dei giochi**.
Su Windows, mentre il gioco è in primo piano, l'interfaccia di Pozzo si mette a riposo (animazioni ferme, anteprime
audio e video in pausa) e riparte quando torni a Pozzo.

## Gioca da disco veloce

Se la libreria sta su un disco lento (HDD), il gioco può essere copiato su un SSD e avviato da lì, per caricamenti più
rapidi.

Nel dettaglio del gioco, **⚡ Gioca da disco veloce** sta accanto a **▶ Gioca**. L'app copia il gioco (l'avanzamento in
percentuale si vede nella barra **In esecuzione**), poi lo avvia da sola.

**Dove va la copia**: nella cartella temporanea scelta in **Impostazioni › Emulatori e avvio**, sezione **Disco veloce**; se non ne hai
scelta una, nella cartella della cache dell'app. Conviene un SSD con abbastanza spazio libero: serve almeno la dimensione
del gioco (per i giochi PC, l'intera cartella di installazione). Se lo spazio non basta, l'app lo dice e non copia nulla.
Per sicurezza, non è consentito scegliere percorsi a rischio come la radice del disco (`C:\`), la cartella home dell'utente o la cartella della libreria.

**Alla fine**: di base la copia viene eliminata quando chiudi il gioco. Disattiva **Elimina la copia quando chiudi il
gioco** per riusarla la volta dopo, senza ricopiare (se nel frattempo il gioco è cambiato, viene ricopiato).

Avvertenze:

- per i giochi PC, i salvataggi scritti dentro la cartella del gioco si perdono con la copia eliminata; quelli nelle
  cartelle standard di Windows o gestiti dall'app no;
- non è disponibile per i giochi avviati da uno store o launcher esterno;
- **Chiudi gioco** durante la copia la annulla immediatamente;
- le copie rimaste su disco dopo un arresto anomalo del PC o dell'emulatore vengono ripulite automaticamente al successivo avvio del launcher;
- la modalità resta attiva anche dopo aver selezionato la finestra in cui avviare il gioco.

## Gioca nel browser

Le console leggere si giocano dentro Pozzo con **EmulatorJS** e i giochi Flash (`.swf`) con **Ruffle**: **Gioca nel
browser** sta nella scheda del gioco, nel menu del tasto destro, in Big Picture e sul telefono. Le console sono NES,
SNES, Game Boy, GBA, Mega Drive, Master System, Game Gear, PC Engine, PlayStation, Atari 2600, N64, DS e arcade.
L'emulatore si scarica alla prima partita; salvataggi e stati stanno nei dati dell'utente e finiscono nel backup.
Per la PlayStation serve il tuo BIOS.

## RetroArch: bezel, shader e cheat

Nella scheda di un gioco RetroArch la sezione **RetroArch: bezel, shader, cheat** permette di scegliere un **bezel**
(dal repository libretro overlay-borders, scaricato e messo in cache), un preset **shader** tra quelli già presenti in
RetroArch e i **cheat** della libretro-database con un interruttore ciascuno (**Cerca cheat**). Le scelte valgono per
il gioco o come predefinito del core. Pozzo scrive solo le sue chiavi nei file di override e prima ne fa una copia
`.pozzo-bak`.

## Ridurre lo spazio dei giochi PC

Per un gioco PC installato su Windows, **🗜 Riduci spazio su disco** (menu del tasto destro) comprime i file con la
compressione di Windows. Scegli l'**algoritmo** e premi **Comprimi** (**Decomprimi** per tornare indietro); se il gioco
è nel database di CompactGUI vedi una stima del risparmio. Se il gioco usa DirectStorage, su file compressi potrebbe
non avviarsi o andare più lento, e Pozzo chiede una conferma esplicita.

## Tempo di gioco e partite

Per ogni gioco l'app registra **tempo di gioco**, **ultima partita** e **numero di avvii**. Una partita entra subito
tra i *Giocati di recente* e nello stato *In corso* appena parte, da qualunque dispositivo (PC, telefono, Moonlight);
l'app sul PC se ne accorge entro pochi secondi.

Per i giochi PC avviati tramite un launcher (Steam, Epic…) il tempo viene registrato riconoscendo il processo del
gioco nella sua cartella. Steam fornisce anche il suo tempo totale, mostrato a parte.

## Mostrare su Discord cosa stai giocando

In **Impostazioni › 🧩 Integrazioni** si attiva la **presenza su Discord**: il tuo profilo mostra *«Sto giocando a …»*
con titolo, console e tempo di sessione. Serve solo l'**ID applicazione** — gratis, da
`discord.com/developers/applications` › *New Application* — e il client Discord aperto.

Usa il **canale locale** di Discord (`named pipe`): nessun dato esce dal PC, nessun server, nessuna chiave. Le immagini
non si possono mostrare, perché Discord accetta solo asset caricati sull'applicazione e non indirizzi web.

![Impostazioni › Integrazioni: avvisi di Windows e presenza su Discord](images/impostazioni-integrazioni.jpg)

## Partita con un amico

Puoi giocare con un amico senza account e senza server: crei un **invito** (un codice o un link) e lo mandi all'amico
su Discord, WhatsApp o come preferisci.

Possono usarlo **RetroArch** ed **Eden**. Per gli altri giochi usa Discord o lo store.

- **👥 Partita con un amico**, nel dettaglio del gioco: crea l'invito da mandare.
- **👥 Ho un invito**, in alto: incolli il codice ricevuto ed entri nella partita.

### Il messaggio di invito

Il pulsante **Copia invito** copia un messaggio già pronto, con il gioco, i requisiti, il link `pozzo://join/…` e il codice. Mandalo all'amico: lui può incollare l'intero messaggio in **Ho un invito**. Il link apre Pozzo sul suo PC, ma il gioco non parte mai da solo: prima compare una conferma.

### Dove giocate?

- **Stessa rete** (Wi-Fi o cavo di casa): non serve fare niente, l'app sceglie l'indirizzo giusto.
- **Su internet**: l'amico deve poter raggiungere il tuo PC. Apri la porta sul router: **TCP 55435** per RetroArch, **UDP 24872** per Eden (come aprirla dipende dal router: cerca «port forwarding» + modello). Nell'app, **Rileva il mio IP pubblico**.
- **VPN gratuita** (Tailscale o ZeroTier): installala su entrambi i PC, usa l'indirizzo che la VPN assegna al tuo PC; nessuna porta da aprire.

Se non sai quale scegliere, usa la VPN.

Avvertenze:

- la password della stanza Eden è nel codice invito: chi lo vede può entrare finché la stanza è aperta;
- la porta aperta sul router resta esposta: chiudila quando finite di giocare;
- l'amico deve avere la stessa versione del gioco e dell'emulatore.

## Giocare con un amico

Con RetroArch si può giocare in rete con un amico, nello stesso gioco (netplay, due giocatori). Pozzo non ha un server:
crea un invito come descritto in «Partita con un amico».

### Creare l'invito

Nel dettaglio di un gioco RetroArch, **👥 Partita con un amico** chiede il nick e l'IP del tuo PC e avvia il gioco come
host. Il codice (`POZZO-…`) si copia e si manda come in «Partita con un amico».

### Unirsi all'invito

Si incolla il codice come in «Partita con un amico». Alla conferma Pozzo avvia lo stesso gioco e RetroArch si collega
all'host.

### Cosa serve

- **Stesso gioco, stessa ROM e stesso core RetroArch** sui due PC. Il gioco deve essere nella libreria anche sul PC
  dell'amico. Se il core è diverso Pozzo lo segnala; se la ROM è diversa RetroArch non si connette.
- La porta è la **55435**.
- **In LAN** (stessa rete di casa) funziona direttamente con l'IP locale proposto.
- **Su internet**: come in «Partita con un amico», ma la porta è la **55435** (port forwarding verso il PC dell'host, o
  VPN con l'IP che la VPN assegna nella finestra al posto dell'IP di casa).

### Limiti e altre piattaforme

- Funziona con **RetroArch** ed **Eden** (vedi sotto). Per gli altri emulatori Pozzo propone lo **Share Play**
  (streaming con Sunshine e Moonlight), in cui l'amico gioca la tua partita da remoto.
- Con il client Discord aperto e la presenza attiva (**Impostazioni › 🧩 Integrazioni**) il tuo profilo mostra la partita
  come «(1 di 2)», perché RetroArch in rete gestisce due giocatori.

### Stanza multiplayer con Eden (Nintendo Switch)

Per i giochi Nintendo Switch che supportano il multigiocatore wireless o locale:

1. **Chi ospita**: nel dettaglio del gioco clicca su **👥 Partita con un amico**. Pozzo Launcher avvia una stanza privata in background (`eden-room` accanto all'eseguibile di Eden, oppure `eden --room`) sulla porta **UDP 24872** con una password sicura generata a caso, e poi fa partire il gioco.
2. **Chi si unisce**: clicca su **👥 Ho un invito** e incolla il codice ricevuto. Pozzo apre Eden con la scheda *Multiplayer › Direct Connect* già precompilata (indirizzo IP dell'host, porta 24872 e nome giocatore): basta premere **Connetti** per entrare immediatamente nella stanza.
3. **Chiudi stanza**: l'host può premere in qualsiasi momento **Chiudi la stanza** per arrestare il server della stanza senza chiudere il gioco.
4. *Requisiti*: entrambi i giocatori devono disporre della stessa versione di Eden e della stessa versione del gioco Switch (inclusi gli aggiornamenti).

## Download mentre giochi

In **Impostazioni › Download › Mentre giochi** si sceglie cosa fanno i download quando parte un gioco:
**Continua normalmente** (predefinito), **Limita la banda** (il limite globale di download diventa quello indicato in
KB/s, l'upload resta com'è) o **Metti in pausa i torrent** (con l'opzione accanto si fermano anche i download HTTP).

Alla chiusura del gioco riprendono **solo** i download fermati da questa funzione: quelli messi in pausa a mano restano
fermi. Il launcher sa da solo quando giochi, anche con un gioco PC avviato da Steam o Epic.

Un singolo download può partire a un'ora precisa: nel menu **⋯** della riga, **⏰ Avvia alle…** chiede l'ora (`23:30`).
Il download resta in coda — la riga mostra ⏰ con l'orario — e parte da solo, anche dopo un riavvio dell'app; la stessa
voce diventa **⏰ Annulla pianificazione** per toglierla. C'è lo stesso campo facoltativo nel dialog **＋ Aggiungi**.

## Salvataggi

Nel dettaglio, **💾 Salvataggi** tiene una **versione prima e una dopo ogni partita** (se i salvataggi non superano
1 GB; oltre quella misura solo a mano, per non riempire il disco in silenzio), più:

- **Copia adesso** per farne una a mano;
- **↶ Annulla l'ultima partita**, che riporta i salvataggi a com'erano prima dell'ultima partita;
- **Ripristina** su una versione qualsiasi: prima copia i salvataggi attuali, quindi si può tornare indietro; il
  ripristino riscrive i file della copia ma non cancella quelli creati dopo. A gioco aperto il ripristino è bloccato,
  perché l'emulatore riscriverebbe i suoi file;
- **★** fissa una versione (non viene mai cancellata), **✎** le aggiunge una nota (per esempio «prima del boss»),
  **Confronta** dice quali file cambierebbero rispetto ai salvataggi attuali.

Si tengono le ultime **20 versioni** per gioco; quelle fissate non contano. Le versioni stanno nella cartella scelta
in **Impostazioni › Libreria › Salvataggi dei giochi** (di base `<cache>/saves`), una cartella per gioco.

Quando un gioco ha **file condivisi con altri giochi** — le memory card di PCSX2, DuckStation, Dolphin o le VMU di
Flycast — l'app lo segnala: ripristinando torna indietro anche il salvataggio degli altri giochi.

### Dove stanno i salvataggi

I salvataggi si riconoscono per singolo gioco, così le copie non si mescolano:

| Emulatore | Come si riconoscono i salvataggi |
|---|---|
| Eden, yuzu (e suyu, citron) | Title ID nel percorso: `nand/user/save/…/<TITLEID>` |
| Ryujinx | Title ID nei primi byte di `ExtraData0` |
| RetroArch | `.srm` e `.state*` con il nome della ROM, anche nelle sottocartelle per core |
| Dolphin | memory card `.gci` (`GC/<regione>/Card ?`) e `Wii/title/00010000/<ID>`, più `StateSaves/` |
| PCSX2 | stati `sstates/<seriale> (<crc>)`; le memory card `.ps2` sono condivise |
| DuckStation | memory card e stati col nome o il seriale del gioco; `shared_card_*` è condivisa |
| PPSSPP | `PSP/SAVEDATA/<seriale>*` e `PSP/PPSSPP_STATE/<seriale>*` |
| RPCS3 | `dev_hdd0/home/00000001/savedata/<TITLEID>*` |
| Vita3K | `ux0/user/00/savedata/<TITLEID>` |
| melonDS | `<ROM>.sav` e `<ROM>.ml*` accanto alla ROM |
| Azahar, Lime3DS, Citra | `sdmc/Nintendo 3DS/…/title/00040000/<id>/data` e `states/<TITLEID>.*` |
| Cemu | `mlc01/usr/save/00050000/<id>` |
| Flycast | `<ROM>_vmu_save_*.bin`, `<ROM>.nvmem*` (le `vmu_save_*.bin` sono condivise) |
| shadPS4 | `user/savedata/1/<CUSA…>` |

Per **xemu** (un unico disco) e **Xenia** (l'ID non si ricava dal file) il percorso va indicato a mano.

### Percorsi aggiunti a mano

Se l'app non trova i salvataggi, nel riquadro **💾 Salvataggi** si scrive la cartella (o il file) dove li tiene il
gioco, per esempio `%APPDATA%\Gioco\Saves`; le variabili `%VARIABILE%` funzionano anche su Linux e macOS. Vale anche
per i **giochi PC**.

A fine partita, se i salvataggi del gioco non erano ancora noti, l'app propone le cartelle cambiate mentre giocavi:
**Sono i salvataggi** le aggiunge, **Ignora** la scarta.

### Giochi PC: le posizioni del manifest di Ludusavi

Per i giochi PC le posizioni dei salvataggi arrivano dal **manifest di Ludusavi** (oltre 50.000 giochi, aggiornato
ogni settimana, scaricato in sottofondo una volta a settimana). L'app riconosce il gioco per ID Steam o GOG, per titolo
o per cartella di installazione, e copia solo i file che il manifest indica come salvataggi. Le chiavi di registro di
Windows non sono gestite: in quel caso il percorso si aggiunge a mano.

### Formato delle copie: compatibile con Ludusavi

Le versioni sono nel **formato di Ludusavi**: per ogni gioco una cartella con `mapping.yaml` e i file
`backup-<data>.zip`, con dentro i percorsi originali, l'hash SHA-1 e la dimensione di ogni file. Scegliendo in
**Impostazioni › Libreria › Salvataggi dei giochi** la **stessa cartella** di Ludusavi (*Backup mode › Backup target*),
i due programmi vedono e ripristinano le stesse copie. Si vedono solo le copie **complete** (le differenziali di
Ludusavi no). Le copie già fatte nel formato precedente vengono convertite da sole al primo avvio.

Per i port PC vengono copiati i file della cartella del port che non vengono dalla release. Le copie si disattivano
con `[app] save_backups = false`.

## Schermate

Dopo ogni partita l'app importa le schermate fatte dall'emulatore (Ryujinx, Eden e derivati, e gli altri
supportati). Per Eden cerca nella cartella predefinita `%APPDATA%\eden\screenshots`, nella versione portatile
`user\screenshots` accanto all'exe e nel percorso personalizzato letto da `qt-config.ini`. Le schermate si sfogliano
nella vista **📷 Schermate** e si possono fare anche dal telefono.

### Overlay in gioco

Durante una partita (Windows) **Ctrl+Shift+O** o **Select + R3** sul controller aprono un overlay sopra il gioco con il
tempo di sessione, la schermata, la pausa, «Chiudi gioco», gli obiettivi, gli appunti dell'estensione Diario (se
installata) e i comandi della musica. Si chiude con lo stesso tasto, con **Esc** o con **B**, e il fuoco torna al gioco.
La scorciatoia si cambia nelle impostazioni delle schermate. L'overlay funziona con i giochi in finestra e a schermo intero
senza bordi: **non si disegna sopra i giochi a schermo intero esclusivo**.

### Obiettivi dal vivo

Per i giochi Steam avviati con un emulatore Steam, Pozzo guarda durante la partita i file degli obiettivi di Goldberg/GSE
(`%APPDATA%\Goldberg SteamEmu Saves`), EMPRESS, CODEX e RUNE e mostra un avviso per ogni obiettivo nuovo. Nome e icona
vengono dallo schema Steam se hai la chiave API; senza, si usa l'id ripulito. Avvisi e suono si scelgono nelle impostazioni
delle schermate (⚙). RPCS3, SmartSteamEmu e CreamAPI non sono supportati.

## RetroAchievements

In **Impostazioni › Store › RetroAchievements** inserisci il tuo utente e la Web API key. Nel dettaglio dei giochi
retro compaiono gli **obiettivi sbloccati**, la percentuale e le icone.

Il gioco viene abbinato:

1. per **hash**: l'MD5 è già noto dal DAT No-Intro, quindi funziona anche con le ROM in `.zip` e con le versioni
   italiane (che su RetroAchievements hanno il titolo inglese);
2. altrimenti per titolo, nome canonico o nome del file.

Cache: catalogo 7 giorni, abbinamento 30 giorni, progresso 30 minuti.

### Eden (Switch)

Con Eden le partite passano dalle **stanze** di Eden: il gioco in locale (wireless) della Switch viaggia su internet, quindi
funziona solo con i giochi che hanno la modalità locale. Il codice invito è lo stesso.

- **Chi ospita**: in **👥 Partita con un amico → Crea invito** Pozzo avvia la stanza (privata, con una password nel codice,
  porta **UDP 24872**) e il gioco, e li chiude insieme a Pozzo. **Chiudi la stanza** la ferma senza chiudere il gioco.
  La stanza richiede `eden-room.exe` accanto a `eden.exe` (o una versione di Eden che accetta `eden --room`).
- **L'amico**: incolla il codice come in «Partita con un amico». Pozzo compila **Multiplayer › Direct Connect** con indirizzo,
  porta e nome e avvia il gioco: in Eden basta **Multiplayer › Direct Connect › Connetti**, poi aprire la modalità locale del gioco.
- Porta **UDP 24872** (fuori dalla rete di casa: port forwarding o VPN, come in «Partita con un amico»). Serve lo stesso
  gioco su entrambi i PC. Chiudi Eden prima di unirti, altrimenti Pozzo non può compilare i campi.
