# Formato Ricette Web (`recipe.toml`) — Pozzo Media

Le **ricette web** permettono a Pozzo Media di estrarre cataloghi di contenuti multimediali da siti e feed web leciti (Internet Archive, podcast RSS, cataloghi aperti), presentandoli nell'interfaccia unificata di Pozzo (griglia, schede dettaglio, episodi e riproduzione) senza pubblicità né elementi superflui di navigazione.

Il formato è **esclusivamente dichiarativo**: specifica URL di partenza, formato sorgente e selettori per individuare le informazioni. **Nessun codice eseguibile** (`code`, `script`, `eval`, `function`, ecc.) è consentito o interpretato.

---

## Schema dei campi (`recipe.toml`)

La tabella seguente elenca tutti i campi previsti dal formato delle ricette, specificando tipo di dato, obbligatorietà e significato.

| Campo | Tipo | Obbligatorio | Significato |
|---|---|---|---|
| `name` | string | Sì | Nome descrittivo della ricetta o catalogo visualizzato all'utente (es. "Internet Archive - Film Classici"). |
| `host` | string | Sì | Dominio web consentito per le chiamate HTTP, verificato contro il permesso `rete:<host>` dell'estensione. |
| `type` | string | Sì | Formato della sorgente da analizzare: `"html"`, `"json"` o `"rss"`. |
| `start_url` | string | Sì | URL iniziale http/https da cui iniziare l'estrazione dell'elenco contenuti. |
| `list.selector` | string | Sì | Selettore CSS, chiave JSON o percorso XML del contenitore della lista elementi. |
| `list.item` | string | Sì | Selettore CSS, chiave o percorso del singolo elemento all'interno della lista. |
| `list.title` | string | Sì | Selettore o chiave per estrarre il titolo dell'elemento nella lista. |
| `list.cover` | string | No | Selettore o chiave per estrarre l'URL della copertina o locandina (supporta attributi con `@`, es. `img@src`). |
| `list.link` | string | Sì | Selettore o chiave per estrarre l'URL della pagina di dettaglio o della risorsa. |
| `detail.title` | string | Sì | Selettore o chiave per estrarre il titolo nella scheda di dettaglio del contenuto. |
| `detail.cover` | string | No | Selettore o chiave per estrarre l'immagine di copertina o poster in alta definizione. |
| `detail.overview` | string | No | Selettore o chiave per estrarre la descrizione, sinossi o trama. |
| `detail.year` | string | No | Selettore o chiave per estrarre l'anno o data di pubblicazione. |
| `detail.duration` | string | No | Selettore o chiave per estrarre la durata del contenuto (testuale o in secondi). |
| `detail.stream_url` | string | No | Selettore o chiave per estrarre l'URL diretto del flusso multimediale (audio/video). Accetta anche il prefisso `regex:` (vedi sotto). |
| `episodes.selector` | string | No | Selettore CSS o percorso XML/JSON del blocco contenitore degli episodi. |
| `episodes.item` | string | No | Selettore CSS o percorso relativo di ciascun episodio nella lista. |
| `episodes.title` | string | No | Selettore o chiave per estrarre il titolo dell'episodio. |
| `episodes.duration` | string | No | Selettore o chiave per estrarre la durata dell'episodio. |
| `episodes.stream_url` | string | No | Selettore o chiave per estrarre l'URL del flusso audio o video dell'episodio. |
| `episodes.season` | string | No | Selettore o chiave per estrarre il numero della stagione. |
| `episodes.episode` | string | No | Selettore o chiave per estrarre il numero dell'episodio. |
| `pagination.next_url` | string | No | Selettore del link alla pagina successiva (es. `a.pagination-next@href`) o pattern URL. |
| `pagination.param` | string | No | Nome del parametro query HTTP usato per la paginazione (es. `"page"`). |
| `pagination.increment` | integer | No | Valore numerico di incremento del parametro di pagina ad ogni richiesta successiva (es. `1`). |
| `pagination.limit` | integer | No | Numero massimo di pagine consecutive da scorrere automaticamente (es. `10`). |

---

## Tipi di sorgente (`type`)

Il campo `type` definisce la modalità di analisi adottata dal motore di scraping:

1. **`"html"`**:
   - I selettori utilizzano la sintassi dei selettori CSS (es. `.item-ia`, `h1.title`, `a.next`).
   - Per estrarre gli attributi di un tag HTML si usa la notazione `@nomeattributo` (es. `img@src`, `a@href`).
   - In assenza di `@`, viene estratto il testo interno dell'elemento.

2. **`"json"`**:
   - I selettori utilizzano percorsi dot-notation o JSONPath semplificato (es. `items`, `metadata.title`, `files[0].url`).

3. **`"rss"`**:
   - I selettori mappano tag XML standard di feed RSS o podcast iTunes (es. `channel`, `item`, `title`, `itunes:image@href`, `enclosure@url`, `itunes:duration`).

