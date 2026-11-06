"""Ryujinx: configurazione per gioco `games/<titleid>/Config.json` (JSON piatto)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..library.launcher import ryujinx_data_dir

NAME = "ryujinx"
_TITLE = re.compile(r"^[0-9A-Fa-f]{16}$")


def target(exe, game_id, *, core=None, game_name=None) -> Path | None:
    if not exe or not isinstance(game_id, str) or not _TITLE.fullmatch(game_id):
        return None
    return ryujinx_data_dir(exe) / "games" / game_id.lower() / "Config.json"


def render(existing: str, values: dict) -> str:
    try:
        data = json.loads(existing) if existing.strip() else {}
    except ValueError as exc:
        raise ValueError("Config Ryujinx non riconosciuta") from exc
    if not isinstance(data, dict):
        raise ValueError("Config Ryujinx non riconosciuta")
    for kv in values.values():
        data.update({k: json.loads(v) for k, v in kv.items()})  # i valori del catalogo sono JSON ("2", "true", "\"Vulkan\"")
    # shortcut: se il file manca, Ryujinx completa i campi mancanti con i valori globali; da verificare su una build reale
    return json.dumps(data, indent=2)


def running_names() -> tuple[str, ...]:
    return ("ryujinx.exe", "ryujinx", "ryujinx.ava.exe")
