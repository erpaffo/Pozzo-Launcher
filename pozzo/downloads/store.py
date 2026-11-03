"""Download su disco (SQLite): alla riapertura del launcher la coda riprende da dove era."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .task import LOG_SAVED, DownloadTask


class Store:
    def __init__(self, folder: Path):
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(folder) / "downloads.db", timeout=60, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY, data TEXT)")
        self.lock = threading.Lock()

    def save(self, tasks: list[DownloadTask]):
        with self.lock, self.db:
            self.db.executemany("INSERT OR REPLACE INTO downloads VALUES(?,?)",
                                [(t.id, json.dumps({**d, "logs": d["logs"][-LOG_SAVED:]}, ensure_ascii=False)) for t in tasks for d in (t.data(),)])

    def delete(self, tid: str):
        with self.lock, self.db:
            self.db.execute("DELETE FROM downloads WHERE id=?", (tid,))

    def load(self) -> list[DownloadTask]:
        with self.lock:
            rows = self.db.execute("SELECT data FROM downloads").fetchall()
        out = []
        for (raw,) in rows:
            try:
                out.append(DownloadTask(**json.loads(raw)))
            except (TypeError, ValueError):  # riga di una versione futura/rovinata: non blocca l'avvio
                continue
        return out
