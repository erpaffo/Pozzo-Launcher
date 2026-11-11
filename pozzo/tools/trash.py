"""Sposta nel Cestino invece di cancellare. Mai eliminazione definitiva: dove il Cestino non c'e' (rete, dischi
rimovibili, Linux/macOS) si usa la cartella .pozzo-trash sullo stesso volume (rename, quindi istantaneo e senza spazio)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def _fixed_drive(p: Path) -> bool:
    # il Cestino di Windows su rete/USB cancella davvero: lo usiamo solo sui dischi fissi
    try:
        import ctypes
        return ctypes.windll.kernel32.GetDriveTypeW(str(p.resolve().anchor)) == 3
    except Exception:
        return False


def _win_recycle(p: Path) -> bool:
    kind = "DeleteDirectory" if p.is_dir() else "DeleteFile"
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::"
                        f"{kind}($env:GS_TRASH_PATH, 'OnlyErrorDialogs', 'SendToRecycleBin')"],
                       env={**os.environ, "GS_TRASH_PATH": str(p)}, capture_output=True, timeout=300,
                       creationflags=0x08000000)
    return not r.returncode and not p.exists()


def to_trash(path) -> str:
    """Ritorna dove e' finito ('cestino' o il percorso in .pozzo-trash). OSError se non riesce: non cancella mai."""
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(str(p))
    if sys.platform == "win32" and _fixed_drive(p):
        try:
            if _win_recycle(p):
                return "cestino"
        except (OSError, subprocess.SubprocessError):
            pass
    root = Path(p.anchor) / ".pozzo-trash"
    root.mkdir(exist_ok=True)
    dst, n = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}", 2
    while dst.exists():
        dst, n = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{n}-{p.name}", n + 1
    p.rename(dst)  # stesso volume: se non e' possibile solleva OSError e il file resta dov'e'
    return str(dst)
