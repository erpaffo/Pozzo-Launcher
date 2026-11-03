"""Switch: dal nome del file si capisce se e' il gioco base, un aggiornamento o un DLC (e di quale gioco).

Regola dei Title ID (la stessa che usano gli emulatori): il gioco base finisce per 000, il suo aggiornamento e' lo stesso
ID piu' 0x800 (…800), i DLC stanno nel blocco successivo (…001, …002; l'ID sale di 0x1000). Il Title ID si legge dal nome
(«[0100…]» o un nome fatto solo dall'ID); senza ID restano le etichette [UPD]/[DLC]/[APP] e la parola nel nome.
Sola lettura del nome: niente apertura dei file, quindi funziona anche senza prod.keys.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_EXTS = (".nsp", ".xci", ".nsz", ".xcz")
_TID = re.compile(r"(?<![0-9A-Fa-f])(0?1[0-9A-Fa-f]{14})(?![0-9A-Fa-f])")  # anche con lo 0 iniziale perso nel nome
_VER = re.compile(r"\[\s*v(\d+)\s*\]|\bv(\d{4,})\b|\]\s*\[(\d{5,})\]", re.I)


def tid(name: str) -> int | None:
    m = _TID.search(Path(str(name)).name)
    return int(m[1], 16) if m else None


def kind(name: str) -> str:
    """«base», «update» o «dlc» (senza indizi: «base», come un file qualunque che l'utente ha messo li')."""
    t = tid(name)
    if t is not None:
        return {0: "base", 0x800: "update"}.get(t & 0xFFF, "dlc")
    n = Path(str(name)).name.lower()
    if "[upd]" in n or "update" in n:
        return "update"
    if "[dlc" in n or "dlc" in n:
        return "dlc"
    return "base"


def family(name: str) -> int | None:
    """Title ID del gioco base a cui il file appartiene (None se il nome non ha un ID)."""
    t = tid(name)
    if t is None:
        return None
    low = t & 0xFFF
    return t if low == 0 else t - 0x800 if low == 0x800 else (t & ~0xFFF) - 0x1000


def version(name: str) -> int:
    m = _VER.search(Path(str(name)).name)
    return int(next(g for g in m.groups() if g)) if m else 0


def _is_update(f: Path, files: list[Path]) -> bool:
    """Un aggiornamento col Title ID del gioco base (nome sbagliato, capita): stesso gioco, versione piu' alta del base."""
    low = min((version(g.name) for g in files if family(g.name) == family(f.name) and kind(g.name) == "base"), default=0)
    return kind(f.name) == "base" and family(f.name) is not None and version(f.name) > low


def pick_base(files: list[Path]) -> Path | None:
    """Il file da avviare: il gioco base (il piu' grande se ce n'e' piu' d'uno). None se nessun file e' un base."""
    base = [f for f in files if kind(f.name) == "base" and not _is_update(f, files)]
    return max(base, key=lambda f: f.stat().st_size, default=None)


def companions(base: Path, files: list[Path]) -> tuple[list[Path], list[Path]]:
    """(aggiornamenti dal piu' nuovo, DLC) di `base` tra `files`: stesso gioco per Title ID."""
    fam = family(base.name)
    if fam is None:
        return [], []
    same = [f for f in files if f != base and family(f.name) == fam]
    ups = sorted((f for f in same if kind(f.name) == "update" or _is_update(f, files)), key=lambda f: version(f.name), reverse=True)
    return ups, [f for f in same if kind(f.name) == "dlc"]


def package_files(folder: Path) -> list[Path]:
    """Pacchetti Switch in una cartella di gioco (anche in una sottocartella)."""
    return sorted(f for pat in ("*", "*/*") for f in folder.glob(pat) if f.is_file() and f.suffix.lower() in PACKAGE_EXTS)


def hide_companions(entries: list[tuple[Path, bool]]) -> list[tuple[Path, bool]]:
    """Per la scansione: un aggiornamento o DLC sciolto accanto al suo gioco base non e' un gioco a parte."""
    loose = [p for p, is_dir in entries if not is_dir]
    bases = {(p.parent, family(p.name)) for p in loose if kind(p.name) == "base" and family(p.name) is not None
             and not _is_update(p, loose)}
    return [(p, d) for p, d in entries
            if d or (kind(p.name) == "base" and not _is_update(p, loose)) or (p.parent, family(p.name)) not in bases]
