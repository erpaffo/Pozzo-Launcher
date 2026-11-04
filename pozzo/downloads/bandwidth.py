"""Storico della banda: byte scaricati per minuto e per host, nella stessa downloads.db dello Store."""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

FLUSH_EVERY = 30  # secondi tra due scritture su disco
KEEP_DAYS = 90
MINUTE = 60
DAY = 86400
UPSERT = "INSERT INTO bw(ts,host,bytes) VALUES(?,?,?) ON CONFLICT(ts,host) DO UPDATE SET bytes=bytes+excluded.bytes"


class _Meter:
    def __init__(self):
        self.lock = threading.Lock()  # pending, last_flush
        self.io = threading.Lock()  # connessione e scritture sul DB
        self.pending: dict[tuple[int, str], int] = {}  # (minuto, host) -> byte non ancora scritti
        self.folder: Path | None = None
        self.db: sqlite3.Connection | None = None
        self.last_flush = 0.0
        self.last_prune = 0.0


_m = _Meter()


def _now() -> float:
    return time.time()


def configure(folder: Path):
    """Cartella dello Store (dove sta downloads.db). Prima di questa chiamata i byte restano in memoria."""
    with _m.io:
        if _m.db:
            _m.db.close()
        _m.db, _m.folder = None, Path(folder)


def _conn() -> sqlite3.Connection:
    if _m.db is None:
        if _m.folder is None:
            raise RuntimeError("bandwidth: cartella non configurata")
        _m.folder.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(_m.folder / "downloads.db", timeout=60, check_same_thread=False)
        db.execute("CREATE TABLE IF NOT EXISTS bw(ts INTEGER, host TEXT, bytes INTEGER, PRIMARY KEY(ts,host))")
        _m.db = db
    return _m.db


def record(host: str, nbytes: int):
    """Chiamata dal ciclo dei download: somma i byte nel minuto corrente; scrive ogni ~30 s o al cambio minuto."""
    if nbytes <= 0:
        return
    now = _now()
    bucket = int(now) // MINUTE * MINUTE
    with _m.lock:
        key = (bucket, host or "?")
        _m.pending[key] = _m.pending.get(key, 0) + int(nbytes)
        due = now - _m.last_flush >= FLUSH_EVERY or any(ts < bucket for ts, _ in _m.pending)
    if due:
        flush(now)


def flush(now: float | None = None):
    """Scrive su disco i byte in memoria. Se la scrittura fallisce, restano in memoria per il giro dopo."""
    now = _now() if now is None else now
    with _m.lock:
        batch, _m.pending = _m.pending, {}
        _m.last_flush = now
    with _m.io:
        try:
            db = _conn()
            if batch:
                with db:
                    db.executemany(UPSERT, [(ts, h, b) for (ts, h), b in batch.items()])
        except Exception:  # noqa: BLE001 - il download non deve cadere per uno storico: riprova al giro dopo
            with _m.lock:
                for k, b in batch.items():
                    _m.pending[k] = _m.pending.get(k, 0) + b
            return
        if batch and now - _m.last_prune >= DAY:
            try:
                with db:
                    db.execute("DELETE FROM bw WHERE ts < ?", (int(now) - KEEP_DAYS * DAY,))
                _m.last_prune = now
            except sqlite3.Error:
                pass


def _read(since: int, hour_start: int) -> tuple[Counter, Counter, Counter]:
    """Byte per minuto (da `since`), per host in tutto e per host negli ultimi 30 giorni, dal DB."""
    minutes, hosts30, hosts = Counter(), Counter(), Counter()
    try:
        with _m.io:
            db = _conn()
            for ts, b in db.execute("SELECT ts, SUM(bytes) FROM bw WHERE ts>=? GROUP BY ts", (since,)):
                minutes[ts] += b or 0
            for h, tot, b30 in db.execute(
                    "SELECT host, SUM(bytes), SUM(CASE WHEN ts>=? THEN bytes ELSE 0 END) FROM bw GROUP BY host", (since,)):
                hosts[h] += tot or 0
                hosts30[h] += b30 or 0
    except (sqlite3.Error, RuntimeError, OSError):  # nessun DB ancora: si mostra solo quello in memoria
        pass
    return minutes, hosts30, hosts


def stats(now: float | None = None) -> dict:
    """Storico per la UI: ultima ora per minuto, ultimi 30 giorni per giorno, host, totale. Include i byte non ancora scritti."""
    now = _now() if now is None else now
    cur = int(now) // MINUTE * MINUTE
    hour_start = cur - 59 * MINUTE
    days = [date.fromtimestamp(now) - timedelta(days=i) for i in range(29, -1, -1)]
    since = int(datetime.combine(days[0], datetime.min.time()).timestamp())  # mezzanotte locale del primo giorno

    minutes, hosts30, hosts = _read(since, hour_start)
    with _m.lock:
        pend = dict(_m.pending)
    for (ts, h), b in pend.items():  # in memoria: stesso conteggio del DB dopo la scrittura
        if ts >= since:
            minutes[ts] += b
            hosts30[h] += b
        hosts[h] += b

    per_day = Counter()
    for ts, b in minutes.items():
        if ts >= since:
            per_day[date.fromtimestamp(ts)] += b
    per_host = sorted((h for h in hosts if hosts[h] > 0), key=lambda h: (-hosts[h], h))

    last_hour = []
    for t in range(hour_start, cur + 1, MINUTE):
        b = minutes.get(t, 0)
        last_hour.append({"t": t, "bytes": b, "bps": b / MINUTE})
    return {
        "last_hour": last_hour,
        "per_day": [{"day": d.isoformat(), "bytes": per_day.get(d, 0)} for d in days],
        "per_host": [{"host": h, "bytes_total": hosts[h], "bytes_30d": hosts30[h]} for h in per_host],
        "total_bytes": sum(hosts.values()),
    }
