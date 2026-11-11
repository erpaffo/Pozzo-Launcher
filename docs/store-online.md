# Aggiungere store online e store PC

Oltre ai giochi che possiedi, Pozzo Launcher può mostrare i giochi **disponibili da scaricare** letti da pagine web che
scegli tu: i **cataloghi delle console** (store online) e gli **elenchi di giochi PC** non ufficiali (repack e
download diretto). Questi giochi compaiono nella libreria come «da scaricare», con un pulsante per ogni sito che li
offre.

> **Nota legale.** L'app non contiene né importa elenchi di siti: gli indirizzi li aggiungi tu. Scarica solo ciò che
> hai il diritto di scaricare (giochi che possiedi dove la copia di backup è consentita, homebrew, freeware, demo,
> titoli liberi): il download di giochi protetti senza licenza è illegale.

Questo capitolo spiega:

1. come aggiungere un catalogo a una console;
2. quali formati di pagina l'app sa leggere e come verificarli;
3. come aggiungere gli elenchi di giochi PC;
4. come funziona l'aggiornamento degli store (coda, pianificazione, log);
5. i plugin inclusi che aggiungono store in blocco;
6. per chi programma: come aggiungere un nuovo formato di pagina o un nuovo store.

## Store online di una console

### Aggiungere un catalogo

1. Apri la console nella barra laterale.
2. Premi **Store online** nella barra della console (il numero tra parentesi indica quanti cataloghi ci sono).
3. Incolla uno o più indirizzi di **pagine che elencano i giochi** di quella console, **uno per riga**.
4. Premi **Salva e leggi**.

Da ogni pagina vengono letti nome, peso, link di download e link magnet. I giochi che non hai compaiono come
**da scaricare** nella vista della console, nella vista **🛒 Store** e nelle classifiche. Quelli che possiedi già non
vengono ripetuti.

Nella stessa finestra:

- la tabella mostra per ogni indirizzo il numero di giochi letti, quando è stato letto e il formato riconosciuto;
- **↻ Rileggi** rilegge subito gli elenchi;
- togliere tutti gli indirizzi e salvare scollega la console dagli store online.

![La finestra Store online di una console: indirizzi, giochi letti per pagina e pulsanti Rileggi e Salva e leggi](images/store-online.jpg)

### Come compaiono i giochi

- Il titolo viene **ripulito** dalle parole dei siti: «Zumba World – The Marble Adventure Switch NSP (eShop)» diventa
  «Zumba World – The Marble Adventure». La parola «Switch» che fa parte del titolo resta («1-2-Switch»).
- **Stesso gioco da più fonti**: se due siti offrono lo stesso gioco, anche con nomi leggermente diversi, la libreria
  mostra **una sola scheda** con la pagina di ogni fonte («🌐 nxbrew.net ↗», «🌐 ziperto.com ↗») e il pulsante Torrent
  quando c'è un link magnet **per il singolo file**.
- **DLC e aggiornamenti**: il tipo dichiarato dallo store, le indicazioni nel titolo o nel nome del file e, per
  Switch, il Title ID distinguono DLC, aggiornamenti e giochi base. Il peso può confermare una DLC solo se il catalogo
  contiene anche il gioco base e la console supporta contenuti scaricabili; gli aggiornamenti vengono associati al
  gioco base. Nella pagina **🛒 Store**, **Escludi DLC** nasconde o mostra le DLC riconosciute.
- **Software che non sono giochi**: le schede **e-Reader** del Game Boy Advance (compreso il lettore stesso) sono
  migliaia e finiscono tra i giochi: la voce ha un catalogo con «e-Reader» nell'indirizzo o il nome lo dice, quindi
  arriva come **DLC** e si nasconde con **Nascondi DLC**.
- **⬇ Scarica** mette in coda i file elencati nella pagina del gioco, non la pagina dello store. La scheda
  mostra tutti i link disponibili, uno per provider, divisi per tipo: **gioco** (anche a parti: «Part 2», «Part 3»),
  **aggiornamento**, **DLC/espansioni** e le eventuali **versioni in altre lingue**. Il pulsante grande mette in coda
  un link per tipo, tutti insieme e dalla stessa fonte; ogni provider si può mettere in coda anche da solo. I
  download compaiono nella pagina **⬇ Download** come tutti gli altri.
