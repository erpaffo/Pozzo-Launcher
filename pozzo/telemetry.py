"""Registro locale degli errori: ultimi 50 in memoria + append su errors.log. Nessun invio: l'utente esporta a mano."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path

MAX_ERRORS = 50
_lock = threading.Lock()
_buf: deque[dict] = deque(maxlen=MAX_ERRORS)
_path: Path | None = None  # impostato da set_path(); senza, il registro resta solo in memoria
_USER = re.compile(r"""(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/(?:home|Users)/)[^\\/\s"']+""")  # copre anche i percorsi dentro JSON (\\)


def set_path(path: str | os.PathLike | None) -> None:
    global _path
    _path = Path(path) if path else None


def mask(text: str) -> str:
    """Sostituisce la cartella utente (C:\\Users\\nome, /home/nome, /Users/nome) con ~."""
    return _USER.sub("~", text)


def log_error(module: str, message: str, traceback_str: str = "") -> dict:
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "module": module, "message": message, "traceback": traceback_str}
    with _lock:
        _buf.append(entry)
        if _path:
            try:
                _path.parent.mkdir(parents=True, exist_ok=True)
                with open(_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass  # il registro non deve mai far cadere l'app
    return entry


def recent() -> list[dict]:
    with _lock:
        return list(_buf)


def clear() -> None:
    with _lock:
        _buf.clear()
        if _path:
            try:
                _path.write_text("", encoding="utf-8")
            except OSError:
                pass


def export_report() -> str:
    """Testo pronto da incollare in una segnalazione, con i percorsi utente mascherati."""
    return mask(json.dumps(recent(), ensure_ascii=False, indent=2))
