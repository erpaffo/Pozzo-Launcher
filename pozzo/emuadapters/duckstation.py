"""DuckStation: impostazioni per gioco in <DataRoot>/gamesettings/<SERIAL>.ini."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..remote import emusetup

NAME = "duckstation"
_SERIAL = re.compile(r"^[A-Za-z0-9]+-[0-9]+$")


def _data_root(exe: str | None) -> Path:
    if exe and any((Path(exe).parent / n).exists() for n in ("portable.txt", "settings.ini")):
        return Path(exe).parent
    if sys.platform == "win32":
        old = emusetup.documents_dir() / "DuckStation"  # vecchie installazioni, ha la precedenza
        if old.is_dir():
            return old
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "DuckStation"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DuckStation"
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    return Path(xdg) / "duckstation" if os.path.isabs(xdg) else Path.home() / ".local" / "share" / "duckstation"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    # Multi-disco: DuckStation usa il seriale del primo disco; qui si usa quello ricevuto.
    if not isinstance(game_id, str) or not _SERIAL.fullmatch(game_id):
        return None
    return _data_root(exe) / "gamesettings" / f"{game_id}.ini"


def render(existing: str, values: dict) -> str:
    return emusetup.ini_update(existing, values)


def running_names() -> tuple[str, ...]:
    return ("duckstation-qt-x64-releaseltcg.exe", "duckstation-qt.exe", "duckstation-qt", "duckstation-nogui", "duckstation")
