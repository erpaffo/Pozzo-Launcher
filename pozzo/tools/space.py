"""Controllo dello spazio PRIMA di un lavoro lungo: meglio rifiutare subito che fermarsi a meta' col disco pieno."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class NoSpace(OSError):
    pass


def tree_size(p: Path) -> int:
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _gb(n: int) -> str:
    return f"{n / 2**30:.1f} GB"


def _existing(p: Path) -> Path:
    p = Path(p)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def need(estimate: int) -> int:
    """Byte da avere liberi: stima + margine (10%, minimo 256 MB) per file temporanei e altri processi."""
    return estimate + max(estimate // 10, 256 * 2**20)


def check(estimate: int, *dirs: Path):
    """Solleva NoSpace se in una delle cartelle (es. destinazione e temporanea) non c'e' posto.
    Se due cartelle stanno sullo stesso volume i fabbisogni si sommano."""
    per_vol: dict[int, list] = {}
    for d in dirs:
        e = _existing(d)
        per_vol.setdefault(os.stat(e).st_dev, [e, 0])[1] += 1
    for e, n in per_vol.values():
        want, free = need(estimate) * n, shutil.disk_usage(e).free
        if free < want:
            raise NoSpace(f"Spazio insufficiente su {e}: servono {_gb(want)}, liberi {_gb(free)}")
