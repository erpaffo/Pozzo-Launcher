"""Compressione WOF (Windows Overlay Filter) della cartella di un gioco PC, come CompactGUI: `compact.exe /c /s /i /exe:<algo>`.

La stima viene dal database della comunita' di CompactGUI (risparmio medio misurato per gioco), in cache 7 giorni."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import urllib.request

from .. import matching as M

DB_URL = "https://raw.githubusercontent.com/IridiumIO/CompactGUI/database/database.json"
DB_TTL = 7 * 86400
ALGOS = ("xpress4k", "xpress8k", "xpress16k", "lzx")  # stesso ordine di CompType nel database (0..3)
DEFAULT_ALGO = "xpress8k"
_FILE_LINE = re.compile(r"\[[^\]]+\]\s*$")  # `compact /i` stampa una riga per file che finisce con [OK] o [Errore...]


def supported() -> bool:
    return sys.platform == "win32"


def build_cmd(algo: str = DEFAULT_ALGO, uncompress: bool = False) -> list[str]:
    """Argomenti di compact.exe; si esegue con cwd = cartella del gioco (/s = sottocartelle comprese)."""
    if uncompress:
        return ["compact", "/u", "/s", "/i", "/exe"]
    if algo not in ALGOS:
        raise ValueError(algo)
    return ["compact", "/c", "/s", "/i", f"/exe:{algo}"]


def has_dstorage(folder) -> bool:
    """DirectStorage legge i file in modo diretto: su file compressi il gioco puo' non partire."""
    return any(f.lower() == "dstorage.dll" for _, _, files in os.walk(folder) for f in files)


def is_file_line(line: str) -> bool:
    return bool(_FILE_LINE.search(line))


def count_files(folder) -> int:
    return sum(len(f) for _, _, f in os.walk(folder))


# ------------------------------------------------------------ stima dal database CompactGUI
def build_index(raw: list) -> dict:
    """{titolo normalizzato: {"n": nome, "r": [rapporto dopo/prima per ciascun algoritmo, None = nessun dato]}}."""
    out = {}
    for e in raw:
        r = [None] * len(ALGOS)
        for c in e.get("CompressionResults") or []:
            if 0 <= c.get("CompType", -1) < len(ALGOS) and c.get("BeforeBytes"):
                r[c["CompType"]] = c["AfterBytes"] / c["BeforeBytes"]
        if any(x is not None for x in r):
            for name in (e.get("GameName"), e.get("FolderName")):
                if name and M.normalize(name):
                    out.setdefault(M.normalize(name), {"n": e.get("GameName") or name, "r": r})
    return out


def _download() -> list:
    req = urllib.request.Request(DB_URL, headers={"User-Agent": "Pozzo"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def load_index(cache, fetch=_download) -> dict:
    hit = cache.kv_get("wof:db", DB_TTL)
    if hit is not None:
        return hit
    idx = build_index(fetch())
    cache.kv_set("wof:db", idx)
    return idx


def estimate(title: str, size: int, index: dict) -> dict | None:
    """{"name", "savings": {algo: byte risparmiati}, "best": algo} oppure None se il gioco non e' nel database."""
    hit = index.get(M.normalize(title))
    if not hit:
        n, _ = M.best(title, list(index), min_score=92)
        hit = index.get(n) if n else None
    if not hit:
        return None
    sav = {a: round(size * (1 - r)) for a, r in zip(ALGOS, hit["r"]) if r is not None}
    return {"name": hit["n"], "savings": sav, "best": max(sav, key=sav.get)}


# ------------------------------------------------------------ esecuzione
class Job:
    """compact.exe in un thread: `done`/`total` = file elaborati / file totali, cancel() lo interrompe."""

    def __init__(self, folder, algo: str = DEFAULT_ALGO, uncompress: bool = False):
        self.folder, self.cmd = str(folder), build_cmd(algo, uncompress)
        self.status, self.done, self.total, self.error = "running", 0, 0, ""
        self._proc: subprocess.Popen | None = None
        self._cancel = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.total = count_files(self.folder)
            self._proc = subprocess.Popen(self.cmd, cwd=self.folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          text=True, encoding="oem", errors="replace",
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in self._proc.stdout:
                if is_file_line(line):
                    self.done += 1
            rc = self._proc.wait()
            self.status = "cancelled" if self._cancel else "done" if rc == 0 else "error"
            if self.status == "error":
                self.error = f"compact.exe: {rc}"
        except Exception as e:
            self.status, self.error = "error", str(e)

    def cancel(self):
        self._cancel = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def state(self) -> dict:
        return {"status": self.status, "done": self.done, "total": self.total, "error": self.error}
