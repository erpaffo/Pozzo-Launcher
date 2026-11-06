"""RPCS3: configurazione per gioco `custom_configs/config_<serial>.yml` (YAML, gruppo «Video»)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

NAME = "rpcs3"
_SERIAL = re.compile(r"^[A-Za-z0-9]{4,12}$")


def _config_dir(exe: str | None) -> Path:
    """fs::get_config_dir (Utilities/File.cpp): Windows = cartella dell'exe + config/, altrove cartella utente."""
    if sys.platform == "win32":
        env = os.environ.get("RPCS3_CONFIG_DIR")
        base = Path(env) if env else Path(exe).parent if exe else None
        return base / "config" if base else Path()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "rpcs3"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rpcs3"


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    if not isinstance(game_id, str) or not _SERIAL.fullmatch(game_id):
        return None  # seriale PS3 fornito da gamekey
    base = _config_dir(exe)
    if base == Path():
        return None
    return base / "custom_configs" / f"config_{game_id}.yml"


def _val(v: str):
    return int(v) if re.fullmatch(r"\d+", v) else v


def render(existing: str, values: dict) -> str:
    try:
        data = yaml.safe_load(existing) if existing.strip() else {}
    except yaml.YAMLError as exc:
        raise ValueError("Config RPCS3 non riconosciuta") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Config RPCS3 non riconosciuta")
    for section, kv in values.items():
        node = data.setdefault(section, {})
        if not isinstance(node, dict):
            raise ValueError("Config RPCS3 non riconosciuta")
        node.update({k: _val(v) for k, v in kv.items()})
    # shortcut: i commenti YAML vanno persi (RPCS3 non ne scrive); il backup conserva l'originale
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def running_names() -> tuple[str, ...]:
    return ("rpcs3.exe", "rpcs3", "rpcs3.appimage")
