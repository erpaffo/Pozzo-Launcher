# Musica e chiamate

Big Picture include un mini-player Spotify, i tasti multimediali di sistema e i comandi vocali Discord. Apri o chiudi il pannello col pulsante in alto a destra oppure cliccando lo stick destro; una volta aperto, usa croce/stick per spostare il fuoco, A per attivare e B per chiudere. Il pannello aggiorna lo stato solo mentre ? aperto (al massimo una richiesta Spotify ogni 5 secondi). Fuori da Spotify collegato, play/pausa, brano successivo/precedente e volume provano i tasti multimediali del sistema.

## Spotify

1. Crea un'app nel [dashboard Spotify](https://developer.spotify.com/dashboard).
2. Copia il **Client ID** in Impostazioni ? Integrazioni ? Musica e chiamate.
3. Nella configurazione dell'app Spotify aggiungi come Redirect URI esattamente `http://127.0.0.1:<porta>/api/spotify/callback` (la porta predefinita ? `8765`; usa quella configurata in Pozzo Launcher).
4. Salva il Client ID e premi **Accedi a Spotify**.

L'accesso usa Authorization Code con PKCE, senza Client Secret. Il controllo remoto del player richiede Spotify Premium e un dispositivo Spotify attivo; il fallback di sistema pu? controllare qualunque player che gestisca i tasti multimediali. Un'app Spotify Development pu? avere restrizioni proprie sugli utenti autorizzati.

## Discord

Le impostazioni gi? esistenti per ?Sto giocando a?? restano separate. Per i controlli vocali, inserisci l'Application ID e il Client Secret dell'app personale del Discord Developer Portal, poi premi **Testa connessione** e approva gli scope `rpc`, `rpc.voice.read` e `rpc.voice.write` nel client Discord aperto.

Discord limita gli scope RPC vocali: in genere sono disponibili solo al proprietario e ai tester registrati dell'applicazione. Serve Discord desktop aperto sullo stesso PC; non funziona con Discord web o con il client chiuso. L'IPC permette di leggere il canale/partecipanti e cambiare mute, deafen e volume o lasciare il canale; lo stato ?chi parla? dipende dagli eventi vocali che Discord espone al client. Se Discord non ? aperto o l'autorizzazione ? negata, Pozzo mostra lo stato e il motivo senza bloccare il launcher.

Client ID, Client Secret Discord e token OAuth sono salvati nelle impostazioni locali di Pozzo e non sono restituiti al frontend. Non sono state effettuate prove con account reali: autorizzazione, limiti Premium e disponibilit? degli scope RPC dipendono dagli account e dai client effettivi.
