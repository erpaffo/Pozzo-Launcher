# Sviluppo e dettagli tecnici

Per chi usa i sorgenti, vuole creare gli eseguibili o è curioso di come lavora Pozzo Launcher.

## Avvio rapido dai sorgenti (Windows)

```powershell
python -m pip install -r requirements.txt
copy config.example.toml config.toml     # solo la prima volta, se non hai ancora usato l'exe: poi modifica roms = "..." e le credenziali
python -m pozzo app                      # apre l'app su http://127.0.0.1:8765
```

## Creare gli eseguibili

Su GitHub li crea il workflow [`.github/workflows/release.yml`](https://github.com/erpaffo/Pozzo-Launcher/blob/main/.github/workflows/release.yml) a ogni tag di versione (`git tag v0.1.0 && git push origin v0.1.0`): build su Windows, macOS e Linux e pubblicazione nella release. In locale (solo per il sistema in uso):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller packaging/pozzo.spec --noconfirm     # risultato in dist/PozzoLauncher/
```

## Struttura del codice

```
pozzo/
  cli.py          comandi e barre di avanzamento
  config.py       caricamento di config.toml
  platforms.py    piattaforme: estensioni, id ScreenScraper/IGDB/TGDB, sistemi libretro, alias
  scanner.py      scansione cartelle, hash in parallelo, modello Game
  cache.py        cache SQLite
  net.py          client HTTP/2, rate limiter, retry, download media con verifica
  matching.py     confronto titoli (rapidfuzz)
  pipeline.py     orchestrazione a cascata e priorità per campo
  export.py       JSON/CSV/media per console
  api_client.py   client dell'API locale /api/v1 (usato da pozzo-cli e dagli script)
  sources/        libretro, arcadedb, igdb, screenscraper, thegamesdb
  app/            server FastAPI
    server.py       create_app(): parti condivise (config, libreria, launcher, eventi, lavori) + app
    routes/         endpoint /api, un modulo per area (vedi sotto): build_router(ctx)
    apiv1.py        API stabile /api/v1
    apitoken.py     token dell'API
    themes/         temi inclusi (chiaro, notte-blu, oled, retro)
    static/         interfaccia desktop, Big Picture e app del telefono (vedi sotto)
tests/test_pipeline.py   test end-to-end con API simulate (python tests/test_pipeline.py)
tests/perf/              budget di tempo e RAM di avvio e libreria (test_perf_budget.py)
```

### Server: `server.py` e `routes/`

`create_app()` costruisce una volta sola le parti condivise (config, libreria, profilo attivo, launcher,
eventi, lavori in background, telefono, plugin) e le passa ai moduli di `pozzo/app/routes/`, uno per
area: `library`, `stores`, `gameinfo`, `scan`, `saves`, `appsettings` (impostazioni e temi), `system`,
`wishlist`, `pages`… Ogni modulo espone `build_router(ctx) -> APIRouter` e prende da `ctx` solo ciò che
gli serve:

```python
def build_router(ctx) -> APIRouter:
    cfg, lib, events, job = ctx.cfg, ctx.lib, ctx.events, ctx.job
    router = APIRouter()

    @router.get("/api/...")
    def ...:
        ...

    return router
```

L'ordine di montaggio è in `routes/__init__.py` (`ORDER`): chi usa una funzione di un altro modulo
viene dopo, e la funzione arriva nel `ctx` con `vars(ctx).update(...)`. Un endpoint nuovo va nel modulo
dell'area che lo possiede; una funzione nuova condivisa si aggiunge al `ctx` in `create_app()`.

Lo split è **in corso**: gli endpoint passano via via nei moduli di `routes/`, mentre `create_app()` e
le parti condivise restano in `server.py`.

### Interfaccia: `core.js`, `js/` e `app.js`

Niente bundler: `index.html` carica **script classici** nell'ordine scritto nel file, e tutti
condividono l'ambito globale (`S`, `GS`, `api`, `esc`, `toast`…).

| File | Contenuto |
|---|---|
| `core.js` | utilità condivise (`api`, `esc`, `fold`, `store`), caricamento di temi, esperienze e plugin |
| `js/state.js` | stato della libreria, caricamento, filtri, ordinamenti |
| `js/grid.js` | griglia virtualizzata (nel DOM solo le copertine visibili) |
| `js/sidebar.js`, `js/home.js` | barra laterale e collezioni; vista «Per te» |
| `js/detail.js`, `js/actions.js` | scheda del gioco; popover, avvio, menu contestuale |
| `js/ports.js`, `js/pages.js` | giochi gratis e port PC; lista desideri, statistiche, top, schermate |
| `js/stores.js`, `js/settings.js`, `js/emulators.js` | store e fonti; impostazioni e toast; emulatori |
| `js/remote.js`, `js/events.js` | telefono e streaming; `bind()` di tutti gli eventi della pagina |
| `app.js` | avvio: impostazioni, estensioni, libreria, prima vista, polling |
| `motion.js`, `motion-settings.js`, `skeleton.css` | animazioni e segnaposto di caricamento |
| `icons.js` | icone SVG |
| `bigpicture.js` + `bigpicture.html` | modalità Big Picture (stessa API, markup suo) |
| `m/` | app del telefono (`index.html`, `m.js`, `m.css`, `sw.js`) |

Regola pratica: si tocca il file dell'area, e si aggiunge una funzione all'ambito globale solo se
serve davvero a più file — altrimenti resta in `js/` locale.

### Micro-animazioni

- `motion.css` definisce i token del movimento (`--mo-fast`, `--mo-base`, `--mo-ease`, distanza e
  ritardo a scalare) e le classi (`.mo-in` per l'ingresso di una copertina, `.mo-paused`). Si animano
  solo `transform` e `opacity`: mai il layout.
- `motion.js` non è legato alle viste: guarda il DOM, anima gli elementi che compaiono nel viewport
  (ingresso scaglionato, al massimo 24 per volta) e mette in pausa quando la scheda è nascosta o
  mentre si scorre.
- Intensità in `html[data-motion]`: `normal`, `reduced`, `off`. Si sceglie in **Impostazioni ›
  Aspetto › Animazioni** (`motion-settings.js`, salvata in `localStorage` come `gs.motion`); senza una
  scelta vale `prefers-reduced-motion` del sistema. Un tema o un'esperienza possono cambiare il
  carattere del movimento solo coi token (`--mo-k`, `--mo-t`), non con animazioni proprie.
- `GSSkeleton.show(container, n)` / `.hide(container)` (in `motion-settings.js`) mettono i segnaposto
  di `skeleton.css` durante il caricamento di una griglia.

### Icone

Tutte in `icons.js`: SVG inline 24×24, tratto 1,5 px, giunzioni arrotondate, `currentColor` (quindi
seguono il colore del tema). Tre modi per usarle:

- `GS.icon("nome", { size: 18, cls: "…" })` (alias `ic(...)`) nei template JS: restituisce la stringa SVG;
- `data-icon="nome"` nell'HTML statico;
- le emoji note a inizio testo («⚙ Impostazioni», «✕») vengono sostituite da sole nel DOM, anche per il
  contenuto creato dopo (`data-noicon` sull'elemento per lasciarle stare).

Per un'icona nuova basta aggiungere la voce all'oggetto `ICONS`: nessun file esterno, nessuna sprite.

### Come aggiungere un tema

Un tema sono due file, `theme.json` e `theme.css`, in `<cartella dati>/themes/<id>/` (accanto a
`config.toml`) oppure dentro l'app in `pozzo/app/themes/<id>/`. Formato dei file, variabili CSS da
ridefinire e attributi utili (`<html data-mode>`, `<html data-theme>`) sono in
[Temi e plugin](ESTENSIONI.md#temi): lì ci sono anche i quattro temi inclusi come esempio.

Lato codice, un tema non richiede modifiche:

- `pozzo/app/extensions.py` — `list_themes(cfg)` legge i `theme.json` (prima la cartella utente, poi
  `pozzo/app/themes/`), `theme_file(cfg, id, rel)` restituisce il file da servire;
- `pozzo/app/routes/appsettings.py` — `GET /api/extensions` dà temi, tema attivo ed esperienze,
  `POST /api/app/theme` salva `app.theme` in `config.toml`, `GET /themes/<id>/<file>` serve i file;
- `core.js` (`loadExtensions`) — aggiunge i fogli `<link data-ext="theme">` (`desktop` o `bigpicture`
  secondo la modalità), aspetta che siano applicati prima di mostrare la finestra e scrive
  `document.documentElement.dataset.theme`.

L'API stabile per script e integrazioni è descritta in [Riferimento › API locale](riferimento.md#api-locale):
gli endpoint `/api/v1` non cambiano a sorpresa, quelli sotto `/api` sono interni all'interfaccia.

## Esportare la libreria come pagina web

`python -m pozzo export-frontend --format html --out C:\mialibreria` (oppure Impostazioni › ▦ Libreria ›
*Esporta per altri frontend* › **Pagina web**) produce:

```
index.html          la collezione, con ricerca, filtro per console, ordinamento e scheda del gioco
covers/             le copertine (file locali)
```

È **un solo file più le immagini**, senza server e senza risorse esterne: si apre con doppio clic (anche da `file://`),
da un NAS, da un disco di rete o da un sito statico. La pagina funziona anche con migliaia di giochi (le schede si
disegnano man mano che scorri).

## Prestazioni

| | Pozzo Launcher |
|---|---|
| Identificazione | **Offline**: CRC e nome confrontati con i DAT No-Intro/Redump di libretro |
| Hash delle ROM | **Prima si prova il nome esatto sui DAT**: se corrisponde, CRC/MD5/SHA1 arrivano dal DAT e il file non viene letto. Gli altri: CRC degli ZIP letto dall'indice, blocchi da 8 MB, strategia HDD/SSD, risultati in cache |
| Rete | Asincrona con HTTP/2, rate limit solo dove serve |
| ScreenScraper | Media scaricati in parallelo, e solo quelli mancanti |
| IGDB | **10 giochi per richiesta**, 4 richieste/s |
| ArcadeDB | **25 giochi per richiesta** |
| Cache | SQLite con salvataggio continuo e ripresa automatica |
| Console | Tutte insieme |
| Fonti | **A catena**: tutte lavorano contemporaneamente su giochi diversi |

Misurato su 10.000 ROM in 5 console, con cartelle annidate: 9.500 identificate per nome senza leggere i file; scansione, hash dei restanti 500, identificazione ed export in **meno di 10 secondi** (senza media). Sulla collezione reale di prova (14.782 giochi su HDD), gli NDS da leggere passano da 149 GB a 3,6 GB. Le immagini da libretro arrivano a circa 16 al secondo (misurate su 300 copertine SNES, l'84% trovate): circa 30 minuti per cover, screenshot e title di 10.000 giochi.

### Come funziona la cascata delle sorgenti

Ogni fonte è uno stadio con la propria coda. Un gioco passa alla fonte successiva appena la precedente ha finito con lui, media compresi. Così, mentre ScreenScraper consuma lentamente la sua quota, libretro e IGDB stanno già lavorando sugli altri giochi. L'ordine di priorità non cambia: una fonte vede un gioco solo dopo tutte quelle che la precedono.

1. **libretro**: identifica ogni ROM offline e ricava titolo, sviluppatore, editore, genere, anno e giocatori. Scarica cover, screenshot e title screen da thumbnails.libretro.com, senza quota.
2. **arcadedb**: solo per le console arcade.
3. **igdb**: descrizioni, rating, cover e artwork per quello che manca ancora. Usa il nome canonico trovato da libretro. Prima cerca 10 giochi per richiesta con il nome esatto, poi fa la ricerca singola solo per quelli non trovati (la multiquery di IGDB non supporta `search`).
4. **screenscraper**: wheel, marquee, video, descrizioni in italiano e giochi non ancora trovati.
5. **thegamesdb**: ultima risorsa (ha una quota mensile).

Ogni sorgente riceve **solo** i giochi a cui manca qualcosa che lei sa fornire. Per sfruttare al massimo la velocità, chiedi i media `wheel`/`marquee`/`video` solo se ti servono: esistono quasi solo su ScreenScraper, e quindi la quota giornaliera del tuo account (es. 20.000 richieste) diventa il limite. Per 10.000 giochi, con quei media, servono circa 10-12.000 richieste ScreenScraper, cioè 1 giorno con un account base. Se la quota finisce, l'esecuzione si ferma pulita e riprende il giorno dopo.

## Cosa non c'è

- Il compositing delle immagini: vengono salvate le immagini originali.
- I moduli MobyGames (API ora a pagamento), OpenRetro e WorldOfSpectrum.

Se servono, si possono aggiungere come nuovi moduli in `pozzo/sources/` o in `export.py`.
