"""Un parser per formato. Leggono solo i file indicati (o nomi fissi dentro una cartella), mai i file di gioco."""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from . import ImportError_, MAX_GAMES, read_bytes, safe_file


def _json(path):
    try:
        return json.loads(read_bytes(path, (".json",)).decode("utf-8-sig", "replace"))
    except json.JSONDecodeError as e:
        raise ImportError_("json") from e


def _folder(path) -> Path:
    p = Path(str(path or "").strip().strip('"'))
    if ".." in p.parts or p.is_symlink() or not p.is_dir():
        raise ImportError_("notdir")
    return p


def _exe(path) -> str | None:
    return str(path) if path and Path(str(path)).suffix.lower() in (".exe", ".bat", ".cmd", ".lnk") else None


def _ts(v) -> float:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _rec(title, playtime=0.0, favorite=False, last_played=0.0, collections=None, exe=None, scripts=False) -> dict:
    # scripts: la fonte ha comandi/script propri. Si segnalano soltanto: non si importano MAI (vedi importers.apply)
    return {"title": str(title), "playtime": float(playtime or 0), "favorite": bool(favorite),
            "last_played": float(last_played or 0), "collections": collections or [], "exe": exe, "scripts": bool(scripts)}


# ------------------------------------------------------------------ Playnite
def parse_playnite(path) -> list[dict]:
    """File JSON: elenco di giochi (o {"Items"|"games": [...]}) con Name, Playtime (s), Favorite, LastActivity,
    Categories (nomi o oggetti con Name), GameActions (Path). shortcut: il database nativo di Playnite 5 e' LiteDB
    binario e non si legge; serve l'export JSON (o i file games/*.json uniti in un elenco)."""
    d = _json(path)
    if isinstance(d, dict):
        d = next((d[k] for k in ("Items", "items", "games", "Games") if isinstance(d.get(k), list)), None)
    if not isinstance(d, list):
        raise ImportError_("format")
    out = []
    for g in d[:MAX_GAMES]:
        if not isinstance(g, dict) or not g.get("Name") or g.get("Hidden"):
            continue
        cats = [c.get("Name") if isinstance(c, dict) else c for c in g.get("Categories") or [] if c]
        exe = next((a.get("Path") for a in g.get("GameActions") or [] if isinstance(a, dict) and a.get("Path")), None)
        if exe:
            exe = _exe(str(exe).replace("{InstallDir}", str(g.get("InstallDirectory") or "")))
        # script di Playnite: PreScript/PostScript/GameStartedScript e azioni di tipo Script
        scripts = any(g.get(k) for k in ("PreScript", "PostScript", "GameStartedScript")) or any(
            isinstance(a, dict) and str(a.get("Type")).lower() in ("script", "2") for a in g.get("GameActions") or [])
        out.append(_rec(g["Name"], g.get("Playtime"), g.get("Favorite"), _ts(g.get("LastActivity")) if g.get("LastActivity") else 0,
                        [c for c in cats if isinstance(c, str)], exe, scripts))
    return out


# ------------------------------------------------------------------ LaunchBox
def _xml(path) -> ET.Element:
    raw = read_bytes(path, (".xml",))
    if re.search(rb"<!(DOCTYPE|ENTITY)", raw, re.I):  # ElementTree non e' protetto da entita' ricorsive
        raise ImportError_("xml")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as e:
        raise ImportError_("xml") from e


def parse_launchbox(path) -> list[dict]:
    """Un file XML di LaunchBox, oppure la sua cartella (Data/Platforms/*.xml e Data/Playlists/*.xml).
    Le playlist diventano raccolte."""
    p = Path(str(path or "").strip().strip('"'))
    if p.is_dir():
        p = _folder(p)
        files = sorted(f for sub in ("Platforms", "Playlists") for f in (p / "Data" / sub).glob("*.xml") if not f.is_symlink())
    else:
        files = [safe_file(p, (".xml",))]
    games: dict[str, dict] = {}
    plays: list[tuple[str, str]] = []
    for f in files:
        root = _xml(f)
        for g in root.iter("Game"):
            t = (g.findtext("Title") or "").strip()
            if not t:
                continue
            r = games.setdefault(t.lower(), _rec(t))
            r["favorite"] |= (g.findtext("Favorite") or "").lower() == "true"
            r["playtime"] = max(r["playtime"], float(g.findtext("PlayTime") or 0))
            r["last_played"] = max(r["last_played"], _ts(g.findtext("LastPlayedDate") or ""))
            r["exe"] = r["exe"] or _exe(g.findtext("ApplicationPath"))  # relativo a LaunchBox: is_file() lo scarta in apply
        name = (root.findtext("Playlist/Name") or "").strip()
        if name:
            plays += [(name, (pg.findtext("GameTitle") or "").strip()) for pg in root.iter("PlaylistGame")]
    for name, t in plays:
        if t.lower() in games:
            games[t.lower()]["collections"].append(name)
    return list(games.values())[:MAX_GAMES]


