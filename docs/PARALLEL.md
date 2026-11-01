# Lavoro in parallelo (Claude + Copilot)

Piano completo: ondate W0–W4, task e modelli. Qui solo le regole.

## Proprietà dei file
Il file è del proprietario per tutta l'ondata; l'altro non lo apre. Se serve un cambio in un file altrui, lo si scrive nel report della PR.

**Claude**: `pozzo/app/server.py`, `pozzo/app/routes/*`, `pozzo/app/static/app.js` e `static/js/*`, `index.html`, `bigpicture.html`, `app.css`, `core.js`, `pozzo/library/build.py`, `pipeline.py`, `pozzo/app/extensions.py`, `cli.py`, `updates.py`, `cache.py`, `net.py`, `notify.py`, `emuinstall.py`, `library/launcher.py`, `settings/emulatori.html`; file di rilascio: `changelog.md`, `docs/TODO.md`, `pozzo-progressi.csv`, `pozzo/__init__.py`, `packaging/pozzo.spec`, `tests/conftest.py`, `packaging/run_tests.py`, `extensions/index.json`, `.github/workflows/ci.yml`.

**Copilot**: `motion.css/js`, `motion-settings.js`, `splash.js`, `palette.js`, `onboarding.js`, `hints.js`, `i18n.js` (dopo la struttura di Claude), `skeleton.css`, nuove `extensions/<id>/`, `tests/e2e/`, `tests/perf/`, `docs/sviluppo.md`, `pozzo/emuinstall_extra.py`.

## Worker
- **Claude**: fondazioni e file caldi (sopra). **Copilot**: UI/frontend su file propri. **DeepSeek**: backend/dati/test, un task alla volta (non può far girare più agenti): `tests/perf/`, `docs/sviluppo.md`, `pozzo/emuinstall_extra.py`, `pozzo/taste.py`, `pozzo/similar.py`, `pozzo/importers/`, estensioni `sconti`, `recensioni`, `eventi`, `speedrun`. Branch `deepseek/<ID>-slug`.

## Regole
- **La PR è finita solo quando i 3 job di GitHub Actions (windows, macos, linux) sono verdi.** Se falliscono, correggi sul tuo branch. Nei test non importare librerie che non sono in `requirements.txt` o `requirements-dev.txt`.
- Branch `claude/<ID>-slug` / `copilot/<ID>-slug`; prima della PR `git pull --rebase origin main`; squash merge in ordine di apertura.
- Changelog: solo `docs/changelog.d/<ID>.md`. TODO e CSV li spunta Claude al merge. `extensions/index.json` lo rigenera Claude (`python tools/extensions.py index`). La versione si cambia solo a fine ondata.
- `python packaging/run_tests.py` verde prima di ogni PR. Niente rete reale nei test.
- Nessun `Co-Authored-By` nei commit. Nessuna nuova dipendenza senza chiederla.
- Gli script/stili degli stub sono già inclusi in `index.html` e `bigpicture.html`: si riempiono i file, non si toccano le pagine.
