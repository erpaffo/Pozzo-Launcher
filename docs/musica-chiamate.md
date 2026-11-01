# Musica e chiamate

La modalità **Big Picture** include un mini-player integrato per **Spotify**, i controlli dei tasti multimediali di sistema e la gestione delle chiamate vocali con **Discord**.

Puoi aprire o chiudere il pannello multimediale tramite l'icona in alto a destra o cliccando lo stick destro del controller (`R3`). Una volta aperto:
- usa la croce direzionale o lo stick sinistro per navigare;
- premi **A (✕)** per selezionare o cambiare stato;
- premi **B (○)** per chiudere il pannello e tornare al gioco.

Il pannello aggiorna lo stato in tempo reale solo mentre è aperto (al massimo una richiesta Spotify ogni 5 secondi, per non gravare sulle risorse del PC). Fuori da Spotify collegato, i comandi di play/pausa, brano successivo/precedente e volume agiscono direttamente sui tasti multimediali di sistema di Windows.

---

## Spotify

Il controllo remoto di Spotify consente di ascoltare le tue playlist preferite in sottofondo durante le partite, visualizzare la traccia in riproduzione e passare al brano successivo con la combinazione `Select + RB` dal controller:

1. Apri la [dashboard per sviluppatori di Spotify](https://developer.spotify.com/dashboard) e crea una nuova applicazione (è gratuito).
2. Nella configurazione dell'app Spotify, aggiungi nei **Redirect URI** esattamente:  
   `http://127.0.0.1:8765/api/spotify/callback`  
   *(se hai cambiato la porta predefinita in `config.toml`, inserisci la porta in uso).*
3. Copia il tuo **Client ID** e incollalo in **Impostazioni › Integrazioni › Musica e chiamate**.
4. Premi **Accedi a Spotify** per autorizzare l'applicazione.

> [!NOTE]
> L'accesso usa il protocollo sicuro *Authorization Code con PKCE*, senza necessità di inserire il Client Secret. Il controllo remoto dei brani richiede un account Spotify Premium e un client Spotify attivo sul PC o sulla rete. Se non disponi di Spotify Premium, Pozzo Launcher utilizzerà i comandi multimediali di sistema per controllare qualsiasi riproduttore audio attivo (come VLC, foobar2000 o browser).

---

## Discord (Controlli Vocali in Gioco)

Oltre alla presenza ricca (*«Sto giocando a...»*, configurabile separatamente), puoi gestire i canali vocali di Discord direttamente dall'overlay di gioco senza dover premere Alt+Tab:

1. Crea un'applicazione personale nel [Discord Developer Portal](https://discord.com/developers/applications).
2. Inserisci l'**Application ID** e il **Client Secret** in **Impostazioni › Integrazioni › Musica e chiamate**.
3. Premi **Testa connessione** e approva gli scope richiesti (`rpc`, `rpc.voice.read`, `rpc.voice.write`) nella finestra di conferma di Discord.

### Cosa puoi fare dal controller durante il gioco:
- **Disattivare o riattivare il microfono (Mute)**: combinazione `Select + X (□)`.
- **Disattivare o riattivare l'audio in cuffia (Deafen)**: combinazione `Select + Y (△)`.
- **Regolare il volume** o visualizzare i partecipanti attivi nel canale vocale.

> [!TIP]
> Per il funzionamento dei comandi vocali è necessario che l'applicazione desktop di Discord sia aperta sullo stesso PC. I token OAuth e le chiavi rimangono salvati esclusivamente nelle impostazioni locali di Pozzo Launcher e non vengono mai condivisi all'esterno.