- **Pubblicità e pagine intermedie saltate**: molti provider nascondono il file dietro un accorciatore (ouo.io) che
  porta alla pagina dell'host (DataNodes, FileKeeper, KrakenFiles, 1Fichier, MegaUp); il file vero è un passo più in là.
  Il link si risolve **all'avvio del download**: con una richiesta normale quando l'host ha un modulo da compilare,
  altrimenti nella finestra del browser dell'app, dove si clicca il pulsante che sblocca il download e si legge l'URL
  del download che parte. Quella finestra resta nascosta, tranne per gli host col conto alla rovescia (FileKeeper):
  lì compare per pochi secondi, perché Chromium ferma i timer delle finestre nascoste. Le pubblicità che aprono
  finestre vengono chiuse lì: niente schede nel tuo browser. Il risultato resta in cache, quindi la seconda volta è
  immediato.
- **Si vede a che punto è**: nella pagina **⬇ Download** la riga dice il passaggio in corso prima che il file
  cominci — «⏳ Salto la pubblicità (ouo.io)», «⏳ Cerco il file su datanodes.to», «⏳ Preparo il download (nome e
  dimensione)» — e poi passa ad avanzamento e velocità. Se qualcosa si blocca, il passaggio resta scritto accanto
  all'errore («⛔ fermo a: …»): si capisce subito se il problema è l'accorciatore, la pagina dell'host o il file.
- **DataNodes e FileKeeper**: il file parte solo come download vero, dopo il conto alla rovescia, e il link non compare
  mai nella pagina. L'app clicca i pulsanti nella finestra del browser e legge l'URL del download da lì, annullandolo:
  il file lo scarica il manager, non il browser. Funziona su Windows (WebView2).
- **MegaUp non si può completare**: il download passa da un popup con la sessione del sito, che non possiamo passare
  al manager. Se un file è solo su MegaUp, scaricalo dal browser.
- Se un host cambia pagina o mette un captcha che non passa, il download si ferma con un messaggio chiaro
  («Il link è una pagina, non un file (host)»): non salva un file pieno di HTML, e la pagina dell'host resta apribile
  dal pulsante del provider.
- **Torrent**: si offre solo per i magnet che indicano il file (nome con estensione); quelli che scaricherebbero
  l'intero set non hanno il pulsante, e la scheda lo dice, così non si scaricano decine di giochi per sbaglio.
- I giochi solo online **non contano come posseduti**: non entrano nel conteggio della console, in «Multigiocatore
  locale» né nei consigli basati sui tuoi giochi.
- Una console con uno store online compare nella barra laterale **anche se non hai nessun suo gioco**: così puoi
  sfogliarne il catalogo.

### Copertine e descrizioni

Le pagine elenco contengono solo i titoli. **🖼 Copertine e descrizioni** nella finestra *Store online* completa
le schede, con due barre di avanzamento (copertine e descrizioni) e un pulsante di stop:

1. **GameTDB** (solo Switch, offline): un database di circa 24.000 giochi scaricato una volta (circa 4 MB, valido
   30 giorni). Riempie in pochi secondi copertina, descrizione (prima in italiano), editore, giocatori. Le copertine
   mancanti in una regione vengono cercate nelle altre.
2. **Pagine dei siti**: per le voci ancora senza copertina o descrizione l'app legge la pagina del gioco (al massimo
   2 richieste al secondo) e ne ricava copertina, descrizione, Title ID, data, editore, generi, peso e schermate.
   Vanno bene sia i siti che scrivono «Genre: …» nel testo sia quelli con i dati in tabella (`<dl>` con `<dt>`/`<dd>`,
   come superpsx); le date estese («April 20, 2021») diventano `AAAA-MM-GG`.
