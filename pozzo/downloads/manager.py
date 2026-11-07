"""Coda dei download: un thread con il proprio event loop dentro il launcher.

Chi chiama (rotte, altri moduli) lo fa da altri thread: tutto cio' che e' pubblico prende `lock` e
sveglia il ciclo. Ogni secondo il ciclo promuove i task in coda, calcola le velocita', salva su disco
e manda l'evento `downloads` (la UI lo legge dallo stream SSE).
"""
from __future__ import annotations

import asyncio
import math
import random
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx

from .. import config as C, net
from . import hosts, ingest as I, resolvers, task as TASK
try:
    from .bandwidth import record as _record_bw
except ImportError:  # modulo non ancora presente: niente statistiche di banda
    def _record_bw(host: str, nbytes: int) -> None:
        pass
from .debrid import SERVICES
from .extract import drive_of, queue_forecast
from .engines import http as HTTP, torrent as TOR
from .store import Store
from .task import ACTIVE, COMPLETED, ERROR, PAUSED, QUEUED, RUNNING, DownloadTask, mb

# limiti in KB/s, 0 = illimitato; port 0 = a caso; max_active_<tipo> 0 = vale solo max_active;
# seed_ratio/seed_minutes 0 = il torrent esce dalla sessione appena finito; alt_* = modalita' lenta (a mano o a orario)
DEFAULTS = {"dir": "", "max_active": 3, "segments": 4, "limit_down": 0, "limit_up": 0, "port": 0,
            "max_active_http": 0, "max_active_torrent": 0, "trackers": [],
            "discovery": {"dht": True, "pex": True, "lsd": True, "upnp": True}, "encryption": "prefer",
            "seed_ratio": 0.0, "seed_minutes": 0, "alt_limit_down": 0, "alt_limit_up": 0, "alt_enabled": False,
            "alt_schedule": {"enabled": False, "from": "22:00", "to": "07:00", "days": [0, 1, 2, 3, 4, 5, 6]},
            "debrid": {}, "clipboard": False, "auto_extract": True, "delete_archive": True,
            "show_browser": False, "game_mode": "off", "game_limit_kbps": 0, "game_pause_http": False}
INTS = {"max_active": (1, 10), "segments": (1, 8), "limit_down": (0, 10_000_000), "limit_up": (0, 10_000_000),
        "port": (0, 65535), "max_active_http": (0, 10), "max_active_torrent": (0, 10), "seed_minutes": (0, 100_000),
        "alt_limit_down": (0, 10_000_000), "alt_limit_up": (0, 10_000_000), "game_limit_kbps": (0, 10_000_000)}
BOOLS = ("alt_enabled", "clipboard", "auto_extract", "delete_archive", "show_browser", "game_pause_http")
SCHEMES = ("http://", "https://")
TRACKER_SCHEMES = ("udp://", "http://", "https://", "wss://")
GAME_MODES = ("off", "limit", "pause")  # mentre giochi: niente, solo un limite di banda, torrent in pausa
RESOLVERS_MAX = 3  # task HTTP che risolvono il link insieme (non occupano posti: senza tetto partirebbero tutti)
SPACE_PHASE = "Spazio insufficiente"  # fase di un task in coda che non ha ancora spazio sul disco
NET_TRIES = 20  # riprese automatiche per task dopo un errore di rete
SAVE_EVERY = 10 # s tra due salvataggi dello stesso task nel tick, se non cambia stato/fase/errore/nome


def default_dir() -> Path:
    return Path.home() / "Downloads" / "Pozzo"


def _prio(v) -> int:
    return min(max(int(v), -2), 2)


def _order(t: DownloadTask):
    return -t.priority, t.created


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def alt_active(s: dict, now: datetime | None = None) -> bool:
    """Modalita' lenta: a mano, oppure dentro la fascia oraria nei giorni scelti (0 = lunedi').
    Una fascia che passa la mezzanotte (22:00-07:00) appartiene al giorno in cui inizia; from == to = tutto il giorno."""
    if s.get("alt_enabled"):
        return True
    sc = s.get("alt_schedule") or {}
    if not sc.get("enabled"):
        return False
    now = now or datetime.now()
    f, t, m, day = _mins(sc["from"]), _mins(sc["to"]), now.hour * 60 + now.minute, now.weekday()
    if f > t and m < t:
        day = (day - 1) % 7  # dopo mezzanotte: e' la fascia iniziata ieri
    inside = f <= m < t if f < t else (m >= f or m < t) if f > t else True
    return inside and day in (sc.get("days") or [])


_TIME = re.compile(r"(\d{1,2}):(\d{2})")


def _norm_schedule(start_at, days=None) -> dict:
    """Pianificazione di un singolo download: {} se non c'e', altrimenti {"start_at": ..., "days": [...]}.

    `start_at` = "HH:MM" (ogni giorno, o solo nei giorni di `days`, 0 = lunedi'), oppure data e ora ISO
    "YYYY-MM-DD HH:MM" per un avvio una volta sola. ValueError con il motivo se non e' valida."""
    txt = str(start_at or "").strip()
    if not txt:
        return {}
    m = _TIME.fullmatch(txt)
    if m:
        if int(m[1]) > 23 or int(m[2]) > 59:
            raise ValueError("start_at: ora non valida, serve HH:MM")
        out = {"start_at": f"{int(m[1]):02d}:{m[2]}"}
        if days is not None:
            if not isinstance(days, (list, tuple)) or any(type(x) is not int or not 0 <= x <= 6 for x in days):
                raise ValueError("days: giorni da 0 (lunedi') a 6")
            out["days"] = sorted(set(days))
        return out
    try:
        when = datetime.fromisoformat(txt)
    except ValueError:
        raise ValueError("start_at: serve un orario HH:MM o una data AAAA-MM-GG HH:MM")
    return {"start_at": when.strftime("%Y-%m-%d %H:%M")}  # una data e ora precisa: i giorni non servono


