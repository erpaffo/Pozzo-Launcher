"""RetroArch: bezel (overlay), shader e cheat per gioco o per core, senza toccare il lanciatore.

Tutto passa da file che RetroArch carica da solo: override `config/<core>/<gioco>.cfg` (o `<core>.cfg`),
preset `config/<core>/<gioco>.slangp` e cheat `cheats/<core>/<gioco>.cht`. Dei file dell'utente si
cambiano solo le nostre chiavi, con una copia `.pozzo-bak` fatta una volta sola.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from . import emucfg, matching

API = "https://api.github.com/repos/libretro/{repo}/contents/{path}"
RAW = "https://raw.githubusercontent.com/libretro/{repo}/master/{path}"
BEZEL_DIR = "16x9 Collections/Nosh01 1440 Plain"  # shortcut: una sola collezione 16:9; altre/verticali se servono
BEZEL_REPO = "overlay-borders"
TTL = 7 * 86400
YEAR = 365 * 86400
MARK = "# pozzo"
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. ()+,&!-]*$")
_OVERLAY_KEYS = ("input_overlay", "input_overlay_enable", "input_overlay_opacity", "input_overlay_scale")


def cache_dir() -> Path:
    from . import config
    return config.app_data_dir() / "retroarch_extras"


def fetch(url: str) -> bytes:  # sostituibile nei test
    import httpx
    r = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "PozzoLauncher"})
    r.raise_for_status()
    return r.content


def _cached(name: str, url: str, ttl: float = TTL) -> bytes:
    p = cache_dir() / name
    if p.is_file() and time.time() - p.stat().st_mtime < ttl:
        return p.read_bytes()
    try:
        data = fetch(url)
    except Exception:  # offline: meglio una copia vecchia che niente
        if p.is_file():
            return p.read_bytes()
        raise
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return data


def _q(s: str) -> str:
    return s.replace(" ", "%20")


# ---- file con le nostre chiavi ------------------------------------------------------------

def read_cfg(path: Path) -> dict:
    out = {}
    if path.is_file():
        for m in re.finditer(r'^\s*([A-Za-z_]\w*)\s*=\s*"?([^"\r\n]*)"?', path.read_text("utf-8-sig", "replace"), re.M):
            out[m[1]] = m[2].strip()
    return out


def _backup_once(path: Path):
    bak = path.with_name(path.name + ".pozzo-bak")
    if path.is_file() and not bak.exists():
        shutil.copy2(path, bak)


def merge_cfg(path: Path, values: dict):
    """Imposta le chiavi (valore None = toglie la riga) lasciando tutto il resto."""
    text = path.read_text("utf-8-sig") if path.is_file() else ""
    drop = {k for k, v in values.items() if v is None}
    if drop:
        text = "".join(l for l in text.splitlines(keepends=True)
                       if not (m := re.match(r"^\s*([A-Za-z_]\w*)\s*=", l)) or m[1] not in drop)
    text = emucfg._patch(text, {k: f'"{v}"' for k, v in values.items() if v is not None})
    _backup_once(path)
    emucfg._atomic_write(path, text.encode("utf-8"))


# ---- bezel --------------------------------------------------------------------------------

def parse_bezels(listing: list) -> list[dict]:
    """Elenco GitHub contents -> [{id, name}] per i .cfg che hanno il .png accanto."""
    names = {x.get("name", "") for x in listing if x.get("type") == "file"}
    return sorted(({"id": n, "name": n[:-4]} for n in names if n.endswith(".cfg") and n[:-4] + ".png" in names),
                  key=lambda b: b["name"].lower())


def bezel_index() -> list[dict]:
    return parse_bezels(json.loads(_cached("bezels.json", API.format(repo=BEZEL_REPO, path=_q(BEZEL_DIR)))))


def bezels_for(platform) -> list[dict]:
    """Bezel della console: nome piattaforma/libretro confrontato col nome del file (senza «-Bezel-16x9-...»)."""
    keys = [platform.name, *platform.libretro]
    out = []
    for b in bezel_index():
        label = re.sub(r"-Bezel.*$", "", b["name"]).replace("-", " ")
        if max(matching.score(k, label) for k in keys) >= 80:
            out.append(b)
    return out


def bezel_file(bezel_id: str, ext: str = "cfg") -> Path:
    """Scarica (una volta) .cfg e .png del bezel: il .cfg rimanda al .png per nome, quindi stanno insieme."""
    if not _SAFE.match(bezel_id) or not bezel_id.endswith(".cfg"):
        raise ValueError("bezel")
    stem = bezel_id[:-4]
    for e in ("cfg", "png"):
        _cached(f"bezels/{stem}.{e}", RAW.format(repo=BEZEL_REPO, path=_q(f"{BEZEL_DIR}/{stem}.{e}")), YEAR)
    return cache_dir() / "bezels" / f"{stem}.{ext}"


def set_bezel(cfg_path: Path, bezel_id: str | None):
    """None = toglie le nostre chiavi (eredita); "" = nessun bezel; altrimenti l'id del bezel."""
    if bezel_id is None:
        vals = {k: None for k in _OVERLAY_KEYS}
    elif bezel_id == "":
        vals = {"input_overlay_enable": "false"}
    else:
        vals = {"input_overlay": bezel_file(bezel_id).as_posix(), "input_overlay_enable": "true",
                "input_overlay_opacity": "1.000000", "input_overlay_scale": "1.000000"}
    merge_cfg(cfg_path, vals)


