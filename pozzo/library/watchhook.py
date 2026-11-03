"""Collegamento del watcher delle cartelle ROM (library/watcher.py) alla libreria.

Il watcher dice «in questa cartella console sono comparsi questi file»; qui si mettono in libreria con l'aggiunta rapida
(library.incremental, la stessa dei download: solo la riga del gioco, nessuna ricostruzione) e parte la ricerca dei
dati. Durante una partita il lavoro e' piano: priorita' di fondo per disco e CPU del thread (su HDD non deve rubare il
disco al gioco) e la ricerca dei dati aspetta la fine della partita.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .. import platforms as P

_BACKGROUND_BEGIN, _BACKGROUND_END = 0x00010000, 0x00020000  # THREAD_MODE_BACKGROUND_*


def enabled(cfg) -> bool:
    """Impostazione `watch_roms` ({"enabled": bool, ...}): acceso se non e' stata mai toccata."""
    from .watcher import settings_of
    return settings_of(cfg)["enabled"]


@contextmanager
def background_mode(on: bool):
    """Windows: il thread chiamante lavora con priorita' di fondo (CPU e I/O) finche' dura il blocco. Altrove non fa nulla."""
    if not on or sys.platform != "win32":
        yield
        return
    import ctypes
    k = ctypes.windll.kernel32
    h = k.GetCurrentThread()
    ok = bool(k.SetThreadPriority(h, _BACKGROUND_BEGIN))
    try:
        yield
    finally:
        if ok:
            k.SetThreadPriority(h, _BACKGROUND_END)


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


class Hook:
    """Le funzioni da dare a RomWatcher. `scan(body)` = api_scan_start (HTTPException 409 se un lavoro e' in corso),
    `busy()` = libreria in ricostruzione o ricerca in corso, `playing()` = una partita e' in corso."""

    def __init__(self, cfg, lib, events, scan, busy, playing, log=lambda msg: None):
        self.cfg, self.lib, self.events, self.scan, self.busy, self.playing, self.log = cfg, lib, events, scan, busy, playing, log
        self._queue: list[int] = []  # giochi nuovi in attesa della ricerca dei dati
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def known(self, pid: str) -> set[str]:
        """Percorsi dei giochi gia' in libreria (file, o cartella per le console a cartella): non si riportano."""
        with self.lib.lock:
            return {_norm(f) for g in self.lib.games if g["platform"] == pid and not g.get("store") for f in g["files"]}

    def on_new(self, pid: str, paths: list[Path], low: bool = False) -> None:
        from . import incremental
        with background_mode(low):
            keys = incremental.add_games(self.cfg, pid, paths)
            if keys:
                self.lib.add_games(keys)
        if not keys:
            return  # libreria non ancora costruita o fuori da una cartella console: ci pensa la scansione normale
        with self.lib.lock:
            games = [g for k in keys if (g := self.lib.by_key.get(k))]
        if not games:
            return
        plat = P.PLATFORMS.get(pid)
        self.events.emit("library_watch", {"platform": plat.name if plat else pid, "count": len(games),
                                           "titles": [g["title"] for g in games]})
        self.log(f"{len(games)} giochi nuovi in {pid}: " + ", ".join(g["title"] for g in games[:5]))
        with self._lock:
            self._queue += [g["id"] for g in games]
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._search, daemon=True, name="rom-watcher-search")
                self._worker.start()

    def _search(self, poll: float = 5.0, give_up: float = 3600.0) -> None:
        """Ricerca di dati e copertina, un gioco alla volta: aspetta che non ci sia un lavoro in corso ne' una partita
        (shortcut: sondaggio ogni `poll` s, niente coda persistente: se l'app si chiude i dati arrivano alla ricerca dopo)."""
        t0 = time.time()
        while time.time() - t0 < give_up:
            with self._lock:
                if not self._queue:
                    self._worker = None
                    return
                gid = self._queue[0]
            if self.playing() or self.busy():
                time.sleep(poll)
                continue
            try:
                self.scan({"game": gid})
            except Exception as e:  # noqa: BLE001 - 409: un lavoro e' partito nel frattempo, si riprova
                if getattr(e, "status_code", 0) == 409:
                    time.sleep(poll)
                    continue
                self.log(f"ricerca dati non partita: {type(e).__name__}: {e}")
            with self._lock:
                self._queue.pop(0)
            time.sleep(1)  # il lavoro appena partito risulta gia' in corso al giro dopo
        with self._lock:
            self._queue.clear()
            self._worker = None