3. **Ricerca per titolo** sui siti che la permettono, per le voci rimaste senza copertina (solo per le console del
   sito: la ricerca di Ziperto, per esempio, vale solo per Switch).

Il lavoro già fatto resta in cache (60 giorni): ogni esecuzione riprende da dove era rimasta. Gli elenchi di file
(formato `filelist`) sono esclusi: i loro dati arrivano dallo scraping normale.

### Metadati offline degli store

**Metadati store** (LaunchBox e TheGamesDB, solo copie locali: nessuna API, nessun token) cerca descrizione, sviluppatore,
editore, generi, giocatori, data e voto non solo per i giochi degli store PC ma anche per i giochi degli store online
delle console. La ricerca resta nella piattaforma dello store (una voce Switch non si confonde con quella PC), salta
DLC e aggiornamenti e riempie solo i campi ancora vuoti: i dati già presi dalle pagine dei siti non vengono sovrascritti.

## Gestore dei download integrato (Coda, Torrent e Debrid)

Pozzo Launcher include un **gestore dei download completo**, progettato sia per scaricare file HTTP da host online sia per gestire torrent e magnet, senza dover installare client esterni come qBittorrent o JDownloader.

La schermata si apre cliccando su **⬇ Download** nella barra laterale (o dal contatore vicino al logo) oppure dal pannello delle **Attività**.

### La tabella della coda

La coda raccoglie tutti i download attivi, in pausa o completati in una vista a tabella centrata e reattiva:

- **Colonne ordinabili**: Cliccando sull'intestazione puoi ordinare i download per *Nome*, *Host*, *Dimensione*, *Avanzamento*, *Velocità*, *ETA (tempo stimato)*, *Stato* o *Priorità*. L'ordinamento scelto viene ricordato per le sessioni successive.
- **Barra di avanzamento estesa**: Mostra visivamente lo stato del trasferimento e si allarga dinamicamente con la larghezza della finestra.
- **Barra di stato inferiore**:
  - Velocità totale istantanea in download (discesa) e upload (salita);
  - Posti occupati rispetto al limite massimo dei download contemporanei (impostabile in *Impostazioni › Download*);
  - Indicatore della **Modalità lenta** (limite di banda attivabile a mano o su fasce orarie programmate);
  - Indicatore **🎮 Modalità gioco**: quando avvii una partita, il launcher rileva la sessione attiva e riduce automaticamente la priorità dei download in corso per proteggere il ping e la CPU.
- **Pulsanti e menu rapido**: Con il tasto destro su una riga (o con il tasto `Menu` da tastiera) puoi cambiare la priorità del download, spostarlo in cima o in fondo alla lista, metterlo in pausa o riprenderlo, forzare il ricontrollo, aprire la cartella del file scaricato o copiare il link originale.

### Dettagli e registro in tempo reale

Facendo doppio clic su un download (oppure aprendo il pannello inferiore ridimensionabile) sono disponibili tre schede di dettaglio:

1. **Generale**: Mostra la cartella di destinazione su disco, la data di avvio, il tempo trascorso, il tipo di connessione e l'eventuale stato di estrazione dell'archivio.
2. **File**: Per i download Torrent con più file, elenca tutti gli elementi contenuti consentendo di escludere file non desiderati o assegnare priorità differenti ai singoli file.
3. **Registro**: Mostra la cronologia temporale dettagliata di ogni singolo passaggio con timestamp preciso. In caso di link protetti, registra i passaggi del browser nascosto (pulsanti cliccati, timer di attesa, tentativi anti-bot). In alto sono presenti filtri per isolare avvisi o errori, oltre ai pulsanti per copiare o ripulire il registro.

### Download HTTP a segmenti e risolutore link

