# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Giocatori che tengono in un'unica libreria le ROM di ogni console e i giochi PC dei loro store. Giocano dal desktop, da Big Picture con il controller, dal telefono o in streaming. Per l'overlay di gioco (pywebview su Windows) non c'è una situazione prioritaria: deve funzionare allo stesso modo con tastiera/mouse a scrivania e con il pad dal divano.

## Product Purpose
Pozzo Launcher raccoglie ROM e giochi PC, scarica da solo copertine, descrizioni, voti e tempi di gioco, e permette di giocare da qualsiasi dispositivo. L'overlay si apre durante il gioco (hotkey, di default ctrl+shift+o, oppure Select+R3) e offre tempo di sessione, screenshot, pausa, chiusura del gioco, tasti media, obiettivi e ultime note del diario. Successo: azioni rapide senza uscire dal gioco.

## Positioning
Per l'overlay: funziona con ROM ed emulatori oltre che con i giochi PC (salva/carica stato, cambio disco, tempo e diario per qualsiasi sistema), cosa che gli overlay degli store e delle schede video non coprono. Decisione confermata dall'utente.

## Operating Context
App desktop Windows con interfaccia web servita localmente (FastAPI + pywebview). L'overlay è una finestra trasparente sopra al gioco, con un toast separato per gli obiettivi. Non funziona con il fullscreen esclusivo. Navigazione con tastiera e controller (croce, A conferma, B chiude).

## Capabilities and Constraints
- Solo locale, nessun account o servizio cloud obbligatorio (vedi PRIVACY.md).
- Ogni testo visibile passa dall'i18n in 7 lingue: it, en, de, es, fr, pt-BR, tr (`pozzo/data/locales/`, skill `translate`).
- Gratuito e open source: nessuna funzione a pagamento.
- Estensioni opzionali in `extensions/` (es. diario, limite-tempo) che l'overlay può leggere, ma che possono mancare.
- Indecisi: quali widget includere nella prima versione (metriche, clip, menu emulatori), uso di dipendenze di sistema per le metriche.

## Brand Commitments
Nome: Pozzo Launcher. Interfaccia in italiano per default, documentazione in italiano e inglese. Stile e tema dell'app (token in `app.css`, temi e layout selezionabili) sono incumbent e l'overlay li eredita.

## Evidence on Hand
README.md, docs/ (manuale online), screenshot in docs/img/. Nessuna testimonianza o numero di utenti documentato: non inventarne.

## Product Principles
1. Non togliere il giocatore dal gioco: apertura e chiusura rapide, il focus torna sempre al gioco.
2. Un solo overlay per tutti i sistemi, ROM ed emulatori compresi.
3. Tastiera e controller sono cittadini di pari livello.
4. Tutto locale e senza account.
5. Ogni funzione nuova arriva in tutte e 7 le lingue.

## Accessibility & Inclusion
Navigazione completa da tastiera e controller con focus sempre visibile; contrasto del testo leggibile a distanza; rispetto di "riduci movimento"; target di tocco/focus ampi.
