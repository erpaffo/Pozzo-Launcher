"""Preset emulatori verificati e override per-gioco (catalogo, precedenza, backup, ripristino)."""

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

PRESETS_DIR = Path(__file__).parent / "data" / "emu_presets"
LEAVE = "leave"
INHERIT = "inherit"
LEVELS = ("quality", "performance", "faithful")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]*$")
_EMU = re.compile(r"^[a-z0-9]+$")


class EmuCfgError(Exception):
    """Errore leggibile dall'utente (emulatore aperto, file non determinabile, ...)."""


@dataclass(frozen=True)
class Backup:
    """Esito di apply_for_game(): cosa è stato scritto e dove sta l'originale."""

    path: Path
    backup_path: Path | None
    existed: bool
    changed: bool
    preset_id: str


def _check_values(values, where: str):
    if not isinstance(values, dict) or not values:
        raise ValueError(f"Valori emucfg mancanti: {where}")
    for section, kv in values.items():
        if not isinstance(section, str) or not isinstance(kv, dict) or not kv:
            raise ValueError(f"Valori emucfg non validi: {where}")
        for k, v in kv.items():
            if not isinstance(k, str) or not k or "\n" in k or not isinstance(v, str):
                raise ValueError(f"Valori emucfg non validi: {where}")


def _check_sources(obj: dict, where: str):
    sources = obj.get("sources")
    if (not isinstance(sources, list) or not sources
            or any(not isinstance(u, str) or not u.startswith("https://") for u in sources)):
        raise ValueError(f"Fonti pubbliche mancanti: {where}")


def catalog(emulator: str, folder: str | Path | None = None) -> dict:
    """Legge e valida il catalogo locale di un emulatore; nessuna richiesta di rete."""
    if not isinstance(emulator, str) or not _EMU.fullmatch(emulator):
        raise ValueError("Emulatore non valido")
    source = Path(folder or PRESETS_DIR) / f"{emulator}.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("emulator") != emulator:
        raise ValueError("Catalogo emucfg non supportato")
    presets, games = data.get("presets"), data.get("games", {})
    if not isinstance(presets, dict) or not presets or not isinstance(games, dict):
        raise ValueError("Catalogo emucfg senza preset")
    for level, preset in presets.items():
        if level not in LEVELS or not isinstance(preset, dict) or not isinstance(preset.get("name"), str):
            raise ValueError(f"Preset emucfg non valido: {level}")
        _check_values(preset.get("values"), level)
        _check_sources(preset, level)
    for gid, game in games.items():
        if not isinstance(game, dict) or not gid:
            raise ValueError("Override emucfg non valido")
        if "preset" not in game and "values" not in game:
            raise ValueError(f"Override emucfg vuoto: {gid}")
        if "preset" in game and game["preset"] not in presets:
            raise ValueError(f"Override emucfg con preset sconosciuto: {gid}")
        if "values" in game:
            _check_values(game["values"], gid)
        if not isinstance(game.get("reason"), str) or not game["reason"]:
            raise ValueError(f"Motivo mancante: {gid}")
        _check_sources(game, gid)
    return data


def presets_for(emulator: str) -> dict:
    """Livelli disponibili {livello: preset} per l'emulatore."""
    return catalog(emulator)["presets"]


def supported(emulator: str) -> bool:
    """True se esistono sia l'adattatore sia un catalogo valido."""
    from . import emuadapters
    if emuadapters.get(emulator) is None:
        return False
    try:
        catalog(emulator)
    except (OSError, ValueError):
        return False
    return True


def _level(selection) -> str | None:
    """Livello scelto; None = leave, INHERIT = eredita."""
    if selection is None or selection == LEAVE:
        return None
    if isinstance(selection, Mapping):
        mode = selection.get("mode", "preset")
        if mode == LEAVE:
            return None
        if mode == INHERIT:
            return INHERIT
        selection = selection.get("preset") or selection.get("id")
    if selection == INHERIT:
        return INHERIT
    if isinstance(selection, str) and selection in LEVELS:
        return selection
    raise ValueError("Selezione emucfg non valida")


def _merge(base: dict, extra: dict) -> dict:
    out = {s: dict(kv) for s, kv in base.items()}
    for s, kv in extra.items():
        out.setdefault(s, {}).update(kv)
    return out