- **Segmenti paralleli**: I file HTTP vengono scaricati a segmenti contemporanei con protocollo HTTP/1.1 per sfruttare la massima velocità consentita dall'host. Su Windows i file parziali vengono creati come file «sparsi», evitando di dover scrivere tutti gli zeri in anticipo sul disco.
- **Risoluzione automatica**: Gli accorciatori e le pagine dei provider (DataNodes, FileKeeper, KrakenFiles, 1Fichier, ecc.) vengono risolti in un'istanza del browser interno. Se il download viene chiuso o interrotto, riprende esattamente dal punto raggiunto senza riscaricare i megabyte già completati.
- **Mostra browser per Captcha**: Se un host richiede di risolvere manualmente un captcha o un controllo Cloudflare, puoi attivare **Impostazioni › Download › Mostra il browser mentre risolve i link**: la finestra diventerà visibile consentendoti di completare la verifica a schermo prima che il download parta.

### Torrent e Magnet integrati

- I collegamenti magnet e i file `.torrent` vengono gestiti nativamente.
- Include supporto per tracker UDP e TCP, DHT (Distributed Hash Table), PEX (Peer Exchange), LSD (Local Peer Discovery) e inoltro automatico delle porte UPnP sul router.
- Puoi impostare una porta fissa o lasciare che il launcher scelga una porta casuale stabile. La sessione salva su disco lo stato dei peer per riprendere subito la ricerca all'avvio.
- Supporto al **download sequenziale**, utile per ordinare i pezzi del file ed eseguire controlli di integrità immediati.

### Servizi Debrid (Multi-host)

Se possiedi un account per un servizio Debrid, puoi configurare la tua chiave API in **Impostazioni › Download**:

- **Provider supportati**: **Real-Debrid**, **AllDebrid**, **Premiumize**, **TorBox** e **Debrid-Link**.
- **Massima sicurezza**: La chiave API viene salvata esclusivamente sul tuo computer locale, non viene mai trasmessa a server esterni né inclusa nei registri o nelle segnalazioni di errore.
- I link dei provider associati vengono sbloccati automaticamente alla velocità massima consentita dal tuo account Debrid, superando code di attesa e limiti di velocità degli host gratuiti.
- Se un gioco è disponibile tramite MultiUp, la scheda mostrerà i singoli host disponibili con pulsanti dedicati per scegliere il server desiderato.

### Estrazione automatica e smistamento nelle cartelle

Quando un download viene completato:

1. **Estrazione automatica**: Se il gioco scaricato è un archivio `.zip`, `.7z` o `.rar` (compresi gli archivi multi-volume divisi in più parti), il launcher avvia l'estrazione non appena tutti i volumi sono disponibili. Per i file RAR è richiesto 7-Zip o UnRAR installato sul PC. L'archivio compresso viene rimosso automaticamente a estrazione ultimata.
2. **Smistamento intelligente per console**: Il gioco estratto viene spostato nella cartella corretta della console associata.
3. **Riconoscimento speciale per Nintendo Switch**: Il launcher riconosce tramite Title ID il gioco base, gli aggiornamenti e i DLC, raggruppandoli ordinatamente all'interno di una cartella unica intitolata con il nome del gioco.
4. **Aggiunta istantanea in libreria**: Il nuovo gioco appare in libreria in frazioni di secondo (da 0,1 a 0,4 s), e in background viene avviata la ricerca di copertine, valutazioni e metadati.
5. **Rilevamento automatico ROM su disco (Hot-reload)**: Se copi manualmente nuove ROM all'interno delle cartelle delle console senza passare dal download manager, Pozzo Launcher le rileva automaticamente dopo 10 secondi di calma e le aggiunge alla tua libreria.

## Formati di pagina riconosciuti

L'app sa leggere cinque strutture di pagina. Di solito **non serve sceglierle**: se il formato non è indicato,
viene riconosciuto dalla pagina stessa.

| Formato | Che pagina è | Paginazione | Esempio di struttura |
|---|---|---|---|
| `filelist` | Elenco di file o indice di cartella (Apache, nginx) | No | Link diretti ai file `.zip`, `.7z`, `.nsp`, … con il peso |
| `type_a` | Elenco paginato di schede | `?lcp_page0=N` | `<ul class="lcp_catlist">` con un link per gioco |
| `type_b` | Elenco A–Z su una pagina | No | `<div class="…-az-list">`, lettere `<h2 id="letter-X">`, giochi `<div class="…-game">` |
| `type_c` | Archivio di articoli (WordPress) | `/page/N/` | Ogni gioco è un `<article>` con titolo `h2.entry-title` |
| `type_d` | Elenco A–Z completo su una pagina | No | `div.az-listing` con sezioni per lettera e liste di link |

