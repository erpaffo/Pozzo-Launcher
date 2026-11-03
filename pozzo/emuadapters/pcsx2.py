"""PCSX2 (Qt): impostazioni per gioco in <DataRoot>/gamesettings/<SERIAL>_<CRC>.ini."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..remote import emusetup

NAME = "pcsx2"
_SERIAL = re.compile(r"^[A-Za-z0-9]+-[0-9]+$")


def _data_root(exe: str | None) -> Path:
    if exe and any((Path(exe).parent / n).exists() for n in ("portable.ini", "portable.txt")):
        return Path(exe).parent
    if sys.platform == "win32":
        return emusetup.documents_dir() / "PCSX2"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PCSX2"
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    return (Path(xdg) if os.path.isabs(xdg) else Path.home() / ".config") / "PCSX2"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    # Il nome reale richiede il CRC del disco, che qui non si calcola: si usa un file
    # già creato da PCSX2 (<SERIAL>_*.ini); se manca o è ambiguo, non supportato.
    if not isinstance(game_id, str) or not _SERIAL.fullmatch(game_id):
        return None
    found = sorted((_data_root(exe) / "gamesettings").glob(f"{game_id}_????????.ini"))
    return found[0] if len(found) == 1 else None


def render(existing: str, values: dict) -> str:
    return emusetup.ini_update(existing, values)


def running_names() -> tuple[str, ...]:
    return ("pcsx2-qt.exe", "pcsx2-qt", "pcsx2.exe", "pcsx2")
