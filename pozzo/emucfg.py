"""Preset emulatori verificati e override per-gioco."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

CATALOG_PATH = Path(__file__).parent / "data" / "emu_profiles.json"
LEAVE = "leave"
INHERIT = "inherit"
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]*$")


@dataclass(frozen=True)
class Backup:
    """Token restituito da apply(), necessario per ripristinare il file originale."""

    path: Path
    backup_path: Path | None
    existed: bool
    changed: bool
    preset_id: str


def catalog(path: str | Path | None = None) -> dict:
    """Legge e valida il catalogo locale; nessuna richiesta di rete."""
    source = Path(path) if path is not None else CATALOG_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("default") != LEAVE:
        raise ValueError("Catalogo emucfg non supportato")
    presets = data.get("presets")
    if not isinstance(presets, list):
        raise ValueError("Catalogo emucfg senza preset")
    ids = set()
    for preset in presets:
        if not isinstance(preset, dict) or not isinstance(preset.get("id"), str):
            raise ValueError("Preset emucfg non valido")
        if preset["id"] in ids:
            raise ValueError(f"Preset emucfg duplicato: {preset['id']}")
        ids.add(preset["id"])
        if not preset.get("emulator") or not isinstance(preset.get("values"), dict):
            raise ValueError(f"Preset emucfg incompleto: {preset['id']}")
        if any(not _KEY.fullmatch(k) or not isinstance(v, str) for k, v in preset["values"].items()):
            raise ValueError(f"Valori emucfg non validi: {preset['id']}")
        sources = preset.get("sources")
        if not sources or any(not isinstance(url, str) or not url.startswith("https://") for url in sources):
            raise ValueError(f"Fonti pubbliche mancanti: {preset['id']}")
    return data


def presets() -> list[dict]:
    """Restituisce i preset verificati del catalogo incluso."""
    return catalog()["presets"]


def _preset_id(selection) -> str | None:
    if selection is None or selection == LEAVE:
        return None
    if isinstance(selection, str):
        return selection
    if isinstance(selection, Mapping):
        mode = selection.get("mode", "preset")
        if mode == LEAVE:
            return None
        if mode == INHERIT:
            return INHERIT
        if mode == "preset":
            value = selection.get("preset") or selection.get("id")
            if isinstance(value, str) and value:
                return value
    raise ValueError("Selezione emucfg non valida")


def resolve(game=None, general=None) -> dict | None:
    """Risoluzione game > generale; `None`/`inherit` nel gioco eredita, `leave` disattiva."""
    selected = _preset_id(game)
    if selected == INHERIT:
        selected = _preset_id(general)
    elif game is None:
        selected = _preset_id(general)
    if selected is None:
        return None
    for preset in catalog()["presets"]:
        if preset["id"] == selected:
            return preset
    raise ValueError(f"Preset emucfg sconosciuto: {selected}")


def retroarch_override_path(config_dir: str | Path, core: str, game_name: str) -> Path:
    """Percorso `/config/<core>/<game>.cfg` documentato da RetroArch.

    `config_dir` è la cartella impostata in RetroArch per Directory > Config;
    `game_name` è il nome contenuto senza estensione.
    """
    for value in (core, game_name):
        if (not isinstance(value, str) or not _COMPONENT.fullmatch(value)
                or value in {".", ".."} or value.endswith((".", " "))):
            raise ValueError("Nome core/gioco non valido")
    return Path(config_dir) / core / f"{game_name}.cfg"


def _patch(text: str, values: Mapping[str, str]) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    remaining = set(values)
    lines = text.splitlines(keepends=True)
    result = []
    for line in lines:
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else "\r" if line.endswith("\r") else ""
        body = line[:-len(ending)] if ending else line
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$", body)
        if not match or match[2] not in values:
            result.append(line)
            continue
        key = match[2]
        comment = re.search(r"\s+#.*$", match[4])
        suffix = comment.group() if comment else ""
        result.append(f"{match[1]}{key}{match[3]}{values[key]}{suffix}{ending}")
        remaining.discard(key)
    if remaining:
        if result and not result[-1].endswith(("\n", "\r")):
            result[-1] += newline
        result.extend(f"{key} = {values[key]}{newline}" for key in values if key in remaining)
    return "".join(result)


def _atomic_write(path: Path, contents: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.pozzo-{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(contents)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.pozzo-{stamp}")
    suffix = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.pozzo-{stamp}-{suffix}")
        suffix += 1
    return candidate


def apply(path: str | Path, selection=None) -> Backup | None:
    """Applica un preset al file override; `None`/`leave` non crea né scrive nulla."""
    preset = resolve(selection)
    if preset is None:
        return None
    if preset["emulator"] != "retroarch":
        raise ValueError(f"Emulatore non supportato: {preset['emulator']}")

    target = Path(path)
    existed = target.exists()
    original = target.read_bytes() if existed else b""
    has_bom = original.startswith(b"\xef\xbb\xbf")
    text = original[3:].decode("utf-8") if has_bom else original.decode("utf-8")
    patched = _patch(text, preset["values"])
    updated = (b"\xef\xbb\xbf" if has_bom else b"") + patched.encode("utf-8")
    if updated == original:
        return None

    backup_path = _backup_path(target) if existed else None
    if backup_path:
        shutil.copy2(target, backup_path)
    _atomic_write(target, updated)
    return Backup(target, backup_path, existed, True, preset["id"])


def restore(backup: Backup) -> bool:
    """Ripristina il file originale dal token di apply(); i backup restano disponibili."""
    if not backup.changed:
        return False
    if backup.existed:
        if backup.backup_path is None or not backup.backup_path.is_file():
            raise FileNotFoundError("Backup emucfg non trovato")
        _atomic_write(backup.path, backup.backup_path.read_bytes())
        shutil.copystat(backup.backup_path, backup.path)
    else:
        try:
            backup.path.unlink()
        except FileNotFoundError:
            return False
    return True