---

## Flussi streaming: `regex:` ed estrazione automatica

Molti siti non espongono il flusso in un tag HTML raggiungibile con un selettore CSS: l'URL è nascosto dentro uno script del player (`file: "https://.../master.m3u8"`). Per questi casi `detail.stream_url` accetta il prefisso **`regex:`** seguito da un'espressione regolare applicata al **testo grezzo** della pagina:

```toml
[detail]
title = "h1.title"
stream_url = 'regex:file:\s*"(https://[^"]+\.m3u8)"'
```

- Se l'espressione ha un **gruppo di cattura** viene usato quello (gruppo 1), altrimenti l'intero match.
- Il valore estratto viene normalizzato in URL assoluto rispetto alla pagina di dettaglio.

Se `stream_url` resta **vuoto** (nessun selettore corrispondente, nessun match della regex) il motore tenta l'**estrazione automatica** dei flussi nella pagina HTML, in quest'ordine:

1. `kodi_bridge.extract_stream_urls()` (modulo `extensions/ricette-web/kodi_bridge.py`): trova `<video>`, `<source>`, `<iframe>` e configurazioni JS (`file:`, `sources:`, URL `.m3u8`/`.mp4`/`.webm`), ordinando i risultati (diretto > HLS > embed);
2. in assenza del modulo, una regex locale su `<video src>`, `<source src>` e URL `.m3u8`/`.mp4` presenti negli script.

Nessuna delle due strade esegue codice: solo espressioni regolari sul testo della pagina, e le richieste restano limitate all'host dichiarato dalla ricetta.

### Risoluzione pigra e scelta del player

Il flusso viene risolto **al primo Play**, anche se la scheda dettaglio non è mai stata aperta: la rotta `play_target` scarica la pagina, applica `[detail]` e salva `stream_url` nel database locale. La risposta include `external`:

| Formato del flusso | `external` | Dove si riproduce |
|---|---|---|
| `.mp4`, `.webm`, `.m4v`, `.ogv`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.opus`, `.wav` | `false` | Player integrato (`<video>` / `<audio>`) |
| `.m3u8` (HLS), embed, altri flussi | `true` | `POST external` → **mpv** o **VLC** se installati, altrimenti il browser di sistema |

Le ricette restano dichiarative: la scelta del player è del backend, non della ricetta.

---

## Addon Kodi

Oltre alle ricette TOML, l'estensione può installare **addon video di Kodi** e usarli come sorgenti di catalogo, tramite il modulo `kodi_bridge.py`:

- **`GET /plugin-api/ricette-web/kodi_addons`** elenca gli addon presenti in `<cache>/kodi-addons/` leggendo il loro `addon.xml` (`id`, `name`, `version`, `summary`, `path`).
- **`POST /plugin-api/ricette-web/kodi_addons`** con `{"url": "https://github.com/<utente>/<addon>"}` oppure `{"path": "<cartella o .zip locale>"}` installa l'addon (verificando che nessun file esca dalla cartella di destinazione) e inserisce i suoi canali nella tabella `items`, così compaiono nel catalogo come le ricette.
- **`POST /plugin-api/ricette-web/kodi_addons`** con `{"remove": "<addon_id>"}` rimuove l'addon e i suoi elementi dal catalogo.

I canali degli addon vengono eseguiti in uno shim in-memory (`xbmc`, `xbmcgui`, `xbmcplugin`, `xbmcaddon`, `xbmcvfs`): nessun codice gira fuori dalla cartella dell'addon installato.

---


## Sicurezza e divieto assoluto di codice

Per proteggere l'utente e il sistema:
- **Nessun codice eseguibile**: campi come `code`, `script`, `eval`, `function`, `handler` o `exec` sono **tassativamente vietati** e rigettati dal validatore dello schema.
- **Isolamento di rete**: le richieste HTTP possono contattare unicamente il dominio dichiarato in `host` (convalidato rispetto ai permessi dell'estensione `rete:<host>`).
- **Politica delle fonti**: nello Store ufficiale di Pozzo sono ammesse solo ricette per fonti lecite (Internet Archive, podcast pubblici, cataloghi aperti con licenze Creative Commons / pubblico dominio). Ricette per siti con contenuti protetti da copyright sono di responsabilità esclusiva dell'utente e non possono essere distribuite nello Store.
- **Buone maniere di rete**: il motore applica automaticamente cache locale su disco, rate limiting e rispetto del file `robots.txt` del sito target.

---

## Esempi inclusi

- **`recipe.toml`**: Esempio di scraping HTML per collezioni video di pubblico dominio su Internet Archive (`type = "html"`).
- **`recipes-podcast.toml`**: Esempio di estrazione da feed podcast RSS/XML aperto (`type = "rss"`).