# ------------------------------------------------------------------ Lutris
def parse_lutris(path) -> list[dict]:
    """pga.db di Lutris (SQLite), aperto in sola lettura. playtime e' in ore."""
    p = safe_file(path, (".db", ".sqlite"))
    db = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)
    try:
        cats: dict[int, list[str]] = {}
        for gid, name in db.execute("SELECT gc.game_id, c.name FROM games_categories gc JOIN categories c ON c.id=gc.category_id"):
            cats.setdefault(gid, []).append(name)
        out = []
        for gid, name, hours, last in db.execute("SELECT id, name, playtime, lastplayed FROM games LIMIT ?", (MAX_GAMES,)):
            c = cats.get(gid, [])
            out.append(_rec(name, float(hours or 0) * 3600, "favorite" in [x.lower() for x in c], last,
                            [x for x in c if not x.startswith(".") and x.lower() != "favorite"]))
        return out
    except sqlite3.Error as e:
        raise ImportError_("sqlite") from e
    finally:
        db.close()


# ------------------------------------------------------------------ Heroic
def parse_heroic(path) -> list[dict]:
    """Cartella di configurazione di Heroic. Nomi fissi: legendary/gog/nile library, timetracking.json, favourites.json.
    shortcut: i nomi seguono Heroic 2.x e non li ho verificati su un'installazione vera, da controllare se cambiano."""
    root = _folder(path)
    lib: dict[str, str] = {}
    for rel, key in (("store_cache/legendary_library.json", "library"), ("gog_store/library.json", "games"),
                     ("store_cache/nile_library.json", "library")):
        if (root / rel).is_file():
            for g in _json(root / rel).get(key) or []:
                if isinstance(g, dict) and (g.get("app_name") or g.get("id")) and g.get("title"):
                    lib[str(g.get("app_name") or g["id"])] = str(g["title"])
    if not lib:
        raise ImportError_("format")
    favs, times = set(), {}
    if (root / "favourites.json").is_file():
        d = _json(root / "favourites.json")
        favs = {str(x.get("appName")) for x in (d.get("favourites") or d.get("games") or []) if isinstance(x, dict)}
    if (root / "timetracking.json").is_file():
        times = _json(root / "timetracking.json")
    out = []
    for app, title in list(lib.items())[:MAX_GAMES]:
        t = times.get(app) if isinstance(times.get(app), dict) else {}
        out.append(_rec(title, float(t.get("totalPlayed") or 0) * 60, app in favs, _ts(t["lastPlayed"]) if t.get("lastPlayed") else 0))
    return out


# ------------------------------------------------------------------ Pegasus
def parse_pegasus(path) -> list[dict]:
    """metadata.pegasus.txt: `collection:` e `game:` con righe `chiave: valore`. Solo giochi e raccolte (il formato
    non ha tempo di gioco). Un gioco entra nella raccolta dichiarata sopra di lui, o in quelle di `collections:`."""
    text = read_bytes(path, (".txt",)).decode("utf-8-sig", "replace")
    out, coll, cur, key = [], "", None, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":  # continuazione
            if cur is not None and key == "collections":
                cur["collections"] += [c.strip() for c in line.split(",") if c.strip()]
            continue
        m = re.match(r"([\w.\-]+)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "collection":
            coll, cur = val, None
        elif key == "game":
            cur = _rec(val, collections=[coll] if coll else [])
            out.append(cur)
        elif cur is not None and key in ("launch", "command", "launch.command"):
            cur["scripts"] = True  # comando di avvio di Pegasus: non si importa
        elif cur is not None and key == "collections":
            cur["collections"] = [c.strip() for c in val.split(",") if c.strip()]
        if len(out) >= MAX_GAMES:
            break
    return out


PARSERS = {"playnite": parse_playnite, "launchbox": parse_launchbox, "lutris": parse_lutris,
           "heroic": parse_heroic, "pegasus": parse_pegasus}
