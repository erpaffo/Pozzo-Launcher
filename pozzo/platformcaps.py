"""Funzioni della versione Windows che mancano su macOS/Linux: unica fonte per UI e documentazione."""
import shutil
import sys

_COMUNI = ["vigem", "magpie", "xboxapp", "amazon", "remap", "setupexe", "resauto", "tray", "xenia"]
_EXTRA = {
    "darwin": ["uriarg", "powerplan"],
    "linux": ["dualscreen", "dolphin", "xdotool", "notifysend"],
}


def missing(platform: str = sys.platform) -> list[str]:
    """Chiavi i18n `p.missing.*` delle funzioni non disponibili ([] su Windows)."""
    if platform == "win32":
        return []
    # le voci legate a un programma esterno spariscono quando e' installato
    tools = {"xdotool": "xdotool", "notifysend": "notify-send"}
    return [f"p.missing.{k}" for k in _COMUNI + _EXTRA.get(platform, [])
            if k not in tools or not shutil.which(tools[k])]