def _due(opts: dict, now: datetime) -> bool:
    """Il download pianificato puo' partire adesso? Senza `start_at` (o con una pianificazione rovinata) sempre si'."""
    at = str((opts or {}).get("start_at") or "").strip()
    if not at:
        return True
    if _TIME.fullmatch(at):
        if now.hour * 60 + now.minute < _mins(at):
            return False
        days = opts.get("days")
        return not days or now.weekday() in days  # stessi giorni della modalita' lenta: 0 = lunedi'
    try:
        when = datetime.fromisoformat(at)
    except ValueError:
        return True
    return now >= when


def _bool(k: str, v) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"{k} deve essere true o false")
    return v


def _dict(k: str, v) -> dict:
    if not isinstance(v, dict):
        raise ValueError(f"{k} deve essere un oggetto")
    return v


def _num(k: str, v, kind=int):
    try:
        n = kind(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{k} deve essere un numero")
    if isinstance(n, float) and not math.isfinite(n):
        raise ValueError(f"{k} deve essere un numero")
    return n


def _port_ok(p: int) -> bool:
    """La porta si apre in TCP e UDP (Windows riserva blocchi di porte alte a Hyper-V/WinNAT, anche dopo un riavvio:
    libtorrent non ci ascolterebbe)."""
    try:
        with socket.socket() as a, socket.socket(type=socket.SOCK_DGRAM) as b:
            a.bind(("0.0.0.0", p))
            b.bind(("0.0.0.0", p))
        return True
    except OSError:
        return False


def _free_port() -> int:
    """Porta a caso in 49152-65000 libera in TCP e UDP, 0 se non ne trova."""
    return next((p for p in (random.randint(49152, 65000) for _ in range(50)) if _port_ok(p)), 0)


class Manager:
    def __init__(self, cfg, events=None, client_factory=net.make_client, save=None, playing=None):
        self.cfg, self.events, self.client_factory = cfg, events, client_factory
        self._save = save or (lambda new: C.save_settings(cfg, app={"downloads": new}))
        self.playing = playing or (lambda: False)  # fn() -> True se c'e' un gioco in corso (iniettata dalle rotte)
        self.now = datetime.now  # orologio del ciclo: i test lo sostituiscono per la pianificazione
        self.store = Store(Path(cfg.cache))
        TASK.RATE_FILE = Path(cfg.cache) / "extract_rate.json"
        self.uploads = Path(cfg.cache) / "torrents" / "uploads"  # copie dei .torrent caricati dalla UI
        self.lock = threading.RLock()
        self.on_completed = None  # fn(task), in un thread: estrazione e libreria (downloads/finish.py)
        self.tasks: dict[str, DownloadTask] = {}
        self._jobs: dict[str, asyncio.Task] = {}
        self._buckets: dict[str, HTTP.Bucket] = {}  # limite per task HTTP: quota del globale e limite proprio
        self._torrent = TOR.Engine(Path(cfg.cache) / "torrents") if TOR.available() else None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._ready = threading.Event()
        self._last: dict[str, tuple] = {}  # task id -> (done, tempo) per la velocita'
        self._res: dict[str, tuple] = {}  # task id -> (token, note) della risoluzione del link in corso
        self._sent: dict[str, dict] = {}  # task id -> ultima vista mandata alla UI
        self._alt_sent: bool | None = None  # modalita' lenta all'ultimo evento: se cambia (orario) l'evento porta le impostazioni
        self._game = {"on": False, "paused": []}  # partita in corso e i task fermati da lei (da riprendere alla fine)
        self._dl_ids: set[str] = set()  # task HTTP che hanno il link e scaricano davvero: solo loro occupano un posto
        self._gates: dict[str, asyncio.Future] = {}  # task HTTP col link pronto in attesa di un posto (li sblocca il tick)
        self._saved: dict[str, tuple] = {}  # task id -> (tempo, (status, phase, error, name)) dell'ultimo salvataggio nel tick
        self.ctx = None  # lo mette finish.run: serve a mark_ready per cercare il gioco in libreria
        self._pend_at = 0.0  # ultimo controllo dei task in attesa della scansione
        self.on_idle = None  # fn(completati, falliti), in un thread: la coda si e' svuotata dopo aver lavorato
        self._batch = [0, 0]  # completati / falliti dall'ultima volta che la coda era vuota
        self._was_busy = False
        self._net_at = 0.0  # ultimo controllo della rete per i task caduti per errore di connessione
        self._dirty: set[str] = set()  # task con la vista cambiata dopo l'ultimo salvataggio nel tick

    # ------------------------------------------------------------ impostazioni
    def _raw(self) -> dict:
        """Impostazioni complete, chiavi debrid comprese: mai fuori dal backend (per la UI c'e' settings())."""
        s = {**DEFAULTS, **(self.cfg.app.get("downloads") or {})}
        if isinstance(s["discovery"], bool):  # versioni vecchie: un solo interruttore per tutto
            s["discovery"] = dict.fromkeys(DEFAULTS["discovery"], s["discovery"])
        for k in ("discovery", "alt_schedule"):
            s[k] = {**DEFAULTS[k], **(s[k] if isinstance(s[k], dict) else {})}
        s["dir"] = s["dir"] or str(default_dir())
        return s

    def settings(self) -> dict:
        s = self._raw()
        deb = s["debrid"] or {}
        s["debrid"] = {k: {"enabled": bool((deb.get(k) or {}).get("enabled")), "key_set": bool((deb.get(k) or {}).get("key"))}
                       for k in SERVICES}
        s["alt_active"] = alt_active(s)
        s["game_active"] = self._game["on"]
        return s

    def update_settings(self, body: dict) -> dict:
        """Aggiornamento parziale: valori controllati e riportati nei limiti; ValueError se non validi."""
        with self.lock:
            cur, new = self._raw(), dict(self.cfg.app.get("downloads") or {})
            if "dir" in body:
                d = Path(str(body["dir"])).expanduser() if body["dir"] else None
                if d:
                    try:
                        d.mkdir(parents=True, exist_ok=True)
                    except OSError as e:
                        raise ValueError(f"Cartella non utilizzabile: {e}")
                new["dir"] = str(d) if d else ""
            for k, (lo, hi) in INTS.items():
                if k in body:
                    new[k] = min(max(_num(k, body[k]), lo), hi)
            if "port" in body:  # scelta da start() o dall'utente (a mano: non la cambia piu' nessuno)
                new["port_auto"] = body.get("port_auto") is True
            if "seed_ratio" in body:
                new["seed_ratio"] = min(max(_num("seed_ratio", body["seed_ratio"], float), 0.0), 100.0)
            for k in BOOLS:
                if k in body:
                    new[k] = _bool(k, body[k])
            if "trackers" in body:
                v = body["trackers"].split() if isinstance(body["trackers"], str) else body["trackers"]
                if not isinstance(v, list):
                    raise ValueError("trackers deve essere un elenco")
                new["trackers"] = list(dict.fromkeys(u for u in (str(x).strip() for x in v)
                                                     if u.lower().startswith(TRACKER_SCHEMES)))[:200]
            if "discovery" in body:
                d = _dict("discovery", body["discovery"])
                new["discovery"] = {k: _bool(k, d[k]) if k in d else cur["discovery"][k] for k in DEFAULTS["discovery"]}
            if "encryption" in body:
                if body["encryption"] not in TOR.ENCRYPTION:
                    raise ValueError("encryption: prefer, require o disable")
                new["encryption"] = body["encryption"]
            if "alt_schedule" in body:
                d, sc = _dict("alt_schedule", body["alt_schedule"]), dict(cur["alt_schedule"])
                if "enabled" in d:
                    sc["enabled"] = _bool("enabled", d["enabled"])
                for k in ("from", "to"):
                    if k in d:
                        m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(d[k]).strip())
                        if not m or int(m[1]) > 23 or int(m[2]) > 59:
                            raise ValueError(f"{k}: serve un orario HH:MM")
                        sc[k] = f"{int(m[1]):02d}:{m[2]}"
                if "days" in d:
                    days = d["days"]
                    if not isinstance(days, list) or any(type(x) is not int or not 0 <= x <= 6 for x in days):
                        raise ValueError("days: giorni da 0 (lunedi') a 6")
                    sc["days"] = sorted(set(days))
                new["alt_schedule"] = sc
            if "debrid" in body:
                deb = {k: dict(v) for k, v in (cur["debrid"] or {}).items()}
                for svc, v in _dict("debrid", body["debrid"]).items():
                    if svc not in SERVICES:
                        raise ValueError(f"Servizio debrid sconosciuto: {svc}")
                    v, e = _dict(svc, v), deb.setdefault(svc, {})
                    if "enabled" in v:
                        e["enabled"] = _bool("enabled", v["enabled"])
                    if "key" in v:
                        key = str(v["key"] or "").strip()
                        if key:
                            e["key"] = key
                        else:
                            e.pop("key", None)  # "" toglie la chiave
                new["debrid"] = deb
            if "game_mode" in body:
                if body["game_mode"] not in GAME_MODES:
                    raise ValueError("game_mode: off, limit o pause")
                new["game_mode"] = body["game_mode"]
            self._save(new)
            self.cfg.app["downloads"] = new
            self._alt_sent = None  # il prossimo evento porta le impostazioni nuove (altre finestre aperte)
        self._poke()
        return self.settings()

    def set_alt(self, on: bool) -> dict:
        return self.update_settings({"alt_enabled": bool(on)})

    def _limits(self, s: dict) -> tuple[int, int]:
        """Limiti in KB/s in vigore: quelli lenti se la modalita' lenta e' attiva, la banda da lasciare al gioco se
        e' la modalita' scelta e un gioco sta girando (vale per HTTP e torrent; l'upload resta quello globale)."""
        pre = "alt_" if alt_active(s) else ""
        down, up = int(s[pre + "limit_down"]), int(s[pre + "limit_up"])
        game = int(s.get("game_limit_kbps") or 0)
        if self._game["on"] and s.get("game_mode") == "limit" and game > 0:
            down = game
        return down, up

    def _game_tick(self, s: dict):
        """Partita che parte o finisce: in modalita' «pause» ferma i download in corso, in «limit» basta `_limits`.
        Alla fine riprende solo quello che ha fermato lei: un download messo in pausa a mano resta fermo."""
        try:
            on = bool(self.playing())
        except Exception:  # noqa: BLE001 - un callback rotto (launcher assente…) non deve fermare la coda
            on = False
        if on == self._game["on"]:
            return
        self._game["on"] = on
        with self.lock:
            if on:
                if s.get("game_mode") != "pause":
                    return
                ids = []
                for t in self.tasks.values():
                    if t.status != RUNNING:  # i task in coda partono quando tocca a loro: in pausa non partirebbero piu'
                        continue
                    if not (t.type == "torrent" or s.get("game_pause_http")):
                        continue
                    self.pause(t.id)
                    if t.status == PAUSED:  # chi stava solo condividendo resta completato: niente da riprendere
                        ids.append(t.id)
                        t.log("In pausa: c'è un gioco in esecuzione")
                self._game["paused"] = ids
            else:
                ids, self._game["paused"] = self._game["paused"], []
                for tid in ids:
                    t = self.tasks.get(tid)
                    if t and t.status == PAUSED:
                        t.log("Il gioco è finito: riprendo i download")
                        self.resume(tid)

    # ------------------------------------------------------------ ciclo di vita
    def start(self):
        if self._loop:
            return
        # port 0 = «scegli tu»: una porta a caso salvata, cosi' a ogni avvio e' la stessa (UPnP e i peer ritrovano il
        # client); se nel frattempo Windows l'ha riservata se ne sceglie un'altra. Quella impostata a mano non si tocca
        port = int(self._raw()["port"] or 0)
        auto = (self.cfg.app.get("downloads") or {}).get("port_auto")
        if not port or (auto and not _port_ok(port)):
            port = _free_port()
            if port:
                self.update_settings({"port": port, "port_auto": True})
        for t in self.store.load():
            if t.status == RUNNING:
                t.status = QUEUED  # il launcher e' stato chiuso a meta': riprende da dove era
                t.log("Il launcher era stato chiuso durante il download: riprendo", "warn")
            t.priority = _prio(t.priority)  # versioni vecchie: priorita' libera
            t.options.pop("seeding", None)  # la condivisione non riparte dopo un riavvio
            self.tasks[t.id] = t
        used = {Path(t.source) for t in self.tasks.values()}
        for p in self.uploads.glob("*.torrent"):  # .torrent caricati di task che non ci sono piu'
            if p not in used:
                try:
                    p.unlink()
                except OSError:
                    pass
        threading.Thread(target=self._thread, daemon=True, name="downloads").start()
        self._ready.wait(10)

    def _thread(self):
        loop = self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._wake = asyncio.Event()
        self._ready.set()
        loop.run_until_complete(self._main())

    def _poke(self):
        if self._loop and self._wake:
            self._loop.call_soon_threadsafe(self._wake.set)

    def stop(self):
        """Ferma i download in corso conservandone lo stato: alla prossima apertura ripartono."""
        with self.lock:
            jobs = list(self._jobs.values())
            for tid in list(self._jobs):
                self._cancel_job(tid)
        if jobs and self._loop:  # i torrent salvano i resume data prima di uscire: si aspetta (poco)
            try:
                asyncio.run_coroutine_threadsafe(asyncio.wait(jobs, timeout=5), self._loop).result(6)
            except Exception:  # noqa: BLE001 - alla chiusura vale lo stato salvato finora
                pass
        with self.lock:
            self.store.save(list(self.tasks.values()))
        if self._torrent and self._loop:
            self._loop.call_soon_threadsafe(self._torrent.close)

    # ------------------------------------------------------------ comandi
    def add(self, source: str, save_path: str = "", **opts) -> DownloadTask:
        source = source.strip()
        sched = _norm_schedule(opts.pop("start_at", None), opts.pop("days", None))  # «Avvia alle», facoltativo
        kind = "torrent" if TOR.is_torrent(source) else "http"
        if kind == "torrent":
            if not self._torrent:
                raise ValueError("Per i torrent serve libtorrent: installalo con «pip install libtorrent»")
            TOR.check_magnet(source)
            if not source.lower().startswith(("magnet:", *SCHEMES)) and not Path(source).expanduser().is_file():
                raise ValueError("File .torrent non trovato")
        elif not source.lower().startswith(SCHEMES):
            raise ValueError("Serve un link http(s)")
        dest = Path(save_path or self.settings()["dir"]).expanduser()
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ValueError(f"Cartella non utilizzabile: {e}")
        t = DownloadTask(source=source, save_path=str(dest), type=kind, name=opts.pop("name", ""), priority=_prio(opts.pop("priority", 0)),
                         category=opts.pop("category", ""), options={**opts, **sched})
        t.log(f"Aggiunto ({kind}): {source}  ->  {dest}")
        with self.lock:
            self.tasks[t.id] = t
            self.store.save([t])
        self._poke()
        return t

    def _get(self, tid: str) -> DownloadTask:
        t = self.tasks.get(tid)
        if not t:
            raise KeyError(tid)
        return t

    def pause(self, tid: str):
        with self.lock:
            t = self._get(tid)
            if t.status in ACTIVE:
                t.status = PAUSED
                t.log("In pausa")
            elif not t.options.get("seeding"):
                return
            else:
                t.log("Condivisione fermata")
            self._cancel_job(tid)  # in condivisione: si ferma e resta completato
            self.store.save([t])
        self._poke()

    def pause_all(self):
        with self.lock:
            for tid in list(self.tasks):
                self.pause(tid)

    def resume_all(self):
        with self.lock:
            for tid in list(self.tasks):
                self.resume(tid)

    def resume(self, tid: str):
        with self.lock:
            t = self._get(tid)
            if t.status in (PAUSED, ERROR):
                t.status, t.error = QUEUED, ""
                t.log("Ripreso: in coda")
                self.store.save([t])
        self._poke()

    def cancel(self, tid: str, delete_files: bool = False):
        with self.lock:
            t = self.tasks.pop(self._get(tid).id)
            self._sent.pop(tid, None)
            self._saved.pop(tid, None)
            self._dirty.discard(tid)
            self._cancel_job(tid)
            job = self._jobs.get(tid)
            self.store.delete(tid)

        def purge():
            paths = [self._torrent.resume_file(tid)] if self._torrent else []
            if t.type == "torrent" and Path(t.source).parent == self.uploads:
                paths.append(Path(t.source))  # la copia del .torrent caricato: i metadati non servono piu'
            dirs = set()
            if delete_files:
                names = [f["name"] for f in t.options.get("files") or []] if t.type == "torrent" else \
                    [t.name] if t.name and t.status == COMPLETED else []
                root = Path(t.save_path).resolve()
                files = [Path(p).resolve() for p in [t.options.get("part"), *(str(root / n) for n in names)] if p]
                files = [p for p in files if p.is_relative_to(root)]
                paths += files
                dirs = {d for p in files for d in p.parents if d != root and d.is_relative_to(root)}
            for p in paths:
                try:
                    p.unlink(missing_ok=True)
                except OSError:  # aperto da un altro programma: resta li', il download e' comunque annullato
                    pass
            for d in sorted(dirs, key=lambda d: len(d.parts), reverse=True):  # cartelle del torrent rimaste vuote
                try:
                    d.rmdir()
                except OSError:  # non vuota (altri file della persona): resta
                    pass

        if job and self._loop:  # a job finito: file chiusi (Windows non cancella file aperti) e resume data gia' scritti
            async def later():
                await asyncio.wait([job])
                purge()
            asyncio.run_coroutine_threadsafe(later(), self._loop)
        else:
            purge()
        self._poke()

    def set_files(self, tid: str, priorities: dict):
        """Priorita' dei file di un torrent (0 salta, 1 normale, 4 alta, 7 massima): subito se sta scaricando."""
        with self.lock:
            t = self._get(tid)
            if t.options.get("wanted"):
                raise ValueError("Di questo gioco si scarica solo il file scelto: la selezione non si cambia")
            new = {**(t.options.get("priorities") or {})}
            for i, v in priorities.items():
                if int(v) not in TOR.PRIORITIES:
                    raise ValueError("Priorita' non valida")
                new[str(int(i))] = int(v)
            t.options["priorities"] = new
            t.log(f"Selezione file cambiata: {sum(1 for v in new.values() if v)} file da scaricare")
            for f in t.options.get("files") or []:  # la vista resta giusta anche in pausa
                f["priority"] = new.get(str(f["index"]), 0)
            if t.type == "torrent" and t.status == COMPLETED and any(int(v) for v in priorities.values()):
                t.status = QUEUED  # altri file scelti dopo la fine: si riprende
                if t.options.get("seeding"):
                    self._cancel_job(tid)  # il job che condivide finisce; il tick ne fa partire uno che scarica
            h = self._torrent.handles.get(tid) if self._torrent else None
            if h and h.status().has_metadata:
                h.prioritize_files([new.get(str(i), 0) for i in range(h.torrent_file().num_files())])
            self.store.save([t])
        self._poke()

    def set_sequential(self, tid: str, on: bool):
        with self.lock:
            t = self._get(tid)
            t.options["sequential"] = bool(on)  # il motore lo applica al giro successivo (mezzo secondo)
            t.log(f"Download sequenziale {'attivo' if on else 'disattivato'}")
            self.store.save([t])
        self._poke()

    def set_priority(self, tid: str, priority: int):
        with self.lock:
            t = self._get(tid)
            t.priority = _prio(priority)
            t.log(f"Priorità: {t.priority}")
            self.store.save([t])
        self._poke()

    def move(self, tid: str, to: str):
        """In cima o in fondo alla coda: priorita' all'estremo di quelle degli altri non completati e `created` oltre il loro."""
        if to not in ("top", "bottom"):
            raise ValueError("to: top o bottom")
        with self.lock:
            t = self._get(tid)
            others = [o for o in self.tasks.values() if o is not t and o.status != COMPLETED]
            if others:
                top = to == "top"
                t.priority = (max if top else min)(t.priority, *(o.priority for o in others))
                t.created = min(o.created for o in others) - 1 if top else max(o.created for o in others) + 1
                t.log(f"Spostato in {'cima' if top else 'fondo'} alla coda")
                self.store.save([t])
        self._poke()

    def set_limit(self, tid: str, down: int, up: int):
        """Limite del singolo task in KB/s (0 = nessuno), oltre a quello globale."""
        lim = {"down": min(max(_num("down", down), 0), 10_000_000), "up": min(max(_num("up", up), 0), 10_000_000)}
        with self.lock:
            t = self._get(tid)
            t.options["limit"] = lim  # sostituito intero: la vista lo copia mentre il ciclo lo legge
            t.log(f"Limite di velocità: giù {lim['down'] or 'nessuno'}, su {lim['up'] or 'nessuno'} (KB/s)")
            self.store.save([t])
        self._poke()

    def set_schedule(self, tid: str, start_at, days=None):
        """«Avvia alle»: il task resta in coda e parte da solo (stringa vuota = pianificazione cancellata)."""
        sched = _norm_schedule(start_at, days)
        with self.lock:
            t = self._get(tid)
            t.options.pop("start_at", None)
            t.options.pop("days", None)
            t.options.update(sched)
            if sched and t.status == PAUSED:
                t.status = QUEUED  # pianificato: torna in coda e parte all'ora scelta
            t.log(f"Avvio pianificato per {sched['start_at']}" if sched else "Pianificazione annullata")
            self.store.save([t])
        self._poke()

    def _torrent_handle(self, tid: str):
        t = self._get(tid)
        if t.type != "torrent":
            raise ValueError("Solo per i torrent")
        return t, self._torrent.handles.get(tid) if self._torrent else None

    def recheck(self, tid: str):
        """Ricontrolla i file su disco: subito se il torrent e' nella sessione, altrimenti alla prossima partenza."""
        with self.lock:
            t, h = self._torrent_handle(tid)
            if h and h.is_valid():
                h.force_recheck()
                t.log("Ricontrollo dei file su disco")
                return
            t.options["recheck"] = True
            t.log("Ricontrollo dei file alla prossima partenza")
            if t.status == COMPLETED:
                t.status = QUEUED  # riparte, ricontrolla e (se manca qualcosa) riscarica
            self.store.save([t])
        self._poke()

    def reannounce(self, tid: str):
        with self.lock:
            _, h = self._torrent_handle(tid)
            if h and h.is_valid():
                h.force_reannounce()
                self.tasks[tid].log("Riannuncio ai tracker")

    def log_clear(self, tid: str):
        self._get(tid).log_clear()

    def list(self) -> list[dict]:
        with self.lock:
            return [t.view() for t in sorted(self.tasks.values(), key=_order)]

    def _cancel_job(self, tid: str):
        # resta in _jobs finche' non e' finito davvero (lo toglie _job): un «riprendi» subito dopo non si sovrappone
        job = self._jobs.get(tid)
        if job and self._loop:
            self._loop.call_soon_threadsafe(job.cancel)

    # ------------------------------------------------------------ ciclo
    async def _main(self):
        try:  # HTTP/1.1: con HTTP/2 tutti i segmenti verso un host passano su una sola connessione
            client = self.client_factory(http2=False)
        except TypeError:  # factory senza il parametro (test)
            client = self.client_factory()
        async with client:
            self._client = client
            opened = False
            while True:
                try:
                    self._tick()
                except Exception:  # noqa: BLE001 - un tick sbagliato non deve fermare la coda
                    import traceback
                    traceback.print_exc()
                if not opened and self._torrent:  # sessione subito, dopo il primo configure: DHT gia' caldo al primo magnet
                    opened = True
                    try:
                        self._torrent.session()
                    except Exception:  # noqa: BLE001 - senza sessione ora, la apre il primo torrent
                        pass
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass

    def mark_ready(self, tid: str) -> bool:
        """Task con la libreria in attesa della scansione: se il gioco e' comparso, libreria e dati sono fatti."""
        t = self.tasks.get(tid)
        if not (t and self.ctx and t.options.get("pending_files")) or t._stage("library")["state"] != "active":
            return False
        files = t.options["pending_files"]
        if not (g := I._lib_match(self.ctx.lib, [Path(p) for p in files])):  # mai pronto senza il gioco
            return False
        t.set_stage("library", "done")
        t.set_stage("data", "done")
        t.options.pop("pending_files", None)
        self.store.save([t])
        self._poke()
        # ingest non l'ha emesso (pending): lo si fa qui, una volta sola (pending_files tolto e salvato), per webhook e avviso
        if ev := getattr(self.ctx, "events", None):
            ev.emit("game_downloaded", {"game_id": g["id"], "from_id": t.options.get("game_id"),
                                        "title": g["title"], "key": g["key"], "files": list(files)})
        return True

    def _tick(self):
        if time.monotonic() - self._pend_at >= 30:
            self._pend_at = time.monotonic()
            for tid in [i for i, x in list(self.tasks.items()) if x.options.get("pending_files")]:
                try:
                    self.mark_ready(tid)
                except Exception:  # noqa: BLE001 - un controllo fallito si ripete al giro dopo
                    pass
        self._net_resume()
        s = self._raw()
        self._game_tick(s)
        down, up = self._limits(s)
        if self._torrent:
            self._torrent.configure({**s, "limit_down": down, "limit_up": up})
        now = time.monotonic()
        with self.lock:
            for t in self.tasks.values():
                if t.status == RUNNING:
                    prev = self._last.get(t.id)
                    if prev and now > prev[1]:
                        inst = max(t.done - prev[0], 0) / (now - prev[1])
                        if t.done > prev[0]:  # magnet e .torrent non hanno host: vanno sotto «torrent»
                            _record_bw(hosts.host(t.source) or t.type, t.done - prev[0])
                        t.speed = inst if not t.speed else t.speed * 0.7 + inst * 0.3
                        t.speed = t.speed if t.speed >= 1 else 0.0  # fermo: la media da sola non arriva mai a zero
                    self._last[t.id] = (t.done, now)
                else:
                    t.speed = 0.0
            # posti: solo chi scarica davvero. Fuori: torrent in condivisione o in attesa dei metadati, task HTTP che
            # risolvono il link o lo aspettano al gate. Un job annullato ma non ancora finito occupa (tipo "")
            busy, resolving = [], 0
            for tid in self._jobs:
                o = self.tasks.get(tid)
                if o is None:
                    busy.append("")
                elif o.options.get("seeding") or o.options.get("metadata") is False:
                    continue
                elif o.type == "http" and tid not in self._dl_ids:
                    resolving += tid not in self._gates
                else:
                    busy.append(o.type)

            def free(kind: str) -> bool:
                cap = int(s.get(f"max_active_{kind}") or 0)
                return len(busy) < int(s["max_active"]) and not (cap and busy.count(kind) >= cap)

            for t in sorted((self.tasks[i] for i, f in self._gates.items() if not f.done() and i in self.tasks), key=_order):
                if free("http"):  # link pronto e posto libero: si scarica (prima chi ha priorita')
                    busy.append("http")
                    self._dl_ids.add(t.id)
                    self._gates[t.id].set_result(None)
            for t in sorted((t for t in self.tasks.values() if t.status == QUEUED and t.id not in self._jobs), key=_order):
                if not _due(t.options, self.now()):
                    continue  # pianificato («Avvia alle»): aspetta il suo orario, senza occupare un posto
                if len(busy) >= int(s["max_active"]):
                    break
                gap = self._space_gap(t)
                if gap:  # resta in coda: il posto e' di chi sta dopo, se e' piu' piccolo
                    if not t.phase.startswith(SPACE_PHASE):  # una riga sola, non una per tick
                        t.log(f"In attesa: spazio insufficiente (mancano {gap / 2**30:.1f} GB)", "warn")
                    self._phase(t, f"{SPACE_PHASE}: servono {gap / 2**30:.1f} GB")
                    continue
                if t.phase.startswith(SPACE_PHASE):
                    t.phase = ""
                if t.type == "http":
                    if resolving >= RESOLVERS_MAX:
                        continue
                    resolving += 1  # il posto lo prende al gate, a link risolto
                elif not free(t.type):
                    continue
                else:
                    busy.append(t.type)
                t.status = RUNNING
                planned = t.options.pop("start_at", None), t.options.pop("days", None)
                if any(v is not None for v in planned):
                    self.store.save([t])  # partito: la pianificazione non serve piu', neanche dopo un riavvio
                t.log("Avviato")
                self._jobs[t.id] = asyncio.ensure_future(self._job(t, int(s["segments"])))
            self._share(down)
            changed, views = [], []
            for t in self.tasks.values():  # solo le viste cambiate: niente elenco file ogni secondo per nulla
                v = t.view()
                if v != self._sent.get(t.id):
                    self._sent[t.id] = v
                    changed.append(t)
                    views.append(v)
                    self._dirty.add(t.id)
            save = []  # su disco subito se cambia stato/fase/errore/nome, l'avanzamento al massimo ogni SAVE_EVERY s
            for tid in list(self._dirty):
                t = self.tasks.get(tid)
                sig = t and (t.status, t.phase, t.error, t.name)
                if t and sig == self._saved.get(tid, (0.0, None))[1] and now - self._saved[tid][0] < SAVE_EVERY:
                    continue
                self._dirty.discard(tid)
                if t:
                    self._saved[tid] = (now, sig)
                    save.append(t)
            self.store.save(save)
            busy_now = any(t.status == RUNNING or (t.status == QUEUED and _due(t.options, self.now()))
                           for t in self.tasks.values() if not t.options.get("seeding"))
            done, idle = (0, 0), self._was_busy and not busy_now
            self._was_busy = busy_now
            if idle:
                done, self._batch = tuple(self._batch), [0, 0]
        if idle and self.on_idle and any(done):
            threading.Thread(target=self.on_idle, args=done, daemon=True, name="dl-idle").start()
        alt = alt_active(s)
        if self.events and (views or alt != self._alt_sent):
            ev = {"tasks": views}
            if alt != self._alt_sent:
                self._alt_sent, ev["settings"] = alt, self.settings()
            self.events.emit("downloads", ev)

    def _net_resume(self):
        """Task caduti per rete assente: ogni 30 s, se internet c'e' di nuovo, tornano in coda (al massimo NET_TRIES volte)."""
        if time.monotonic() - self._net_at < 30:
            return
        if not any(t.status == ERROR and t.options.get("net_err") for t in self.tasks.values()):
            return
        self._net_at = time.monotonic()

        def probe():
            try:
                socket.create_connection(("1.1.1.1", 443), 3).close()
            except OSError:
                return  # ancora offline
            with self.lock:
                for t in self.tasks.values():
                    if t.status == ERROR and t.options.get("net_err"):
                        t.options["net_err"] = t.options["net_err"] + 1
                        if t.options["net_err"] > NET_TRIES:
                            self._batch[1] += 1
                            t.options["net_err"] = False  # troppi tentativi: resta in errore, lo riprende l'utente
                            continue
                        t.status, t.error = QUEUED, ""
                        t.log("Connessione tornata: riprendo")
                        self.store.save([t])
            self._poke()
        threading.Thread(target=probe, daemon=True, name="dl-net").start()

    def _share(self, down: int):
        """Limite globale (KB/s) diviso tra i task in corso dello stesso motore con peso 2**priority, ricalcolato a ogni
        giro; il limite del singolo task vale in ogni caso. HTTP: secchiello del task; torrent: limiti per torrent di
        libtorrent (il limite della sessione resta come tetto)."""
        rates = {}
        for kind in ("http", "torrent"):
            run = [t for t in self.tasks.values() if t.type == kind and t.status == RUNNING and t.id in self._jobs
                   and (kind != "http" or t.id in self._dl_ids)]  # HTTP che risolve o aspetta il gate: niente quota
            w = sum(2 ** t.priority for t in run)
            for t in run:
                own = int((t.options.get("limit") or {}).get("down") or 0) * 1024
                rates[t.id] = min([r for r in (int(down * 1024 * 2 ** t.priority / w) if down else 0, own) if r], default=0)
                if kind == "http":
                    self._buckets.setdefault(t.id, HTTP.Bucket()).rate = rates[t.id]
        for tid, h in (self._torrent.handles.items() if self._torrent else ()):
            lim = (self.tasks[tid].options.get("limit") or {}) if tid in self.tasks else {}
            try:
                h.set_download_limit(rates.get(tid) or -1)  # -1 = nessun limite proprio
                h.set_upload_limit(int(lim.get("up") or 0) * 1024 or -1)
            except RuntimeError:  # appena tolto dalla sessione (il job lo sta chiudendo)
                pass

    def _space_gap(self, t: DownloadTask) -> int:
        """Byte che mancano per far partire `t` insieme ai task in corso sullo stesso disco (0 = bastano).
        La coda in attesa non conta: un task piu' piccolo puo' partire lo stesso."""
        run = [o for o in self.tasks.values() if o.status == RUNNING]
        drv = drive_of(t.save_path)
        d = next(x for x in queue_forecast([*run, t])["drives"] if x["drive"] == drv)
        return 0 if d["ok"] else -d["after_extract"]

    def _resolve(self, t: DownloadTask, url: str) -> str:
        """Gira in un thread. `tok` identifica questa risoluzione: se nel frattempo il task e' stato fermato o e' scaduto
        (il thread non si puo' uccidere) le sue scritture tardive sulla fase e sul task vengono scartate."""
        tok, notes = object(), []
        with self.lock:
            self._res[t.id] = (tok, notes)

        def live() -> bool:
            return self._res.get(t.id, (None,))[0] is tok

        orig = url
        url, by = resolvers.resolve(url, on_phase=lambda name: live() and self._phase(t, name), notes=notes,
                                    on_log=lambda m, lv: live() and self._log(t, m, lv))
        with self.lock:
            if live():
                t.options["resolved_by"] = by  # servizio debrid che ha sbloccato il link, "" se nessuno
                self._log(t, (f"Link finale: {url}" if url != orig else "Link diretto, nessun passaggio da fare")
                          + (f" (sbloccato da {by})" if by else ""))
        return url

    def _log(self, t: DownloadTask, msg: str, level: str = "info"):
        """Riga di registro senza le chiavi debrid salvate (un errore di rete le potrebbe riportare)."""
        for c in (self._raw()["debrid"] or {}).values():
            if isinstance(c, dict) and c.get("key"):
                msg = msg.replace(c["key"], "***")
        t.log(msg, level)

    def _phase(self, t: DownloadTask, name: str):
        """Passaggio in corso prima del download (accorciatore, pagina dell'host…): la coda lo mostra."""
        with self.lock:
            if t.id not in self.tasks or t.phase == name:
                return
            t.phase = name
            view = t.view()
        if self.events:
            self.events.emit("downloads", {"tasks": [view]})

    def _completed(self, t: DownloadTask):
        """Torrent finito che resta a condividere: completato per la coda (non occupa piu' un posto)."""
        with self.lock:
            t.status, t.speed, t.finished, t.error = COMPLETED, 0.0, time.time(), ""
            t.options["seeding"] = True
            t.log(f"Completato ({mb(t.size)}): resto a condividere")
            self.store.save([t])
        self._poke()

    async def _gate(self, t: DownloadTask):
        """Link risolto: aspetta un posto per scaricare. Lo assegna il tick (per priorita') mettendo il task in _dl_ids;
        un annullamento qui arriva come CancelledError e il posto, se gia' dato, lo libera _job."""
        fut = self._gates[t.id] = asyncio.get_running_loop().create_future()
        self._phase(t, "In attesa di un posto libero")  # la sovrascrive _fetch appena parte
        self._poke()
        try:
            await fut
        finally:
            self._gates.pop(t.id, None)

    async def _job(self, t: DownloadTask, segments: int):
        net = False
        try:
            if t.type == "torrent":
                await TOR.run(t, self._torrent, self._client, lambda: self._completed(t))
            else:
                await HTTP.run(t, self._client, self._buckets.setdefault(t.id, HTTP.Bucket()), segments,
                               lambda u: self._resolve(t, u), gate=lambda: self._gate(t))
            end = (COMPLETED, "")
        except asyncio.CancelledError:
            end = None  # pausa/annulla/chiusura: lo stato lo ha gia' messo chi ha chiesto
        except (httpx.HTTPError, OSError, ValueError, RuntimeError) as e:  # RuntimeError: libtorrent
            net = isinstance(e, (httpx.TransportError, ConnectionError, socket.timeout)) and t.type == "http"
            end = (ERROR,f"{type(e).__name__}: {e}" if not str(e) else str(e))
            notes = self._res.get(t.id, (0, []))[1]
            if t.phase and notes:  # fallito prima del download: porta con se' perche' i risolutori non hanno risolto
                end = (ERROR, f"{end[1]} ({'; '.join(notes)})")
            self._log(t, f"Errore: {end[1]}", "error")
        with self.lock:
            self._res.pop(t.id, None)  # un thread del risolutore ancora vivo non scrive piu' sul task
            self._jobs.pop(t.id, None)
            self._dl_ids.discard(t.id)  # posto liberato: il tick lo da' al prossimo
            self._buckets.pop(t.id, None)
            if t.options.pop("seeding", None):
                end = None  # gia' completato: un errore durante la condivisione non lo rovina
                t.log("Condivisione terminata")
            if end and t.id in self.tasks:
                if not (net and (t.options.get("net_err") or 0) < NET_TRIES):  # un errore di rete che si ritenta non e' un fallimento
                    self._batch[end[0] == ERROR] += 1
                # net_err = n. di riprese automatiche gia' fatte; False = non si riprende da sola
                t.options["net_err"] = (t.options.get("net_err") or 1) if net else False
                t.status, t.error = end
                t.speed = 0.0
                t.finished = time.time() if end[0] == COMPLETED else 0.0
                if end[0] == COMPLETED:
                    t.log(f"Completato: {t.name} ({mb(t.size)})")
            if t.id in self.tasks:
                self.store.save([t])
            self._last.pop(t.id, None)
            post = bool(self.on_completed and t.status == COMPLETED and t.id in self.tasks
                        and not t.options.get("post_done") and not t.options.get("seeding"))
            if post:
                t.options["post_done"] = True  # una volta sola, anche se la pausa di una condivisione rifa' finire il job
        self._poke()  # l'evento lo manda il tick
        if post:
            threading.Thread(target=self.on_completed, args=(t,), daemon=True, name="dl-finish").start()
