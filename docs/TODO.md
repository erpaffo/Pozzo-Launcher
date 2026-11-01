[ ] Migliorare la sezione download (sia per minerva che per il resto). Vorrei che cliccando sul pulsante download si possa scaricare solo il gioco e non tutto il pacchetto, mentre per gli altri vorrei il link diretto. PEr i giochi della switch utilizziamo un qualcosa per skippare oio e avere direttaemnte il link al download del file di gioco. Il pulsante download deve reindirizzare alla pagina dove si può scaricare il gioco oppure al torrent che scaricare il singolo gioco (e non il pacchetto di tutta la console. Se non si può fare cerca di modificare il magnet per richiedere solo il gioco desiderato)
[x] Suddividere per i giochi degli store tra giochi e DLC («add-on» = DLC: una categoria sola), con gli
    aggiornamenti aggregati al gioco base
    - `pozzo/storekind.py`: `content_kind()` -> game | dlc | extra | update. Prima i segnali del nome
      (aggiornamento, colonna sonora/artbook), poi il tipo dichiarato dallo store, poi le parole DLC.
      `switch_kind(title_id)`: `…x000` gioco, `…x800` update, altro dlc.
    - Store PC: tipo dichiarato, niente euristiche. Steam `IStoreBrowseService/GetItems/v1` (GET,
      `input_json`, senza chiave, blocchi di 250 appid): `type` 0=gioco / 4=dlc / 6=app. Epic
      `categories "addons"` / `mainGameItem`. GOG `type` 1=gioco / 3=pack.
    - Cataloghi console: nome + `title_id` della pagina (Switch) + conferma dal peso (`_dlc_by_size`:
      «Gioco - Qualcosa» sotto il 35% del gioco omonimo). Niente soglie assolute.
    - Aggiornamenti: non sono voci della libreria; `_attach_updates` li aggancia al gioco base (stesso
      elenco o già posseduto) e la scheda li mostra come «⬆ Aggiornamenti installabili».
    - Colonna `content` in `games`, campo in `/api/library` e nella scheda gioco; badge «DLC» sui riquadri.
    - Checkbox «Nascondi DLC» nella vista di ogni console (`POST /api/app/hide-dlc`, `app.hide_dlc`).
    - Test: `tests/catalog/test_build_store.py`, `tests/test_stores.py`, `tests/test_fixes_backend.py`.
[x] Capire come mostrare le copertine dei giochi degli store quando ci sono 140000 elementi. Il problema è che quando scendo troppo nella lista, le copertine dei giochi che osservo non sono presenti, perché vengono caricate in ordine. Invece io vorrei caricare solo le copertine dei giochi che "sto vedendo", quindi in quel determinato punto dell'elenco. Carica i giochi con un offset di una riga di giochi, sia sopra che sotto

# Roadmap

Priorità: **H** alta, **M** media, **L** bassa. Dentro ogni gruppo le voci sono già in ordine di importanza consigliato; ogni voce ha la versione prevista (`vX.Y.Z`); l'elenco completo con stato è in `pozzo-progressi.csv`.

## Splash screen e avvio

[ ] **[H]** Splash screen all'avvio dell'app — v0.12.0
    - Schermata con logo del pozzo e barra di avanzamento mentre partono server, libreria, store ed estensioni; chiusura appena la UI è pronta
[ ] **[H]** Splash a schermo intero per Big Picture — v0.12.0
    - Stile Steam: logo animato, messaggi di stato («Carico la libreria…», «Cerco il controller…»), poi transizione alla Home
[ ] **[M]** Avanzamento reale dell'avvio nello splash — v0.13.0
    - Collegare la barra ai passi veri (db, libreria, estensioni) invece di un timer; mostrare l'eventuale errore
[ ] **[M]** Avvio diretto in Big Picture — v0.13.0
    - Opzione «apri in Big Picture all'avvio» e parametro da riga di comando, utile per HTPC e console casalinga
[ ] **[L]** Ripresa rapida dell'ultima sessione — v0.16.0
    - Riaprire l'ultima vista e l'ultimo gioco selezionato senza ricaricare tutto

## Esperienza utente

