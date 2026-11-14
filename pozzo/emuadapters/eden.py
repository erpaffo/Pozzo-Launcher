r"""Eden (fork di yuzu): profilo per gioco `config/custom/<titleid>.ini` (formato Qt, chiavi `x\use_global`)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..remote.emusetup import ini_update

NAME = "eden"
_TITLE = re.compile(r"^[0-9A-Fa-f]{16}$")


def _base(exe) -> Path:
    if exe and (Path(exe).parent / "user").is_dir():  # modalità portatile
        return Path(exe).parent / "user"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "eden"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "eden"
    xdg = os.environ.get("XDG_DATA_HOME", "")
    return (Path(xdg) if os.path.isabs(xdg) else Path.home() / ".local" / "share") / "eden"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    if not isinstance(game_id, str) or not _TITLE.fullmatch(game_id):
        return None
    return _base(exe) / "config" / "custom" / f"{game_id.upper()}.ini"


def render(existing: str, values: dict) -> str:
    # shortcut: cartella dati e codici (resolution_setup, backend) da yuzu, non verificati su Eden reale
    return ini_update(existing, values, sep="=")


def running_names() -> tuple[str, ...]:
    return ("eden.exe", "eden", "eden.appimage")