Dettagli utili:

- **filelist** filtra i link per estensione: tiene solo i file di giochi (più le estensioni della console). È il
  formato storico ed è quello usato quando nient'altro corrisponde.
- **type_a** e **type_c** leggono la prima pagina, ricavano il numero totale di pagine dal paginatore e leggono le
  altre in sequenza, con una pausa casuale tra una pagina e l'altra. Se il paginatore mostra solo «Next», si
  seguono i link fino in fondo.
- **type_a, type_b, type_c, type_d** puntano alla **scheda** del gioco, non a un file: non c'è filtro per
  estensione.
- Se un elenco paginato si accorcia, o cambi formato, le voci vecchie vengono tolte: in libreria non restano giochi
  fantasma.

### Indicare il formato a mano

Se il riconoscimento automatico sbaglia, il formato si indica in `settings.json`, sezione `catalogs`:

```json
{
  "catalogs": {
    "snes": ["https://esempio.test/roms/"],
    "nds":  { "urls": ["https://esempio-a.test/all/"], "type": "type_a" },
    "gba":  { "urls": ["https://esempio-b.test/all"], "type": "type_b",
              "css": { "az_list": "miosito-az-list", "game": "miosito-game" } }
  }
}
```

- La forma **lista di indirizzi** usa il riconoscimento automatico (o `filelist`).
- La forma **oggetto** ha `urls` (gli indirizzi) e le opzioni: `type` e, solo per `type_b`, `css` con le classi
  dei due elementi della pagina (`az_list` per il contenitore, `game` per ogni gioco).
- Cambiando gli indirizzi dalla finestra *Store online* il `type` e le opzioni restano.

### Verificare un indirizzo prima di aggiungerlo

Un errore tipico è incollare una pagina che non elenca **tutto** il catalogo (una categoria, un archivio parziale,
una singola pagina): si ottengono pochi giochi o nessuno. Il pulsante **🔍 Prova** (in *Altri store PC*) legge solo
quella pagina e risponde con formato, giochi nella pagina, pagine totali e i primi titoli:

```
✅ Formato type_c: 10 giochi in questa pagina, su 1.373 pagine. Esempi: …
⚠️ Formato filelist: 0 giochi in questa pagina, su una sola pagina.
```

- Più pagine: l'indirizzo è un indice completo, l'app le leggerà tutte.
- Pochi giochi e una sola pagina: probabilmente non è l'elenco completo. Cerca la pagina «tutti i giochi» del sito,
  spesso chiamata *All*, *Archive*, *A–Z* o *Index*.

## Altri store PC

In **Impostazioni › Store › Altri store PC (non ufficiali)** si aggiungono elenchi di giochi PC che non sono store
ufficiali, in due categorie:

| Categoria | Cos'è |
|---|---|
| **📦 Repack** | Giochi molto compressi: download più corto, installazione più lunga. Adatti a una connessione lenta |
| **⬇ Download diretto** | Il gioco così com'è |

Per aggiungerne uno:

1. incolla l'**indirizzo dell'elenco** e scegli la **categoria**;
2. **🔍 Prova** per controllare formato e numero di giochi;
3. **Aggiungi**;
4. **↻ Leggi gli elenchi** legge tutti gli elenchi e ricostruisce la libreria.

Gli elenchi usano gli stessi formati delle console, con il riconoscimento automatico. I giochi diventano giochi PC
da scaricare: compaiono nella sezione PC, nei filtri e nella scheda come gli altri giochi PC. La scheda mostra la
categoria («📦 Repack (download corto, installazione lunga)» oppure «⬇ Download diretto») e un pulsante per ogni
fonte. Lo stesso gioco su più siti è una scheda sola.

### Le fonti di un repack