def resolve(emulator: str, game_id: str, game_sel=None, console_sel=None) -> dict | None:
    """Gioco > console > leave. Ritorna {preset, values, sources, reason} o None (non tocca)."""
    level = INHERIT if game_sel is None else _level(game_sel)
    if level == INHERIT:
        level = _level(console_sel)
        if level == INHERIT:
            level = None
    if level is None:
        return None
    data = catalog(emulator)
    preset = data["presets"].get(level)
    if preset is None:
        raise ValueError(f"Preset emucfg sconosciuto: {level}")
    values, sources, reason = preset["values"], list(preset["sources"]), ""
    over = data.get("games", {}).get(game_id)
    if over:
        if "preset" in over:
            base = data["presets"][over["preset"]]
            values, sources = base["values"], list(base["sources"])
        if "values" in over:
            values = _merge(values, over["values"])
        sources += [u for u in over["sources"] if u not in sources]
        reason = over["reason"]
    return {"preset": level, "values": values, "sources": sources, "reason": reason}


def preview(emulator: str, game_id: str, game_sel=None, console_sel=None) -> dict:
    """Come resolve(), ma con valori vuoti al posto di None (per «Cosa cambierà»)."""
    return resolve(emulator, game_id, game_sel, console_sel) or {
        "preset": None, "values": {}, "sources": [], "reason": ""}


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


def _marker(path: Path) -> Path:
    # niente «.pozzo-» nel nome: latest_backup() non deve scambiarlo per un backup
    return path.with_name(path.name + ".pozzo_new")


def _adapter_target(emulator, exe, game_id, core, game_name):
    from . import emuadapters
    adapter = emuadapters.get(emulator)
    if adapter is None:
        raise EmuCfgError("Emulatore non supportato")
    target = adapter.target(exe, game_id, core=core, game_name=game_name)
    if target is None:
        raise EmuCfgError("File di configurazione del gioco non determinabile")
    return adapter, Path(target)


def apply_for_game(emulator: str, exe, game_id: str, game_sel=None, console_sel=None, *,
                   core=None, game_name=None, cfg_running=None) -> Backup | None:
    """Scrive il preset nel file per-gioco. None se non c'è nulla da fare.

    `cfg_running`: bool o funzione che sostituisce il controllo dei processi (test).
    """
    resolved = resolve(emulator, game_id, game_sel, console_sel)
    if resolved is None:
        return None
    adapter, target = _adapter_target(emulator, exe, game_id, core, game_name)
    running = cfg_running
    if running is None:
        from .remote import emusetup
        running = emusetup._running(tuple(adapter.running_names()))
    if running() if callable(running) else running:
        raise EmuCfgError("L'emulatore è aperto: chiudilo prima di cambiare le impostazioni")

    existed = target.exists()
    original = target.read_bytes() if existed else b""
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    new_text = adapter.render(original[len(bom):].decode("utf-8"), resolved["values"])
    updated = bom + new_text.encode("utf-8")
    if updated == original:
        return None

    from .remote import emusetup
    backup_path = None
    if existed:
        # un backup ancora in attesa di ripristino è l'originale vero: non lo si sovrascrive
        backup_path = emusetup.latest_backup(target)
        if backup_path is None:
            backup_path = _backup_path(target)
            shutil.copy2(target, backup_path)
    else:
        _atomic_write(_marker(target), b"")
    _atomic_write(target, updated)
    return Backup(target, backup_path, existed, True, resolved["preset"])


def restore_for_game(emulator: str, exe, game_id: str, *, core=None, game_name=None) -> bool:
    """Ripristina il file per-gioco (byte per byte) o lo elimina se prima non esisteva.

    Non richiede token: usa l'ultimo backup `.pozzo-*` o il marcatore accanto al file,
    quindi funziona anche dopo un riavvio dell'app.
    """
    from .remote import emusetup
    _, target = _adapter_target(emulator, exe, game_id, core, game_name)
    marker = _marker(target)
    if marker.exists():
        target.unlink(missing_ok=True)
        marker.unlink()
        return True
    last = emusetup.latest_backup(target)
    if last is None:
        return False
    _atomic_write(target, last.read_bytes())
    shutil.copystat(last, target)
    last.unlink()  # consumato: il prossimo apply farà un backup nuovo
    return True
