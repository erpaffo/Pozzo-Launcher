"""Server locale del frontend (FastAPI).

Velocita' all'avvio:
- la libreria (library.db, gia' unita e con le collezioni calcolate) si carica in memoria in ms
- /api/library manda TUTTA la libreria in un unico JSON compatto (colonne, compresso gzip):
  il browser filtra/ordina/cerca in locale, senza altre richieste
- le copertine si servono come miniature WebP generate una volta e messe in cache su disco
  (una cover originale puo' pesare 1-2 MB; la miniatura ~15 KB), con revalidazione HTTP (ETag)
- la griglia del frontend e' virtualizzata: esistono nel DOM solo le copertine visibili
"""

from __future__ import annotations

import hashlib
import http
import json
import os
import sys
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import config as C
from ..errors import explain as explain_error, where as error_where
from .. import ownership as OW
from .. import profilecfg as PC
from .. import platforms as P
from .. import storelinks as SL
from ..library import launcher as L
from . import extensions as X
from ..boot import BOOT
from . import jobs as J
from . import browserdl
from .. import stores as STORES

STORE_NAMES = {p.id: p.name for p in STORES.PROVIDERS}
STORE_NAMES["online"] = "Store online"
_REMOTE_SEM = threading.Semaphore(4)  # immagini remote scaricate al massimo 4 alla volta
_REMOTE_DOWN: dict[str, float] = {}  # host che non risponde -> fino a quando non si riprova (secondi)
_REMOTE_MISS: dict[str, float] = {}  # copertina della griglia non scaricabile -> fino a quando non si riprova
from ..library.userdata import UserData
from .library_service import Library, _ActiveUser  # noqa: F401  (Library riesportata: la usano i test)


def _silence_proactor_pipe_reset() -> None:
    """Su Windows, _ProactorBasePipeTransport._call_connection_lost solleva ConnectionResetError [WinError 10054]
    quando il browser o webview chiude bruscamente la connessione TCP."""
    if sys.platform != "win32":
        return
    try:
        import asyncio.proactor_events
        orig_call = asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost

        def safe_call(self, exc):
            try:
                orig_call(self, exc)
            except (ConnectionResetError, OSError):
                try:
                    if hasattr(self, "_sock") and self._sock is not None:
                        self._sock.close()
                        self._sock = None
                    if hasattr(self, "_server") and self._server is not None:
                        self._server._detach(self)
                        self._server = None
                    self._called_connection_lost = True
                except Exception:
                    pass

        asyncio.proactor_events._ProactorBasePipeTransport._call_connection_lost = safe_call
    except Exception:
        pass


_silence_proactor_pipe_reset()

STATIC = Path(__file__).parent / "static"
THUMB_WIDTHS = (200, 300, 450, 700, 1280)


def _asset_version() -> str:
    from .. import __version__

    digest = hashlib.sha256()
    assets = [*STATIC.glob("*.css"), *STATIC.glob("*.js")]
    assets.extend(path for path in STATIC.joinpath("experiences").rglob("*")
                  if path.is_file() and path.suffix in (".css", ".js"))
    assets.extend(path for path in STATIC.joinpath("settings").rglob("*.html") if path.is_file())
    for path in sorted(assets):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return f"{__version__}.{digest.hexdigest()[:12]}"


def _players(v, platform: str = "") -> int:
    """Numero massimo di giocatori IN LOCALE (stesso schermo/console), 0 se sconosciuto.
    '1-4', '2', 'Up to 8'... -> il massimo. Valori da gioco online (es. 16, 64) vengono scartati:
    per i PC oltre 4 (le schede PC indicano quasi sempre i giocatori online), per le console oltre 8.
    Portatili (P.NO_SPLIT): 0, il multiplayer richiede piu' console."""
    if platform in P.NO_SPLIT:
        return 0
    n =[int(x) for x in re.findall(r"\d+", str(v or ""))]
    m = max(n) if n else 0
    if m > (4 if platform == "windows" else 8):
        return 0
    return m


def _hltb_main(v) -> float | None:
    """Ore per finire la storia (o storia + extra) da HowLongToBeat, None se sconosciuto."""
    if not v:
        return None
    try:
        h = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        return None
    return h.get("main") or h.get("extra") or h.get("complete")


def _json(o) -> bytes:
    """Gli stessi byte di JSONResponse, ma le liste lunghe a blocchi: json.dumps tiene un pezzo di testo per ogni
    valore fino alla fine (~200 MB in piu' per i 26 MB delle 150.000 righe di /api/library)."""
    if isinstance(o, dict):
        return b"{" + b",".join(_json(str(k)) + b":" + _json(v) for k, v in o.items()) + b"}"
    if isinstance(o, list) and len(o) > 2000:
        return b"[" + b",".join(_json(o[i:i + 2000])[1:-1] for i in range(0, len(o), 2000)) + b"]"
    return json.dumps(o, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _players_label(v, platform: str = "") -> str:
    m = _players(v, platform)
    return "" if not m else "1 (solo giocatore)" if m == 1 else f"1–{m} in locale"


# codice stabile per ogni errore: i client esterni di /api/v1 lo usano per capire il caso senza leggere il testo
ERROR_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
               405: "method_not_allowed", 409: "conflict", 413: "too_large", 422: "invalid_request",
               429: "too_many_requests", 500: "internal_error", 502: "bad_gateway", 503: "unavailable", 504: "timeout"}


