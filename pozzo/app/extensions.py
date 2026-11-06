"""Temi e plugin.

TEMI  - cartella <config>/themes/<id>/ (oppure quelli inclusi in pozzo/app/themes/):
    theme.json      {"name", "description", "author", "preview": "#colore", "desktop": "theme.css",
                     "bigpicture": "bigpicture.css"}
    theme.css       sovrascrive le variabili CSS (--bg, --accent, ...) e qualsiasi regola
    bigpicture.css  idem per la modalita' Big Picture

PLUGIN - cartella <config>/plugins/<id>/:
    plugin.toml     [plugin] name, version, author, description, api = 1 (o 2, vedi sotto)
    frontend.js     (facoltativo) modulo ES: export default function (gs, ctx) { ... }
    style.css       (facoltativo)
    backend.py      (facoltativo) def register(gs): ...   con gs = PluginAPI (vedi sotto)
    load = "lazy"   (facoltativo, in [plugin]) il backend si avvia al primo uso invece che all'avvio dell'app:
                    solo per plugin che usano soltanto gs.route (vedi LazyPlugin)
    events = [...]  (facoltativo, con load = "lazy") eventi a cui il plugin si iscrive con gs.on: il backend si avvia al
                    primo di quegli eventi (che gli viene consegnato) invece che all'avvio dell'app

Un plugin backend puo': aggiungere endpoint (gs.route), fornitori di libreria/store (gs.add_store),
fonti di metadati per lo scraping (gs.add_source), reagire agli eventi (gs.on), lavori periodici (gs.job) e salvare
impostazioni proprie (gs.settings / gs.save_settings). Guida completa: docs/ESTENSIONI.md

API 2 (api = 2 nel plugin.toml; le api = 1 restano invariate) aggiunge tre registrazioni dichiarative, lette dal
frontend in /api/extensions: gs.add_library_kind({id, label, icon}), gs.add_player({id, label, mode}) e
gs.add_scraper({id, url, ...ricetta}). Le prime due servono ai media (Pozzo Media, roadmap 0.18); il permesso
"media:lettura" dichiara l'accesso alle cartelle di film e musica scelte dall'utente.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import queue
import re
import threading
import time
import tomllib
import traceback
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.routing import Route

from .. import config as C

BUILTIN_THEMES = Path(__file__).parent / "themes"
BUILTIN_EXPERIENCES = Path(__file__).parent / "static" / "experiences"
DEFAULT_EXPERIENCE = {
    "id": "catalog", "name": "Catalogo", "description": "Interfaccia classica con navigazione laterale.",
    "nav": "sidebar", "detail": "panel",
}
EXPERIENCE_METADATA = {
    "original": {
        "name": "Originale", "description": "Interfaccia originale del launcher, con navigazione laterale e schede a pannello.",
        "nav": "sidebar", "detail": "panel",
    },
    "catalog": {
        "name": "Catalogo", "description": "Catalogo della libreria con navigazione laterale.",
        "nav": "sidebar", "detail": "panel",
    },
    "shelves": {
        "name": "Scaffali", "description": "Home a scaffali e navigazione principale superiore.",
        "nav": "top", "detail": "panel",
    },
    "console": {
        "name": "Console", "description": "Raccolta immersiva navigabile per selezione e messa a fuoco.",
        "nav": "none", "detail": "page",
    },
    "dashboard": {
        "name": "Dashboard", "description": "Home a gruppi di giochi con accesso rapido alle viste.",
        "nav": "top", "detail": "panel",
    },
    "cinema": {
        "name": "Cinema", "description": "Home con gioco in evidenza e file orizzontali per la raccolta.",
        "nav": "top", "detail": "modal",
    },
    "storefront": {
        "name": "Vetrina", "description": "Home curata con giochi in evidenza e sezioni della raccolta.",
        "nav": "top", "detail": "page",
    },
}
BUILTIN_PLUGINS = Path(__file__).parent / "plugins"  # solo lo store: le altre estensioni si installano da li'
STORE_ID = "estensioni"
API_VERSION = 2


def user_dir(cfg, name: str) -> Path:
    base = cfg.config_path.parent if cfg.config_path else Path.cwd()
    d = base / name
    d.mkdir(exist_ok=True)
    return d


class Events:
    """Bus di eventi lato server: game_launching (sincrono, prima dell'avvio), game_started, game_stopped, library_built, scrape_finished, stores_refreshed."""

    def __init__(self):
        self.handlers: dict[str, list] = {}
        self.subs: set[queue.Queue] = set()  # chi ascolta in streaming (SSE di /api/v1/events)
        self.lock = threading.Lock()

    def on(self, name: str, fn):
        with self.lock:
            self.handlers.setdefault(name, []).append(fn)

    def subscribe(self) -> queue.Queue:
        """Coda che riceve ogni evento come {"event", "data"}. Se si riempie, gli eventi nuovi si perdono:
        chi ascolta non deve poter bloccare l'app."""
        q: queue.Queue = queue.Queue(maxsize=100)
        with self.lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.lock:
            self.subs.discard(q)

    def emit(self, name: str, data: dict | None = None):
        payload = data or {}
        with self.lock:
            handlers, subs = list(self.handlers.get(name, [])), list(self.subs)
        for fn in handlers:
            try:
                fn(payload)
            except Exception:
                traceback.print_exc()
        for q in subs:
            try:
                q.put_nowait({"event": name, "data": payload})
            except queue.Full:
                pass


# ---------------------------------------------------------------- temi

def theme_dirs(cfg) -> list[Path]:
    return [user_dir(cfg, "themes"), BUILTIN_THEMES]


def list_themes(cfg) -> list[dict]:
    out = [{"id": "default", "name": "Predefinito", "description": "Scuro, blu e viola", "preview": "#151821",
            "desktop": None, "bigpicture": None}]
    seen = {"default"}
    for base in theme_dirs(cfg):
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            mf = d / "theme.json"
            try:
                if d.name in seen or not mf.exists():
                    continue
            except OSError:  # cartella illeggibile (es. WinError 448): il tema si salta
                continue
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            seen.add(d.name)
            out.append({"id": d.name, "name": m.get("name", d.name), "description": m.get("description", ""),
                        "author": m.get("author", ""), "preview": m.get("preview", "#1c2030"),
                        "desktop": f"/themes/{d.name}/{m['desktop']}" if m.get("desktop") else None,
                        "bigpicture": f"/themes/{d.name}/{m['bigpicture']}" if m.get("bigpicture") else None})
    return out


def active_experience(cfg) -> str:
    value = cfg.app.get("experience", "catalog")
    return value if isinstance(value, str) and value in {
        item["id"] for item in list_experiences() if item.get("available")
    } else "catalog"


_EXP_CACHE: tuple[float, list[dict]] | None = None


def list_experiences() -> list[dict]:
    """Esperienze incluse nell'app: l'elenco e' in cache (scansione su disco lenta, es. OneDrive)."""
    global _EXP_CACHE
    now = time.monotonic()
    if _EXP_CACHE is None or now - _EXP_CACHE[0] > 30:
        _EXP_CACHE = (now, _scan_experiences())
    return [dict(x) for x in _EXP_CACHE[1]]


def _scan_experiences() -> list[dict]:
    """Scopre esperienze incluse nell'app senza consentire cartelle o link esterni."""
    out, seen = [], set()
    try:
        dirs = sorted(BUILTIN_EXPERIENCES.iterdir()) if BUILTIN_EXPERIENCES.exists() else []
    except OSError:
        dirs = []
    root = BUILTIN_EXPERIENCES.resolve()
    for d in dirs:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", d.name):
            continue
        try:
            folder = d.resolve()
            if folder.parent != root or not folder.is_dir():
                continue
            metadata = EXPERIENCE_METADATA.get(d.name, {})
            has_script = experience_file(d.name, "experience.js") is not None
            has_style = experience_file(d.name, "style.css") is not None
            available = has_script or d.name == "catalog"
            out.append({
                "id": d.name,
                "name": metadata.get("name", d.name),
                "description": metadata.get("description", ""),
                "nav": metadata.get("nav", "sidebar"),
                "detail": metadata.get("detail", "panel"),
                "script": f"/experiences/{d.name}/experience.js" if has_script else None,
                "style": f"/experiences/{d.name}/style.css" if has_style else None,
                "available": available,
                "error": None if has_script else "File experience.js mancante" if d.name != "catalog" else
                    "File experience.js mancante: uso il comportamento predefinito sicuro.",
            })
            seen.add(d.name)
        except OSError as e:
            out.append({"id": d.name, "name": d.name, "description": "", "script": None, "style": None,
                        "available": False, "error": f"Cartella illeggibile: {e}"})
            seen.add(d.name)
    if "catalog" not in seen:
        out.insert(0, {**DEFAULT_EXPERIENCE, "script": None, "style": None, "available": True,
                       "error": "Cartella dell'esperienza predefinita mancante: uso il comportamento sicuro incorporato."})
    out.sort(key=lambda item: (item["id"] != "catalog", item["id"]))
    return out


def experience_file(experience_id: str, rel: str) -> Path | None:
    """Risoluzione statica limitata ai due asset previsti in ogni cartella esperienza."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", experience_id) or rel not in ("experience.js", "style.css"):
        return None
    try:
        root = (BUILTIN_EXPERIENCES / experience_id).resolve()
        f = (root / rel).resolve()
        if root.parent == BUILTIN_EXPERIENCES.resolve() and root.is_dir() and root in f.parents and f.is_file():
            return f
    except OSError:
        pass
    return None


def theme_file(cfg, tid: str, rel: str) -> Path | None:
    for base in theme_dirs(cfg):
        root = (base / tid).resolve()
        f = (root / rel).resolve()
        if root.is_dir() and root in f.parents and f.is_file():
            return f
    return None


# ---------------------------------------------------------------- plugin

def plugin_dirs(cfg) -> list[Path]:
    return [user_dir(cfg, "plugins"), BUILTIN_PLUGINS]


# permessi dichiarati in plugin.toml ("permissions = [...]"): chiave -> etichetta. "rete:<host>" e "rete:*" a parte.
PERMISSION_LABELS = {
    "libreria:lettura": "Legge la libreria", "libreria:scrittura": "Modifica la libreria",
    "file:lettura": "Legge file sul disco", "file:scrittura": "Modifica o elimina file sul disco",
    "impostazioni": "Legge e salva impostazioni", "notifiche": "Mostra notifiche",
    "avvio": "Avvia giochi o programmi",
    "media:lettura": "Legge le cartelle di film e musica scelte dall'utente",
}


def describe_permissions(perms) -> list[dict]:
    """[{"id", "label"}] in italiano. Un permesso non riconosciuto resta nell'elenco, con etichetta di avviso."""
    out = []
    for p in perms or []:
        if not isinstance(p, str):
            continue
        if p == "rete:*":  # estensioni che contattano siti scelti dall'utente (es. feed o store personalizzati)
            label = "Accesso a internet: qualsiasi sito, scelto dall'utente"
        elif p.startswith("rete:") and len(p) > 5:
            label = f"Accesso a internet: {p[5:]}"
        else:
            base = next((k for k in PERMISSION_LABELS if p == k or p.startswith(k + ":")), None)
            label = PERMISSION_LABELS[base] if base else f"Permesso non riconosciuto: {p}"
        out.append({"id": p, "label": label})
    return out


# ---------------------------------------------------------------- media (API 2)
# Registrazioni dichiarative delle estensioni api = 2: il core le mostra, il frontend le legge da /api/extensions.
# Sono elenchi di dizionari con "extension" (id del plugin che le ha registrate); una ri-registrazione le sostituisce.
PLAYER_MODES = ("integrato", "esterno")
LIBRARY_KINDS: list[dict] = []
PLAYERS: list[dict] = []
SCRAPERS: list[dict] = []


def _slug(value) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", str(value or "")) is not None


def _register(registry: list[dict], item: dict, pid: str) -> dict:
    entry = {**item, "extension": pid}
    for i, x in enumerate(registry):
        if x["id"] == entry["id"] and x["extension"] == pid:
            registry[i] = entry
            return entry
    registry.append(entry)
    return entry


def media_registry() -> dict:
    """Registrazioni API 2 per /api/extensions (copia: il frontend non tocca gli elenchi veri)."""
    return {"api": API_VERSION, "library_kinds": [dict(x) for x in LIBRARY_KINDS],
            "players": [dict(x) for x in PLAYERS], "scrapers": [dict(x) for x in SCRAPERS]}


def _manifest(d: Path) -> dict | None:
    mf = d / "plugin.toml"
    if not mf.exists():
        return None
    try:
        return tomllib.loads(mf.read_text(encoding="utf-8")).get("plugin", {})
    except (OSError, tomllib.TOMLDecodeError):
        return None


def list_plugins(cfg, errors: dict | None = None) -> list[dict]:
    disabled = set(cfg.app.get("disabled_plugins", []))
    settings = C.read_settings(cfg).get("plugins", {})
    out, seen = [], set()
    for base in plugin_dirs(cfg):
        try:
            dirs = sorted(base.iterdir()) if base.exists() else []
        except OSError:  # cartella dei plugin illeggibile: l'app parte lo stesso, senza estensioni
            continue
        for d in dirs:
            if d.name.startswith(".") or d.name in seen:  # .<id>.tmp/.old: installazione dello store a meta'
                continue
            try:
                m = _manifest(d)
                if m is None or (d.name == STORE_ID and base != BUILTIN_PLUGINS):  # lo store e' sempre quello incluso nell'app
                    continue
                seen.add(d.name)
                try:
                    api = int(m.get("api", 1))
                except (TypeError, ValueError):
                    api = None  # manifest sbagliato: l'estensione non si carica (come api troppo alta)
                out.append({
                    "id": d.name, "name": m.get("name", d.name), "version": str(m.get("version", "")),
                    "author": m.get("author", ""), "description": m.get("description", ""), "api": api,
                    "enabled": (d.name not in disabled or d.name == STORE_ID) and api is not None and api <= API_VERSION,
                    "locked": d.name == STORE_ID,
                    "frontend": f"/plugins/{d.name}/frontend.js" if (d / "frontend.js").exists() else None,
                    "style": f"/plugins/{d.name}/style.css" if (d / "style.css").exists() else None,
                    "backend": str(d / "backend.py") if (d / "backend.py").exists() else None,
                    "settings": settings.get(d.name, {}), "error": (errors or {}).get(d.name),
                    "dir": str(d), "load_ms": LOAD_MS.get(d.name),
                    "load": "lazy" if m.get("load") == "lazy" else "eager", "first_use_ms": FIRST_USE_MS.get(d.name),
                    "events": [str(e) for e in m.get("events", [])] if isinstance(m.get("events"), list) else [],
                    "permissions": [x for x in m["permissions"] if isinstance(x, str)] if isinstance(m.get("permissions"), list) else [],
                    "permissions_unknown": "permissions" not in m,
                    "eager_needed": sorted(EAGER_NEEDED.get(d.name, ())),
                    "jobs": [{"name": j.name, "every": j.every, "runs": j.runs, "error": j.last_error}
                             for j in JOBS if j.pid == d.name],
                })
            except OSError as e:
                # es. WinError 448: collegamento (junction) non attendibile. Una cartella illeggibile non deve
                # impedire l'avvio: l'estensione compare disattivata, con il motivo.
                seen.add(d.name)
                out.append({"id": d.name, "name": d.name, "version": "", "author": "", "description": "", "enabled": False,
                            "locked": False, "frontend": None, "style": None, "backend": None, "settings": {},
                            "error": f"Cartella illeggibile: {e}", "dir": str(d)})
    out.sort(key=lambda p: p["id"] != STORE_ID)  # lo store per primo: in Impostazioni e nella barra laterale
    return out


def plugin_file(cfg, pid: str, rel: str) -> Path | None:
    bases = plugin_dirs(cfg)
    repo_ext = Path(__file__).resolve().parent.parent.parent / "extensions"
    if repo_ext.is_dir():
        bases = [*bases, repo_ext]
    for base in bases:
        try:
            root = (base / pid).resolve()
            f = (root / rel).resolve()
            if root.is_dir() and root in f.parents and f.is_file() and f.suffix in (".js", ".css", ".png", ".jpg",
                                                                                   ".svg", ".webp", ".json", ".woff2"):
                return f
        except OSError:  # percorso non attraversabile: come se non ci fosse
            continue
    return None


JOBS: list["Job"] = []           # lavori periodici dei plugin (gs.job), fermati con stop_jobs()
LOAD_MS: dict[str, float] = {}   # {id plugin: millisecondi spesi all'avvio (register() se eager, solo il montaggio se lazy)}
FIRST_USE_MS: dict[str, float] = {}  # {id plugin lazy: millisecondi di import + register() al primo accesso}
EAGER_NEEDED: dict[str, set] = {}    # {id plugin lazy: API non differibili usate in register()}
LOAD_TOTAL_MS = 0.0              # tempo totale di load_backends all'avvio
_HOOKED_APPS: set[int] = set()


class Job:
    """Lavoro periodico di un plugin: un thread daemon che chiama fn ogni `every` secondi."""

    def __init__(self, pid: str, name: str, fn, every: float, log):
        self.pid, self.name, self.fn, self.every, self.log = pid, name, fn, every, log
        self.stopped = threading.Event()
        self.runs, self.last_error = 0, None

    def tick(self):
        """Un giro: gli errori si registrano e il lavoro continua."""
        try:
            self.fn()
            self.last_error = None
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.log(f"Plugin {self.pid}, lavoro {self.name}: {self.last_error}")
        self.runs += 1

    def _loop(self, run_at_start: bool):
        if run_at_start and not self.stopped.is_set():
            self.tick()
        while not self.stopped.wait(self.every):
            self.tick()

    def stop(self):
        self.stopped.set()


def stop_jobs():
    for j in JOBS:
        j.stop()
    JOBS.clear()


class PluginAPI:
    """Oggetto passato a backend.register(gs)."""

    def __init__(self, app, cfg, pid: str, events: Events, log):
        self.app, self.cfg, self.id, self.events, self.log = app, cfg, pid, events, log
        self.settings: dict = C.read_settings(cfg).get("plugins", {}).get(pid, {})

    def route(self, path: str, methods=("GET",)):
        """Decoratore: espone una funzione su /plugin-api/<id>/<path>."""
        def deco(fn):
            self.app.add_api_route(f"/plugin-api/{self.id}/{path.lstrip('/')}", fn, methods=list(methods))
            return fn
        return deco

    def add_store(self, provider_cls):
        """Aggiunge un fornitore di libreria (sottoclasse di pozzo.stores.base.StoreProvider)."""
        from .. import stores
        if provider_cls.id not in stores.BY_ID:
            stores.PROVIDERS.append(provider_cls)
            stores.BY_ID[provider_cls.id] = provider_cls
            stores.STORE_ORDER.append(provider_cls.id)

    def add_source(self, source_cls):
        """Aggiunge una fonte di metadati per lo scraping (sottoclasse di pozzo.sources.base.Source)."""
        from ..sources import SOURCES
        SOURCES[source_cls.name] = source_cls

    def add_library_kind(self, kind: dict):
        """API 2: una sezione di media accanto ai giochi. {id, label, icon?}; id = lettere minuscole, cifre, - e _."""
        kind = kind if isinstance(kind, dict) else {}
        label = str(kind.get("label") or "").strip()
        if not _slug(kind.get("id")) or not label:
            raise ValueError("gs.add_library_kind: servono id (minuscole, cifre, - e _) ed etichetta")
        return _register(LIBRARY_KINDS, {"id": kind["id"], "label": label[:60],
                                        "icon": str(kind.get("icon") or "")[:8]}, self.id)

    def add_player(self, player: dict):
        """API 2: chi riproduce un contenuto. {id, label, mode}; mode = "integrato" (<video>) o "esterno" (mpv/VLC)."""
        player = player if isinstance(player, dict) else {}
        label = str(player.get("label") or "").strip()
        if not _slug(player.get("id")) or not label or player.get("mode") not in PLAYER_MODES:
            raise ValueError("gs.add_player: servono id, etichetta e mode «integrato» o «esterno»")
        return _register(PLAYERS, {"id": player["id"], "label": label[:60], "mode": player["mode"]}, self.id)

    def add_scraper(self, recipe: dict):
        """API 2: una ricetta dichiarativa (nessun codice eseguito). {id, url, ...campi della ricetta}."""
        recipe = recipe if isinstance(recipe, dict) else {}
        url = str(recipe.get("url") or "").strip()
        if not _slug(recipe.get("id")) or not re.match(r"^https?://[^\s]+$", url):
            raise ValueError("gs.add_scraper: servono id e url http/https")
        return _register(SCRAPERS, {**recipe, "id": recipe["id"], "url": url}, self.id)

    def on(self, event: str, fn):
        self.events.on(event, fn)

    def job(self, name: str, fn, every: float, run_at_start: bool = False) -> Job:
        """Esegue fn() ogni `every` secondi su un thread daemon; si ferma alla chiusura dell'app."""
        if not every or every <= 0:
            raise ValueError("every deve essere > 0 secondi")
        j = Job(self.id, name, fn, float(every), self.log)
        JOBS.append(j)
        if id(self.app) not in _HOOKED_APPS and hasattr(self.app, "add_event_handler"):
            _HOOKED_APPS.add(id(self.app))
            self.app.add_event_handler("shutdown", stop_jobs)
        threading.Thread(target=j._loop, args=(run_at_start,), daemon=True, name=f"plugin-{self.id}-{name}").start()
        return j

    def save_settings(self, values: dict):
        self.settings.update(values)
        C.save_settings(self.cfg, plugins={self.id: dict(self.settings)})


class _LazyAPI(PluginAPI):
    """gs di un plugin lazy: le route vanno nel router privato del plugin; gs.on/job/add_store/add_source
    funzionano ma, essendo chiamate solo al primo uso, vengono segnalate (il plugin va reso eager)."""

    def __init__(self, sub: APIRouter, app, cfg, pid, events, log, handlers: dict, declared: set):
        super().__init__(app, cfg, pid, events, log)
        self.sub, self.handlers, self.declared = sub, handlers, declared

    def route(self, path: str, methods=("GET",)):
        def deco(fn):
            self.sub.add_api_route(f"/plugin-api/{self.id}/{path.lstrip('/')}", fn, methods=list(methods))
            return fn
        return deco

    def _late(self, what: str):
        EAGER_NEEDED.setdefault(self.id, set()).add(what)
        self.log(f"Plugin {self.id}: load = \"lazy\" ma usa {what}, che serve dall'avvio: resta attivo solo dal primo uso. "
                 "Va reso eager (togli load dal plugin.toml)")

    def on(self, event, fn):
        if event in self.declared:  # sottoscritto dallo stub del manifest: nessun evento perso
            self.handlers.setdefault(event, []).append(fn)
            return
        self._late("gs.on")
        super().on(event, fn)

    def job(self, *a, **k):
        self._late("gs.job")
        return super().job(*a, **k)

    def add_store(self, provider_cls):
        self._late("gs.add_store")
        super().add_store(provider_cls)

    def add_source(self, source_cls):
        self._late("gs.add_source")
        super().add_source(source_cls)

    # API 2: le sezioni e i lettori fanno parte della finestra principale, quindi servono dall'avvio
    def add_library_kind(self, kind: dict):
        self._late("gs.add_library_kind")
        return super().add_library_kind(kind)

    def add_player(self, player: dict):
        self._late("gs.add_player")
        return super().add_player(player)

    def add_scraper(self, recipe: dict):
        self._late("gs.add_scraper")
        return super().add_scraper(recipe)


class LazyPlugin:
    """Segnaposto di un plugin load = "lazy": risponde su /plugin-api/<id>/{path} e al PRIMO accesso importa il
    backend ed esegue register(); poi le sue route prendono il posto del segnaposto (come un plugin eager).
    Un errore in import/register() da' 500 solo sulle route di quel plugin, senza riprovare."""

    def __init__(self, app, cfg, p: dict, events, log, errors: dict):
        self.app, self.cfg, self.p, self.events, self.log, self.errors = app, cfg, p, events, log, errors
        self.sub, self.error, self.done = APIRouter(), None, False
        self.handlers: dict[str, list] = {}  # gs.on del plugin per gli eventi dichiarati in events
        self.lock = threading.Lock()
        self.route = Route(f"/plugin-api/{p['id']}/{{path:path}}", self)

    def mount(self):
        self.app.router.routes.append(self.route)
        for ev in self.p.get("events", []):
            self.events.on(ev, lambda data, ev=ev: self._on_event(ev, data))

    def _on_event(self, ev: str, data: dict):
        """Primo evento dichiarato: avvia il backend (che registra i suoi gs.on) e consegna l'evento ai suoi handler."""
        self._load()
        for fn in list(self.handlers.get(ev, [])):
            fn(data)

    def _load(self):
        pid = self.p["id"]
        with self.lock:
            if self.done:
                return
            t0 = time.perf_counter()
            try:
                spec = importlib.util.spec_from_file_location(f"gs_plugin_{pid}", self.p["backend"])
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "register"):
                    mod.register(_LazyAPI(self.sub, self.app, self.cfg, pid, self.events, self.log, self.handlers,
                                          set(self.p.get("events", []))))
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
                self.errors[pid] = self.error
                self.log(f"Plugin {pid}: errore nel backend: {self.error}")
            finally:
                FIRST_USE_MS[pid] = round((time.perf_counter() - t0) * 1000, 1)
                self.done = True

    async def __call__(self, scope, receive, send):
        if not self.done:
            await asyncio.to_thread(self._load)
            routes = self.app.router.routes  # il cambio avviene sul ciclo di eventi, mai durante un confronto di route
            if self.error is None and self.route in routes:
                i = routes.index(self.route)
                routes[i:i + 1] = self.sub.routes
        if self.error:
            await JSONResponse({"detail": f"Plugin {self.p['id']}: errore nel backend: {self.error}"},
                               status_code=500)(scope, receive, send)
            return
        await self.sub(scope, receive, send)