Le pagine dei repack non linkano il file: elencano più fonti per lo stesso gioco. La scheda le mostra ognuna col
suo pulsante, nell'ordine in cui funzionano meglio: prima il **torrent** (quasi sempre disponibile e senza pubblicità),
poi **FuckingFast**, **DataNodes**, **FileKeeper** e infine le altre pagine.

| Pulsante | Cosa fa |
|---|---|
| 🧲 **Torrent** | mette in coda il magnet: è il gioco intero, niente pubblicità e niente browser |
| ↗ **sito** | apre la pagina del torrent (1337x, RuTor, Tapochek…) nel browser |
| 📄 **Filehoster** | legge l'elenco nascosto nel paste (MultiUP, PixelDrain, DataNodes…) e propone i file |
| ⬇ **Scarica le N parti** | mette in coda tutte le parti (`.part01.rar`, …): stessa cartella, e l'estrazione parte da sola quando ci sono tutte |

Il pulsante **⬇ Scarica** in cima alla scheda usa da solo la prima fonte diretta disponibile (FuckingFast, poi
DataNodes, FileKeeper e gli altri) e mette in coda tutte le sue parti; il **🧲 Torrent** gli sta accanto, quando la
pagina ne elenca uno.

Restano solo i link che scaricano davvero: sito dello sviluppatore, forum, screenshot e pagine di terzi vengono
scartati, e il «.torrent file only» sparisce quando c'è già il magnet (è lo stesso torrent). Se la pagina elenca un
**aggiornamento**, compare come riga «Aggiornamento» con le sue fonti: **⬇ Scarica** prende il gioco, mentre
**⬇ Scarica gioco + aggiornamento** (quando c'è) mette in coda tutti e due.

I paste dei filehoster sono elenchi incollati, a volte cifrati (PrivateBin): l'app li decifra e mostra solo i link ai
file, con cache di 7 giorni. Se il formato cambia resta il pulsante **↗** per aprire la pagina a mano. I link diretti
si risolvono all'avvio del download: FuckingFast e DataNodes passano dalla finestra nascosta (Cloudflare, conto alla
rovescia e captcha), gli altri host dal loro modulo.

Nella tabella degli elenchi c'è un filtro *Tutti / 📦 Repack / ⬇ Download diretto*, e per ogni riga si cambia
la categoria o si rimuove l'elenco. In `settings.json` gli elenchi stanno in `pc_stores`:

```json
{ "pc_stores": [ { "url": "https://esempio.test/giochi/", "kind": "repack" },
                 { "url": "https://altro.test/a-z/", "kind": "direct" } ] }
```

### Installare un repack

Un repack non è un gioco pronto: è un archivio che contiene il **setup** dell'installazione. Quando il download è
finito e le parti sono state estratte, la riga in **Download** mostra **📦 Installa**: il launcher avvia il `setup.exe`
del repack (con la richiesta di amministratore, se serve) nella sua finestra, dove si sceglie la cartella e le opzioni.

Quando la finestra del setup si chiude, il launcher cerca il gioco appena installato — nell'elenco delle app di
Windows oppure nelle cartelle nuove di *Program Files* e dei dischi fissi — e lo aggiunge alla libreria come gioco PC,
che compare subito senza dover lanciare una scansione. La voce *da scaricare* dello stesso gioco sparisce.

In **Attività** l'installazione compare come **Installazione · *gioco*** con il tempo trascorso: l'avanzamento del
setup non è leggibile da fuori, quindi la barra resta indeterminata finché non si chiude la finestra.

## Aggiornamento degli store

Gli elenchi letti restano salvati nella cache: all'avvio i giochi degli store ci sono **subito**, e l'aggiornamento
gira in sottofondo senza bloccare l'interfaccia. In **Impostazioni › Store › 🔄 Aggiornamento degli store** si
sceglie quando rileggerli:

| Modalità | Comportamento |
|---|---|
| **All'avvio dell'app** (predefinita) | Rilegge tutti gli elenchi poco dopo l'avvio |
| **Ogni giorno alle** | Una volta al giorno all'ora scelta, con l'app aperta |
| **Solo manualmente** | Mai in automatico: si usa **⟳ Aggiorna tutti** |