def create_app(cfg) -> FastAPI:
    BOOT.reset()  # fasi dell'avvio (schermata di caricamento, GET /api/boot): ripartono da capo ad ogni app
    BOOT.start("server")
    stop = threading.Event()  # segnalato all'arresto: i thread in background escono prima che si chiudano i database
    app = FastAPI(
        title="Pozzo Launcher", version="1",
        description="API locale dell'app. Gli endpoint **/api/v1** sono stabili e vogliono il token "
                    "(`Authorization: Bearer <token>`, vedi Impostazioni › Info); quelli sotto **/api** sono "
                    "interni all'interfaccia e possono cambiare a ogni versione.",
        openapi_tags=[{"name": "stato", "description": "Se l'app c'e' e che versione e' (senza token)"},
                      {"name": "libreria", "description": "Giochi, console, collezioni"},
                      {"name": "gioco in corso", "description": "Che cosa gira e come fermarlo"},
                      {"name": "attivita'", "description": "Lavori in corso, comandi, eventi in tempo reale"},
                      {"name": "salvataggi", "description": "Versioni dei salvataggi dei giochi"},
                      {"name": "dati", "description": "Copie di sicurezza dei dati personali"},
                      {"name": "lista desideri", "description": "Prezzi dei giochi che vuoi comprare"}])
    app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=1)  # in locale conta la velocita', non il peso
    BOOT.done("server")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request, exc):
        """Tutti gli errori hanno la stessa forma: {"detail", "code"}. `detail` resta il testo per la persona."""
        detail = exc.detail or http.HTTPStatus(exc.status_code).phrase
        return JSONResponse({"detail": detail, "code": ERROR_CODES.get(exc.status_code, "error")},
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):
        """Eccezione che nessuno ha gestito: si dice che errore e' e dove e' nato, invece di «Internal Server Error».
        Starlette la rilancia dopo la risposta, quindi finisce comunque nel registro con la traccia completa."""
        status, detail = explain_error(exc)
        try:
            import traceback
            from .. import telemetry
            telemetry.log_error("api", f"{type(exc).__name__}: {exc}", traceback.format_exc())
        except Exception:
            pass
        return JSONResponse({"detail": detail, "code": ERROR_CODES.get(status, "internal_error"),
                             "error": type(exc).__name__, "where": error_where(exc)}, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request, exc):
        errs = [{"loc": [str(x) for x in e.get("loc", ())], "msg": str(e.get("msg", ""))} for e in exc.errors()[:8]]
        return JSONResponse({"detail": errs[0]["msg"] if errs else "Parametri non validi",
                             "code": "invalid_request", "errors": errs}, status_code=422)

    app.state.cfg = cfg  # LocalGuard lo legge per il token dell'API
    BOOT.done("config")
    lib = Library(cfg)
    app.state.lib = lib  # per i test
    with BOOT.phase("library", "Libreria"):
        lib.load(online=False)
    threading.Thread(target=lib.load, daemon=True).start()
    Path(cfg.cache).mkdir(parents=True, exist_ok=True)  # prima installazione: la cache non esiste ancora
    from .. import sync as SY
    PC.migrate(cfg)  # primo avvio dopo l'introduzione dei profili: il principale copia gli account globali
    users: dict[str, UserData] = {}  # profili aperti: restano aperti (chi ne ha un metodo continua a funzionare)

    def user_of(pid: str) -> UserData:
        if pid not in users:
            users[pid] = SY.open_profile(cfg, pid)
        return users[pid]
    active = cfg.app.get("profile") or "default"
    user = _ActiveUser(user_of(active if any(p["id"] == active for p in SY.profiles(cfg)) else "default"), user_of)
    try:  # gioco d'esempio (Doom) al primo avvio: una volta sola, non deve impedire l'avvio
        from .. import sample
        if not os.environ.get("POZZO_NO_SAMPLE"):  # i test non estraggono né riscrivono le impostazioni
            sample.seed(cfg, user_of("default"))
    except Exception as e:  # noqa: BLE001
        print(f"Gioco d'esempio: {e}")

    @app.middleware("http")
    async def _lang(request, call_next):
        """Lingua dei messaggi di errore: la stessa dell'interfaccia (cookie gs_lang impostato da i18n.js)."""
        from .. import i18n as I
        token = I.current.set(I.from_request(request.cookies.get("gs_lang"), request.headers.get("accept-language")))
        try:
            return await call_next(request)
        finally:
            I.current.reset(token)

    @app.middleware("http")
    async def _profile_cookie(request, call_next):
        """Profilo per dispositivo: il cookie gs_profile (impostato da POST /api/profiles/active) vale per questa richiesta."""
        pid = request.cookies.get("gs_profile")
        if pid and any(p["id"] == pid for p in SY.profiles(cfg)):
            with PC.override(pid):
                return await call_next(request)
        return await call_next(request)
    sync = SY.Sync(cfg, user_of)
    events = X.Events()
    app.state.events = events  # chi ascolta in streaming (/api/v1/events) e i test
    # presenza su Discord («sto giocando a …»): si aggiorna sugli eventi del launcher
    from ..discordrpc import PresenceService

    discord = PresenceService(cfg, save=lambda values: PC.set(cfg, "discord", values["discord"]))
    from ..spotify import SpotifyClient, SpotifyError
    from ..discordvoice import DiscordVoice, DiscordVoiceError
    spotify = SpotifyClient(cfg, save=lambda values: PC.set(cfg, "spotify", values))
    discord_voice = DiscordVoice(cfg, save=lambda values: PC.set(cfg, "discord_voice", values))
    app.state.spotify, app.state.discord_voice = spotify, discord_voice
    events.on("game_started", discord.game_started)
    events.on("game_stopped", discord.game_stopped)
    from .. import webhooks as WH
    WH.register(events, cfg)
    from ..library import automation as AUTO
    AUTO.register_global(events, cfg)
    from ..library import screens as SC
    shots = SC.Shots(cfg.cache, Path(cfg.cache) / "userdata.db")
    launcher = L.Launcher(cfg, user, on_event=events.emit, shots=shots, profile_of=user.profile,
                          prelaunch=lambda st: _ds_prelaunch(st))
    from .. import overlay as OV
    overlay = OV.Overlay(cfg, launcher)  # finestra d'overlay in gioco: si aggancia alla finestra nativa in run_desktop
    events.on("game_started", overlay.game_started)
    events.on("game_stopped", overlay.game_stopped)
    app.state.overlay = overlay
    from ..liveach import LiveAch
    live = LiveAch(cfg, overlay)  # avvisi degli obiettivi scritti dagli emulatori Steam
    events.on("game_started", live.game_started)
    events.on("game_stopped", live.game_stopped)
    from ..remote import phone as PH
    phone_hub = PH.PhoneHub(cfg, C.save_settings)
    PH.register(app, phone_hub, STATIC)
    app.state.phone_hub = phone_hub  # per i test (vibrazioni verso il telefono)
    app.state.launcher = launcher  # per i test (avvio dei giochi DS/3DS con il telefono)

    # ------------------------------------------------------------ DS/3DS: il telefono come schermo touch
    from ..remote import dualscreen as DSC
    ds = {"state": None}

    def _ds_restore(*_):
        """Fine partita (o avvio dopo una chiusura a meta'): la configurazione dell'emulatore torna com'era."""
        st = ds["state"] or cfg.app.get("dualscreen")
        ds["state"], phone_hub.screen = None, None
        if st:
            try:
                DSC.restore(st)
            except OSError as e:
                print(f"configurazione dell'emulatore non ripristinata: {e}", file=sys.stderr)
            cfg.app.pop("dualscreen", None)
            C.save_settings(cfg, app={"dualscreen": None})

    def _phone_here() -> bool:
        """Telefono collegato adesso: un controller aperto, oppure un dispositivo abbinato visto da poco
        (l'app del telefono aggiorna l'ultimo accesso a ogni richiesta: basta averla aperta)."""
        if phone_hub.slots:
            return True
        now = time.time()
        return any(now - float(d.get("last") or 0) < 600 for d in phone_hub.devices())

    def _ds_prelaunch(st: dict) -> list[str]:
        """Prima dell'avvio: con il telefono collegato, emulatore a finestre separate e schermo superiore a tutto schermo."""
        platform = (st.get("key") or "").split("/")[0]
        if not DSC.wanted(platform, st.get("emulator_id"), bool(phone_hub.conf.get("touchscreen")), _phone_here()):
            return []
        try:
            ds["state"] = DSC.apply(st["emulator_id"], st["exe"])
        except Exception as e:  # file dell'emulatore non scrivibile o emulatore non gestito: si gioca come sempre
            print(f"schermo touch sul telefono non attivato: {type(e).__name__}: {e}", file=sys.stderr)
            ds["state"] = None
            return []
        C.save_settings(cfg, app={"dualscreen": ds["state"]})  # per il ripristino anche se l'app si chiude a meta'
        threading.Thread(target=_ds_session, args=(getattr(launcher, "_proc", None),), daemon=True).start()
        return [DSC.FULLSCREEN_ARG]

    def _ds_watch(proc, s):
        """Sul PC lo schermo inferiore resta nascosto dietro lo schermo principale. Lo si mostra solo se il telefono
        si scollega (dopo qualche secondo, il tempo di un riaggancio) o se non lo si usa da piu' di `screen_idle`
        secondi (Impostazioni › Telefono, 30 di default); al primo tocco torna nascosto."""
        idle = float(phone_hub.conf.get("screen_idle") or 30)
        started, on_pc = time.time(), False
        while proc.poll() is None and ds["state"] and phone_hub.screen is s:
            watching = phone_hub.screen_clients > 0
            seen = phone_hub.last_touch if watching else (phone_hub.screen_seen or started)
            want = DSC.show_on_pc(watching, time.time() - seen, idle)
            if want != on_pc:
                on_pc = want
                try:
                    (s.pip if want else s.hide)()
                except OSError:
                    pass
            time.sleep(0.25)

    def _ds_session(old):
        """Trova la finestra dello schermo inferiore del processo appena avviato e la passa al telefono."""
        for _ in range(100):
            proc = getattr(launcher, "_proc", None)
            if proc is not None and proc is not old:
                break
            time.sleep(0.1)
        else:
            return
        s = DSC.Session(proc.pid)
        for _ in range(120):
            if proc.poll() is not None or not ds["state"]:
                return
            if s.find():
                break
            time.sleep(0.5)
        else:
            return
        time.sleep(2)  # le finestre prendono la loro dimensione: serve a misurare la barra dei menu
        s.find()
        s.hide()
        phone_hub.screen = s
        _ds_watch(proc, s)

    events.on("game_stopped", _ds_restore)
    if cfg.app.get("dualscreen"):
        _ds_restore()
    with BOOT.phase("extensions", "Estensioni"):
        plugin_errors = X.load_backends(app, cfg, events)
    BOOT.done("stores")  # gli store si leggono dalle istantanee in cache; il loro aggiornamento parte dopo, in background
    thumbs_dir = Path(cfg.cache) / "thumbs"
    state = {"building": False, "build_log": [], "build_stats": None, "thumbs_total": 0, "thumbs_done": 0, "thumbs_started": 0, "build_started": 0}
    job: dict = {"current": J.ScrapeJob(), "stores": J.StoreJob(), "storemeta": J.StoreMetaJob(),
                 "hltb": J.HltbJob(), "collart": J.CollArtJob(),  # copertine degli store online: "netmeta:<pid>", uno per console
                 "pcstores": J.PcStoreJob(), "top": J.TopGamesJob(), "store_refresh": J.StoreRefreshJob()}
    activity_hidden: set[str] = set()
    # ultime risposte di /api/library gia' pronte: telefono e PC la richiedono a ogni apertura (costruirla
    # costa 0,2-0,6 s e qualche MB con una libreria grande) e cambia solo quando cambia libreria o dati utente
    lib_payloads: dict = {}
    start_lock = threading.Lock()

    def _claim(name: str, j) -> bool:
        """Mette j al posto del job `name` se quello non gira; False se gira gia'. Controllo e cambio sono
        sotto lock e j risulta subito "running": due clic rapidi (o PC e telefono) non avviano due job."""
        with start_lock:
            if name in job and job[name].status == "running":
                return False
            activity_hidden.discard(name)
            j.status = "running"
            job[name] = j
            return True

    # ------------------------------------------------------------ watcher delle cartelle ROM
    from .. import applog as _applog
    from ..library import watchhook as _watchhook, watcher as _watcher_mod

    hook = _watchhook.Hook(
        cfg, lib, events, lambda body: ctx.api_scan_start(body),  # ctx esiste piu' sotto: si risolve alla chiamata
        busy=lambda: bool(state["building"]) or job["current"].status == "running",
        playing=lambda: launcher.running().get("status") in ("starting", "extracting", "running"),
        log=lambda msg: _applog.write("watcher", msg))
    # acceso/spento (e tempi) si rileggono a ogni passaggio da cfg.app["watch_roms"]: nessun riavvio
    watcher = _watcher_mod.RomWatcher(
        lambda: cfg, hook.on_new, known=hook.known, busy=hook.busy, low=hook.playing,
        log=lambda msg: _applog.write("watcher", msg))

    # ------------------------------------------------------------ vista unita (gruppi + utente)
    def view(only=None) -> dict:
        """Calcola gruppi, versione principale, dati utente e collezioni (modifiche incluse).
        only: i soli gruppi di cui servono i dati (le collezioni restano complete)."""
        with lib.lock:
            ug = user.games()
            uc = user.collections()
            edits = user.edits()
            groups = lib.groups if only is None else {grp: lib.groups[grp] for grp in only}
            pid = PC.active(cfg)  # il gioco principale e' scelto tra le versioni visibili al profilo
            groups = {grp: OW.members(ms, pid) for grp, ms in groups.items()} if lib.has_owners else groups
            # collezioni: automatiche + personali, a livello di GRUPPO (tutte le versioni di un gioco)
            colls: dict[str, dict] = {}
            for slug, c in lib.auto.items():
                grps = {lib.by_key[k]["grp"] for k in c["keys"] if k in lib.by_key}
                colls[slug] = {"slug": slug, "name": c["name"], "auto": True, "custom": False, "groups": grps}
            for slug, u in uc.items():
                if u["custom"]:
                    colls[slug] = {"slug": slug, "name": u["name"], "auto": False, "custom": True, "groups": set()}
                if slug in colls:
                    colls[slug]["name"] = u["name"] or colls[slug]["name"]
                    colls[slug]["hidden"] = bool(u["hidden"])
            for slug, key, action in edits:
                g = lib.by_key.get(key)
                if slug in colls and g:
                    (colls[slug]["groups"].add if action == "add" else colls[slug]["groups"].discard)(g["grp"])

            gdata = {}
            for grp, members in groups.items():
                pref = [m for m in members if ug.get(m["key"], {}).get("preferred") == "1"]
                primary = pref[0] if pref else next((m for m in members if m["is_primary"]), members[0])
                us = [ug.get(m["key"], {}) for m in members]
                gdata[grp] = {
                    "primary": primary["id"],
                    "favorite": int(any(u.get("favorite") for u in us)),
                    "hidden": int(any(u.get("hidden") for u in us)),
                    "last_played": max((u.get("last_played") or 0 for u in us), default=0),
                    "playtime": sum(u.get("playtime") or 0 for u in us),
                    "play_count": sum(u.get("play_count") or 0 for u in us),
                    # stato: quello della versione principale, altrimenti il primo impostato
                    "status": ug.get(primary["key"], {}).get("status") or next((u.get("status") for u in us if u.get("status")), "") or "",
                    "note": next((u.get("note") for u in us if u.get("note")), "") or "",
                    "my_rating": max((u.get("my_rating") or 0 for u in us), default=0),
                }
            return {"colls": colls, "groups": gdata}

    # ------------------------------------------------------------ API (pozzo/app/routes)
    from types import SimpleNamespace
    from . import routes
    # parti condivise; ogni modulo aggiunge le funzioni che servono ai moduli successivi (vars(ctx).update)
    ctx = SimpleNamespace(
        app=app, cfg=cfg, lib=lib, user=user, users=users, user_of=user_of, sync=sync, events=events,
        launcher=launcher, shots=shots, overlay=overlay, phone_hub=phone_hub, ds=ds, view=view, job=job, state=state,
        activity_hidden=activity_hidden, lib_payloads=lib_payloads, thumbs_dir=thumbs_dir,
        plugin_errors=plugin_errors, _claim=_claim, watcher=watcher, discord=discord, spotify=spotify, discord_voice=discord_voice,
        SpotifyError=SpotifyError, DiscordVoiceError=DiscordVoiceError, SY=SY, SC=SC, PH=PH, stop=stop)
    for mod in routes.ORDER:
        app.include_router(getattr(routes, mod).build_router(ctx))

    def _phone_start():
        # riaperto subito dopo la chiusura: la porta e' ancora della copia che sta uscendo, si aspetta che la lasci
        host, port = phone_hub.conf.get("host") or "0.0.0.0", int(phone_hub.conf["port"])
        for _ in range(30):
            if stop.is_set() or _port_free(port, host):
                break
            time.sleep(1)
        if not stop.is_set():
            phone_hub.start(app)
            from ..remote import libshare as LS
            if LS.conf(cfg)["internet"]:  # la mappatura UPnP non sopravvive al riavvio
                LS.open_upnp(phone_hub)

    def _phone_startup():
        # il server HTTPS serve anche ai PC abbinati per la sincronizzazione in rete
        if phone_hub.conf.get("enabled") or any(d.get("kind") in ("pc", "lib") for d in phone_hub.conf["devices"]):
            threading.Thread(target=_phone_start, daemon=True).start()
        threading.Thread(target=ctx._sync_loop, daemon=True).start()
        threading.Thread(target=ctx._wish_loop, daemon=True).start()
        watcher.start()

    def _phone_shutdown():
        stop.set()
        phone_hub.stop()
        from ..remote import libshare
        libshare.close_upnp(phone_hub)
        # chiude i database aperti dall'app: su Windows un file ancora aperto impedisce di spostare
        # o cancellare la cartella dati (e nei test il file temporaneo resterebbe bloccato)
        watcher.stop()
        for closer in (getattr(user, "close", None), getattr(shots, "close", None)):
            try:
                if callable(closer):
                    closer()
            except Exception:
                pass

    def _startup():
        if not lib.games and lib.path.exists():
            lib.full.wait()  # nessun gioco posseduto: prima di ricreare la libreria si guarda anche il catalogo
        if not lib.games:
            if not ctx._setup_done() and not Path(cfg.roms).is_dir():
                return  # primo avvio: prima la configurazione guidata
            threading.Thread(target=ctx._rebuild, daemon=True).start()
        else:
            threading.Thread(target=ctx._pregen_thumbs, daemon=True).start()

    # add_event_handler invece di @app.on_event (deprecato): stessi eventi, nessun avviso
    app.router.add_event_handler("startup", _phone_startup)
    app.router.add_event_handler("shutdown", _phone_shutdown)
    app.router.add_event_handler("startup", _startup)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # ------------------------------------------------------------ API pubblica (/api/v1, con token)
    from . import apiv1
    apiv1.register(app, {
        "cfg": cfg, "lib": lib, "user": user, "launcher": launcher, "events": events,
        "base_url": lambda req: str(req.base_url).rstrip("/"),
        "view": view, "game": lambda gid: {**lib.game(gid)}, "play": ctx.api_play, "member_keys": ctx._member_keys,
        "jobs": ctx._job_rows, "action": ctx.api_mobile_action,
        "saves": ctx.api_saves, "saves_backup": ctx.api_saves_backup, "saves_restore": ctx.api_saves_restore,
        "backups": ctx.api_backups, "backup_create": ctx.api_backup_create,
    })
    return app


