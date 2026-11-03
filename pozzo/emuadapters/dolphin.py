"""Dolphin: «User/GameSettings/<GAMEID>.ini»; solo le chiavi del preset, il resto resta nel Sys integrato."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..remote import emusetup

NAME = "dolphin"
_ID = re.compile(r"^[A-Za-z0-9]{4,6}$")


def _user_dir(exe) -> Path:
    if sys.platform == "win32":
        return emusetup.dolphin_dir(exe)
    if exe and (Path(exe).parent / "portable.txt").exists():
        return Path(exe).parent / "User"
    env = os.environ.get("DOLPHIN_EMU_USERPATH")
    if env:
        return Path(env)
    if sys.platform == "darwin":  # shortcut: nome cartella macOS non letto per intero dai sorgenti
        return Path.home() / "Library" / "Application Support" / "Dolphin"
    legacy = Path.home() / ".dolphin-emu"
    if legacy.exists():
        return legacy
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "dolphin-emu"


def target(exe, game_id, *, core=None, game_name=None):
    if not isinstance(game_id, str) or not _ID.fullmatch(game_id):
        return None
    return _user_dir(exe) / "GameSettings" / f"{game_id.upper()}.ini"


def render(existing: str, values: dict) -> str:
    out = emusetup.ini_update(existing, values)
    return out.replace("\n", "\r\n") if "\r\n" in existing else out


def running_names():
    return ("dolphin.exe", "dolphin", "dolphin-emu", "dolphin-emu.exe", "dolphin-emu-nogui", "dolphinbar.exe")
