# Centro Assistenza e Domande Frequenti (FAQ)

Benvenuto nel **Centro Assistenza di Pozzo Launcher**. Questa guida è strutturata per rispondere rapidamente ai tuoi dubbi, guidarti passo-passo nella risoluzione dei problemi più comuni e permetterti di sfruttare al massimo ogni funzionalità dell'applicazione.

---

## 🔍 Cosa stai cercando di fare?

Scegli l'argomento su cui desideri ricevere supporto:

| Categoria | Descrizione |
|---|---|
| [📁 ROM, Cartelle e Copertine](#rom-cartelle-e-copertine) | Configurare le cartelle ROM, identificare i giochi e correggere immagini o titoli mancanti |
| [🎮 Avvio Giochi ed Emulatori](#avvio-giochi-ed-emulatori) | Risolvere problemi di avvio, configurare emulatori e parametri personalizzati |
| [📱 Telefono, Telecomando e Doppio Schermo](#telefono-telecomando-e-doppio-schermo) | Abbinare lo smartphone, certificato HTTPS, touchscreen DS/3DS e controller |
| [💾 Salvataggi, Versioni e Backup](#salvataggi-versioni-e-backup) | Come ripristinare un salvataggio precedente, sincronizzare due PC e usare Ludusavi |
| [💻 Giochi PC, Store e Web Game](#giochi-pc-store-e-web-game) | Integrare Steam, Epic, GOG, Riot, Battle.net e aggiungere giochi browser o .exe |
| [🎨 Aspetto, Temi e Big Picture](#aspetto-temi-e-big-picture) | Selezionare i 4 temi, cambiare profilo di esperienza o giocare dalla TV con controller |
| [🛠️ Diagnostica, Porte e Risoluzione Errori](#diagnostica-porte-e-risoluzione-errori) | Schermata Salute, porte 8765/8766 occupate e file bloccati |

---

## 📁 ROM, Cartelle e Copertine

![La console Game Boy Advance con oltre 5000 giochi organizzati e metadati completi](images/console.jpg)

### Dove devo mettere le mie ROM per farle comparire nell'app?
**Risposta:** Non serve spostare le tue ROM se le hai già organizzate!  
1. Vai in **Impostazioni › Libreria › Cartelle delle ROM**.
2. Clicca su **＋ Aggiungi cartella** e seleziona la cartella radice che contiene le tue raccolte (es. `E:\Roms`).
3. Pozzo Launcher riconosce automaticamente le sottocartelle con i nomi standard delle console (es. `gba`, `snes`, `psx`, `switch`, `nds`, `n64`, `megadrive`, ecc.).
4. In alternativa, puoi aggiungere una cartella dedicata a una singola console associandola direttamente dal menu a tendina.
5. Clicca su **⟳ Cerca nuovi giochi** in alto: i nuovi giochi compariranno istantaneamente nella barra laterale della console corrispondente!

Se copi una ROM in una cartella di console mentre l'app è aperta, compare da sola dopo una decina di secondi (si spegne in **Impostazioni › Libreria › Giochi nuovi**; i giochi cancellati dal disco si tolgono con **↻ Ricontrolla cartelle**).

---

### Perché una ROM non viene riconosciuta o non trova la copertina?
**Risposta:** Pozzo Launcher identifica i giochi tramite una combinazione di firme digitali (CRC32, MD5, SHA-1 del file o della partizione) e pulizia intelligente del nome del file:
- **Verifica il nome del file**: Nomi puliti come `Pokemon - Versione Rubino.gba` o codici scena No-Intro vengono identificati al primo colpo. Nomi con caratteri insoliti o abbreviazioni criptiche possono fallire.
- **Formati compressi**: I file `.zip` e `.7z` sono supportati per le console classiche. Per Switch sono supportati `.nsp`, `.xci` e `.nsz`.
- **Riprova la ricerca manuale**: Clicca con il tasto destro sul gioco e seleziona **🖼 Immagini del gioco…**: potrai caricare un'immagine dal PC, sceglierne una da SteamGridDB o incollare l'URL di un'immagine trovata su Internet.
- **Consulta la vista ? Senza dati**: Nella barra laterale, clicca su **? Senza dati** per vedere tutti i giochi che necessitano di una verifica e avviare **⟳ Cerca dati mancanti** solo per loro.

![La vista Senza dati: raggruppa tutti i giochi che richiedono attenzione o metadati manuali](images/libreria-senza-dati.jpg)

---

### Come funziona lo scraping offline per Nintendo Switch?
**Risposta:** Se possiedi una console Nintendo Switch e hai configurato il tuo file `prod.keys` in `config.toml` (chiave `switch_keys = "C:/percorso/prod.keys"`), Pozzo Launcher legge i metadati ufficiali (titolo, publisher, versione del gioco e icona a risoluzione nativa) **direttamente dall'interno del file `.nsp` o `.xci`**, senza richiedere alcuna connessione a Internet!

---

## 🎮 Avvio Giochi ed Emulatori

![Impostazioni › Emulatori: percorsi degli eseguibili e tabella di associazione per console](images/impostazioni-emulatori.jpg)

### Clicco su «Gioca» ma il gioco o l'emulatore non si apre: cosa fare?
**Risposta rapida:** Nel 95% dei casi l'emulatore non è ancora stato configurato o il percorso non è corretto.

Segui questa procedura di controllo:
1. Apri **Impostazioni › Emulatori**.
2. Controlla se la riga dell'emulatore che intendi usare (es. *DuckStation*, *PCSX2*, *Dolphin*, *Ryujinx*, *RetroArch*, *melonDS*) ha una spunta verde con il percorso dell'eseguibile compilato (es. `C:\Emulatori\Duckstation\duckstation-qt-x64-ReleaseLTCG.exe`).
3. Se il percorso è vuoto, premi **Cerca sul PC**: Pozzo Launcher cercherà l'emulatore nei percorsi standard di Windows, nei registri e nelle cartelle dell'utente.
4. Se hai una versione portatile, premi **Sfoglia…** e seleziona direttamente il file `.exe`.
5. Verifica nella tabella sottostante che la console (es. `psx`) sia assegnata all'emulatore desiderato (*DuckStation*).

---

### Posso usare parametri speciali o eseguire script prima/dopo la partita?
**Risposta:** Certamente!
- **Globale per emulatore**: In **Impostazioni › Emulatori › Avvio dei giochi** puoi specificare comandi pre-partita e post-partita (es. attivare un profilo colore HDR, accendere strisce LED o disattivare monitor secondari).
- **Singolo gioco**: Apri il dettaglio del gioco, clicca sull'icona **⚙ Profilo di avvio** e imposta parametri specifici per quel titolo (ad esempio un core RetroArch alternativo o risoluzioni personalizzate).

---

## 📱 Telefono, Telecomando e Doppio Schermo

![La web app sul telefono: Home, giochi PC, telecomando e controller virtuale](images/telefono.jpg)

### Come collego il mio smartphone all'applicazione?
**Risposta:** Non serve scaricare alcuna app dal Google Play Store o da Apple App Store: Pozzo Launcher integra una Progressive Web App (PWA) ad altissime prestazioni:
1. Sul PC vai in **Impostazioni › 📱 Telefono e streaming**.
2. Attiva l'interruttore **Accesso dal telefono**.
3. Inquadra il **QR Code di abbinamento** mostrato sullo schermo con la fotocamera del tuo smartphone.
4. Il codice a 6 cifre abbinerà in modo sicuro il tuo telefono al PC senza esporlo all'esterno.
5. Clicca su **Aggiungi alla schermata Home** (o Installa) per usarla come una vera app nativa a schermo intero!

![Impostazioni › Telefono e streaming: certificato, QR code e gestione dispositivi abbinati](images/impostazioni-telefono.jpg)

---

### Perché il browser del telefono dice «Connessione non privata» o non mi fa installare l'app?
**Risposta:** È assolutamente normale: il PC genera un certificato di sicurezza HTTPS locale autofirmato (necessario per abilitare i sensori del giroscopio e la vibrazione senza passare da server esterni).

**Come risolvere in 1 minuto:**
- **Su Android**: Inquadra il QR **🔒 Certificato del PC** in *Impostazioni › Telefono e streaming* (oppure scarica `PozzoLauncher-CA.crt`), aprilo in *Impostazioni › Sicurezza › Crittografia e credenziali › Installa un certificato › Certificato CA* e tocca «Installa comunque».
- **Su iPhone/iPad (Safari obbligatorio)**: Scarica il certificato, vai in *Impostazioni › Profilo scaricato › Installa*. Poi vai in *Impostazioni › Generali › Info › Impostazioni attendibilità certificati* e attiva l'interruttore su «Pozzo Launcher CA». Riapri Safari e l'avviso sarà sparito per sempre!

---

### Come funziona il «Doppio Schermo» per Nintendo DS e Nintendo 3DS?
**Risposta:** Questa è una delle funzionalità più amate di Pozzo Launcher:
- Quando avvii un gioco per Nintendo DS (con *melonDS*) o per Nintendo 3DS (con *Citra* o *Azahar*), se il tuo smartphone è connesso:
  - **Sul PC** vedi lo schermo superiore principale a tutto schermo in alta definizione.
  - **Sul telefono** vedi lo schermo inferiore e puoi toccarlo con le dita come se fosse il touchscreen originale della console!
- Se il telefono dovesse scollegarsi o spegnersi, l'app fa ricomparire istantaneamente il secondo schermo sul PC in modalità Picture-in-Picture senza interrompere la partita.

---

## 💾 Salvataggi, Versioni e Backup

![Impostazioni › Libreria: sincronizzazione tra PC, esportazione e copie di sicurezza](images/impostazioni-libreria.jpg)

### Il gioco si è bloccato o ho sovrascritto un salvataggio per sbaglio: posso recuperarlo?
**Risposta:** **Sì, con un clic!**  
Pozzo Launcher esegue una copia di sicurezza automatica con timestamp dei tuoi file di salvataggio **prima** di ogni avvio e **dopo** ogni chiusura:
1. Apri la scheda del gioco nella libreria.
2. Scorri fino alla sezione **Salvataggi**.
3. Clicca su **⏮ Annulla l'ultima partita**: l'app ripristinerà istantaneamente i salvataggi a come si trovavano prima che aprissi l'ultimo gioco.
4. Puoi anche visionare l'elenco delle versioni storiche, fissare una versione preferita con una nota (es. *"Prima del boss finale"*) o confrontare i file.

---

### Come sincronizzo i giochi tra PC fisso e portatile senza cloud a pagamento?
**Risposta:** Puoi scegliere tra due modalità integrate:
1. **Cartella condivisa**: Se usi OneDrive, Google Drive, Syncthing, Dropbox o una cartella di rete NAS, seleziona la stessa cartella in *Impostazioni › Libreria › Sincronizzazione*. I preferiti, le ore di gioco (sommate senza sovrascritture), i voti e le collezioni rimarranno sincronizzati in background.
2. **Rete locale diretta (Senza cloud)**: Se entrambi i PC sono connessi alla stessa rete Wi-Fi/LAN di casa, sul PC A premi **Genera codice di abbinamento** e sul PC B inserisci il codice. I due computer comunicheranno direttamente via HTTPS locale protetto con impronta SHA-256!

---

## 💻 Giochi PC, Store e Web Game

![I giochi PC degli store ufficiali: Steam, Epic, GOG, Riot e Battle.net](images/store-pc.jpg)

### Quali store PC sono supportati nativamente?
**Risposta:** Pozzo Launcher riconosce e cataloga in tempo reale i giochi installati e posseduti da:
- **Steam** (inclusi account multipli, lettura manifest e file VDF)
- **Epic Games Store**
- **GOG Galaxy**
- **Riot Games** (League of Legends, Valorant, Teamfight Tactics, Runeterra)
- **Battle.net** (Hearthstone, Overwatch 2, Diablo, WoW con monitoraggio del client rapido)
- **Amazon Games** e **Xbox / Game Pass**
- **Minecraft**

---

### Posso aggiungere un gioco browser da URL (es. Chess.com, Wordle)?
**Risposta:** Certamente!
1. Clicca su **＋ Aggiungi gioco** nella barra dei menu o sul pulsante in alto.
2. Scegli **Gioco da indirizzo web (browser)**.
3. Incolla l'indirizzo (es. `https://www.chess.com/play/online`).
4. Pozzo Launcher leggerà automaticamente il titolo, la descrizione e l'immagine Open Graph della pagina web, proteggendo la rete da indirizzi interni non validi.
5. Il gioco comparirà nella tua libreria PC e si aprirà nel tuo browser predefinito a schermo intero!

---

### I DLC o gli aggiornamenti compaiono come giochi separati: come posso raggrupparli?
**Risposta:**
- Nella barra in alto della vista console o store, attiva la casella **Nascondi DLC**: tutti i contenuti aggiuntivi verranno nascosti dalla griglia principale e raggruppati elegantemente all'interno della scheda del gioco base sotto la voce **DLC e aggiornamenti installabili**!

---

## 🎨 Aspetto, Temi e Big Picture

![Impostazioni › Aspetto: scelta del tema e galleria profili di esperienza](images/impostazioni-aspetto.jpg)

### Quali temi grafici sono disponibili?
**Risposta:** In **Impostazioni › Aspetto** puoi scegliere tra 4 palette cromatiche professionali curate nel dettaglio:
1. **OLED (Nero assoluto)**: Contrasto elevatissimo, perfetto per monitor OLED e sessioni notturne.
2. **Notte Blu**: Tonalità rilassanti indaco e blu scuro per il massimo comfort visivo.
3. **Retrò**: Toni caldi ispirati all'epoca d'oro delle sale giochi anni '80 e '90.
4. **Chiaro**: Look moderno, pulito e luminoso ideale per uffici o stanze molto illuminate.

---

### Cosa sono i 6 «Profili di Esperienza» desktop?
**Risposta:** A differenza del tema (che cambia solo i colori), il profilo di esperienza riorganizza completamente la disposizione dell'interfaccia desktop per adattarsi al tuo stile:
- **Scaffali**: Home con righe orizzontali in stile streaming per riprendere subito a giocare.
- **Cinema**: Layout immersivo con enormi sfondi dinamici e dettagli ad alto impatto.
- **Console**: Interfaccia a tutto schermo orientata alla navigazione con frecce.
- **Dashboard**: Vista compatta ricca di widget, statistiche e consigli immediati.
- **Vetrina**: Mette in primo piano le copertine più prestigiose della tua collezione.
- **Catalogo / Originale**: La classica interfaccia a griglia densa con barra laterale per veri collezionisti.

---

### Come gioco dalla TV con il controller (Modalità Big Picture)?
**Risposta:**
- Premi la combinazione `F11` oppure clicca sull'icona **Schermo Intero / Big Picture** nella barra dei menu.
- L'interfaccia si adatta istantaneamente ai display 16:9 4K della TV con caratteri grandi, navigazione fluida tramite D-Pad del controller e suoni d'interfaccia per il massimo relax dal divano!

![Big Picture: la modalità TV per navigare e giocare con il controller sul divano](images/bigpicture.jpg)

---

## 🛠️ Diagnostica, Porte e Risoluzione Errori

![La pagina Salute: controllo automatico di percorsi, database e servizi](images/impostazioni-salute.jpg)

### Cosa fare se compare l'errore «Porta 8765 o 8766 già occupata»?
**Risposta:** Questo accade se una copia precedente di Pozzo Launcher è rimasta attiva in background o se un altro programma usa quelle porte.
1. Controlla nella barra delle applicazioni vicino all'orologio di Windows: se vedi l'icona di Pozzo Launcher, fai clic destro ed esci.
2. Se necessario, apri *Gestione attività* (Task Manager con `Ctrl + Shift + Esc`), cerca eventuali processi `pozzo.exe` o `python.exe` rimasti aperti e premi *Termina attività*.
3. In alternativa, puoi cambiare la porta di rete in `config.toml` (es. `port = 8780`).

---

### Come posso verificare lo stato generale dell'app con la schermata «Salute»?
**Risposta:** Apri **Impostazioni › 🩺 Salute**:
- Pozzo Launcher esegue una diagnosi in tempo reale:
  - Integrità dei database SQLite (`library.db` e `userdata.db`)
  - Validità dei percorsi delle ROM e degli emulatori configurati
  - Stato del server locale e del server per smartphone
  - Servizio di streaming Sunshine e driver controller ViGEmBus
- Se viene rilevato un problema, la schermata ti mostrerà un pulsante verde **Risolvi** con le istruzioni esatte per sistemarlo con un solo clic.

---

> [!TIP]
> Hai un'altra domanda non presente in questa guida? Consulta il [Riferimento Completo dei Comandi](riferimento.md) o visita la community ufficiale sul repository GitHub di Pozzo Launcher!
