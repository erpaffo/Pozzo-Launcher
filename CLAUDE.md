# Pozzo Launcher

Launcher desktop Windows (anche macOS/Linux in CI) per ROM + giochi PC degli store. Python 3.12, FastAPI + uvicorn servito in locale, UI web in finestra pywebview, frontend JS/CSS vanilla. Tutto locale, nessun account, open source. Dettagli di prodotto: `PRODUCT.md`. Commenti nel codice in italiano, brevi, sul *perché*.

## Comandi
- Avvio da sorgenti: `python -m pozzo app` (config separata: `POZZO_CONFIG=/path/config.toml`)
- Test tutti: `PYTHONUTF8=1 python packaging/run_tests.py`; singolo: `PYTHONUTF8=1 python tests/test_X.py` (script con `assert`, niente framework)
- JS: `node --check file.js`
- Changelog/versione: script in `tools/` (`version.py`, non a mano); release: `release.bat`
- i18n: `scripts/i18n_check.py|i18n_todo.py|i18n_merge.py`; skill `/translate`

## Mappa
- `pozzo/` backend. Pipeline scraping: `scanner.py` → `matching.py` → `pipeline.py`, con `sources/` (igdb, rawg, thegamesdb, screenscraper, libretro, offline…), `cache.py`/`cachepolicy.py`, `net.py` (rate limit). Store: `stores/` (steam, epic, gog, xbox…). Libreria utente: `library/` (`userdata.py`, `launcher.py`, `saves.py`…). Emulatori: `emudetect.py`, `emuinstall*.py`, `emuadapters/`, `emucfg.py`. Telefono: `remote/`. Overlay in gioco: `overlay.py`. CLI: `cli.py`.
- `pozzo/app/` server: `server.py` (`create_app`), `routes/*.py` (un file per area, `build_router`), `extensions.py`/`extstore.py` (plugin), `apiv1.py`, `jobs.py`.
- `pozzo/app/static/` frontend: `index.html`, `app.js`, `core.js`, `js/`, `experiences/`, `bigpicture*`, `app.css` (token tema), `i18n.js`.
- `pozzo/data/locales/` 7 lingue (it, en, de, es, fr, pt-BR, tr): ogni testo visibile va in tutte (skill `translate`).
- `extensions/<nome>/` 24 plugin opzionali: `plugin.toml` + `backend.py` + `frontend.js` + `style.css`. Possono mancare, il core non deve dipenderne.
- `tests/` ~240 file; `packaging/` PyInstaller + installer; `docs/` manuale MkDocs (it, `en/`); `themes/`, `profiles/`.
- `cache/ build/ dist/ release/ site/ scratch/` sono output/temporanei: non leggerli.

## Convenzioni
- Segui lo stile dei file vicini; modifica piccola ma completa: aggiorna test, `docs/` e chiamanti.
- Nessuna nuova dipendenza per poche righe.
- Nuovo testo UI → 7 lingue prima del commit.

## Risparmio token
- Per domande sull'architettura leggi `graphify-out/GRAPH_REPORT.md` (god nodes) o usa `/graphify query "..."` invece di scorrere i file. Il grafo è in `graphify-out/` (gitignored); dopo modifiche al codice: `graphify update .` (gratis).
- Usa Grep/Glob mirati; non leggere `graphify-out/graph.json`, `site/`, `dist/`, `cache/`, `*.min.js`, immagini.