[ ] **[H]** Primo avvio guidato (onboarding) — v0.12.0
    - Procedura in 4 passi: cartelle ROM, emulatori, store, tema. Evita impostazioni sparse per il nuovo utente
[ ] **[M]** Ricerca globale con scorciatoia (Ctrl+K) — v0.13.0
    - Palette comandi per giochi, impostazioni, console e azioni; usa il pannello scorciatoie già presente
[ ] **[M]** Schede «Continua a giocare» e «Riprendi» — v0.13.0
    - Home con ultimo gioco, tempo rimasto, salvataggio più recente e avvio con un clic
[ ] **[M]** Messaggi d'errore con azione risolutiva — v0.13.0
    - Ogni errore (emulatore mancante, cartella non raggiungibile) propone il pulsante che lo risolve
[ ] **[M]** Accessibilità: focus visibile e navigazione da tastiera ovunque — v0.13.0
    - Verificare con screen reader e contrasto; estendere quanto fatto in Big Picture al resto dell'app
[ ] **[L]** Suggerimenti contestuali al primo uso di ogni funzione — v0.16.0
    - Brevi tooltip dismissibili, memorizzati per non ripetersi
[ ] **[L]** Localizzazione interfaccia (italiano/inglese) — v0.16.0
    - Estrarre le stringhe in file di traduzione; oggi l'interfaccia è solo in italiano
[ ] **[L]** Tour dei temi con anteprima dal vivo — v0.16.0
    - Anteprima del tema al passaggio del mouse senza applicarlo

## Emulatori: installazione semplice

[ ] **[H]** Installazione guidata «un clic» per console — v0.12.0
    - Dalla scheda console: «Installa l'emulatore consigliato» con scelta automatica (RetroArch, Dolphin, PCSX2, ecc.)
[ ] **[H]** Verifica BIOS e firmware richiesti — v0.12.0
    - Controllo hash di BIOS/firmware per console, con link alla procedura corretta e stato verde/rosso
[ ] **[M]** Emulatore consigliato per console con motivazione — v0.13.0
    - Tabella console → emulatore migliore (fedeltà, prestazioni, controller) mostrata nell'onboarding
[ ] **[M]** Aggiornamento automatico degli emulatori in background — v0.13.0
    - Controllo periodico delle release, aggiornamento con ripristino in caso di errore
[ ] **[M]** Configurazione automatica dei controller per emulatore — v0.13.0
    - Mapping predefinito per Xbox/PlayStation/Switch Pro applicato alla prima installazione
[ ] **[M]** Rilevamento emulatori già installati altrove — v0.13.0
    - Scansione di percorsi comuni, Scoop, Winget, Steam e registro per evitare reinstallazioni
[ ] **[M]** Diagnostica «perché non parte?» — v0.13.0
    - Procedura che controlla emulatore, BIOS, ROM e argomenti e indica la causa più probabile
[ ] **[L]** Profili grafici per emulatore (risoluzione, shader) — v0.16.0
    - Preset «Qualità / Prestazioni / Fedele» per ogni emulatore supportato
[ ] **[L]** Disinstallazione e pulizia emulatori dall'app — v0.16.0
    - Rimozione con scelta di conservare o cancellare config e salvataggi
[ ] **[L]** Installazione portatile con dati separati — v0.16.0
    - Cartella dati di ogni emulatore dentro la cartella dell'app per backup e spostamento facili

## Animazioni leggere

[ ] **[H]** Budget di prestazioni per le animazioni — v0.12.0
    - Limite di frame e di memoria misurato nei test; disattivazione automatica su macchine lente o con batteria
[ ] **[M]** Usare solo transform e opacity (GPU) per ogni animazione — v0.13.0
    - Audit di motion.css/js: niente animazioni di layout, niente filtri blur costosi nelle liste lunghe
[ ] **[M]** Transizioni condivise tra lista e dettaglio gioco — v0.13.0
    - La copertina «vola» nel dettaglio; solo CSS, nessuna libreria
[ ] **[M]** Animazione di caricamento a scheletro (skeleton) — v0.13.0
    - Sostituisce gli spinner nelle griglie, leggera e coerente con il tema