def load_backends(app, cfg, events: Events, log=print) -> dict[str, str]:
    """Carica i backend dei plugin abilitati (quelli lazy solo montati). Ritorna {id: errore} per quelli falliti."""
    global LOAD_TOTAL_MS
    errors = {}
    t_all = time.perf_counter()
    for p in list_plugins(cfg):
        if not p["enabled"] or not p["backend"]:
            continue
        try:
            if p["load"] == "lazy":
                t0 = time.perf_counter()
                FIRST_USE_MS.pop(p["id"], None)
                EAGER_NEEDED.pop(p["id"], None)
                LazyPlugin(app, cfg, p, events, log, errors).mount()
                LOAD_MS[p["id"]] = round((time.perf_counter() - t0) * 1000, 1)
                continue
            spec = importlib.util.spec_from_file_location(f"gs_plugin_{p['id']}", p["backend"])
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                t0 = time.perf_counter()
                try:
                    mod.register(PluginAPI(app, cfg, p["id"], events, log))
                finally:
                    LOAD_MS[p["id"]] = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as e:
            errors[p["id"]] = f"{type(e).__name__}: {e}"
            log(f"Plugin {p['id']}: errore nel backend: {errors[p['id']]}")
    LOAD_TOTAL_MS = round((time.perf_counter() - t_all) * 1000, 1)
    return errors