def _plain(s: str) -> str:
    import re
    return re.sub(r"\[/?[a-z ]*\]", "", s)


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket() as sk:
        try:
            sk.bind((host, port))
            return True
        except OSError:
            return False


class LocalGuard:
    """Middleware ASGI del server desktop: risponde solo a richieste fatte all'app stessa.

    - Host diverso da 127.0.0.1/localhost -> 403 (DNS rebinding: un sito che punta il suo dominio a 127.0.0.1
      leggerebbe libreria, account e codice di abbinamento del telefono);
    - POST/PUT/DELETE e WebSocket con un Origin di un altro sito -> 403 (CSRF: un sito che avvia giochi,
      disinstalla port o usa il controller/mouse del telefono). Senza Origin (curl, pozzo-cli) si passa;
    - /api/v1 (tranne /api/v1/status) -> serve il token del PC in `Authorization: Bearer`, `X-Api-Token`
      oppure `?token=`. Cosi' un programma qualsiasi sul PC - o un tunnel aperto per sbaglio - non usa
      l'API senza il token scritto in <cache>/api-token. L'interfaccia e il telefono usano /api/... e non
      sono toccati.
    """

    V1_OPEN = ("/api/v1/status",)

    def __init__(self, app, port: int):
        self.app = app
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://{h}" for h in self.hosts}
        self.cfg = getattr(getattr(app, "state", None), "cfg", None)

    def _token_ok(self, headers, query: bytes) -> bool:
        if self.cfg is None:  # app senza configurazione (test con un'app finta): nessun token
            return True
        from . import apitoken
        return apitoken.check(self.cfg, apitoken.presented(headers, query))

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            h = dict(scope["headers"])
            origin = h.get(b"origin", b"").decode("latin-1")
            unsafe = scope["type"] == "websocket" or scope.get("method") not in ("GET", "HEAD", "OPTIONS")
            if h.get(b"host", b"").decode("latin-1") not in self.hosts or (unsafe and origin and origin not in self.origins):
                if scope["type"] == "websocket":
                    return await send({"type": "websocket.close", "code": 4403})
                return await Response("Richiesta non consentita", status_code=403)(scope, receive, send)
            path = scope.get("path", "")
            if (scope["type"] == "http" and path.startswith("/api/v1/") and path not in self.V1_OPEN
                    and not self._token_ok(scope["headers"], scope.get("query_string", b""))):
                return await JSONResponse({"detail": "Serve il token dell'API (Authorization: Bearer <token>)",
                                           "code": "unauthorized"}, status_code=401)(scope, receive, send)
        return await self.app(scope, receive, send)


