"""Il task di download, uguale per HTTP e torrent: e' l'unica forma che vede l'interfaccia."""
from __future__ import annotations

import copy
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, fields

QUEUED, RUNNING, PAUSED, COMPLETED, ERROR = "queued", "running", "paused", "completed", "error"
ACTIVE = (QUEUED, RUNNING)

LOG_MAX, LOG_SAVED = 500, 200  # righe tenute in memoria / su disco per task
_LOG_LOCK = threading.Lock()  # i log arrivano dal ciclo, dai thread dei risolutori e dalle rotte
_URL = re.compile(r"(https?://[^\s?#'\"<>]+|magnet:)[?#]\S*")  # niente query: token, chiavi, passkey dei tracker
_AUTH = re.compile(r"(?i)(https?://)[^/@\s]+@|bearer\s+\S+|\b(?:api_?key|token|passkey|password)=[^\s&'\"]+")


def mb(n) -> str:
    return f"{(n or 0) / 1048576:.1f} MB"


def redact(msg: str) -> str:
    return _URL.sub(lambda m: m[1] + "?…", _AUTH.sub(lambda m: (m[1] or "") + "***", msg))


@dataclass
class DownloadTask:
    source: str
    save_path: str
    type: str = "http"  # http | torrent
    name: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = QUEUED
    size: int = 0
    done: int = 0
    speed: float = 0.0  # byte/s, media mobile calcolata dal manager
    priority: int = 0  # -2 bassa .. 2 massima: ordine in coda e quota di banda (peso 2**priority)
    category: str = ""
    error: str = ""
    phase: str = ""  # passaggio prima del download: «Salto la pubblicità», «Cerco il file su …»
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    options: dict = field(default_factory=dict)  # headers, segmenti HTTP (per riprendere), file torrent, game_id, ...
    logs: list = field(default_factory=list)  # ultime LOG_MAX righe {t, level, msg}; la vista porta solo log_n
    log_n: int = 0  # righe scritte in tutto (anche quelle scartate): l'indice assoluto della prossima

    @property
    def progress(self) -> float:
        return min(self.done / self.size, 1.0) if self.size else 0.0

    @property
    def eta(self) -> int | None:
        return int((self.size - self.done) / self.speed) if self.size and self.speed > 1 else None

    def log(self, msg, level: str = "info") -> None:
        """Una riga nel registro del download (thread-safe). Link senza query, credenziali tolte."""
        line = {"t": round(time.time(), 3), "level": level, "msg": redact(str(msg))[:600]}
        with _LOG_LOCK:
            self.logs.append(line)
            self.log_n += 1
            del self.logs[:-LOG_MAX]

    def log_after(self, after: int = 0) -> tuple[list, int]:
        """Righe con indice assoluto >= after e il totale scritto finora."""
        with _LOG_LOCK:
            return self.logs[max(after - (self.log_n - len(self.logs)), 0):], self.log_n

    def log_clear(self) -> None:
        with _LOG_LOCK:
            self.logs.clear()  # log_n resta: i client che chiedono ?after=<n> non rivedono nulla

    def data(self) -> dict:
        """Copia completa. Il ciclo dei download modifica options mentre le rotte leggono: copy() e' atomica (GIL),
        asdict iterava il dict vivo («dictionary changed size during iteration»)."""
        return {**{f.name: getattr(self, f.name) for f in fields(self)}, "options": copy.deepcopy(self.options.copy()), "logs": list(self.logs)}

    def view(self) -> dict:
        d = self.data()
        d.update(progress=self.progress, eta=self.eta)
        del d["logs"]  # il registro si legge a parte (/log?after=): niente righe a ogni tick
        d["options"] = {k: v for k, v in d["options"].items() if k not in ("segs", "headers", "priorities")}  # interni (le priorita' sono gia' in files)
        if d["options"].get("wanted") and d["options"].get("files"):  # gioco scelto da un set: gli altri file non si mostrano
            d["options"]["files"] = [f for f in d["options"]["files"] if f["priority"]]
            d["options"]["files_locked"] = True
        return d
