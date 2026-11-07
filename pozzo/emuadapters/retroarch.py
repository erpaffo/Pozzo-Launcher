"""RetroArch: override per gioco «<cartella config>/<core>/<gioco>.cfg» (mai retroarch.cfg globale)."""

from __future__ import annotations

import os
import re
import socket
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


CMDS = {"save": b"SAVE_STATE", "load": b"LOAD_STATE", "reset": b"RESET"}


def _cfg_value(exe, key):
    for base in _config_dirs(exe):
        f = base / "retroarch.cfg"
        if f.is_file():
            m = re.search(rf'^\s*{key}\s*=\s*"?([^"\r\n]*)"?', f.read_text(encoding="utf-8", errors="ignore"), re.M)
            return m.group(1).strip() if m else None
    return None


def net_ready(exe) -> bool:
    """Comandi di rete attivi in retroarch.cfg (Impostazioni > Rete > Comandi di rete); non si attivano di nascosto."""
    return _cfg_value(exe, "network_cmd_enable") == "true"


def command(exe, action) -> bool:
    """Invia SAVE_STATE / LOAD_STATE / RESET a RetroArch via UDP locale. shortcut: UDP senza risposta, True = inviato, non eseguito."""
    if action not in CMDS or not net_ready(exe):
        return False
    port = _cfg_value(exe, "network_cmd_port")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(CMDS[action], ("127.0.0.1", int(port) if port and port.isdigit() else 55355))
    return True


def running_names():
    return ("retroarch", "retroarch.exe", "retroarch_debug.exe")
