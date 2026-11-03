# Changelog

## 0.14.2 (2026-11-03)

### Aggiunto

- «Gioca con un amico» nel dettaglio dei giochi RetroArch: crea un codice invito da mandare (Discord, WhatsApp…); l'amico lo incolla con «Unisciti a un amico» e RetroArch si collega in netplay (2 giocatori, stessa ROM e stesso core). Gli emulatori senza gioco in rete propongono Share Play
- Con Discord aperto la presenza mostra la partita «(1 di 2)»
- «🖼 Immagini del gioco…» (tasto destro, o «🖼 Immagini» nella scheda): per ogni tipo di immagine (copertina, sfondo, banner, logo, icona, schermata…) si vede se arriva dalle fonti o l'hai scelta tu, e puoi caricare un file dal PC (anche trascinandolo), sceglierne una da SteamGridDB, incollare un indirizzo o tornare all'originale

### Corretto

- Download da DataNodes (e host simili) dopo la chiusura del launcher: riprendono da dove erano invece di ripartire quasi da capo. Il link già risolto si riprova senza rifare i passaggi (si risolve di nuovo solo se è scaduto), e il file parziale vale anche se il server risponde con un ETag diverso
- Alla chiusura i download si fermano in ordine, così l'ultima parte scaricata finisce davvero nel file
- Estrazione dei RAR (e degli altri archivi aperti con 7-Zip) ferma allo 0% quando il file dentro l'archivio ha un nome lungo: ora la percentuale avanza, e il registro del download segna ogni 10%
- «📂 Apri cartella» nella coda dei download: con percorsi che contengono spazi apriva una cartella qualsiasi; ora seleziona il file, e dopo l'estrazione porta al gioco (nella cartella estratta o in libreria) invece che all'archivio
- La copertina scelta a mano non compariva nella griglia per i giochi senza copertina dalle fonti (es. Hearthstone su Battle.net): sembrava che non si potesse impostare
- I candidati di SteamGridDB, descritti nel manuale, non comparivano nella finestra delle immagini: ora ci sono, anche per sfondo, banner, logo e icona
- «Aggiungi un gioco o un'applicazione» dava «Internal Server Error» con una libreria costruita da una versione precedente (colonne `md5`/`sha1` mancanti): ora le colonne mancanti si aggiungono da sole
- Riaprendo il launcher subito dopo averlo chiuso, il server del telefono e della sincronizzazione aspetta che la porta si liberi invece di restare spento con l'errore «[Errno 10048]»

### Migliorato

- Gli errori imprevisti dicono subito che errore sono, invece di «Internal Server Error»: il messaggio riporta la causa (es. «Errore imprevisto (RuntimeError: …)»), e quando la riconosce spiega anche che cosa fare (database di una versione diversa → ricostruisci la libreria, file o cartella non trovati, permesso negato, disco pieno, rete non raggiungibile). La risposta dell'API include anche il tipo (`error`) e il punto del codice (`where`) per le segnalazioni; la traccia completa resta nel registro
- Gli errori che nessuno gestiva (una richiesta che fallisce senza che il pulsante lo dica) ora compaiono in un avviso; se il launcher non risponde, il messaggio lo dice invece di «Failed to fetch»

## 0.14.1 (2026-11-03)

### Aggiunto

- Impostazioni › Emulatori › «Cerca emulatori già installati»: trova gli emulatori già sul PC (Program Files, Winget, Scoop, librerie Steam, registro di Windows) e li propone con «Usa questo»; non cambia nulla da solo. Se un emulatore è già presente, «Installa» non lo riscarica
- Mappa dei tasti del controller per Dolphin, PCSX2, DuckStation, RPCS3 e RetroArch (Xbox, PlayStation DualSense o DualShock 4, Switch Pro): si applica da sola quando installi un emulatore che non ha ancora impostazioni, e a mano da Impostazioni › Controller › «Mappa i tasti negli emulatori». Non tocca mai le impostazioni che esistono già se non la chiedi tu; prima di scrivere si fa una copia del file
- Impostazioni › Estensioni: accanto a ogni plugin il tempo di avvio (e, per quelli differiti, quello del primo uso)
- Test di fumo con RetroArch e una ROM libera (`tests/smoke`): gira solo di notte o a richiesta in CI, mai su push e pull request

### Cambiato

- Le estensioni `limite-tempo` e `statistiche` partono al primo evento di gioco invece che all'avvio dell'app; nessun evento va perso. Nel `plugin.toml`, `load = "lazy"` accetta anche `events = [...]`. `steamgriddb` resta attiva dall'avvio perché deve registrare la sua fonte prima dello scraping

### Migliorato

- La ricerca degli emulatori installati richiede circa 4 secondi invece di 18: le cartelle dei programmi del registro si guardano solo se il nome è quello di un emulatore

## 0.14.0 (2026-11-03)

### Aggiunto

**Gestore dei download**

- Gestore dei download integrato: una coda unica per file HTTP e torrent, nella pagina Download (voce tra Libreria e Preferiti, anche vicino al logo) e nelle Attività. La coda si salva e riprende dopo la chiusura del launcher; la cartella di destinazione la scegli tu
- Coda: priorità per download, sposta in cima o in fondo, pausa e riprendi tutto, limite di velocità globale e per singolo download, modalità lenta a mano o a orario, selezione multipla, ricerca e filtri. Menu col tasto destro sulle righe e tasto Menu da tastiera
- Download HTTP a segmenti con ripresa, nuovi tentativi con attesa crescente e controllo che il link sia un file e non una pagina; i link monouso (1fichier) usano un solo flusso
- Torrent integrati (magnet e file .torrent): scelta dei file con priorità, download sequenziale, tracker, DHT/PEX/LSD/UPnP, cifratura, condivisione fino a un rapporto o a un tempo, ricontrollo dei file e riannuncio ai tracker. Se il torrent viene da un gioco il titolo è il nome del gioco e gli altri file del magnet non si vedono né si scaricano
- Impostazioni › Download: cartella, download contemporanei, segmenti, limiti, modalità lenta e orario, porta, cifratura, rapporto di condivisione, tracker e servizi debrid
- Servizi debrid per sbloccare i link: Real-Debrid, AllDebrid, Premiumize, TorBox e Debrid-Link, con prova della chiave. La chiave resta nelle impostazioni e non viene mai mostrata né scritta nei registri
- MultiUp: la scheda del gioco elenca i provider (1fichier, KrakenFiles…) con un pulsante per ciascuno, anche per i link dietro accorciatori; scarichi da quello che scegli
- Registro dettagliato di ogni download (doppio clic sulla riga): cronologia con tempi dall'inizio, filtri per avvisi ed errori, riepilogo, copia e svuota. Mostra ogni passaggio dei risolutori con i secondi che richiede e, nel browser nascosto, indirizzo, pulsanti, testo, richieste di rete, errori della pagina e controlli anti-bot
- Impostazioni › Download › «Mostra il browser mentre risolve i link»: la finestra diventa visibile per vedere la pagina e superare a mano un captcha
- «Pulisci completati» e «Pulisci falliti» (questi eliminano anche i file parziali)
- Tasto destro su un link di download di un gioco (ogni console): «Copia link» e «Apri nel browser», anche per l'insieme delle parti. I magnet non c'entrano

**Dopo il download**