[ ] **[M]** Interruttore «Animazioni: complete / ridotte / nessuna» — v0.13.0
    - Oltre al rispetto del movimento ridotto del sistema, scelta manuale e salvata
[ ] **[L]** Misura automatica degli FPS in Big Picture — v0.16.0
    - Se scende sotto soglia riduce da sola gli effetti

## Estensioni: feed notizie e novità

[ ] **[H]** Estensione «Feed notizie videogiochi» (stile Twitter) — v0.13.0
    - Pagina timeline con ultime notizie di Nintendo, Sony PlayStation, Xbox, Valve, Epic, CD Projekt, Ubisoft, Capcom, ecc. Fonti: RSS/Atom ufficiali e blog; nessun account social richiesto
[ ] **[H]** Feed filtrato sui tuoi giochi e console — v0.13.0
    - Mostra prima le notizie su titoli posseduti, in wishlist o su console della libreria
[ ] **[M]** Fonti del feed configurabili e raggruppate per casa — v0.14.0
    - Elenco attivabile/disattivabile, con aggiunta di un RSS personalizzato
[ ] **[M]** Annunci e prossime uscite nel feed — v0.14.0
    - Card dedicate con data di uscita, piattaforme e trailer; collegata al Calendario uscite
[ ] **[M]** Rassegna settimanale «Cosa è successo nel mondo console» — v0.14.0
    - Riepilogo automatico dei fatti principali: annunci hardware, scoperte, fine servizio, grandi sconti
[ ] **[M]** Segui un gioco: patch notes e DLC — v0.14.0
    - Pulsante «Segui» nel dettaglio gioco, con avvisi su aggiornamenti e nuovi contenuti
[ ] **[M]** Cache e rispetto dei limiti dei siti nel feed — v0.14.0
    - Controllo condizionale (ETag), pausa tra le richieste, nessun caricamento di immagini non visibili
[ ] **[M]** Estensione «Sconti e bundle» — v0.14.0
    - Storico offerte e minimi storici per i giochi della wishlist, in aggiunta ai prezzi già presenti
[ ] **[M]** Estensione «Recensioni e punteggi» — v0.14.0
    - Punteggi aggregati (OpenCritic/Metacritic via fonti consentite) mostrati nel dettaglio
[ ] **[L]** Notifiche per notizie importanti — v0.16.0
    - Alert (Windows e telefono) per annunci di giochi in wishlist, patch e Direct/State of Play
[ ] **[L]** Estensione «Eventi e fiere» — v0.16.0
    - Calendario di Gamescom, Summer Game Fest, Nintendo Direct, ecc. con promemoria
[ ] **[L]** Estensione «Speedrun e record» — v0.16.0
    - Record del mondo e link da speedrun.com per i giochi in libreria

## Suggerimento estensioni

[ ] **[H]** Estensioni consigliate in base alla libreria — v0.13.0
    - Se hai molti giochi Switch propone l'estensione Switch, se hai wishlist propone Calendario uscite, ecc.
[ ] **[M]** Sezione «Scopri estensioni» nello Store estensioni — v0.14.0
    - Più usate, nuove, aggiornate di recente, con schermate e permessi richiesti
[ ] **[M]** Permessi dichiarati e mostrati per ogni estensione — v0.14.0
    - Mostrare cosa può leggere/scrivere prima dell'installazione; sicurezza dell'ecosistema
[ ] **[L]** Valutazioni e conteggio installazioni delle estensioni — v0.16.0
    - Voti degli utenti e segnale di affidabilità; richiede un indice ufficiale esteso
[ ] **[L]** Estensioni consigliate dopo un'azione dell'utente — v0.16.0
    - Es. dopo aver cercato spesso i prezzi propone «Sconti e bundle»

## Metadati e classifiche

[ ] **[H]** Metadati collegati alle ROM tramite hash — v0.14.0
    - Identificare la ROM con CRC/SHA1 (DAT No-Intro, Redump, LaunchBox) invece del solo nome file, per abbinamenti sicuri
[ ] **[H]** Classifiche collegate alle ROM — v0.14.0
    - Punteggi e Top per console agganciati alla ROM (non solo ai giochi con store), da LaunchBox/RAWG/IGDB
