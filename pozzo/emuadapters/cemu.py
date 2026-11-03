"""Cemu: profilo di gioco `gameProfiles/<titleid>.ini` (sezione [Graphics])."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..remote.emusetup import ini_update

NAME = "cemu"
_TITLE = re.compile(r"^[0-9A-Fa-f]{16}$")


def _base(exe: str | None) -> Path:
    """Cartella dati (sorgente Cemu: CemuApp.cpp): `portable`, vecchio layout con settings.xml, cartella utente."""
    if exe:
        d = Path(exe).parent
        if sys.platform == "darwin" and d.parent.name == "MacOS" and d.parent.parent.suffix == ".app":
            d = d.parent.parent.parent  # dentro il bundle .app: «portable» sta accanto al .app
        if (d / "portable").is_dir():
            return d / "portable"
        if sys.platform == "win32" and (d / "settings.xml").exists():
            return d
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Cemu"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cemu"  # wx GetUserDataDir (non letto nei sorgenti)
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "Cemu"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    if not isinstance(game_id, str) or not _TITLE.fullmatch(game_id):
        return None
    return _base(exe) / "gameProfiles" / f"{game_id.lower()}.ini"


def render(existing: str, values: dict) -> str:
    for line in existing.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", ";", "[")) and "=" not in s:
            raise ValueError("Profilo Cemu non riconosciuto")
    return ini_update(existing, values)


def running_names() -> tuple[str, ...]:
    return ("cemu.exe", "cemu", "cemu.app")
