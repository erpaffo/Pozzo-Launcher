"""Esporta i giochi di Pozzo in Steam come collegamenti «non-Steam» (userdata/<account>/config/shortcuts.vdf).

Le voci di Pozzo si riconoscono dall'etichetta «Pozzo» in `tags`; tutte le altre restano intatte."""

from __future__ import annotations

import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

TAG = "Pozzo"
_ID64 = 76561197960265728  # steamid64 = questo + id dell'account (nome della cartella in userdata)


class SteamRunning(RuntimeError):
    pass


def _cstr(b: bytes, i: int) -> tuple[str, int]:
    j = b.index(b"\0", i)
    return b[i:j].decode("utf-8", "surrogateescape"), j + 1


def _parse(b: bytes, i: int = 0) -> tuple[dict, int]:
    d: dict = {}
    while True:
        t = b[i]
        i += 1
        if t == 8:
            return d, i
        k, i = _cstr(b, i)
        if t == 0:
            d[k], i = _parse(b, i)
        elif t == 1:
            d[k], i = _cstr(b, i)
        elif t == 2:
            d[k] = struct.unpack_from("<i", b, i)[0]
            i += 4
        else:  # tipo sconosciuto: meglio non scrivere che corrompere il file
            raise ValueError(f"tipo VDF {t} non supportato")


def loads(b: bytes) -> dict:
    return _parse(b)[0] if b else {}


def _dump(d: dict) -> bytes:
    out = b""
    for k, v in d.items():
        kb = k.encode("utf-8", "surrogateescape") + b"\0"
        if isinstance(v, dict):
            out += b"\0" + kb + _dump(v) + b"\x08"
        elif isinstance(v, int):
            out += b"\2" + kb + struct.pack("<i", v)
        else:
            out += b"\1" + kb + v.encode("utf-8", "surrogateescape") + b"\0"
    return out


def dumps(d: dict) -> bytes:
    return _dump(d) + b"\x08"


def appid(exe: str, name: str) -> int:
    """Id senza segno del collegamento (standard Steam ROM Manager / BoilR): nomi dei file in grid."""
    return (zlib.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000


def _tags(e: dict) -> dict:
    t = next((v for k, v in e.items() if k.lower() == "tags"), None)
    return t if isinstance(t, dict) else {}


def is_ours(e) -> bool:
    return isinstance(e, dict) and TAG in _tags(e).values()


def steam_running() -> bool:
    if sys.platform != "win32":
        return False
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return "steam.exe" in r.stdout.lower()


def users(steam: Path, persona: dict[str, str] | None = None) -> list[dict]:
    """Account che hanno una cartella in userdata ({id, name}); `persona` e' steamid64 -> nome."""
    persona = persona or {}
    return [{"id": p.name, "name": persona.get(str(_ID64 + int(p.name)), "")}
            for p in sorted((steam / "userdata").glob("*")) if p.name.isdigit() and p.name != "0"]


def _png(src: Path, dest: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(src) as im:
            im.convert("RGBA").save(dest, "PNG")
        return True
    except Exception:
        return False


def apply(steam: Path, account: str, entries: list[dict], now=time.strftime) -> dict:
    """Sostituisce le voci di Pozzo con `entries` (vuoto = le rimuove). Ogni voce: name, exe, start_dir, opts,
    art {"p"|"wide"|"hero"|"logo"|"icon": Path}. Prima di scrivere fa una copia di sicurezza."""
    if steam_running():
        raise SteamRunning()
    cfg = steam / "userdata" / account / "config"
    f = cfg / "shortcuts.vdf"
    raw = f.read_bytes() if f.exists() else b""
    data = loads(raw)
    cur = data.get("shortcuts") if isinstance(data.get("shortcuts"), dict) else {}
    foreign = [e for e in cur.values() if not is_ours(e)]
    removed = len(cur) - len(foreign)
    grid = cfg / "grid"
    art = 0
    new = []
    for e in entries:
        aid = appid(e["exe"], e["name"])
        a = e.get("art") or {}
        icon = ""
        if a:
            grid.mkdir(parents=True, exist_ok=True)
        for kind, suffix in (("p", "p"), ("wide", ""), ("hero", "_hero"), ("logo", "_logo"), ("icon", "_icon")):
            if a.get(kind) and _png(a[kind], grid / f"{aid}{suffix}.png"):
                art += 1
                icon = str(grid / f"{aid}_icon.png") if kind == "icon" else icon
        new.append({"appid": aid - (1 << 32) if aid >= 1 << 31 else aid, "AppName": e["name"], "Exe": e["exe"],
                    "StartDir": e["start_dir"], "icon": icon, "ShortcutPath": "", "LaunchOptions": e["opts"],
                    "IsHidden": 0, "AllowDesktopConfig": 1, "AllowOverlay": 1, "OpenVR": 0, "Devkit": 0,
                    "DevkitGameID": "", "DevkitOverrideAppID": 0, "LastPlayTime": 0, "FlatpakAppID": "",
                    "tags": {"0": TAG}})
    if raw:
        f.with_name(f"shortcuts.vdf.pozzo-bak-{now('%Y%m%d-%H%M%S')}").write_bytes(raw)
    cfg.mkdir(parents=True, exist_ok=True)
    data["shortcuts"] = {str(i): e for i, e in enumerate(foreign + new)}
    f.write_bytes(dumps(data))
    return {"added": len(new), "removed": removed, "kept": len(foreign), "art": art}
