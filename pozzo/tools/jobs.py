"""Un lavoro alla volta per tutti gli strumenti: controllo spazio prima di partire, progresso, annulla.
Modello: routes/switch2.py (dict in memoria + Event + thread), ma generico."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import space


@dataclass
class Tool:
    id: str
    name: str
    applies: Callable[[str, Path], bool]  # (id piattaforma, file) -> utilizzabile su questo gioco
    estimate: Callable[[Path, dict], int]  # (src, options) -> byte che il risultato occuperà (vedi space.need)
    run: Callable[..., "Path | dict"]     # (src, dst_dir, progress(d), cancel(Event), options) -> file prodotto, o dict
    #                                       di informazioni (verifica...) che non sostituisce nessun file
    binary: str = ""                      # nome in binaries.py se serve un programma esterno
    needs_game: bool = True               # False: lavora su un disco/drive, non su un file della libreria


TOOLS: dict[str, Tool] = {}
JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


class Busy(RuntimeError):
    pass


def register(t: Tool):
    TOOLS[t.id] = t


def available(platform_id: str, path) -> list[str]:
    return [t.id for t in TOOLS.values() if t.applies(platform_id, Path(path))]


def public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _size(p, t: Tool):
    try:
        return space.tree_size(Path(p)) if t.needs_game else None
    except OSError:
        return None


def start(tool_id: str, src, dst_dir=None, options: dict | None = None, platform: str = "") -> dict:
    """Controlla lo spazio SUBITO (NoSpace) e avvia il thread. Busy se un altro lavoro è in corso."""
    t, src, options = TOOLS[tool_id], Path(src) if src else Path(), dict(options or {})
    dst = Path(dst_dir) if dst_dir else src.parent
    space.check(t.estimate(src, options), dst)
    if not _LOCK.acquire(blocking=False):
        raise Busy("un altro strumento è già al lavoro")
    job = {"id": uuid.uuid4().hex[:12], "tool": tool_id, "src": str(src), "platform": platform, "status": "running", "pct": 0,
           "out": None, "result": None, "size_src": _size(src, t), "size_out": None, "error": None, "_cancel": threading.Event()}
    JOBS[job["id"]] = job

    def work():
        try:
            out = t.run(src, dst, lambda d: job.update(pct=int(d)), job["_cancel"], options)
            job.update(status="done", pct=100, **({"result": out} if isinstance(out, dict) else
                                                  {"out": str(out), "size_out": _size(out, t)}))
        except InterruptedError:
            job.update(status="cancelled")
        except Exception as e:  # il messaggio arriva alla UI; il lock viene sempre rilasciato
            job.update(status="error", error=str(e))
        finally:
            _LOCK.release()

    threading.Thread(target=work, daemon=True).start()
    return public(job)


def cancel(jid: str) -> bool:
    j = JOBS.get(jid)
    if j and j["status"] == "running":
        j["_cancel"].set()
        return True
    return False