WINDOW_FOCUS = {"fn": None}  # impostata quando l'app gira in una finestra nativa


def _theme_bg(cfg, bigpicture: bool = False) -> str:
    """Colore di sfondo (--bg) del tema attivo: la finestra nasce gia' di quel colore."""
    tid = PC.get(cfg, "theme", "default")  # tema del profilo del server (la finestra nasce prima di ogni richiesta)
    if isinstance(tid, str) and tid != "default":
        for base in X.theme_dirs(cfg):
            try:
                meta = json.loads((base / tid / "theme.json").read_text(encoding="utf-8"))
                css = (base / tid / meta.get("bigpicture" if bigpicture else "desktop", "")).read_text(encoding="utf-8")
            except (OSError, ValueError, TypeError, AttributeError):
                continue
            found = re.search(r"--bg:\s*#([0-9a-fA-F]{3,8})", css)
            if found:
                h = found.group(1)
                h = "".join(c * 2 for c in h) if len(h) in (3, 4) else h
                if len(h) >= 6:
                    return "#" + h[:6]  # pywebview vuole #rrggbb: '#000' lo fa rompere all'avvio
    return "#111318"


def window_titlebar(hwnd: int, color: str) -> dict:
    """Barra del titolo e bordo di una finestra Windows del colore dato ('#rgb', '#rrggbb' o 'rgb(r, g, b)').
    Windows 11: colore esatto. Windows 10 (2004+): solo barra scura o chiara, secondo la luminosita'."""
    import ctypes
    h = str(color).strip()
    rgb = re.fullmatch(r"rgba?\(\s*(\d{1,3})[,\s]+(\d{1,3})[,\s]+(\d{1,3})[^)]*\)", h)
    h = "%02x%02x%02x" % tuple(int(v) for v in rgb.groups()) if rgb else h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))  # ValueError se il colore non e' esadecimale
    dark = r * 299 + g * 587 + b * 114 < 128_000
    dwm, user32 = ctypes.windll.dwmapi, ctypes.windll.user32

    def put(attr: int, value: int) -> bool:
        v = ctypes.c_int(value)
        return dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(v), 4) == 0

    out = {"dark": put(20, dark) or put(19, dark)}  # DWMWA_USE_IMMERSIVE_DARK_MODE (19 sulle build prima della 2004)
    rgb = r | g << 8 | b << 16  # COLORREF: 0x00BBGGRR
    out["color"] = put(35, rgb)  # DWMWA_CAPTION_COLOR, solo Windows 11
    if out["color"]:
        put(34, rgb)  # DWMWA_BORDER_COLOR
        put(36, 0xFFFFFF if dark else 0x000000)  # DWMWA_TEXT_COLOR
    # Windows 10 ridisegna la barra solo quando la finestra cambia stato attivo: la si "riattiva"
    active = user32.GetForegroundWindow() == hwnd
    user32.SendMessageW(ctypes.c_void_p(hwnd), 0x0086, not active, 0)  # WM_NCACTIVATE
    user32.SendMessageW(ctypes.c_void_p(hwnd), 0x0086, active, 0)
    return out


