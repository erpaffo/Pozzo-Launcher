"""Il task di download, uguale per HTTP e torrent: e' l'unica forma che vede l'interfaccia."""
from __future__ import annotations

import copy
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import storekind
from ..gametdb import title_key

QUEUED, RUNNING, PAUSED, COMPLETED, ERROR = "queued", "running", "paused", "completed", "error"
KIND_OF = {"game": "base", "update": "update", "dlc": "dlc", "extra": "altro", "app": "altro"}  # storekind -> kind della coda
_ARCHIVE = re.compile(r"\.(zip|rar|7z|iso|exe|nsp|xci|pkg|torrent)$", re.I)
ACTIVE = (QUEUED, RUNNING)

STAGES = (("download", "Scarico"), ("extract", "Estrazione"), ("library", "Inserimento in libreria"), ("data", "Dati e copertina"))
_PACKED = re.compile(r"\.(zip|rar|7z|[rz]\d{2,}|\d{3,})(\?|$)", re.I)
LIBRARY_S, DATA_S, RATE_DEFAULT = 20, 20, 40 * 1048576  # secondi stimati; byte/s di estrazione senza storia
RATE_FILE = None  # Path del json delle ultime estrazioni (lo imposta il Manager); None = solo in memoria
_RATES: list[float] = []


def extract_rate() -> float:
    """Byte/s medi delle ultime estrazioni."""
    if not _RATES and RATE_FILE:
        try:
            _RATES.extend(float(x) for x in json.loads(Path(RATE_FILE).read_text("utf-8")))
        except (OSError, ValueError, TypeError):
            pass
    return sum(_RATES) / len(_RATES) if _RATES else RATE_DEFAULT


def record_extract(nbytes: int, secs: float) -> None:
    if nbytes <= 0 or secs < 0.5:  # troppo corta per essere una misura
        return
    extract_rate()  # carica la storia
    _RATES[:] = [*_RATES, nbytes / secs][-5:]
    if RATE_FILE:
        try:
            Path(RATE_FILE).write_text(json.dumps(_RATES), "utf-8")
        except OSError:
            pass


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
    kind: str = ""  # base | update | dlc | altro: calcolato da classify() (vale per le viste e il salvataggio)
    group: str = ""  # chiave del gioco base: uguale per gioco, aggiornamenti e DLC dello stesso gioco
    group_title: str = ""  # titolo leggibile del gioco base
    stages: list = field(default_factory=list)  # [{id,label,state,pct}]: scarico, estrazione, libreria, dati (vedi STAGES)

    def _stage(self, sid: str) -> dict:
        if not self.stages:  # costruiti al primo uso: i task salvati prima di questa versione ne sono privi
            self.stages = [{"id": i, "label": l, "state": "todo", "pct": 0} for i, l in STAGES]
            if self.status == COMPLETED and self.options.get("post_done"):  # task vecchio gia' passato in libreria
                for s in self.stages:
                    s["state"], s["pct"] = ("skip" if s["state"] == "skip" else "done"), 100
        return next(s for s in self.stages if s["id"] == sid)

    def set_stage(self, sid: str, state: str, pct: int | None = None, note: str = "") -> None:
        s = self._stage(sid)
        s["state"], s["pct"] = state, (100 if state == "done" else 0 if pct is None else max(0, min(int(pct), 100)))
        s.pop("note", None)
        if note:  # attesa di qualcosa di esterno (setup, scansione): la UI mostra la nota al posto della percentuale
            s["note"] = note

    def fail_stage(self) -> None:
        """Il passaggio in corso (o il primo da fare) e' fallito."""
        self._stage("download")
        s = next((s for s in self.stages if s["state"] in ("active", "todo")), None)
        if s:
            s["state"] = "error"

    @property
    def ready(self) -> bool:
        return self._stage("library")["state"] == "done"

    @property
    def ready_eta(self) -> float | None:
        """Quando il gioco sara' giocabile (epoch), None se non si sa o e' gia' pronto."""
        if self.ready or self.status in (ERROR, PAUSED) or any(s["state"] == "error" for s in self.stages):
            return None
        st = {s["id"]: s for s in self.stages}
        left = 0.0
        if st["download"]["state"] != "done":
            if self.eta is None:
                return None
            left += self.eta
        if st["extract"]["state"] in ("todo", "active"):
            left += (self.size or 0) / extract_rate() * (100 - st["extract"]["pct"]) / 100
        left += LIBRARY_S * (st["library"]["state"] != "done") + DATA_S * (st["data"]["state"] != "done")
        return time.time() + left

    def _title(self) -> str:
        """Il nome del file se c'e' (lo mette l'engine a link risolto), altrimenti quello del link o della magnet."""
        if self.name:
            return self.name
        if self.source.lower().startswith("magnet:"):
            raw = parse_qs(urlparse(self.source).query).get("dn", [""])[0]
        else:
            raw = unquote(re.split(r"[\\/]", urlparse(self.source).path)[-1])
        return _ARCHIVE.sub("", raw)

    def classify(self) -> None:
        """Tipo e gruppo dal titolo. Una DLC («Gioco DLC Pack») si riporta al gioco tagliando la parola chiave."""
        title = self._title()
        self.kind = KIND_OF[storekind.content_kind(title)]
        base = storekind.update_base(title)
        if self.kind in ("dlc", "altro"):
            for rx in (storekind.DLC, storekind.EXTRA):
                m = rx.search(base)
                if m:
                    base = base[:m.start()]
                    break
        base = base.strip(" -–—:.")
        self.group, self.group_title = (title_key(base), base) if base else ("", "")

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
        self.classify()  # nome e link cambiano nel tempo: il gruppo segue l'ultimo titolo
        x = self._stage("extract")  # il nome si sa a link risolto: un file che non e' un archivio non si estrae
        if x["state"] == "todo" and self.name and self.type != "torrent" and not _PACKED.search(self.name):
            x["state"] = "skip"
        d = self._stage("download")  # lo scarico segue il trasferimento
        if self.status == COMPLETED:
            d["state"], d["pct"] = "done", 100
        elif d["state"] != "error":
            d["state"], d["pct"] = ("active" if self.done or self.status == RUNNING else "todo"), int(self.progress * 100)
        return {**{f.name: getattr(self, f.name) for f in fields(self)}, "stages": copy.deepcopy(self.stages), "options": copy.deepcopy(self.options.copy()), "logs": list(self.logs)}

    def view(self) -> dict:
        d = self.data()
        d.update(progress=self.progress, eta=self.eta, ready=self.ready, ready_eta=self.ready_eta)
        del d["logs"]  # il registro si legge a parte (/log?after=): niente righe a ogni tick
        d["options"] = {k: v for k, v in d["options"].items() if k not in ("segs", "headers", "priorities")}  # interni (le priorita' sono gia' in files)
        if d["options"].get("wanted") and d["options"].get("files"):  # gioco scelto da un set: gli altri file non si mostrano
            d["options"]["files"] = [f for f in d["options"]["files"] if f["priority"]]
            d["options"]["files_locked"] = True
        return d