![Impostazioni › Store: stato degli store, account collegati e aggiornamento degli elenchi](images/impostazioni-store.jpg)

### La coda

- **Più elenchi in parallelo**: fino al numero impostato in *in parallelo* (4 di default, da 1 a 8), **mai due
  elenchi dello stesso sito insieme**, per non sovraccaricarlo.
- Premendo **⟳** su più store, ognuno entra **in coda** e parte appena si libera un posto. **⟳ Aggiorna tutti**
  accoda tutti quelli configurati. Aggiungere uno store mentre una lettura è in corso lo accoda invece di rifiutarlo;
  la stessa coda è usata dal pulsante ⟳, da *Leggi gli elenchi*, dalla finestra *Store online* delle console e dal
  plugin Link → Store.
- A coda vuota la libreria si ricostruisce **una volta sola**.
- **■ Interrompi** ferma la lettura a fine pagina, anche a metà di un elenco da centinaia di pagine, e svuota la
  coda. Il pulsante sparisce quando non c'è più niente da fermare.
- Un sito irraggiungibile non blocca gli altri: la sua riga resta con l'errore e gli elenchi già salvati restano
  validi.

### L'elenco degli store

La tabella mostra sempre tutti gli store configurati. Per ogni riga:

| Colonna | Significato |
|---|---|
| Stato | `·` mai letto, ⏳ in corso, ✓ fatto, ✕ errore, ⏭ saltato |
| Coda | Posizione in coda |
| Avanzamento | Pagina corrente su totale, secondi per pagina, tempo rimanente stimato |
| Log | L'ultima riga di log; **📄** apre il log completo di quello store |
| ⟳ | Accoda solo questo store |

### Log su file

Per capire perché un sito è lento o non risponde si avvia l'app con il log su file:

```bat
python -m pozzo app --log                   :: <cache>\logs\diagnostica.log
python -m pozzo app --log C:\temp\gs.log    :: percorso a scelta
set POZZO_LOG=1 && python -m pozzo app
```

Il file contiene, con ora e categoria, le decisioni del pianificatore (modalità, orario, avvio rimandato e perché),
l'apertura e la chiusura di ogni elenco, **ogni pagina letta** (`… pagina 51/147 — 50 giochi`) e gli errori con
tipo e messaggio. Oltre 8 MB viene troncato (la parte vecchia va in `.log.old`). Il percorso attivo è mostrato in
**Impostazioni › Store**.

## Plugin che aggiungono store

### Link → Store

Molti siti raccolgono **elenchi di altri siti**. Il plugin **Link → Store** (attivo da **Impostazioni › Aspetto ›
Plugin**, voce *Link → Store* nella barra laterale) legge una di queste pagine:

1. incolla l'indirizzo della pagina e premi **Leggi i link**;
2. i link vengono **raggruppati per intestazione** (h2/h3 della pagina) e filtrabili;
3. per ogni link scegli la destinazione: una **console** (diventa un suo store online) oppure **store PC** con la
   categoria (📦 Repack o ⬇ Download diretto);
4. il plugin lo aggiunge alle impostazioni (subito, senza riavviare) e indica se era già configurato;
5. **↻ Leggi gli store aggiunti** accoda la lettura: l'avanzamento è in **Impostazioni › Store**.

### Store Minerva

Il plugin **Store Minerva** (voce nella barra laterale) aggiunge allo store online di ogni console le cartelle di
minerva-archive.org elencate su r-roms.github.io, poi ne legge l'elenco dei giochi. **Importa da r-roms** mostra il
log dell'importazione; i link già presenti restano e **non vengono riletti**: si aggiungono e si leggono solo gli store
nuovi per quella console (più quelli presenti ma mai letti, per esempio dopo aver aggiunto una console). Al termine la
libreria si ricostruisce.

