"""Playlist .m3u per i giochi multi-disco: cerca i fratelli "(Disc N)" / "(CD N)" nella stessa cartella."""
import os
import re
from pathlib import Path

from ..jobs import Tool, register

_DISC = re.compile(r"\s*[\(\[]\s*(?:disc|disk|cd)\s*(\d+)(?:\s*of\s*\d+)?\s*[\)\]]", re.I)


def _siblings(f: Path) -> tuple[str, list[Path]]:
    """(titolo senza tag disco, file dei dischi ordinati per numero). Vuoto se f non ha il tag."""
    m = _DISC.search(f.stem)
    if not m:
        return "", []
    title = _DISC.sub("", f.stem, count=1).strip()
    found = {}
    for c in f.parent.iterdir():
        cm = _DISC.search(c.stem)
        if c.is_file() and c.suffix.lower() == f.suffix.lower() and cm and _DISC.sub("", c.stem, count=1).strip() == title:
            found[int(cm.group(1))] = c
    return title, [found[k] for k in sorted(found)]


def _applies(pid: str, f: Path) -> bool:
    return f.is_file() and len(_siblings(f)[1]) >= 2


def _run(src, dst, progress, cancel, o):
    title, discs = _siblings(src)
    if len(discs) < 2:
        raise ValueError("servono almeno due dischi")
    out = Path(dst) / f"{title}.m3u"
    # percorsi relativi alla cartella della playlist, con "/" come vuole il formato
    lines = [Path(os.path.relpath(d, out.parent)).as_posix() for d in discs]
    with open(out, "x", encoding="utf-8", newline="\n") as fh:  # "x": mai sovrascrivere
        fh.write("\n".join(lines) + "\n")
    return {"m3u": str(out), "discs": lines}


register(Tool("m3u", "Playlist multi-disco (.m3u)", _applies, lambda s, o: 4096, _run))