[ ] **[H]** Suggerimenti per giochi non presenti in nessuno store — v0.14.0
    - Raccomandazioni basate su generi, serie, sviluppatore e punteggi, anche per titoli solo ROM o solo cataloghi esterni
[ ] **[M]** Verifica dump: ROM buone, danneggiate, hack e traduzioni — v0.15.0
    - Confronto con DAT No-Intro/Redump; badge «verificata» e rapporto
[ ] **[M]** «Perché te lo consiglio» — v0.15.0
    - Ogni suggerimento mostra il motivo (stesso sviluppatore, simile a un gioco amato, genere preferito)
[ ] **[M]** Giochi simili nel dettaglio di ogni gioco — v0.15.0
    - Sezione con titoli affini, anche non posseduti, con pulsante «Aggiungi alla wishlist»
[ ] **[M]** Serie, franchise e ordine di gioco — v0.15.0
    - Riconoscere i capitoli di una saga e proporre l'ordine consigliato e cosa manca
[ ] **[M]** Importazione metadati da IGDB — v0.15.0
    - Fonte aggiuntiva con chiavi dell'utente, per copertura di titoli rari
[ ] **[M]** Classifica personale e statistiche di gusto — v0.15.0
    - Generi e decenni preferiti dedotti da tempo di gioco e voti; alimenta i suggerimenti
[ ] **[M]** Novità interessanti per la tua libreria — v0.15.0
    - Elenco di giochi usciti di recente o remaster legati a ciò che hai
[ ] **[L]** Importazione dati da Backloggd/Steam/Xbox/PSN — v0.16.0
    - Stati, ore e giudizi importati dai servizi pubblici o da export dell'utente
[ ] **[L]** Correzione manuale e riuso dei metadati — v0.16.0
    - Le correzioni dell'utente restano e possono essere esportate/condivise

## Ottimizzazione del codice e delle funzioni

[ ] **[H]** Profilazione e budget di memoria nei test automatici — v0.12.0
    - Test che falliscono se avvio o libreria superano soglie di RAM e tempo (oggi misurati a mano)
[ ] **[H]** Caricamento a pagine della libreria (virtualizzazione liste) — v0.12.0
    - Disegnare solo le righe visibili in tutte le viste, non solo nelle copertine; con 160.000 voci
[ ] **[M]** Suddivisione di app.js e server.py in moduli — v0.13.0
    - File grandi da spezzare per area (libreria, store, impostazioni) per manutenzione e caricamento più rapido
[ ] **[M]** Caricamento differito delle estensioni non usate — v0.13.0
    - Avviare le estensioni solo quando servono, con misura del tempo di avvio per ognuna
[ ] **[M]** Cache disco per le risposte delle fonti dati — v0.13.0
    - Evitare richieste ripetute a LaunchBox, RAWG, HLTB; scadenza e invalidazione chiare
[ ] **[M]** Test end-to-end dell'interfaccia (browser headless) — v0.13.0
    - Provare avvio, ricerca, apertura dettaglio e Big Picture; coprire anche la mancanza del test reale su exe
[ ] **[M]** Test con gioco ed emulatore reali in CI — v0.13.0
    - Smoke test con un emulatore e una ROM di prova libera
[ ] **[M]** Compressione e formati moderni per le copertine — v0.13.0
    - WebP/AVIF e miniature per griglia, per risparmiare disco, banda e RAM
[ ] **[L]** Pulizia del codice morto e delle dipendenze — v0.16.0
    - Rimuovere moduli e CSS inutilizzati dopo i grandi cambi di interfaccia (Skyscraper, vecchie grafiche)
[ ] **[L]** Telemetria locale opzionale degli errori — v0.16.0
    - Registro degli errori leggibile e inviabile a mano; nessun invio automatico
[ ] **[L]** Aggiornamenti differenziali dell'app — v0.16.0
    - Scaricare solo i file cambiati invece dell'intero pacchetto
[ ] **[L]** Documentazione dello sviluppo aggiornata — v0.16.0
    - docs/sviluppo.md con architettura attuale, esperienze, motion, icone e come aggiungere un tema