- Estrazione automatica degli archivi .zip, .7z e .rar, anche a più parti: parte quando ci sono tutti i volumi, con controlli contro percorsi fuori cartella, collegamenti, archivi bomba e disco pieno. Il .rar richiede 7-Zip o UnRAR installato. L'archivio si elimina a gioco messo a posto
- Il gioco estratto va nella cartella giusta tra le ROM e compare subito in libreria con l'aggiunta rapida (da 0,1 a 0,4 secondi, indipendente dalla dimensione della libreria), poi parte la ricerca di dati e copertina. La scheda del gioco online passa al gioco scaricato
- Se il link è incollato a mano e non è legato a un gioco, la console si ricava dai file arrivati e il titolo dal nome; se non è chiara il gioco resta dov'è e il registro lo spiega
- Switch: ogni gioco va in una cartella col suo nome con base, aggiornamenti e DLC dentro, e un aggiornamento scaricato dopo entra nella cartella del suo gioco. Base, aggiornamento e DLC si riconoscono dal Title ID (anche con nomi storti o fatti solo dall'ID)
- Rilevamento automatico delle ROM copiate nelle cartelle delle console: il gioco entra in libreria da solo dopo circa 10 secondi di calma, una cartella alla volta. Durante una partita lavora piano (priorità di fondo, solo file leggeri, ricerca dei dati a gioco finito). Impostazioni › Libreria, con avviso «N nuovi giochi»

**Download dei giochi**

- Download dei giochi Switch: dalla scheda del gioco i link di gioco, aggiornamento e DLC entrano nella coda dei download, non si apre più il browser. Accorciatori (ouo.io) e pagine degli host si saltano da soli: KrakenFiles e 1Fichier compilando il loro modulo, DataNodes, FileKeeper e FuckingFast cliccando nel browser nascosto e leggendo l'URL del download da WebView2 (Windows)
- Download: la riga della coda mostra i passaggi che l'app compie prima di scaricare — «Salto la pubblicità (ouo.io)», «Cerco il file su datanodes.to», «Preparo il download» — e se qualcosa si blocca resta scritto dove si è fermato accanto all'errore
- Giochi PC dei repack: la scheda mostra magnet, pagina del torrent, elenco dei filehoster (paste anche cifrati) e le parti dirette, con un pulsante che le mette in coda tutte nella cartella del gioco
- Giochi PC dei repack: se la pagina elenca un aggiornamento compare come riga sua con le sue fonti, e «Scarica gioco + aggiornamento» li mette in coda assieme
- Download: il pulsante Installa avvia il setup dei repack appena scaricati e il gioco installato compare subito in libreria
- Test di budget per tempo e RAM dell'avvio e della costruzione della libreria (`tests/perf/test_perf_budget.py`): fallisce se superano le soglie misurate, con fixture locali e nessuna rete

### Cambiato

- Switch: l'aggiornamento non è più una seconda versione del gioco nella libreria. Si avvia sempre il gioco base; con Ryujinx l'aggiornamento più nuovo si collega da solo all'avvio. Con Eden gli aggiornamenti vanno installati una volta dal suo menu, perché non c'è un comando per farlo da fuori
- I giochi che possiedi non compaiono più come scaricabili negli store online: vale per i file con lo stesso nome, per il Title ID della Switch, per i titoli in altre lingue e per i nomi con ™ ® ©
- Giochi PC dei repack: il pulsante «Scarica» della scheda prende da solo la prima fonte diretta (FuckingFast, poi DataNodes, FileKeeper) e il torrent gli sta accanto quando la pagina lo elenca
- Il browser nascosto lavora su un host alla volta: due download che passano dal browser insieme non si rubano più il link

### Corretto

- Download: se il file è stato rimosso dall'host (DataNodes «File Not Found», 1Fichier che rimanda alla home, MultiUp «Fichier non trouvé») l'app lo dice in pochi secondi con il motivo, invece di aspettare il browser per oltre un minuto
- Download: le pubblicità e i popup delle pagine degli host non aprono più schede o finestre (prima ogni popup diventava una scheda del browser) e permessi e dialoghi si chiudono da soli
- Giochi PC dei repack: i link diretti (FuckingFast e simili) non vengono più scambiati per un elenco da leggere, quindi niente errore 403
- Giochi PC dei repack: la scheda scarta i link che non scaricano (sito dello sviluppatore, forum, screenshot), tiene le fonti vere e non ripete il «.torrent file only» quando c'è il magnet
- Download: un archivio scaricato da un link incollato a mano ora viene anche messo in libreria, non solo estratto accanto al file

### Migliorato

- Pagina Download: riepilogo con attivi e velocità, righe con una barra colorata per lo stato (blu in corso, giallo in pausa, verde completato, rosso errore), il passaggio in corso sotto la barra, azioni secondarie che compaiono al passaggio del mouse o con la tastiera, pulsanti raggruppati e stato vuoto con il pulsante per aggiungere
- Registro del download in forma di cronologia, con le tappe in evidenza e i sotto-passi rientrati

### Dipendenze

- Nuove: `py7zr` (archivi 7z) e `rarfile` (archivi rar)

## 0.13.0 (2026-11-02)
### Aggiunto

- Sito ufficiale su GitHub Pages con landing page del prodotto, rilevamento automatico del sistema operativo e download diretto da GitHub Releases

### Cambiato

- Separazione chiara nell'header tra il sito ufficiale per il download (Home, Download) e la documentazione tecnica (Guida, Primi passi, Assistenza)
## 0.12.1 (2026-11-02)

### Aggiunto

- Avvio diretto in Big Picture: casella «Apri in Big Picture all'avvio» in Impostazioni › Generale; da riga di comando `--bigpicture` la forza e `--no-bigpicture` forza il desktop (la riga di comando vince)
- Clic destro sui giochi in tutte le viste (Per te, Top, statistiche e le grafiche Cinema, Console, Dashboard, Vetrina e Scaffali, non solo la griglia della libreria). Il menu ora ha anche Installa e Pagina dello store per i giochi degli store, Collegamento sul desktop, Copia il titolo e il voto a stelle; il preferito e lo stato mostrano una conferma
- Utente in uso nella barra dei menu, in alto a destra (👤 nome ▾), con il menu per cambiare utente e creare profili: vale in ogni grafica, anche quando la barra laterale è nascosta. «Cambia utente…» è anche nel menu File e in Impostazioni › Generale › Profili utente
- Con più profili, la schermata «Chi gioca?» compare a ogni avvio; spuntando «Entra sempre con questo profilo su questo dispositivo» non compare più su quel dispositivo (PC e telefono ricordano la scelta ciascuno), e si può togliere dalle Impostazioni. Un profilo con PIN lo richiede di nuovo a ogni nuovo avvio
- Procedura guidata di primo avvio in 4 passi facoltativi e riprendibili: cartella ROM, console (emulatore e BIOS), store, tema ed esperienza. Sostituisce la vecchia configurazione guidata e si riapre da «Rifai la procedura»
- Schermata «Chi gioca?» per scegliere il profilo, con mouse, tastiera e controller (anche in Big Picture) e tastierino per il PIN. Si apre dal menu profilo, con `Ctrl+P` o all'avvio se lo attivi in Impostazioni › Generale, dove puoi anche modificare nome, avatar, colore e PIN dei profili ed eliminarli
- Profili con i propri giochi sopra una libreria unica: cartelle ROM proprie, giochi aggiunti a mano e giochi del proprio account Steam, Epic e GOG, senza duplicare metadati e copertine. Account e impostazioni per profilo (tema, esperienza, Steam, lista desideri, token GitHub) e un profilo diverso su ogni dispositivo
- Impostazioni › Emulatori: per ogni console l'emulatore consigliato con il motivo, lo stato dei BIOS (verde, rosso o giallo «da verificare») con il link alla guida, e l'installazione «un clic» con avanzamento
- Verifica dei BIOS con hash veri, presi dal DAT di libretro (`tools/update_bios_hashes.py`, dati in `pozzo/data/bios_hashes.json`): niente più «sempre da verificare». Per le chiavi della Switch e i firmware personali si controlla solo il formato, perché non hanno un hash pubblico
- API per il gusto personale (`/api/taste`), l'ordine di gioco di una serie (`/api/franchise/{id}`), i consigli con il motivo (`/api/recommend`) e la classifica delle ROM per console con il punteggio combinato delle fonti (`/api/top/roms`). Con 160.000 giochi i consigli si calcolano in circa 2,5 secondi alla prima richiesta. I pannelli dell'interfaccia sono scritti ma non ancora collegati alle pagine: per ora si usano solo come API
- Moduli di calcolo `pozzo/taste.py`, `franchise.py`, `similar.py` e `rankings.py`: funzioni pure, testate, che lavorano sulla libreria condivisa. Un remake o una remaster non contano come capitolo nuovo di una serie
- Palette comandi con `Ctrl/Cmd+K`: cerca giochi, console, sezioni delle Impostazioni e azioni, con frecce, Invio ed Esc
- Errori d'avvio con il pulsante che li risolve: emulatore mancante apre Impostazioni › Emulatori, file o cartella non trovati aprono le cartelle ROM. L'avviso resta finché non lo chiudi
- Verifica dei dump: confronto della ROM con i DAT No-Intro/Redump per hash (prima dell'abbinamento per nome), badge «ROM verificata / sconosciuta» nel dettaglio e rapporto per console (`GET /api/verify/report`). Lo stato si calcola alla costruzione della libreria
- Impostazioni consigliate dell'emulatore: nella scheda del gioco (e per console in Impostazioni › Emulatori) scegli «Qualità», «Prestazioni» o «Fedele», oppure «Non toccare» (predefinito). All'avvio il launcher scrive solo il file di configurazione di quel gioco, dopo averne fatto una copia, e «Ripristina impostazioni originali» lo rimette com'era; un errore non impedisce mai l'avvio. Funziona per RetroArch, Dolphin (GameCube e Wii), DuckStation (PS1) e Cemu; per PCSX2 solo se il gioco ha già un suo file di impostazioni. Non sono ancora disponibili RPCS3 (manca il serial PS3), Ryujinx ed Eden. Valori e percorsi provengono dai sorgenti degli emulatori, non da una fonte che pubblichi le "impostazioni migliori per gioco": i preset valgono per tutti i giochi di un emulatore
- Mod per i titoli famosi della libreria: nella scheda del gioco compaiono i link ai siti di mod giusti (es. Super Smash Bros. Ultimate → GameBanana, Skyrim → Nexus Mods, Minecraft → Modrinth e CurseForge, ROM hack → RomHacking.net), scelti da una tabella curata per titolo e console (`pozzo/data/mod_sites.json`), senza cercare uno per uno i giochi della libreria. Per ora sono link alla ricerca del sito, senza installazione dal launcher
- Mod dei port nella scheda del gioco: Thunderstore con installazione, attivazione e disattivazione (i file sostituiti vanno in un backup e tornano al loro posto), GameBanana e ModDB come link alla pagina; Nexus non è letto senza chiave API. Patch IPS e BPS applicate solo su una copia della ROM
- Preset di esperienza (esperienza, tema e animazioni insieme) in Impostazioni › Aspetto: Classico, Cinema serata, Console TV e Leggero, più quelli salvati da te, per profilo
- Suggerimenti sulle funzioni da scoprire: ogni suggerimento si mostra una sola volta (si segna visto appena compare), al massimo 2 a sessione, scelti tra 15 funzioni diverse (ricerca, palette comandi, Big Picture, clic destro, scorciatoie, profilo, temi, impostazioni dell'emulatore, mod...). Sono posizionati accanto all'elemento con una freccia, si ricalcolano allo scorrimento e al ridimensionamento e non compaiono sopra finestre o procedure aperte. Sotto il fumetto: «Silenzia per 1 giorno» e «Non mostrare più»; in Impostazioni › Generale › Suggerimenti anche 7 giorni e «Rivedi tutti»
- Tour guidato di primo avvio: dopo la procedura di configurazione, 10 passi al massimo con velo e riquadro evidenziato (barra laterale, ricerca, filtri, un gioco, Big Picture, Impostazioni, profilo, scorciatoie). Si guida con mouse, frecce, Invio ed Esc, annuncia il passo ai lettori di schermo e si può saltare o disattivare con «Non mostrare più il tour». Si riapre da Impostazioni › Generale › «Rivedi il tour» e dal menu Impostazioni. Mentre è aperto i suggerimenti restano sospesi
- Test: nessun errore JavaScript in desktop, Impostazioni › Emulatori e Big Picture, e risposta 200 delle API nuove (`tests/e2e/test_console_errors.py`, con Playwright)

### Cambiato

- `Ctrl/Cmd+K` apre la palette comandi; la ricerca rapida nella barra passa a `/`
- Le cartelle ROM aggiunte da Impostazioni › Cartelle ROM o dal pulsante «Incolla cartella» sono ora proprie del profilo attivo e gli altri profili non le vedono; quelle già presenti restano di tutti
- Le copie di sicurezza includono anche i file dei profili, con account e credenziali: conservale con cura

### Migliorato

- HLTB e LaunchBox compaiono nelle statistiche e nello svuotamento della cache (Impostazioni › Sistema › Cache delle fonti)
- Le risposte di RAWG, IGDB, ScreenScraper, TheGamesDB, ArcadeDB e Wikipedia restano su disco con una scadenza chiara, anche per i giochi non trovati: meno richieste ripetute e meno quota consumata, con una sola copia per tutti i profili. Statistiche e svuotamento della cache per fonte; le righe scadute si tolgono da sole all'avvio
- Le copertine scaricate dagli store si salvano in WebP quando pesa meno dell'originale (altrimenti resta com'era), e le miniature usano lo stesso modulo delle immagini, senza codice duplicato
- Le estensioni che usano solo endpoint (Anniversari, Calendario uscite, Diario, Link → Store, Minerva, Obiettivi, Riepilogo annuale) e lo Store estensioni incluso si avviano al primo uso invece che all'avvio. In Impostazioni › Estensioni compaiono i tempi di avvio di ognuna e il totale

## 0.12.0 (2026-11-02)

### Aggiunto

- Schermata di avvio con logo, barra di avanzamento e fase corrente, sul desktop e a schermo intero in Big Picture. Segue le fasi vere dell'avvio (server, impostazioni, libreria, store, estensioni), esposte in `GET /api/boot`; se il server non risponde si chiude da sola dopo pochi secondi
- Profili utente più completi: icona, colore e PIN facoltativo (👤 › Icona, colore e PIN) e account separati per profilo: Spotify, Discord (presenza e voce), RetroAchievements, Epic e GOG. Al primo avvio gli account esistenti passano al profilo Principale. Il PIN blocca il cambio di profilo dal menu, non protegge i file della cartella dati
- Scorciatoie: `Ctrl/Cmd+4` Lista desideri, `Ctrl/Cmd+5` Statistiche, `R` gioco a caso, `H` nasconde o mostra il gioco aperto
- Animazioni: interruttore in Impostazioni › Aspetto (complete, ridotte, nessuna), che vale subito, si ricorda e, senza una scelta, segue il movimento ridotto del sistema; riduzione automatica del movimento sui dispositivi meno potenti, con FPS bassi o a batteria (la scelta manuale ha sempre la precedenza)
- Animazioni: finestre, avvisi e impostazioni si chiudono con una dissolvenza, dissolvenza al cambio di vista, entrata di menu e popover, risposta alla pressione di pulsanti, Preferito, stelle e Gioca, barretta sulla voce attiva della barra laterale
- API per la verifica di BIOS e firmware (`GET /api/emulators/bios`, per PS1, PS2, Saturn, Dreamcast, GBA, DS, 3DS, Switch e Mega CD) e per l'installazione dell'emulatore consigliato di una console (`GET /api/emulators/recommend`, `POST /api/emulators/install-recommended`). Pozzo non include né scarica file BIOS. Per ora senza interfaccia, e senza hash noti inseriti: finora ogni BIOS trovato risulta da verificare
- Test: budget di tempo e RAM per avvio e libreria (`tests/perf`), smoke test del browser con Playwright (`tests/e2e`, saltati senza Playwright), liste virtuali, splash, animazioni, profili, BIOS e installazione consigliata

### Cambiato

- Interno: gli endpoint di `server.py` sono divisi in moduli in `pozzo/app/routes/` e l'interfaccia in `static/js/`, senza cambiamenti visibili
- `docs/sviluppo.md` descrive l'architettura attuale, le liste virtuali, le animazioni, le icone e come aggiungere un tema

### Migliorato

- Liste lunghe: Top, lista desideri, giochi gratis, port e schermate disegnano solo le righe visibili. Con 2.000 voci per vista i nodi della pagina scendono da 13.000-37.000 a meno di 1.700
- Lo scheletro delle copertine e quello della Home del telefono animano solo trasparenza e movimento, senza ridisegnare la pagina a ogni frame
- Release: viene pubblicata anche se la build di un sistema fallisce, con i file dei sistemi riusciti, un avviso nelle note e nel riepilogo del run; senza nessuna build riuscita non si pubblica nulla

### Corretto

- GOG: errore alla lettura di una voce del registro rimasta senza la cartella del gioco (mancava un import)
- Manuale in PDF: la generazione falliva per un pacchetto LaTeX mancante e per due titoli «Scorciatoie» con lo stesso identificativo
- Test: l'installer degli emulatori e il limite di lunghezza dei percorsi dei port valgono solo per Windows e non fanno più fallire macOS e Linux; i test di prestazioni ora girano anche nella CI

## 0.11.1 (2026-11-01)

### Aggiunto

- Installazione degli emulatori dall'app (Impostazioni › Emulatori): ultima versione ufficiale dalle release GitHub (RetroArch, Dolphin, PPSSPP dal loro sito), impostata da sola, aggiornabile senza perdere la configurazione; download dei core RetroArch mancanti per le console della libreria
- Spotify (accesso con PKCE) e tasti multimediali di sistema, più controllo vocale Discord (muto, sordo, esci): widget in Big Picture e sezione «Musica e chiamate» nelle Impostazioni
- Scorciatoie da tastiera per Windows e macOS (Ctrl/Cmd), personalizzabili, con pannello elenco; comandi del controller in Big Picture con legenda e combinazioni Select + tasto per musica e Discord
- Nelle collezioni più famose compaiono anche i giochi degli store con lo stesso titolo
- Durata HowLongToBeat per ogni gioco nel dettaglio a modale (Cinema): se manca, viene cercata al momento e salvata
- Animazioni curate per ogni tema e grafica (motion.css/motion.js), che rispettano il movimento ridotto

### Cambiato

- Barra superiore riordinata: titolo a sinistra e, sempre nello stesso punto a destra, Nuovi giochi, A caso, Big Picture e Impostazioni; sotto, ricerca, filtri e ordinamento. «Idee / bug» passa nel piede fisso della barra laterale
- Barra di ricerca, ordinamento e filtri ridisegnata per il nuovo stile grafico (gruppi a pillola, pulsante di reset)
- I filtri di ricerca ora funzionano in tutte le grafiche, compresi i temi nuovi; la ricerca dalla Home apre la vista Tutti
- Nuova icona a tema pozzo (anello di mattoni, secchio e bagliore) per app, installer, macOS e telefono; script tools/make_icons.py
- Rimossi i riferimenti a Skyscraper da README, manuale e codice
- Icone SVG originali al posto delle emoji nell'interfaccia (icons.js)
- Big Picture solo per giocare: mostra soli giochi installati, senza Store e Gratis; barra voci scorrevole con Esci sempre visibile; Musica nella barra

### Migliorato

- Memoria: l'avvio non satura più la RAM (nelle misure di prova la finestra è passata da circa 6 GB a meno di 0,5 GB) e scorrere molte copertine fa crescere la memoria molto meno
- Vetrina: la griglia mostra al massimo 120 giochi con «Vedi tutti», e le copertine non disponibili non occupano spazio vuoto
- Server: un solo client HTTP per le copertine remote, con connessioni riutilizzate e voci di copertina mancante scadute ripulite
- Caricamento della libreria: risposta serializzata a blocchi e stringhe ripetute condivise, con picchi di memoria più bassi
- Il polling del controller in Big Picture parte solo con un pad collegato e rallenta quando è inattivo
- Dettaglio a modale ridisegnato: hero più alto, titolo più grande, dati con separatori, durate in tessere con barra

### Corretto

- Vetrina: il clic su Integrazioni non blocca più l'app (da circa 7 s a meno di 0,2 s)
- Possibile blocco dell'app aprendo Integrazioni (letture Discord senza timeout, polling Spotify) e perdita di RAM a ogni scansione LaunchBox
- la finestra si apre gia' con il tema scelto: barra del titolo, bordo e interfaccia sono pronti prima che si veda
- temi con colori a tre cifre (OLED: --bg:#000) non bloccano piu' l'avvio della finestra

## 0.11.0 (2026-10-31)

### Aggiunto

- Esperienza Catalogo con stile proprio (copertine e titoli più marcati), distinta da Originale
- README con galleria di screenshot di grafiche e temi e script tools/demo_screenshots.py per rigenerarli

### Cambiato

- Esperienza Console: barra laterale stretta con il solo pulsante ☰ per aprire la navigazione, nascosta nelle Impostazioni
- La barra dei menu (File, Strumenti, Visualizza, Impostazioni) sta sempre in cima alla finestra, sopra la barra dell'esperienza

### Migliorato

- Avvio più rapido: solo l'esperienza attiva blocca il caricamento, le altre e i plugin si caricano in parallelo o in sottofondo; Aspetto riusa i dati già scaricati
- Console mostra al massimo 80 giochi posseduti (non più l'intero catalogo online) e l'elenco delle esperienze è in cache sul server
- Controllo aggiornamenti: cache di 2 ore, ripetuto ogni 30 minuti e al ritorno in primo piano, nuovo tentativo dopo un errore; l'avviso resta finché non lo chiudi o lo clicchi, anche senza rete

### Corretto

- Console: gestione sicura di clic e tastiera su target non elemento
- Cache: «database is locked» all'apertura quando un'altra connessione era attiva (WAL impostato solo se serve, con nuovi tentativi)

### In corso

- Motore e profili di esperienza
- Pagina impostazioni — `pozzo\app\static\index.html` `pozzo\app\static\app.js` `pozzo\app\static\app.css` `pozzo\app\server.py` `pozzo\app\static\settings`

## 0.10.1 (2026-10-30)
### Aggiunto

- Giochi browser aggiunti per URL (es. chess.com) dal dialogo di aggiunta manuale: solo http/https, host locali e IP privati bloccati, titolo/descrizione/immagine Open Graph letti dalla pagina con limiti di tempo, dimensione e redirect
- Profili desktop Catalogo e Scaffali: Home a scaffali, navigazione superiore e cassetto; scelta globale per installazione.

### Corretto

- L'esperienza Scaffali chiude il cassetto dopo il cambio schermata e allinea meglio le icone della navigazione
- La Home Scaffali compatta i filtri e il banner per mostrare subito le copertine

### Migliorato

- La Home Scaffali aggiunge microinterazioni, profondità e animazioni rispettose delle preferenze di movimento

## 0.10.0 (2026-10-29)

### Aggiunto

- Store Minerva: download torrent per singolo gioco. Se un gioco proviene da un set archivio (Minerva / Myrient), la scheda del gioco propone «Scarica (solo questo gioco)» aprendo direttamente il magnet con l'indice del file (`&so=`), senza dover scaricare l'intero set da decine di gigabyte
- Port e app: il catalogo Quiver comprende anche giochi, emulatori e strumenti (non solo port) e si filtrano per tipo
- Download dei Port e app verificato con lo SHA-256 della release (catalogo Quiver o digest di GitHub): un file diverso viene rifiutato
- «Aggiorna tutto» e opzione «Aggiorna da solo»: le patch le installa il launcher, senza aprire quello del gioco
- Port aggiunti a mano anche da GitLab o Codeberg (gitlab:utente/progetto o indirizzo completo)
- Store online: tutti i link di download nella scheda (gioco, aggiornamento, DLC, parti, provider) aperti insieme saltando la pubblicità
- Store: filtro «Escludi DLC» disponibile nella pagina Store e in Big Picture
- Wishlist: minimo storico del prezzo delle key GG.deals mostrato accanto al prezzo attuale
- Pulsante «Idee / bug» nella barra principale, con collegamento ai moduli GitHub per proposte e segnalazioni

### Migliorato

- Metadati store offline: la ricerca in LaunchBox e TheGamesDB include anche i giochi degli store online delle console (stessa piattaforma, nessuna API), senza sovrascrivere i dati gi? presenti
- Port PC: l'aggiunta manuale da repository supporta anche GitLab e Codeberg (`gitlab:utente/progetto`, `codeberg:utente/progetto` o indirizzi web completi), oltre a GitHub
- Avvio diretto dei port e copia automatica delle ROM compatibili
- Port e app: modalità finestra (finestra, senza bordi o schermo intero) con scelta ricordata; il fullscreen segue i processi avviati, privilegia il gioco rispetto al launcher e non coinvolge Esplora file o le finestre standard di selezione ROM
- Store: classificazione più precisa di giochi, DLC, aggiornamenti ed extra; il peso viene usato come indizio solo sulle piattaforme con supporto storico a DLC e aggiornamenti
- Attività: titoli separati dallo stato e pulizia dei lavori terminati
- Impostazioni: aggiorna un singolo store senza aggiornare tutti gli altri

### Corretto

- Vista «Per te»: i dettagli funzionano anche con cache dei giochi prive del campo `content`
- Archivi .7z/.rar estratti con 7-Zip quando il tar di Windows non ha il codec; scartati sorgenti, SDK, asset e build per console
- Port: i port che compilano sul posto (SMS Launcher) si installano in una cartella breve invece di fermarsi sul percorso troppo lungo di Windows; dalla scheda del port si sposta un'installazione esistente con salvataggi e impostazioni, lasciando la cartella di prima in Ports\.backup

## 0.9.7 (2026-10-29)

### Aggiunto

- Store Riot Games: giochi installati rilevati automaticamente dal registro di Windows (League of Legends, Valorant, Teamfight Tactics, Legends of Runeterra) e avviati tramite Riot Client; gli altri giochi del catalogo compaiono come disponibili

### Corretto

- Battle.net (Hearthstone e gli altri giochi): il gioco parte appena il client e' pronto, senza l'attesa fissa di 40+8 secondi dopo l'apertura del launcher

### Migliorato

- Port PC: supporto a download con autorizzazione (token) e verifica del checksum SHA-256 della release per garantire l'integrità dei file scaricati

## 0.9.6 (2026-10-29)
### Migliorato

- Port PC: il catalogo si apre subito dalla copia salvata (anche in memoria) e si aggiorna in background; a fine aggiornamento la pagina si ridisegna da sola
- Store Minerva: gli store già presenti per una console non vengono duplicati né riletti, si aggiungono e si leggono solo i nuovi
- Libreria ricostruita in circa metà del tempo con molti store online (177 s → 83 s su 164.000 voci); l'interfaccia mostra la libreria nuova entro 3 secondi

### Corretto

- Store online PS4/PS5: copertine, descrizioni, generi, data e peso letti dalle pagine del sito (prima solo Switch/NDS)
- Console preferite (e le altre preferenze dell'interfaccia: filtri, ordinamenti, ultimo punto visto) sparivano alla chiusura dell'app: la finestra ora conserva i suoi dati tra un avvio e l'altro
- Store estensioni: lo store ufficiale dava errore 404 (il vecchio repository gamescraper-extensions non esiste più); ora legge l'elenco dal repository dell'app
- «Nuovi giochi» sembrava non finire mai: la libreria veniva ricostruita due volte anche senza niente di nuovo. Ora si ricostruisce solo se ci sono file nuovi o dati scaricati
- Store online PS4/PS5: quasi nessun gioco aveva i dati, perché «PS4»/«PS5» in fondo al titolo impediva di trovarlo in LaunchBox (PS4: da 9 a circa 1600 giochi su 2000; PS5 riconosciuta anche nel database LaunchBox già scaricato)
- «Copertine e descrizioni» di uno store online lavorava su tutte le console: ora solo su quella da cui lo avvii

### Aggiunto

- PlayStation 5: cartelle «ps5» riconosciute e giochi avviati con SharpEmu (eboot.bin)
- Store online PS5: superpsx preimpostato dal plugin Minerva, schede lette con copertina, generi, data e peso
- Icona di Pozzo Launcher nell'area di notifica di Windows (vicino a volume e rete): un clic riapre la finestra, tasto destro per «Apri» ed «Esci»
- DLC e add-on degli store distinti dai giochi: badge «DLC» sui riquadri e casella «Nascondi DLC» in ogni console
- Aggiornamenti dei giochi degli store: non più riquadri a sé, compaiono come «Aggiornamenti installabili» nella scheda del gioco

### Cambiato

- Estensione Store Minerva 1.4: «Importa store» compila solo la sezione «Store online» di ogni console, senza leggerla; un pulsante «Leggi» per console (o per tutti quelli mai letti) scarica gli elenchi
- Tipo dei contenuti degli store (gioco, DLC, applicazione) preso da Steam, Epic e GOG quando lo dichiarano, non solo dal nome

## 0.9.2 (2026-10-28)
### Corretto

- Giochi aggiunti a mano: il gioco appena aggiunto non compariva nell'interfaccia (l'elenco in cache non veniva invalidato)

### Aggiunto

- Pulsante «Chiudi gioco» nella barra del gioco in esecuzione: chiude il gioco e, se non lo trova (per esempio avviato da un launcher), interrompe comunque l'esecuzione mostrata nel launcher

### Migliorato

- Giochi avviati da un launcher (Battle.net, Steam...): se il gioco non parte l'avvio viene ripetuto fino a 3 volte, riaprendo il launcher se si è chiuso. Hearthstone: prima si apre Battle.net e si attende che sia attivo, poi parte il gioco e Battle.net viene ridotto a icona

## 0.9.1 (2026-10-28)
### Corretto

- Aggiornamento dall'app: dopo il cambio di nome del repository (erpaffo/Pozzo-Launcher) il download della nuova versione veniva rifiutato con «Indirizzo di download inatteso». Ora l'indirizzo è controllato solo per host (github.com), così il nome del repository si può cambiare senza rompere gli aggiornamenti
- La versione scritta nel programma torna a corrispondere a quella pubblicata: chi installa questa release non se la vede più riproporre come aggiornamento

### Cambiato

- Link al repository aggiornati in manuale, README, installer e documenti delle estensioni: la vecchia pagina GitHub Pages (erpaffo.github.io/GameScraper) non esiste più

## 0.9.0 (2026-10-28)
### Corretto

- Se la cartella di un'estensione non è leggibile (per esempio un collegamento non attendibile di Windows, errore 448) l'app parte lo stesso: l'estensione compare disattivata, con il motivo, invece di bloccare l'avvio
- Aggiunta di un gioco a mano: non ricostruisce più tutta la libreria (la finestra restava aperta senza mostrare nulla)

### Aggiunto

- Barra dei menu in alto (File, Strumenti, Visualizza, Impostazioni) con le azioni e le impostazioni più usate
- Pulsante «Cerca nuovi giochi» in ogni console e nei giochi PC (anche dal tasto destro sulla console): i file compaiono subito, i metadati arrivano dopo
- Console preferite: tasto destro sulla console nella barra laterale; le preferite stanno in cima, poi le altre in ordine alfabetico
- Tasto destro su un gioco: «Applicazioni abbinate…» e, per i giochi aggiunti a mano, «Rimuovi dalla libreria»

### Cambiato

- Immagini del gioco: la ricerca passa da SteamGridDB a Google Immagini, con il titolo già scritto
- Il progetto si chiama Pozzo Launcher: comando pozzo, eseguibile PozzoLauncher.exe, cartella dati PozzoLauncher. Al primo avvio i dati della vecchia cartella GameScraper vengono copiati (la vecchia resta)

### Migliorato

- Giochi PC avviati da un launcher (Steam, Battle.net…): la finestra del launcher viene ridotta a icona se l'ha aperto il gioco
- Aggiungi gioco o applicazione: il titolo diventa il nome del file .exe, la finestra si chiude subito e il gioco entra in libreria all'istante; copertina e metadati si cercano dopo, in background, solo per quel gioco

## 0.8.0 (2026-10-28)
### Aggiunto

- API locale stabile /api/v1 con token (Impostazioni > Info), errori uniformi, eventi SSE, client incluso per script e plugin
- Preferiti divisi per console nella barra laterale, e vista «Applicazioni» per i programmi aggiunti a mano
- Incolla cartella (📋) per ogni console e per i giochi PC: legge il percorso dagli appunti e cerca solo i giochi nuovi
- Cerca immagini… dal menu del tasto destro: copertina, sfondo o schermata da SteamGridDB, oppure un indirizzo incollato
- App da avviare insieme al gioco nel profilo di avvio, con chiusura automatica a fine partita
- Pulizia libreria: Rimuovi doppioni manuali (stesso eseguibile e argomenti)

### Migliorato

- Manuale: screenshot di ogni funzione, nuova sezione Statistiche e test automatico di link e immagini
- Aggiunta manuale di un gioco o di un'applicazione: nessun aggiornamento degli store, la voce compare subito
- Libreria PC: DLC, colonne sonore, season pass, bundle e simili non compaiono più come giochi
- Battle.net: genere, anno, descrizione e sviluppatore dei giochi
- Giochi aggiunti a mano: lo stesso eseguibile non si aggiunge due volte; le immagini scelte dall'utente hanno la precedenza sulle fonti

### Cambiato

- Store estensioni: le estensioni arrivano da più fonti. La prima è lo store ufficiale (ogni estensione nel proprio repository); con «Aggiungi» si importa il link GitHub di un'altra estensione o di un altro store. Le estensioni di altre fonti sono indicate con la loro provenienza, e lo sha256 dei file viene sempre verificato

### Corretto

- Scheda del gioco: un clic su un altro gioco durante il caricamento non mostra piu' il gioco sbagliato, e le riaperture non ricaricano un pannello gia' chiuso
- Torrent: il pulsante compare solo quando il link magnet scarica il singolo file
- Avvio dei giochi PC: gli script «prima» non bloccano più il gioco oltre 15 secondi
- Store: uno store non più rilevato non lascia giochi fantasma (per esempio titoli GOG che non sono di GOG); le voci GOG nel registro senza cartella del gioco vengono ignorate
- Torrent: i link magnet di un intero set vengono scartati, così non si scarica più tutta la raccolta

## 0.7.3 (2026-10-28)
### Migliorato

- Impostazioni: la finestra si adatta alla larghezza delle schede e, se non ci sta nello schermo (per esempio con le schede delle estensioni), passa a tutto schermo. Scorrono in orizzontale solo le schede (rotella, trascinamento o dito, con sfumatura ai lati); il contenuto di ogni scheda non scorre mai di lato

## 0.7.2 (2026-10-28)
### Aggiunto

- Estensione «Cosa gioco stasera?»: propone un gioco dal backlog in base al tempo che hai (durata HowLongToBeat), al genere e alla console, dando la precedenza a quelli che non giochi da più tempo; «Un altro» e «Avvia»
- Estensione «Anniversari retro»: badge «30 ANNI» sulle copertine dei giochi usciti oggi e pagina «Oggi nel…»
- Estensione «Pulizia libreria»: duplicati, giochi mai avviati o fermi da anni e dati incompleti, con azioni di massa e badge «DUP»
- Estensione «Diario di gioco»: voci datate e cronologia delle sessioni nel dettaglio di ogni gioco
- Estensione «Limite di tempo»: notifica quando superi le ore di gioco scelte al giorno o a settimana
- Estensione «Obiettivi personali»: obiettivi a periodo, serie di giorni consecutivi e distintivi
- Estensione «Riepilogo annuale»: il tuo anno in giochi con un'immagine da salvare e condividere
- Estensione «SteamGridDB»: copertine verticali, sfondi e logo mancanti da SteamGridDB (serve una chiave gratuita)
- Estensione «Calendario uscite»: uscite future della lista dei desideri e dei generi che giochi, da RAWG

### Cambiato

- Lista desideri: le key arrivano da GG.deals e gli store da IsThereAnyDeal; allkeyshop non viene più interrogato (niente più blocchi)

### Migliorato

- Badge 👥 con il numero di giocatori in locale sulle copertine, anche per i giochi non installati
- Lista desideri: la riga mostra prezzo Steam pieno, scontato e key più economica; il dettaglio ha la tabella degli store e i grafici di Steam e delle key

### Corretto

- Multigiocatore locale: Game Boy, DS, PSP e le altre portatili (multiplayer solo con cavo) non compaiono più
- Lista desideri: le copertine si vedono sempre (anche per i giochi senza codice Steam) e le key compaiono anche per i giochi aggiunti con la ricerca IsThereAnyDeal

## 0.7.1 (2026-10-28)
### Corretto

- Telefono: l'app ora si puo' davvero installare. Il certificato del PC e' firmato da una CA locale (si installa una volta sul telefono, Impostazioni › Telefono e streaming › 🔒 Certificato del PC): sparisce l'avviso «connessione non privata» e il browser non rifiuta piu' il service worker; se cambia l'indirizzo IP del PC la CA resta la stessa. Il pulsante «⬇ Installa» compare quando il telefono si fida del certificato

### Migliorato

- Telefono: casella «ho gia' installato il certificato» che nasconde il QR della CA
- Telefono: l'app si apre subito. La pagina e la libreria arrivano dalla copia locale del service worker e i dati nuovi scendono in sottofondo; il PC tiene pronta l'ultima risposta della libreria, che non viene piu' ricostruita a ogni apertura (con 40.000 giochi da ~1 s a poche decine di ms)
- Telefono: la Home parte subito dagli ultimi giochi salvati sul telefono, senza aspettare il PC; il resto della libreria si carica in sottofondo
- Il controllo degli aggiornamenti parte subito all'avvio, in parallelo al caricamento dei giochi

### Aggiunto

- Store estensioni: nuova voce in cima alla barra laterale (e alle estensioni in Impostazioni › Aspetto) da cui installare, aggiornare e rimuovere le estensioni. Ogni file scaricato viene verificato con lo sha256 dell'indice; un'estensione che richiede una versione dell'app più recente non si installa

### Cambiato

- Le estensioni Statistiche di gioco, Link → Store e Store Minerva + Switch non sono più incluse nell'app: si installano dallo Store estensioni. Le loro impostazioni restano; dopo l'installazione riavvia l'app

## 0.7.0 (2026-10-28)
### Corretto

- macOS: l'app non resta piu' bloccata cercando gli indirizzi del PC per il telefono, gli indirizzi si leggono dal sistema senza risolvere il nome host
- Giochi DS e 3DS sul telefono in verticale: croce e tasti sono tornati in basso sotto lo schermo (finivano in alto, sopra lo schermo)
- Telefono: pulsante Home (🏠) sempre visibile nel controller, anche col telefono in verticale, e la barra dei comandi non esce piu' dallo schermo con i titoli lunghi
- Telefono: dopo aver rifatto l'abbinamento la Home non dice piu' «libreria vuota» e il filtro per console salvato non nasconde i giochi, e dopo l'abbinamento si torna sempre alla Home
- Telefono: abbinamento anche aprendo la pagina in chiaro (il cookie non viene piu' scartato dal browser)
- Telefono: la scheda Attivita' ora funziona davvero (stato e comandi erano bloccati dal cancello di rete: rispondevano 403)
- Telefono: si vedono di nuovo le copertine dei giochi in Home e in Libreria (erano coperte dal riquadro colorato col titolo)

### Migliorato

- Test della CI: ogni script ha un limite di tempo e, se si blocca, il log dice dove si e' fermato (niente piu' job appesi)

### Aggiunto

- Giochi DS e 3DS sul telefono anche in orizzontale: lo schermo touch prende tutta l'altezza e i comandi ci stanno sopra, semitrasparenti
- App del telefono installabile (service worker): libreria e copertine consultabili anche senza rete
- Telecomando del PC dal telefono: volume, play/pausa, Esc, Invio, Alt+Tab, schermo intero
- Prova controller sul PC: tasti, levette, grilletti e vibrazione in tempo reale
- Notifiche di Windows per prezzi sotto soglia, giochi gratis nuovi, port da aggiornare e lavori finiti
- Sospensione o spegnimento del PC al termine di scraping, aggiornamenti e download dei port
- «Gioca con un amico a distanza»: invito con link e codice, l'ospite entra dal suo telefono come altro giocatore (solo il controller: niente libreria, mouse o scambio dei posti)
- Ospite a distanza: link sull'indirizzo pubblico (tunnel) e PIN di Moonlight confermato dal PC, senza aprire Sunshine

### Cambiato

- Giocando col telefono lo schermo inferiore non compare piu' sul PC: ricompare in un riquadro solo se il telefono si scollega o se non lo si tocca per 30 secondi, tempo modificabile in Impostazioni > Telefono
- Aspetti del controller, sensibilità e posizione dei tasti salvati sul PC (valgono per tutti i telefoni e finiscono nei backup)

## 0.6.4 (2026-10-28)

### Aggiunto

- Salvataggi nel formato di Ludusavi: scegliendo la stessa cartella (Impostazioni › Libreria › Salvataggi dei giochi) l'app e Ludusavi vedono e ripristinano le stesse copie; le copie già fatte vengono convertite da sole
- Salvataggi dei giochi PC trovati da soli con il manifest di Ludusavi (oltre 50.000 giochi, aggiornato ogni settimana), con le copie automatiche prima e dopo ogni partita
- Presenza su Discord (Impostazioni > Integrazioni): mostra «Sto giocando a ...» con titolo, console e tempo di sessione tramite il canale locale di Discord, senza server ne' dati inviati fuori dal PC
- Esportazione della libreria come pagina web statica (index.html + copertine): ricerca, filtro per console, ordinamento e scheda del gioco, senza server ne' risorse esterne
- Big Picture accessibile: palette per il daltonismo, alto contrasto, tre dimensioni dei testi e lettura vocale di cio' che si seleziona
- Telefono come telecomando completo: nuova scheda Attivita' con i lavori in corso del PC (store, copertine, libreria) e i comandi Aggiorna store, Cerca nuovi giochi, Ricostruisci libreria e Chiudi gioco; in libreria ordinamento per anno, valutazione, tempo di gioco e ultimo avviato
- Doppio schermo DS e 3DS: il telefono collegato mostra e riceve i tocchi dello schermo touch, mentre sul PC resta lo schermo principale (se il telefono non è collegato, il PC mostra entrambi gli schermi)

### Corretto

- I database dell'app si chiudono all'uscita (su Windows un file ancora aperto bloccava la cartella dati), quindi backup e spostamenti della cartella dati non trovano piu' file in uso
- Certificati HTTPS e sincronizzazione tra PC: troncamento sicuro del nome host nel certificato per compatibilità con macOS e runner CI

### Migliorato

- Integrazione continua: workflow GitHub Actions aggiornati a Node.js 24 (actions/checkout@v6, actions/setup-python@v6)

## 0.6.3 (2026-10-28)
### Corretto

- Salvataggi: i percorsi manuali con %VARIABILE% funzionano anche su Linux e macOS

## 0.6.2 (2026-10-28)
### Aggiunto

- Sincronizzazione tra due PC (Impostazioni › Libreria): con una cartella condivisa (OneDrive, Dropbox, NAS, Syncthing) o direttamente in rete locale con un codice di abbinamento. Preferiti, stati, note, voti, tempo di gioco (sommato, senza doppioni), collezioni e lista desideri; a scelta anche le impostazioni dell'app (mai percorsi, emulatori e account)
- Profili utente (pulsante 👤 nella barra laterale): preferiti, tempo di gioco, stati, collezioni e lista desideri separati per ogni persona, con libreria ed emulatori comuni
- Salvataggi: una versione prima e dopo ogni partita, «Annulla l'ultima partita», versioni fissate con nota, confronto con i file attuali, percorsi aggiunti a mano (anche per i giochi PC) e cartelle proposte quando i salvataggi cambiano giocando
- Salvataggi riconosciuti anche per Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3, Vita3K, melonDS, Azahar/Lime3DS/Citra, Cemu, Flycast e shadPS4 (memory card condivise segnalate)

## 0.6.0 (2026-10-28)
### Migliorato

- All'avvio, se è uscita una nuova versione compare un pop-up cliccabile che la scarica e la installa
- Meno memoria: descrizioni, pagine degli store, fonti e valutazioni dettagliate si leggono dal database solo quando apri un gioco (circa 250 MB in meno con 160.000 giochi)
- Memoria del server quasi dimezzata (da ~750 a ~410 MB con 160.000 giochi): fonti di download, indirizzi di installazione e pagine degli store si leggono solo per il gioco che apri, e i valori ripetuti (console, store, regione, generi) sono condivisi. Anche il caricamento della libreria è più veloce

### Corretto

- La chiusura della finestra termina subito l'app: prima restava un processo attivo (CPU e memoria) finché non finivano i lavori in sottofondo, come la lettura degli store
- Le console con uno store online ma senza giochi posseduti compaiono nella barra laterale

### Aggiunto

- Script prima e dopo il gioco: per tutti i giochi (Impostazioni › Emulatori › Avvio dei giochi) e per singolo gioco, anche PC (⚙ Profilo di avvio)
- Chiusura automatica del launcher dello store (Steam, Epic, GOG Galaxy, Battle.net, Amazon) a fine partita, se l'aveva aperto il gioco
- Collegamento sul desktop per ogni gioco, con l'icona del gioco: avvia il gioco tramite Pozzo Launcher e ne registra il tempo
- Store Minerva + Switch: l'estensione aggiunge anche gli store Switch preimpostati (NXBrew game-index, Ziperto NSP e Ziperto XCI) e toglie il tipo fisso quando una console ha piu' elenchi, cosi' ogni pagina viene riconosciuta da sola

## 0.5.4 (2026-10-27)

### Corretto

- Messaggi d'errore degli store che spiegano il motivo: verifica anti-bot (Cloudflare) non superabile con richieste semplici, accesso negato, pagina non trovata, sito che limita le richieste

### Aggiunto

- Lista desideri: prezzi delle key da allkeyshop. Quando aggiungi un gioco viene cercato su allkeyshop; cliccando un gioco della lista vedi prezzo e sconto su Steam con il minimo storico, la key più economica, tutte le altre offerte (negozio, regione, edizione, coupon; gli account a parte) e il minimo storico delle key. Per non farsi bloccare: una richiesta al minuto, ogni gioco una volta al giorno, storico una volta al mese e pausa di 6 ore se il sito rifiuta. Se il gioco trovato è sbagliato puoi incollare l'indirizzo giusto

## 0.5.3 (2026-10-27)
### Migliorato

- Barra del titolo e bordo della finestra seguono il tema: colore esatto su Windows 11, barra scura o chiara su Windows 10

## 0.5.2 (2026-10-27)
### Aggiunto

- Installer per ogni sistema accanto alle versioni portatili: Windows setup.exe (senza permessi di amministratore), macOS .dmg, Linux .deb
- Aggiornamento dall'app: in Impostazioni › Info «⬇ Installa e riavvia» scarica la nuova versione adatta (installer o portatile), ne verifica il checksum, si chiude e si riapre aggiornata; dati e config.toml accanto all'exe restano

## 0.5.1 (2026-10-27)
### Corretto

- L'app non partiva con la versione 0.5.0 (mancava un modulo dei port PC e un import nell'avvio con --log)
- settings.json non si svuota piu' se il file e' bloccato (OneDrive, antivirus) o rotto; scritture da piu' thread senza perdite
- Eseguibili: incluso beautifulsoup4, senza il quale gli store type_a/type_b e «Link → Store» non funzionavano

### Rimosso

- nxbrew_giochi.md (elenco di prova non usato dal programma)

## 0.5.0 (2026-10-27)
### Migliorato

- Anteprima di un indirizzo store con «Prova»: formato, giochi e pagine totali prima di aggiungerlo
- Avvio molto più rapido: i tuoi giochi compaiono in circa un secondo (prima 10-15) con il tema scelto e una barra di caricamento; i giochi del catalogo degli store arrivano subito dopo in sottofondo. Anche l'apertura della scheda di un gioco è più veloce
- **Aggiornamento degli store a coda**: clicchi ⟳ su più store e ognuno entra in coda; restano attivi al massimo
  N elenchi (impostazione «in parallelo», 1–8) e mai due dello stesso sito insieme, gli altri partono appena si
  libera un posto. A coda vuota la libreria si ricostruisce una volta sola.
- **Elenco di tutti gli store sempre visibile** (Impostazioni › Store › Aggiornamento degli store): per ogni riga
  stato, posizione in coda, pagina corrente, secondi per pagina, tempo rimanente e ultima riga di log; **📄** apre il
  log completo di quello store, **⟳** lo accoda da solo.
- **«■ Interrompi»** ferma la lettura a fine pagina (anche a metà di un elenco da centinaia di pagine), svuota la coda
  e **sparisce** appena non c'è più nulla da fermare (per esempio durante la ricostruzione della libreria).
- Gli elenchi letti restano salvati: all'avvio i giochi degli store sono già in libreria e l'aggiornamento può girare
  in sottofondo senza bloccare l'interfaccia.
- I file dell'interfaccia hanno la versione nell'indirizzo (`?v=…`): dopo un aggiornamento il browser non riusa più una
  copia vecchia di `app.js` (era la causa di pulsanti con comportamenti strani).

### Aggiunto

- **🏆 Migliori giochi**: Top 100 di ogni console (pulsante «🏆 Top 100» nella pagina della console) e classifica globale Top 100 / Top 1000 nella barra laterale, fra giochi posseduti e scaricabili dagli store. Entrano solo i giochi con voti affidabili (almeno 2 fonti, voto della critica o 50 voti); il punteggio unisce critica (Metacritic/IGDB) e giocatori. «↻ Aggiorna voti online» chiede a IGDB e RAWG i voti dei candidati (i migliori della console su IGDB + i già ben votati), ora usati anche nelle schede dei giochi da scaricare. Nella globale lo stesso gioco su più console conta una volta (prima la versione posseduta).
- Estensione «Link -> Store»: legge una pagina che raccoglie altri siti, raggruppa i link per intestazione (h2/h3) e li aggiunge come store di una console o come store PC (repack / download diretto)
- **Aggiornamento automatico degli store** (console e PC): all'avvio dell'app, ogni giorno all'ora scelta oppure solo
  manualmente, con il pulsante «⟳ Aggiorna tutti» e più store in parallelo.
- **Log su file** con `--log` (o `POZZO_LOG`): ora, decisioni del pianificatore, apertura di ogni elenco, **ogni
  pagina letta** ed errori completi — serve a capire perché un sito è lento o non risponde. Il percorso del file è
  indicato nelle impostazioni degli store.

### Corretto

- Sicurezza: il server dell'app risponde solo a se' stesso (blocca richieste e WebSocket da altri siti e il DNS rebinding) e le icone scaricate dai siti sono servite in sandbox, cosi' uno script in un SVG non puo' usare l'app
- Due clic rapidi (o PC e telefono insieme) non avviano piu' due volte la stessa ricerca o installazione
- Scheda del gioco: la riga «Fonti» compare di nuovo (era sovrascritta dai link di download degli store online)
- **Aggiungere un altro store mentre una lettura è in corso lo accoda** invece di rispondere «già in corso»: usano la
  stessa coda il pulsante ⟳, «Leggi gli elenchi» degli store PC, la pagina store delle console e il plugin Link → Store.
- L'interruzione e l'accodamento non si bloccano più a vicenda: dopo «Interrompi» il job si chiude davvero (prima poteva
  restare «in corso»), e più letture in parallelo non si scontrano sulle stesse connessioni al database.

## 0.4.0 (2026-10-27)
### Aggiunto
- **Store online: tipo di pagina per ogni console** (campo `type` in `settings.json`): `filelist` (elenco di file, invariato),
  `type_a` (elenco paginato con `?lcp_page0=N`), `type_b` (elenco A-Z senza paginazione, con la lettera di ogni gioco) e
  `type_c` (archivio paginato `/page/N/`, es. Ziperto); se il tipo non è indicato viene riconosciuto dalla pagina stessa.
- **Store online: copertine e descrizioni** (pulsante 🖼 nella finestra dello store, con due barre di avanzamento — copertine
  e descrizioni — e pulsante di stop): database offline **GameTDB** per i giochi Switch e lettura delle pagine dei siti
  (nxbrew, ziperto) per copertina, descrizione, Title ID, data, editore, generi e peso. I dati già letti restano in cache:
  ogni esecuzione riprende da dove era.
- **Store online: Ziperto** (elenco paginato letto da solo, `https://www.ziperto.com/nintendo-switch-nsp/`) e **stesso gioco
  da più fonti**: se dopo la pulizia del titolo NXBrew e Ziperto hanno la stessa partita, la libreria mostra una sola scheda
  con un pulsante di scaricamento per ogni sito.
- **Altri store PC** (Impostazioni › Store, separati dagli store ufficiali): si incolla l'indirizzo di una pagina elenco e
  i giochi compaiono tra quelli PC, divisi in **📦 Repack** (download corto, installazione lunga) e **⬇ Download diretto**,
  con filtro, cambio categoria e stesso gioco da più fonti su una sola scheda.
### Migliorato
- Titoli degli store online ripuliti da «Switch NSP (eShop)» e dalla versione finale; le copertine mancanti in una regione
  vengono cercate nelle altre (GameTDB US/EN/JA).
- La tabella degli store mostra anche i **Port PC**, con il numero di port e il pulsante per gestirli.

## 0.3.1 (2026-10-27)
### Aggiunto
- **Port PC** (nuova voce nella barra laterale): i giochi console ricompilati o ricostruiti per Windows (Zelda64Recomp,
  Ship of Harkinian, Banjo Recompiled…) dal catalogo di Quiver Launcher (~580 port, in cache 24 ore).
  - Filtri per console, ricerca, «🎮 Ho la ROM», «Installati», «Da aggiornare».
  - **Installa** dall'ultima release GitHub/GitLab/Codeberg (asset Windows scelto da solo) in `Ports\<cartella>`,
    con `portable.txt` dove il port lo prevede; il port diventa un gioco PC (tempo di gioco, Big Picture, telefono).
  - Più eseguibili: si sceglie quale avviare e resta ricordato. **Disinstalla** sposta la cartella nel Cestino.
  - **Aggiornamenti** (controllo al massimo ogni 12 ore): copia di sicurezza in `Ports\.backup`, salvataggi,
    configurazione e mod conservati, «Salta questa versione». Token GitHub facoltativo (⚙ nella pagina).
  - **ROM della libreria**: la scheda di una ROM mostra «Disponibile come port PC»; per i port che indicano l'hash
    richiesto, «Copia dalla libreria» mette la ROM giusta nella cartella del port dopo il controllo.
  - **Salvataggi** del port nel backup per gioco (i file della cartella che non vengono dalla release).
  - **Mod** da Thunderstore (installa/rimuovi); GameBanana solo come link.
  - **Aggiungi a mano**: da un repository GitHub (`utente/progetto`) o da una cartella già scaricata.
- **Nuovi controller sul telefono** (⚙ › Aspetto del controller):
  - **Buzz!**: pulsante rosso grande e 4 colori, telefono in verticale; un telefono per giocatore (fino a 4).
  - **Wii Remote** in verticale o in orizzontale (come un NES) e **Wii Remote + Nunchuk**: tasti, levetta, inclinazione,
    scuotimento e puntatore arrivano a Dolphin dal server DSU.
  - **Volante**: si sterza inclinando il telefono, pedali a pressione, «Centra».
  - **Chitarra** (Guitar Hero / Rock Band): 5 tasti colorati, plettro, leva del vibrato, Star Power.
  - **Arcade** a 6 tasti per i picchiaduro e **GameCube** (A grande, C-stick giallo, tasti per lettera).
  - **Pistola ottica / touchpad**: il telefono muove il mouse del PC (GunCon, Zapper, pennino del DS). Va permesso sul PC.
  - **Microfono (SingStar)**: la voce va in un cavo audio virtuale del PC (es. VB-Cable) che PCSX2 usa come microfono.
  - Aspetto scelto da solo anche per GameCube, Wii e per i giochi Buzz!, Guitar Hero/Rock Band e SingStar.
- **Sala giocatori**: numero e colore del giocatore sul telefono e sul PC; i telefoni si scambiano il posto senza ricollegarsi.
  Il numero è quello che vedono giochi ed emulatori (indice XInput).
- **Configurazione automatica degli emulatori** (Impostazioni › Telefono e streaming): PCSX2 per Buzz! o per la chitarra,
  Dolphin per il Wii Remote (server DSU, profili «Pozzo Launcher Telefono N», Wii Remote 1..N), con copia dei file e «Annulla».
- **Lista desideri: storico dei prezzi** (un punto al giorno, store e negozi di key) con grafichino e avviso quando il prezzo
  è il più basso da quando segui il gioco.
- **Layout del controller sul telefono**: oltre a Xbox, **PlayStation** (croce in alto a sinistra, levette in basso e
  simmetriche come sul DualSense, tasti △ ○ ✕ □ con i loro colori, L1/L2/R1/R2, Create/PS/Options) e **Nintendo Switch**
  (Pro Controller: X in alto, A a destra, B in basso, Y a sinistra, ZL/L/R/ZR, − ⌂ +). Si sceglie in ⚙ del controller.
  Per la Switch i tasti mandano al PC la stessa *posizione* di un controller Xbox (valgono le impostazioni che l'emulatore
  ha già per i controller veri); un'opzione fa mandare invece la *lettera* (A Nintendo = A).
- **Aspetto automatico del controller**: con un gioco PS1/PS2/PS3/PSP/Vita in corso il telefono passa da solo al layout
  PlayStation, con un gioco Switch al layout Switch (disattivabile in ⚙).
- **Vibrazione dal gioco al telefono**: quando il gioco fa vibrare il controller virtuale, vibra il telefono (impulsi
  più lunghi per vibrazioni più forti). Funziona su Android; Safari su iPhone/iPad non permette la vibrazione alle pagine web.
- **Tasti a schermo personalizzabili**: ⚙ › «Sposta e ridimensiona i tasti»: si trascina ogni gruppo (levette, croce,
  tasti azione, dorsali, tasti centrali) e se ne cambia la dimensione. La disposizione si salva per ogni aspetto
  (Xbox, PlayStation, Switch) in percentuale dello schermo; «Ripristina» torna a quella originale.
- **«📱 Gioca su questo telefono»** nella scheda di un gioco sul telefono: avvia il gioco sul PC e spiega come entrarci
  da Moonlight con un tocco tramite la nuova app **«▶ Gioco in corso»** pubblicata in Sunshine (mostra lo schermo del PC).
  Aprire Moonlight direttamente su un gioco da una pagina web non è possibile: Moonlight per iOS non registra schemi
  URL e su Android il suo collegamento ai giochi non è raggiungibile dal browser (verificato sui sorgenti ufficiali).
- **«⚡ Ottimizza lo streaming»** (Impostazioni › Telefono e streaming): controlla Sunshine (avviato, con Windows),
  il preset dell'encoder NVIDIA, il two-pass, la correzione degli errori e se il PC è via cavo o Wi-Fi, con le istruzioni
  per ogni modifica; consigli per TV, box e telefono (Modalità Gioco, cavo, frame pacing, bitrate, statistiche di Moonlight).

### Corretto
- **Giochi avviati dal telefono che non comparivano in «In corso» e «Giocati di recente».** Due cause: la partita veniva
  registrata solo alla fine, e l'app sul PC controllava lo stato solo dei giochi avviati da lei, quindi non ricaricava
  i dati. Ora una partita, da qualunque dispositivo (PC, telefono, Moonlight), entra subito tra i recenti e «In corso»
  quando parte; l'app sul PC si accorge entro pochi secondi delle modifiche fatte altrove (partite, preferiti, stati)
  e mostra anche la barra «In esecuzione» dei giochi avviati dal telefono.
- **Store Minerva: non per tutte le console venivano aggiunti i link.** L'importazione si fermava se una console aveva già gli store nella forma `{"urls": [...], "type": ...}` (le console seguenti restavano senza link); ora il tipo e le opzioni restano e gli URL si aggiungono. Riconosciute anche 3DO, PC Engine CD, Neo Geo CD, Jaguar CD e MS-DOS, prima scartate.

### Cambiato

- Sviluppo: versioni e changelog con `tools/version.py` (numero calcolato dal changelog, commit «Version x.y.z», lavori in corso fuori dal commit); istruzioni in `VERSIONING.md`.

## 0.2.2 (2026-10-26)

### Cambiato
- **Una sola cartella dati per exe e sorgenti.** Prima l'exe usava `%LOCALAPPDATA%\Pozzo Launcher\` e i sorgenti il
  `config.toml` del progetto: libreria, cache, preferiti e impostazioni si dividevano in due copie. Ora `config.toml`
  si cerca in quest'ordine: `POZZO_CONFIG`, accanto all'exe (versione portatile), cartella dati dell'utente;
  solo se questa non esiste ancora, da sorgenti, quello del progetto o della cartella corrente. Una copia nel progetto
  non viene più letta e il programma lo segnala sulla console; per usarla: `POZZO_CONFIG=<percorso>`.
  La copia vecchia nel progetto (`cache\`, `settings.json`) non è stata toccata né cancellata.

### Aggiunto
- **Riassociazione delle cartelle rinominate** in Impostazioni › Nuovi giochi: i giochi con file mancanti vengono
  abbinati alle cartelle nuove (stessa console e stessa dimensione, oppure nome simile) e si possono riassociare
  con un clic: metadati, tempo di gioco, preferiti e collezioni passano alla nuova cartella. Prima si salva una
  copia dei database (`*.bak`, ora con l'API di backup di sqlite, coerente anche a database aperto).
  Nuovi endpoint `GET /api/relink/plan` e `POST /api/relink/apply` (l'abbinamento si ricalcola sul server).
  Limite: funziona finché la libreria contiene ancora i giochi con i vecchi percorsi, cioè prima di una ricostruzione.
- **Copie di sicurezza dei dati utente** (Impostazioni › Libreria): preferiti, tempi di gioco, stati, note, collezioni
  personali e `settings.json` in uno zip in `<cache>/backups`. Copia automatica settimanale all'avvio, si tengono le
  ultime 10. Il ripristino funziona con l'app aperta e prima salva una copia dei dati attuali, così si può annullare.
- **Pagina «Salute»** (Impostazioni › 🩺 Salute): cartelle ROM non raggiungibili, console senza emulatore pronto,
  `prod.keys` mancante, giochi senza dati o copertina, giochi con i file non trovati, fonti online che non rispondono,
  età dell'ultima copia dei dati. Ogni problema ha il pulsante che lo risolve. Nessuna richiesta in rete.
- **Più cartelle ROM** (Impostazioni › Nuovi giochi › Altre cartelle ROM, oppure `[paths] extra_roms`): altri dischi,
  anche una cartella che è essa stessa una console (es. `E:\Switch`). Un disco scollegato viene saltato e segnalato.
- **Nota personale e voto (1-5 stelle)** nella scheda del gioco, validi per tutte le versioni. Per i tag si usano le
  collezioni personali.
- **🎲 Gioco a caso** tra quelli mostrati (filtri e ricerca compresi), preferendo quelli avviabili subito.
- **Giochi gratis**: etichetta «Nuovo» e numero 🆕 nella barra laterale per le offerte comparse dall'ultima visita;
  pulsante «✓ Preso» per segnare quelle già riscattate; ordine per scadenza più vicina, prima quelle ancora da
  prendere; ♡ per quelle nella lista desideri.
- **Schermate di Eden** (e yuzu, suyu, citron) importate dopo ogni partita come già per Ryujinx e gli altri emulatori:
  cartella predefinita `%APPDATA%\eden\screenshots`, versione portatile `user\screenshots` accanto all'exe e percorso
  personalizzato letto da `qt-config.ini`.
- **Copie dei salvataggi dei giochi** (scheda del gioco › 💾 Salvataggi): una copia automatica a ogni fine partita
  (se i salvataggi non superano 1 GB), «Copia adesso» e «Ripristina» (che prima copia i salvataggi attuali). Si tengono
  le ultime 10 per gioco in `<cache>/saves`. Emulatori supportati, perché lì i salvataggi si riconoscono per singolo
  gioco: Eden/yuzu (Title ID nel percorso), Ryujinx (Title ID in `ExtraData0`), RetroArch (file `.srm`/`.state` con
  il nome della ROM). Sui tuoi dati: salvataggi riconosciuti per 6 giochi con Eden e 44 con Ryujinx. Il ripristino
  riscrive i file della copia ma non cancella quelli nuovi creati dopo. Disattivabile con `[app] save_backups = false`.
- **Telefono e Big Picture**: stato del gioco e «Togli da Giocati di recente» anche lì.
- **Lista desideri: prezzi dei negozi di key** (giochi PC con codice Steam) tramite l'API ufficiale di
  **GG.deals** (chiave gratuita, da inserire in ⚙ della lista): prezzo più basso dei negozi di key, sconto rispetto al
  prezzo pieno ufficiale (es. 59,99 € su Steam → 18,50 € = -69%), minimo storico e pulsante 🔑 per il confronto.
  La soglia «≤ €» di ogni gioco vale ora anche per i negozi di key: se uno qualsiasi scende a quel prezzo o sotto
  arriva l'avviso. Allkeyshop non è usabile per questo: blocca l'IP dopo 4-5 richieste e un prezzo per gioco
  richiederebbe una richiesta per ciascuno.
- **Giochi gratis: Prime Gaming anche senza allkeyshop**, dal feed Atom pubblico di LootScraper (link diretto al
  riscatto su Luna, copertina, scadenza e valore). Cache di 12 ore, 3 ore di attesa dopo un errore; se un gioco c'è
  già da allkeyshop si aggiungono solo scadenza e valore. *(Gemini)*
- **Metadati Switch dai file `.nsz` e `.xcz`** (compressi): il Control NCA resta non compresso, quindi si leggono senza
  dipendenze nuove (es. Crawl). Riconosciuti anche come file sciolti fuori dalle cartelle. *(Gemini)*
- **Prova di avvio dell'exe nella release** (`packaging/smoke_test.py`): dopo la build il workflow avvia l'eseguibile
  con una cartella dati temporanea, aspetta che `/api/status` risponda e lo chiude, su Windows, macOS e Linux
  (con `xvfb-run`). Il workflow esegue ora **tutti** i test di `tests/`. *(Gemini)*
- **Streaming su TV, telefono e iPad (Sunshine + Moonlight), sistemato.** Il motivo per cui non funzionava: il servizio
  di Sunshine era fermo e impostato su avvio manuale (dopo un «Esci» dall'icona di Sunshine o un riavvio non ripartiva,
  quindi Moonlight non trovava il PC). «▶ Avvia Sunshine» ora lo avvia **e** lo imposta per partire con Windows, con
  una sola richiesta dei permessi di amministratore; la scheda avvisa se è in avvio manuale e la pagina «Salute»
  segnala quando è fermo. Nuova guida in Impostazioni › Telefono e streaming: TV con il controller collegato in
  Bluetooth alla TV (gli input arrivano al PC come controller Xbox virtuale tramite Moonlight → Sunshine → ViGEmBus),
  telefono/iPad con i tasti a schermo di Moonlight o un controller Bluetooth, telefono come controller.
- **App del telefono: controller vero o tasti a schermo.** Se al telefono/iPad è collegato un controller Bluetooth
  (PS5, PS4, Xbox, Switch Pro, MFi) l'app lo usa come controller del PC al posto dei tasti a schermo (Gamepad API);
  pulsante 🎮 per scegliere *Auto* / *A schermo* / *Il mio*. I tasti a schermo restano disponibili come prima.
- **Switch: aggiornamento e DLC** nella scheda del gioco («Aggiornamento 1.2.0», «3 DLC»), letti dalle intestazioni dei
  pacchetti nella cartella. Sulla tua libreria: 178 giochi con aggiornamento e 81 con DLC (670 in tutto). *(lettura: Gemini)*
- **Esportazione per ES-DE e Pegasus** (Impostazioni › Libreria, oppure `pozzo export-frontend --format esde|pegasus`):
  `gamelist.xml` + `downloaded_media`, oppure `metadata.pegasus.txt` + media. Sulla tua libreria: Saturn e Switch
  (476 giochi) in circa un secondo. *(formati: Gemini)*
- **RetroAchievements** (Impostazioni › Account: utente e Web API key): nella scheda dei giochi retro, obiettivi
  sbloccati, percentuale e icone. Abbinamento per hash (MD5 già noto dal DAT No-Intro, quindi funziona anche con le ROM
  in `.zip` e con le versioni italiane, che su RetroAchievements hanno il titolo inglese), altrimenti per titolo,
  nome canonico o nome del file. Cache: catalogo 7 giorni, abbinamento 30 giorni, progresso 30 minuti. *(client: Gemini)*
- **GG.deals**: formato della risposta verificato su implementazioni pubbliche dell'API (era scritto a memoria ed era
  giusto); regioni e limiti (100 giochi per richiesta, 1000 l'ora) rispettati. *(Gemini)*
- **Impostazioni › ℹ Info**: versione installata, controllo aggiornamenti sull'ultima release di GitHub (al massimo
  una richiesta ogni 12 ore, avviso una sola volta per versione) e questo changelog, ora incluso nell'eseguibile.

### Migliorato
- **Ricostruzione della libreria quasi due volte più veloce** (da 21,5 a 11,9 s su 20.187 voci): mancava l'indice
  su `games.grp`, quindi ogni aggiornamento delle durate HowLongToBeat scorreva tutta la tabella.

### Corretto
- **Eden**: argomenti di avvio verificati sui sorgenti ufficiali (`-g <gioco>`, `-f` schermo intero); gli argomenti
  extra di un profilo (es. `-f`) ora vanno *prima* di `-g`, che deve essere seguito subito dal gioco. Riconosciuto anche
  l'AppImage di Linux. *(Gemini)*
- **Switch, cartelle con aggiornamenti e DLC**: il gioco base è quello con il Title ID che finisce per `000`; prima un
  file `[v0]` poteva essere scartato e veniva avviato un aggiornamento. *(Gemini)*
- **Pacchetti Switch troncati riconosciuti**: OCTOPATH TRAVELER II è lungo esattamente 4 GiB (limite FAT32, prima parte
  di un NSP diviso) mentre il suo contenuto ne dichiara 5,2: il Control NCA sta oltre la fine del file. Ora l'errore
  lo dice chiaramente invece di «NCA Control non trovato». Il file va riscaricato o ricomposto. *(Gemini)*
- **`release.bat`**: niente più +0.0.1 automatico (vedi nota in alto); `*.bak` in `.gitignore`. *(Gemini)*
- **`release.bat`: zip non più interrotto da «file in uso da un altro processo»** (OneDrive o antivirus che
  aprono i file appena compilati): la compressione ora la fa Python, che legge i file in modo condiviso, invece di
  `Compress-Archive`.
- Un test scriveva lo stato dei giochi gratis nel `settings.json` della cartella corrente; ora usa una cartella temporanea.
- **GitHub Actions**: gli artifact scaricati dal workflow erano uno zip contenente un altro zip (`upload-artifact`
  impacchetta sempre quello che carica). Ora si usa `upload-artifact@v7` con `archive: false`: si scarica direttamente
  `Pozzo Launcher-<versione>-<sistema>.zip` (o `.tar.gz` su Linux). Il job di release usa `download-artifact@v8`.

## 0.2.0 (2026-10-25)

### Aggiunto
- **Menu del tasto destro su un gioco** (schermata principale): Gioca, Dettagli, Mostra nella cartella,
  preferiti, aggiungi a una collezione, stato (Da giocare / In corso / Finito / Abbandonato), nascondi.
- **«Rimuovi da…»** nel menu: dalla vista corrente (es. «Giocati di recente», Preferiti, uno stato, una collezione)
  con la voce in evidenza, e dalle altre categorie a cui il gioco appartiene. Togliere da «Giocati di recente»
  azzera solo l'ultima partita; tempo di gioco e avvii restano.
- **Giochi gratis da Steam**: giochi normalmente a pagamento con sconto del 100% (esclusi free to play, DLC e
  colonne sonore), letti dalla ricerca ufficiale di Steam.
- `/api/status` ora include `built_at` (data di costruzione della libreria).

### Corretto
- **Copertine e metadati che sparivano dalla schermata**: dopo una ricostruzione della libreria fatta altrove
  (scansione, CLI, altra finestra) la pagina usava i numeri di gioco vecchi e riceveva 404. Ora confronta la data
  di costruzione ogni 20 s, al ritorno sulla finestra e dopo un errore su copertina/dettaglio, e ricarica da sola.
- Una copertina che dà errore viene riprovata 2 volte prima di essere tolta (prima veniva rimossa al primo errore).
- **Giochi gratis / allkeyshop**: una sola richiesta al widget (niente più secondo tentativo sulla pagina del blog, che
  non contiene l'elenco), interrogato al massimo ogni 12 h, 3 h di attesa dopo un errore di rete, timeout di
  connessione 8 s. Se il sito non risponde (blocca l'IP dopo poche richieste) si tiene l'ultimo elenco buono, con i
  giochi Prime, invece di perderlo.
- **Pagina «Giochi gratis» che bloccava il resto dell'app**: con `cdn.allkeyshop.com` irraggiungibile (timeout 20 s)
  le copertine remote restavano appese e occupavano le poche connessioni del browser verso l'app, così le copertine
  e i dati dei propri giochi, anche cambiando pagina, restavano in coda. Ora le immagini remote hanno timeout brevi
  (connessione 4 s, totale 10 s) e un host che non risponde viene saltato per 5 minuti.
- **«Nuovi giochi» che restavano nuovi dopo lo scraping**: i file `[BIOS]` (64 nella tua raccolta) non entrano mai
  in libreria, quindi venivano contati come nuovi per sempre. Ora «nuovi» sono solo i giochi presenti nelle cartelle
  delle ROM e non ancora nella libreria; i BIOS sono esclusi (a meno di `show_bios`). I giochi aggiunti ma senza
  risultati compaiono tra i «Senza dati».
- Host delle copertine Steam aggiunto a quelli consentiti per le immagini remote.

### Test
- Widget allkeyshop reale come fixture (16 giochi, 9 Prime) e test del comportamento in caso di blocco.
- Test per la rimozione da «Giocati di recente» e per `built_at`.

### Note
- Prime Gaming si legge solo tramite allkeyshop: GamerPower non lo elenca più e la pagina di Amazon richiede login.
- L'exe non è stato provato con un gioco e un emulatore reali; il menu del tasto destro non è stato provato nell'interfaccia.

## 0.1.5 (2026-10-23)

### Aggiunto
- **Emulatore Eden** per Switch (accanto a Ryujinx): argomenti `-g {rom}`, ricerca di `eden.exe`.
  L'argomento `-g` non è verificato sulla documentazione di Eden.
- **Metadati Switch letti dal file** (`.nsp` / `.xci`) con il `prod.keys` dell'utente, come fanno gli emulatori:
  titolo, publisher, versione e icona 256×256 usata come copertina. Fonte `nsp`, offline, in testa alla catena;
  le altre fonti scaricano solo ciò che manca. Configurabile con `[paths] switch_keys`.
  Su 438 giochi Switch, 437 hanno copertina e publisher. Restano fuori `.nsz` e i titoli senza Control NCA
  (es. OCTOPATH TRAVELER II).
- **Comando `relink`** (`--apply`): riassocia i giochi con tutti i file mancanti ai nuovi percorsi dopo uno
  spostamento o la pulizia dei nomi delle cartelle, conservando metadati, tempi di gioco e collezioni
  (con backup dei database).
- **Istanza unica**: una seconda copia dell'app riporta in primo piano la finestra già aperta (`/api/focus`)
  invece di aprire una pagina nel browser.
- `release.bat`: aumenta la versione di 0.0.1, compila con PyInstaller e crea
  `release\Pozzo Launcher-<versione>-windows-x64.zip`. Nessuna operazione git.
- Note di progetto per Obsidian in `docs/obsidian/Pozzo Launcher/` (18 note: architettura, pipeline, fonti, cache,
  frontend, avvio giochi, store, Big Picture, telefono, plugin, packaging, test, cronologia).

### Corretto
- Build che non apriva i giochi, apriva una pagina web al posto della finestra e mostrava
  `ERR_CONNECTION_REFUSED` su `:8765`: restava in esecuzione una copia vecchia sulla stessa porta.
- Lo zip veniva dichiarato creato anche quando la compressione falliva (file in uso).
- Lettura dei pacchetti XCI: la partizione radice HFS0 è a 0x130, non 0x138; cartelle annidate cercate
  fino a un livello.

### Note
- Esistono due copie dei dati: `cache\` nel progetto e `%LOCALAPPDATA%\Pozzo Launcher\cache` per l'exe.
  Vanno tenute allineate a mano.

## 0.1.1 e precedenti

- 0.1.0 – 0.1.1: prima versione in Python con interfaccia in stile Playnite
  (FastAPI + pywebview): scansione ROM, cascata di fonti (ScreenScraper, IGDB, RAWG, TheGamesDB, Libretro,
  LaunchBox, Wikipedia…), cache, libreria, collezioni, avvio con emulatori, store, Big Picture, versione per telefono.
  Il dettaglio è nello storico git (`git log`).