def current_bezel(cfg_path: Path):
    """None = non impostato, "" = disattivato, altrimenti l'id (solo se è un nostro bezel)."""
    c = read_cfg(cfg_path)
    if c.get("input_overlay_enable") == "false":
        return ""
    ov = c.get("input_overlay")
    return Path(ov).stem + ".cfg" if ov and "retroarch_extras" in ov.replace("\\", "/") else None


# ---- shader -------------------------------------------------------------------------------

def shader_root(base: Path) -> Path:
    d = read_cfg(base / "retroarch.cfg").get("video_shader_dir", "")
    d = Path(d) if d and not d.startswith(":") else base / "shaders"
    d = d if d.is_absolute() else base / d
    return d / "shaders_slang" if (d / "shaders_slang").is_dir() else d


def list_shaders(base: Path, limit: int = 1500) -> list[dict]:
    root = shader_root(base)
    if not root.is_dir():
        return []
    found = sorted(root.rglob("*.slangp"), key=lambda p: p.as_posix().lower())[:limit]
    return [{"id": p.relative_to(root).as_posix(), "name": p.relative_to(root).with_suffix("").as_posix()} for p in found]


def set_shader(preset_path: Path, base: Path, shader_id: str | None):
    """Scrive `<gioco>.slangp` (caricato da RetroArch da solo) che rimanda al preset scelto; vuoto lo toglie."""
    ours = preset_path.is_file() and preset_path.read_text("utf-8-sig", "replace").startswith(MARK)
    if not shader_id:
        if ours:
            preset_path.unlink()
        return
    root = shader_root(base).resolve()
    src = (root / shader_id).resolve()
    if not src.is_file() or root not in src.parents:
        raise ValueError("shader")
    if not ours:
        _backup_once(preset_path)
    emucfg._atomic_write(preset_path, f'{MARK}\n#reference "{src.as_posix()}"\n'.encode())


def current_shader(preset_path: Path, base: Path) -> str:
    if not preset_path.is_file():
        return ""
    m = re.search(r'^#reference\s+"([^"]+)"', preset_path.read_text("utf-8-sig", "replace"), re.M)
    try:
        return Path(m[1]).relative_to(shader_root(base).resolve()).as_posix() if m else ""
    except ValueError:
        return ""


# ---- cheat --------------------------------------------------------------------------------

def parse_cht(text: str) -> list[dict]:
    kv = {m[1]: m[2] for m in re.finditer(r'^\s*(\w+)\s*=\s*"?(.*?)"?\s*$', text, re.M)}
    n = int(kv.get("cheats", "0") or 0)
    return [{"i": i, "desc": kv.get(f"cheat{i}_desc", f"#{i}"), "code": kv.get(f"cheat{i}_code", ""),
             "enable": kv.get(f"cheat{i}_enable", "false") == "true"} for i in range(n)]


def render_cht(entries: list[dict], enabled: set) -> str:
    out = [f"cheats = {len(entries)}\n"]
    for i, e in enumerate(entries):
        desc = e["desc"].replace('"', "'")
        out.append(f'cheat{i}_desc = "{desc}"\ncheat{i}_code = "{e["code"]}"\n'
                   f'cheat{i}_enable = {"true" if i in enabled else "false"}\n')
    return "".join(out)


def match_cheat(game_name: str, files: list[str]) -> str | None:
    best, _ = matching.best(game_name, files, key=lambda f: f[:-4] if f.endswith(".cht") else f, min_score=80)
    return best


def cheat_files(libretro_name: str) -> list[str]:
    listing = json.loads(_cached(f"cht-{re.sub(r'[^A-Za-z0-9]+', '_', libretro_name)}.json",
                                 API.format(repo="libretro-database", path=_q(f"cht/{libretro_name}"))))
    return [x["name"] for x in listing if x.get("name", "").endswith(".cht")]


def cheat_text(libretro_name: str, file: str) -> str:
    url = RAW.format(repo="libretro-database", path=_q(f"cht/{libretro_name}/{file}"))
    return _cached(f"cht/{libretro_name}/{file}", url, YEAR).decode("utf-8", "replace")


def cheats_dir(base: Path) -> Path:
    d = read_cfg(base / "retroarch.cfg").get("cheat_database_path", "")
    return Path(d) if d and Path(d).is_absolute() else base / (d or "cheats")


def write_cheats(path: Path, entries: list[dict], enabled: set):
    if path.is_file() and not path.read_text("utf-8-sig", "replace").startswith(MARK):
        _backup_once(path)
    emucfg._atomic_write(path, (MARK + "\n" + render_cht(entries, enabled)).encode("utf-8"))