Per **Switch** aggiunge anche tre elenchi completi **preimpostati**: l'indice dei giochi di NXBrew (formato `type_b`),
Ziperto NSP (`type_c`) e Ziperto XCI (`type_d`). Per **Switch 2** preimposta l'archivio della categoria Switch 2 di
NXBrew (`type_c`, paginato). Per **PS4** e **PS5** preimposta l'archivio di superpsx
(`type_c`, letto come i siti di ROM). Quando una console ha più elenchi di formati diversi, il plugin
toglie il tipo fisso da `settings.json`, così ogni pagina viene riconosciuta da sola.

## Per chi programma

### Un nuovo formato di pagina

I formati sono un registro in `pozzo/catalog.py`:

```python
PARSERS = {
    "filelist": _parse_filelist,
    "type_a": parse_type_a_index,
    "type_b": parse_type_b,
    "type_c": parse_type_c_index,
    "type_d": parse_type_d_index,
}
```

Per aggiungerne uno:

1. scrivi `parse_type_x(page, base_url, exts=None, config=None)` che restituisce una lista di voci
   `{"name", "size", "url", "magnet"}` (oppure `(voci, pagine_totali)` se la pagina è paginata);
2. registrala in `PARSERS`;
3. se serve, aggiungi il riconoscimento automatico in `detect_kind()`.

Lettura, cache, potatura delle voci vecchie, costruzione della libreria e API funzionano senza altre modifiche. I
test stanno in `tests/catalog/` e sostituiscono solo il confine HTTP (`catalog._get_page`): nessuna richiesta di
rete.

### Un nuovo store (fornitore di libreria)

Uno store nuovo, per esempio un launcher che l'app non conosce, si aggiunge con un **plugin** (vedi
[Temi e plugin](ESTENSIONI.md)). Il backend del plugin registra una sottoclasse di `StoreProvider` il cui metodo
`fetch()` restituisce i giochi come `StoreGame`:

```python
# plugins/mio-launcher/backend.py
import json
from pathlib import Path

from pozzo.stores.base import StoreGame, StoreProvider


class MioLauncher(StoreProvider):
    id = "miolauncher"
    name = "Mio Launcher"

    LIBRARY = Path.home() / "MioLauncher" / "library.json"

    def detected(self) -> bool:
        return self.LIBRARY.exists()  # lo store compare solo se il launcher e' installato

    async def fetch(self) -> list[StoreGame]:
        games = []
        for g in json.loads(self.LIBRARY.read_text(encoding="utf-8")):
            games.append(StoreGame(
                store=self.id, id=str(g["id"]), title=g["name"],
                installed=bool(g.get("path")), install_dir=g.get("path", ""),
                launch={"type": "uri", "target": f"miolauncher://run/{g['id']}"},
                install_uri=f"miolauncher://install/{g['id']}",
            ))
        return games


def register(gs):
    gs.add_store(MioLauncher)
```

Campi principali di `StoreGame`:

| Campo | Significato |
|---|---|
| `store`, `id`, `title` | Store, identificativo del gioco nello store, titolo |
| `installed`, `install_dir` | Se è installato e dove |
| `launch` | Come avviarlo: `{"type": "uri", "target": "…"}` oppure `{"type": "exe", "target": percorso, "args": [], "cwd": ""}` |
| `install_uri` | Indirizzo che apre il client dello store sulla pagina d'installazione |
| `page` | Pagina web dello store |
| `playtime`, `last_played` | Tempo di gioco (secondi) e ultima partita, se lo store li fornisce |
| `images` | Immagini per tipo (`cover`, `hero`, `logo`, `icon`, `header`) → indirizzo |
| `genres`, `description`, `developer`, `publisher`, `release_date`, `size`, `reviews` | Metadati facoltativi |

Lo store nuovo compare in **Impostazioni › Store** e i suoi giochi nella sezione PC, con avvio, tempo di gioco e
unione con lo stesso gioco degli altri store come per gli store inclusi. Gli store inclusi
(`pozzo/stores/`) sono buoni esempi: `manual.py` è il più semplice, `steam.py` ed `epic.py` mostrano account e
giochi non installati.