def _focus_running_window(port: int) -> bool:
    import json as _json
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/focus", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return bool(_json.loads(r.read()).get("window"))
    except Exception:
        return False


def _is_pozzo(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return b"build_stats" in r.read(400)
    except Exception:
        return False


def run(cfg, port: int = 8765, browser: bool = False, bigpicture: bool = False):
    import uvicorn
    if not _port_free(port):
        if _is_pozzo(port):  # una copia e' gia' aperta: non se ne avvia un'altra sugli stessi dati
            if not browser and _focus_running_window(port):
                print("Pozzo Launcher e' gia' aperto: ho riportato in primo piano la sua finestra.")
                return
            print(f"Pozzo Launcher e' gia' in esecuzione su http://127.0.0.1:{port}/ - lo apro nel browser. "
                  "Per aprirne un'altra usa --port.")
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}/" + ("bigpicture" if bigpicture else ""))
            return
        free = next((q for q in range(port + 1, port + 50) if _port_free(q)), None)
        if free is None:
            raise SystemExit(f"Porta {port} occupata da un altro programma: scegline un'altra con --port")
        print(f"Porta {port} occupata da un altro programma: uso la {free}")
        port = free
    inner = create_app(cfg)
    app = LocalGuard(inner, port)  # il server del telefono usa l'app senza guardia, dietro PhoneGate
    url = f"http://127.0.0.1:{port}/"
    start_url = url + ("bigpicture" if bigpicture else "")
    if browser:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(start_url)).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        return
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    try:
        import webview

        class Api:
            """Esposto al JavaScript come window.pywebview.api: finestre native di scelta file/cartella."""

            def pick_file(self):
                win = webview.windows[0]
                kind = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
                types = ("Programmi (*.exe)", "Tutti i file (*.*)") if sys.platform == "win32" else ("Tutti i file (*)",)
                r = win.create_file_dialog(kind, file_types=types)
                return r[0] if r else None

            def login(self, store_id):
                """Apre la pagina ufficiale di login (Epic/GOG) e cattura il codice di autorizzazione."""
                import json as _json
                import urllib.request
                prov = STORES.BY_ID.get(store_id)
                if not prov or not getattr(prov, "login_url", None):
                    return {"ok": False, "error": "login non previsto"}
                win = webview.create_window(f"Accedi a {prov.name}", prov.login_url, width=520, height=760)
                done = {"code": None}

                def watch():
                    for _ in range(600):  # 5 minuti
                        time.sleep(0.5)
                        try:
                            u = win.get_current_url() or ""
                        except Exception:
                            return
                        if store_id == "gog" and "on_login_success" in u and "code=" in u:
                            done["code"] = u
                        elif store_id == "epic" and "/id/api/redirect" in u:
                            try:
                                done["code"] = win.evaluate_js("document.body.innerText")
                            except Exception:
                                pass
                        if done["code"]:
                            win.destroy()
                            return
                watch()
                if not done["code"]:
                    return {"ok": False, "error": "accesso annullato"}
                req = urllib.request.Request(f"{url}api/accounts/{store_id}/code",
                                             data=_json.dumps({"code": done["code"]}).encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        return {"ok": True, **_json.loads(r.read())}
                except Exception as e:
                    return {"ok": False, "error": str(getattr(e, "read", lambda: b"")().decode() or e)}

            def window_ready(self, color):
                """Barra del titolo, bordo e comparsa della finestra con il colore del tema. La chiama il
                frontend quando tema e interfaccia sono gia' applicati: prima non si vede nulla, cosi' non
                si vede per un attimo il tema predefinito e i colori di sistema."""
                win = webview.windows[0]
                try:
                    if sys.platform == "win32" and color:
                        window_titlebar(win.native.Handle.ToInt64(), color)
                except Exception:  # colore non valido o finestra non pronta: si mostra lo stesso
                    pass
                if not shown.is_set():  # le chiamate successive (cambio tema) aggiornano solo titolo e bordo
                    shown.set()
                    win.show()
                return True

            def focus_window(self):
                """Riporta in primo piano la finestra dell'app quando il gioco si chiude."""
                win = webview.windows[0]
                try:
                    win.restore()
                    win.show()
                    if sys.platform == "win32":
                        import ctypes
                        hwnd = win.native.Handle.ToInt64()
                        ctypes.windll.user32.ShowWindow(hwnd, 9)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                return True

            def set_fullscreen(self, on):
                """Schermo intero (Big Picture)."""
                win = webview.windows[0]
                if bool(on) != state_fs["on"]:
                    win.toggle_fullscreen()
                    state_fs["on"] = bool(on)
                return state_fs["on"]

            def open_activity(self):
                """Finestra separata con le operazioni in corso; se e' gia' aperta torna in primo piano."""
                w = activity_win.get("w")
                if w is not None and w in webview.windows:
                    w.restore()
                    w.show()
                    return True
                activity_win["w"] = webview.create_window("Attività · Pozzo Launcher", f"{url}activity", width=520,
                                                          height=640, min_size=(360, 300), background_color="#111318",
                                                          js_api=api)
                return True

            def open_media(self):
                """Seconda finestra del launcher aperta sulla vista Media: il launcher principale resta libero
                (altre schermate, giochi) mentre qui si guarda una serie. Se e' gia' aperta torna in primo piano."""
                w = media_win.get("w")
                if w is not None and w in webview.windows:
                    w.restore()
                    w.show()
                    return True
                mapi = MediaApi()
                w = webview.create_window("Media · Pozzo Launcher", f"{url}#media-window", width=1280, height=820,
                                          min_size=(720, 480), background_color="#0f1115", js_api=mapi)
                mapi.win = w
                media_win["w"] = w
                return True

            def resolve_link(self, link):
                """Link vero dietro un accorciatore (ouo) o dietro la pagina di un host di file: finestra
                nascosta, clic da soli, URL del download letto da WebView2. None se non si arriva al file."""
                return browserdl.resolve(link)

            def pick_folder(self):
                win = webview.windows[0]
                kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
                r = win.create_file_dialog(kind)
                return r[0] if r else None

        class MediaApi(Api):
            """js_api della finestra Media: schermo intero, dialoghi e colore del titolo riguardano QUESTA finestra e non la principale."""
            win = None
            fs = False

            def set_fullscreen(self, on):
                if self.win is not None and bool(on) != self.fs:
                    self.win.toggle_fullscreen()
                    self.fs = bool(on)
                return self.fs

            def pick_folder(self):
                win = self.win or webview.windows[0]
                kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
                r = win.create_file_dialog(kind)
                return r[0] if r else None

            def window_ready(self, color):
                try:
                    if sys.platform == "win32" and color and self.win is not None:
                        window_titlebar(self.win.native.Handle.ToInt64(), color)
                except Exception:
                    pass
                return True

        state_fs = {"on": bigpicture}
        activity_win: dict = {}
        media_win: dict = {}
        api = Api()
        # la finestra principale nasce nascosta e si mostra quando il frontend ha applicato tema e interfaccia
        shown = threading.Event()
        WINDOW_FOCUS["fn"] = api.focus_window
        SL.set_resolver(api.resolve_link, browserdl.reason)  # accorciatori (ouo) e host (DataNodes)
        browserdl.install()  # l'URL del download del WebView si legge solo con questo aggancio (Windows)
        from .. import notify
        ico = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "packaging" / "icon.ico"
        def on_notification_click(action):
            api.focus_window()
            try:
                webview.windows[0].evaluate_js(f"window.gsNotifyAction && window.gsNotifyAction({json.dumps(action)})")
            except Exception:
                pass

        notify.start_tray(str(ico), api.focus_window, lambda: webview.windows[0].destroy(),  # icona vicino a volume e rete
                          on_notification_click)
        bg = _theme_bg(cfg, bigpicture)
        # hidden=True (solo Windows: altrove pywebview non ha un modo affidabile di mostrarla dopo): la
        # finestra appare gia' con tema, colori e disposizione giusti, non con quelli predefiniti
        geo_file = Path(cfg.cache).parent / "window.json"
        try:
            g = json.loads(geo_file.read_text("utf-8"))
            pos = {k: int(g[k]) for k in ("x", "y", "width", "height")}
            if pos["x"] < -10000 or pos["y"] < -10000:  # finestra chiusa da minimizzata (-32000)
                raise ValueError
        except Exception:
            pos = {"width": 1500, "height": 940}
        main_win = webview.create_window("Pozzo Launcher", start_url, **pos, min_size=(960, 600),
                                         background_color=bg, js_api=api, fullscreen=bigpicture,
                                         hidden=sys.platform == "win32")

        def save_geometry():
            if bigpicture:
                return
            try:  # shortcut: non ricorda lo stato "massimizzata", solo posizione e misura
                geo = {"x": main_win.x, "y": main_win.y, "width": main_win.width, "height": main_win.height}
                if geo["x"] > -10000 and geo["y"] > -10000:
                    geo_file.write_text(json.dumps(geo), "utf-8")
            except Exception:
                pass
        main_win.events.closing += save_geometry
        if sys.platform == "win32":  # errore JS: la finestra si mostra lo stesso, senza aspettare all'infinito
            def show_anyway():
                if not shown.wait(15):
                    try:
                        window_titlebar(main_win.native.Handle.ToInt64(), bg)
                    except Exception:
                        pass
                    main_win.show()
            threading.Thread(target=show_anyway, daemon=True).start()

        # chiusa la finestra principale si chiude anche quella delle attivita' (altrimenti l'app resta aperta)
        main_win.events.closed += lambda: activity_win.get("w") and activity_win["w"].destroy()
        inner.state.overlay.attach(url)
        # il suono degli avvisi (WebAudio) parte senza un clic dentro la finestra
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
                                                              + " --autoplay-policy=no-user-gesture-required").strip()
        # private_mode=False + cartella fissa: senza, la finestra butta via il localStorage alla chiusura
        # (console preferite, filtri, ordinamenti...)
        webview.start(private_mode=False, storage_path=str(Path(cfg.cache).parent / "webview"))
    except Exception as e:  # pywebview non disponibile: si usa il browser
        print(f"Finestra desktop non disponibile ({e}), apro il browser: {url}")
        import webbrowser
        webbrowser.open(start_url)
        t.join()
    finally:
        server.should_exit = True
        try:
            from .. import notify
            notify.remove()
        except Exception:
            pass
        t.join(timeout=3)  # spegnimento ordinato del server: telefono e controller virtuali
        # uscita immediata: senza, Python aspetta i lavori in sottofondo (lettura store, scraping) e la
        # finestra chiusa resta un processo che lavora; quei lavori riprendono da soli al prossimo avvio
        os._exit(0)
