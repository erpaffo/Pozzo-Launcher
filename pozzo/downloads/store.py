"""Download su disco (SQLite): alla riapertura del launcher la coda riprende da dove era."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .task import LOG_SAVED, DownloadTask


class Store:
    def __init__(self, folder: Path):
        Path(folder).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(Path(folder) / "downloads.db", timeout=60, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS downloads(id TEXT PRIMARY KEY, data TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS rss_seen(feed TEXT, item TEXT, ts REAL, PRIMARY KEY(feed, item))")
        self.lock = threading.Lock()

    def rss_seen(self, feed: str, ids: list[str]) -> set[str]:
        """Quali `ids` del feed sono gia' stati visti (per non accodarli due volte)."""
        with self.lock:
            return {r[0] for i in range(0, len(ids), 500) for r in self.db.execute(
                f"SELECT item FROM rss_seen WHERE feed=? AND item IN ({','.join('?' * len(ids[i:i + 500]))})", [feed, *ids[i:i + 500]])}

    def rss_mark(self, feed: str, ids: list[str], keep: int = 5000):
        with self.lock, self.db:
            self.db.executemany("INSERT OR IGNORE INTO rss_seen VALUES(?,?,?)", [(feed, i, time.time()) for i in ids])
            self.db.execute("DELETE FROM rss_seen WHERE feed=? AND item NOT IN "
                            "(SELECT item FROM rss_seen WHERE feed=? ORDER BY ts DESC LIMIT ?)", (feed, feed, keep))

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
