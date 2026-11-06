r"""Eden (fork di yuzu): profilo per gioco `config/custom/<titleid>.ini` (formato Qt, chiavi `x\use_global`)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..remote.emusetup import ini_update

NAME = "eden"
_TITLE = re.compile(r"^[0-9A-Fa-f]{16}$")


def _base(exe) -> Path:
    if exe and (Path(exe).parent / "user").is_dir():  # modalità portatile
        return Path(exe).parent / "user"
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "eden"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    if not isinstance(game_id, str) or not _TITLE.fullmatch(game_id):
        return None
    return _base(exe) / "config" / "custom" / f"{game_id.upper()}.ini"


def render(existing: str, values: dict) -> str:
    # shortcut: cartella dati e codici (resolution_setup, backend) da yuzu, non verificati su Eden reale
    return ini_update(existing, values, sep="=")


def running_names() -> tuple[str, ...]:
    return ("eden.exe", "eden", "eden.appimage")
