"""Sorveglia le cartelle console: una ROM copiata dentro viene notata e passata a on_new (di solito add_games).

Polling leggero (solo os.scandir/stat: niente hash, niente lettura dei file, niente watchdog). Prima si guarda la data
delle sole cartelle: se nessuna e' cambiata la console non si rilegge (costo trascurabile anche con migliaia di ROM su
HDD). Una cartella cambiata diventa "in attesa" e si elabora solo quando la sua firma resta identica per `debounce`
secondi (file ancora in copia = dimensione che cresce = si aspetta). Una cartella alla volta, mai in parallelo.

Timidezza durante una partita (`low`): un passaggio ogni `low_interval`, una sola cartella per passaggio e solo
file leggeri (<= LIGHT_MAX, la soglia dello scanner): i grandi aspettano la fine della partita, perche' aggiungerli
vuol dire leggerli dal disco per l'impronta.

Impostazioni (cfg.app["watch_roms"]): {"enabled": bool, "poll": s, "debounce": s}; si rileggono a ogni passaggio, quindi
si cambiano a caldo. Le cancellazioni si notano ma NON tolgono nulla dalla libreria (lo fa la scansione normale).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .. import platforms as P
from .. import switchfiles as SF
from ..scanner import LIGHT_MAX, SKIP_DIRS, _ignored, find_platform_dirs

DEFAULT_POLL = 15.0       # secondi tra due passaggi
DEFAULT_DEBOUNCE = 10.0   # secondi di cartella ferma prima dell'aggiunta
LOW_FACTOR = 6            # in partita il passaggio e' LOW_FACTOR volte piu' raro
MAX_PER_CALL = 25         # giochi passati a on_new in una volta
MAX_DEPTH = 6  # profondita' massima della scansione per le console non dir_games
FULL_EVERY = 10  # ogni quanti passaggi si rilegge tutto anche se i mtime delle cartelle non sono cambiati
MAX_BACKOFF = 600.0
# margine (s) sul confronto delle date: exFAT e condivisioni di rete arrotondano il mtime a 1-2 secondi, quindi un
# file copiato subito dopo la lettura lascerebbe la cartella con la stessa data e non verrebbe visto
MTIME_MARGIN = 2.0
_TEMP_SUFFIX = (".part", ".crdownload", ".tmp", ".!qb")

__all__ = ["RomWatcher", "settings_of", "LIGHT_MAX", "DEFAULT_POLL", "DEFAULT_DEBOUNCE"]


def _clamp(v, lo, hi, default):
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def settings_of(cfg) -> dict:
    """Impostazioni effettive: attivo di default, tempi entro limiti sensati."""
    app = getattr(cfg, "app", None)
    raw = app.get("watch_roms") if isinstance(app, dict) else None
    raw = {"enabled": raw} if isinstance(raw, bool) else raw if isinstance(raw, dict) else {}
    return {"enabled": raw.get("enabled", True) is not False,
            "poll": _clamp(raw.get("poll"), 2.0, 300.0, DEFAULT_POLL),
            "debounce": _clamp(raw.get("debounce"), 2.0, 120.0, DEFAULT_DEBOUNCE)}


def _temp(name: str) -> bool:
    n = name.lower()
    return n.endswith(_TEMP_SUFFIX) or n.startswith(".estrazione-")


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _scan(p: P.Platform, folder: Path) -> tuple[dict[str, tuple[int, int]], dict[str, int], dict[str, Path]]:
    """(voci, cartelle, percorsi originali) della console. voci: chiave normalizzata -> (mtime_ns, size); cartelle: percorso -> mtime_ns.
    Stesse regole di ignore di scanner.list_entries, ma senza leggere altro che i metadati."""
    exts = tuple("." + e for e in p.all_exts)
    entries: dict[str, tuple[int, int]] = {}
    paths: dict[str, Path] = {}
    dirs: dict[str, int] = {}

    def mt(d: Path) -> int:
        return os.stat(d).st_mtime_ns

    dirs[str(folder)] = mt(folder)
    if p.dir_games:
        found: list[tuple[Path, bool]] = []
        with os.scandir(folder) as it:
            for e in it:
                if e.is_dir():
                    if not _ignored(Path(e.path)):
                        found.append((Path(e.path), True))
                elif e.name.lower().endswith(exts) and not _temp(e.name):
                    found.append((Path(e.path), False))
        if p.id == "switch":
            found = SF.hide_companions(found)
        for path, is_dir in found:
            try:
                if not is_dir:
                    st = path.stat()
                    val = (st.st_mtime_ns, st.st_size)
                else:  # un livello: massimo mtime e dimensione totale dei figli diretti
                    dirs[str(path)] = mt(path)
                    m, s = dirs[str(path)], 0
                    with os.scandir(path) as it:
                        for c in it:
                            if c.is_file() and not _temp(c.name):
                                st = c.stat()
                                m, s = max(m, st.st_mtime_ns), s + st.st_size
                    val = (m, s)
            except OSError:
                continue  # sparito o illeggibile mentre lo guardavo: al prossimo giro
            entries[_norm(path)] = val
            paths[_norm(path)] = path
    else:
        def walk(d: Path, depth: int):
            try:
                with os.scandir(d) as it:
                    items = list(it)
            except OSError:
                return
            dirs[str(d)] = mt(d)
            for e in items:
                try:
                    if e.is_dir():
                        n = e.name
                        if depth < MAX_DEPTH and not n.startswith(".") and n.lower() not in SKIP_DIRS \
                                and not _ignored(Path(e.path)):
                            walk(Path(e.path), depth + 1)
                    elif e.name.lower().endswith(exts) and not _temp(e.name):
                        st = e.stat()
                        entries[_norm(e.path)] = (st.st_mtime_ns, st.st_size)
                        paths[_norm(e.path)] = Path(e.path)
                except OSError:
                    continue
        dirs.clear()
        walk(folder, 1)
        dirs.setdefault(str(folder), 0)
    return entries, dirs, paths


class _Folder:
    def __init__(self, p: P.Platform, path: Path):
        self.p, self.path = p, path
        self.snap: dict[str, tuple[int, int]] = {}
        self.dirs: dict[str, int] = {}
        self.paths: dict[str, Path] = {}
        self.seen: set[str] = set()  # voci gia' riportate (o presenti alla base)
        self.since: float | None = None  # inizio attesa (None = nulla in sospeso)
        self.at_ns = 0  # quando l'abbiamo letta (per MTIME_MARGIN)
        self.last_change = 0.0
        self.fails = 0
        self.retry_at = 0.0


class RomWatcher:
    """`cfg_fn()` -> cfg corrente; `on_new(platform_id, paths, low)` riceve i giochi nuovi di UNA console alla volta;
    `known(pid)` -> percorsi gia' in libreria (non si riportano); `busy()` = scansione/ricostruzione in corso;
    `low()` = partita in corso. `interval`/`low_interval`/`debounce` forzano i tempi (di norma vengono dalle impostazioni)."""

    def __init__(self, cfg_fn, on_new, *, known=lambda pid: set(), busy=lambda: False, low=lambda: False,
                 interval=None, low_interval=None, debounce=None, clock=time.monotonic, sleep=time.sleep,
                 log=lambda msg: None):
        self.cfg_fn, self.on_new, self.known, self.busy, self.low = cfg_fn, on_new, known, busy, low
        self._interval, self._low_interval, self._debounce = interval, low_interval, debounce
        self.clock, self.sleep, self.log = clock, sleep, log
        self._folders: dict[str, _Folder] = {}
        self._based = False
        self._passes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()  # protegge solo i campi letti da status()
        self._pending: list[str] = []
        self._last_scan: float | None = None
        self._added = 0
        self._errors = 0

    # ---------------------------------------------------------------- impostazioni
    def settings(self) -> dict:
        s = settings_of(self.cfg_fn())
        if self._interval is not None:
            s["poll"] = self._interval
        if self._debounce is not None:
            s["debounce"] = self._debounce
        return s

    @property
    def interval(self) -> float:
        return self.settings()["poll"]

    @property
    def low_interval(self) -> float:
        return self._low_interval if self._low_interval is not None else self.interval * LOW_FACTOR

    @property
    def debounce(self) -> float:
        return self.settings()["debounce"]

    # ---------------------------------------------------------------- thread
    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="rom-watcher", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t is not threading.current_thread():
            t.join(timeout=5)

    def status(self) -> dict:
        with self._lock:
            return {"enabled": self.settings()["enabled"],
                    "running": bool(self._thread and self._thread.is_alive()), "pending": [Path(k).name for k in self._pending],
                    "last_scan": self._last_scan, "added": self._added, "errors": self._errors}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # il thread non deve mai morire
                with self._lock:
                    self._errors += 1
                self.log(f"Watcher cartelle: {type(e).__name__}: {e}")
            try:
                wait = self.low_interval if self.low() else self.interval
            except Exception:
                wait = DEFAULT_POLL
            self._stop.wait(wait)

    # ---------------------------------------------------------------- un passaggio
    def tick(self) -> int:
        """Un passaggio di polling; ritorna quante cartelle sono state elaborate (on_new chiamato)."""
        if not self.settings()["enabled"]:
            return 0
        try:
            if self.busy():
                return 0  # scansione/build in corso: lo stato in sospeso resta com'e'
            dirs = find_platform_dirs(self.cfg_fn())
        except OSError:
            return 0  # nessuna radice raggiungibile: non e' "tutto cancellato", si riprova
        low = bool(self.low())
        self._passes += 1
        # shortcut: i mtime delle cartelle bastano a vedere un file nuovo, ma su condivisioni di rete / exFAT non
        # sempre il padre cambia: ogni FULL_EVERY passaggi si rilegge tutto comunque. Da rivedere se serve di piu'.
        full = self._passes % FULL_EVERY == 0
        first = not self._based
        done = 0
        for p, path in dirs:
            if self._stop.is_set() or (low and done):
                break
            key = str(path)
            f = self._folders.get(key)
            if f is None:
                f = self._folders[key] = _Folder(p, path)
                if first:
                    self._baseline(f)
                    continue
            if self._step(f, full, low):
                done += 1
                self.sleep(0.2)
        self._based = True
        with self._lock:
            self._last_scan = time.time()
            self._pending = [k for k, f in self._folders.items() if f.since is not None]
        return done

    def _baseline(self, f: _Folder) -> None:
        f.at_ns = time.time_ns()
        try:
            f.snap, f.dirs, f.paths = _scan(f.p, f.path)
        except OSError:
            self._folders.pop(str(f.path), None)  # irraggiungibile ora: baseline al prossimo giro (se ancora prima)
            return
        f.seen = set(f.snap)

    def _unchanged(self, f: _Folder) -> bool:
        # vale solo se la data e' vecchia abbastanza da non poter essere stata scritta dopo la nostra lettura
        limit = f.at_ns - int(MTIME_MARGIN * 1e9)
        try:
            return bool(f.dirs) and all(m <= limit and os.stat(d).st_mtime_ns == m for d, m in f.dirs.items())
        except OSError:
            return False

    def _step(self, f: _Folder, full: bool, low: bool) -> bool:
        """Controlla una cartella; True se ha chiamato on_new."""
        now = self.clock()
        if f.since is None and not full and self._unchanged(f):
            return False
        f.at_ns = time.time_ns()
        try:
            new, dirs, f.paths = _scan(f.p, f.path)
        except OSError:
            return False  # disco scollegato: si tiene lo snapshot vecchio
        changed = any(f.snap.get(k) != v for k, v in new.items())
        f.snap, f.dirs = new, dirs
        if changed:
            f.last_change = now
            if f.since is None:
                f.since = now
        if f.since is None:
            return False
        if changed or now - f.last_change < self.debounce or now < f.retry_at:
            return False
        try:
            known = {_norm(k) for k in self.known(f.p.id)}
        except Exception:
            known = set()
        todo = [k for k in f.snap if k not in f.seen and k not in known]
        if not todo:
            f.seen.update(f.snap)
            f.since = None
            return False
        if low:  # in partita solo i leggeri: aggiungerli vuol dire leggerli dal disco per l'impronta
            todo = [k for k in todo if f.snap[k][1] <= LIGHT_MAX]
            if not todo:
                return False  # i grandi restano in attesa della fine della partita
        ready = [k for k in todo if self._openable(f.paths[k])]
        if len(ready) < len(todo):
            return False  # qualche file e' ancora bloccato (copia in corso): si aspetta
        batch = ready[:MAX_PER_CALL]
        try:
            self.on_new(f.p.id, [f.paths[k] for k in batch], low)
        except Exception as e:
            f.fails += 1
            f.retry_at = now + min(self.interval * 2 ** f.fails, MAX_BACKOFF)
            with self._lock:
                self._errors += 1
            self.log(f"Watcher: aggiunta in {f.p.id} non riuscita ({type(e).__name__}: {e}), riprovo piu' tardi")
            return True
        f.fails = 0
        f.seen.update(batch)
        left = [k for k in f.snap if k not in f.seen and k not in known]
        if not left:
            f.seen.update(f.snap)
            f.since = None
        with self._lock:
            self._added += len(batch)
        return True

    @staticmethod
    def _openable(path: Path) -> bool:
        # shortcut: per le cartelle gioco non si provano i file interni; il debounce sulla dimensione totale basta
        if path.is_dir():
            return True
        try:
            with open(path, "rb"):
                return True
        except OSError:
            return False
