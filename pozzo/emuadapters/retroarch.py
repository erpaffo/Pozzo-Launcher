"""RetroArch: override per gioco «<cartella config>/<core>/<gioco>.cfg» (mai retroarch.cfg globale)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .. import emucfg

NAME = "retroarch"
_BAD_NAME = re.compile(r'[\/:*?"<>|\x00-\x1f]')
_QUOTED = re.compile(r'^".*"$')


def _safe(part) -> bool:
    return (isinstance(part, str) and part not in {"", ".", ".."} and not _BAD_NAME.search(part)
            and not part.endswith((".", " ")))


def _config_dirs(exe):
    """Cartelle che contengono retroarch.cfg, nell'ordine di ricerca documentato (portatile prima)."""
    if exe:
        yield Path(exe).parent
    if sys.platform != "win32":
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            yield Path(xdg) / "retroarch"
        yield Path.home() / ".config" / "retroarch"
        if sys.platform == "darwin":  # shortcut: percorso del pacchetto macOS non documentato su docs.libretro.com
            yield Path.home() / "Library" / "Application Support" / "RetroArch"


def target(exe, game_id, *, core=None, game_name=None):
    if not (_safe(core) and _safe(game_name)):
        return None
    for base in _config_dirs(exe):
        if (base / "retroarch.cfg").is_file():
            return base / "config" / core / f"{game_name}.cfg"
    return None


def render(existing: str, values: dict) -> str:
    # RetroArch scrive i valori tra virgolette; _patch conserva commenti e altre chiavi
    quoted = {k: v if _QUOTED.match(v) else f'"{v}"' for k, v in values.get("", {}).items()}
    return emucfg._patch(existing, quoted)


def running_names():
    return ("retroarch", "retroarch.exe", "retroarch_debug.exe")
