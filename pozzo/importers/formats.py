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


# ------------------------------------------------------------------ Steam ROM Manager
def _vdf_bin(raw: bytes) -> dict:
    """VDF binario di Steam (shortcuts.vdf): 0=sottomappa, 1=stringa, 2=int32, 8=fine. Solo quanto serve."""
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = raw.index(b"\0", pos)
        s, pos = raw[pos:end].decode("utf-8", "replace"), end + 1
        return s

    def mapping(depth=0) -> dict:
        nonlocal pos
        d = {}
        while pos < len(raw):
            t = raw[pos]
            pos += 1
            if t == 8:
                return d
            k = cstr()
            if t == 0 and depth < 8:
                d[k] = mapping(depth + 1)
            elif t == 1:
                d[k] = cstr()
            elif t == 2:
                d[k] = int.from_bytes(raw[pos:pos + 4], "little")
                pos += 4
            else:
                raise ValueError
        return d
    try:
        return mapping()
    except (ValueError, IndexError) as e:
        raise ImportError_("format") from e


def parse_srm(path) -> list[dict]:
    """Steam ROM Manager. `shortcuts.vdf` (le scorciatoie non-Steam che SRM ha scritto: titolo, tag come raccolte,
    ultimo avvio; LaunchOptions = comando, solo segnalato) oppure `userConfigurations.json` (un parser per ogni
    emulatore: i file direttamente dentro romDirectory diventano titoli, nella raccolta col nome del parser)."""
    p = Path(str(path or "").strip().strip('"'))
    if p.suffix.lower() == ".vdf":
        d = _vdf_bin(read_bytes(p, (".vdf",)))
        sc = next((v for k, v in d.items() if k.lower() == "shortcuts" and isinstance(v, dict)), None)
        if sc is None:
            raise ImportError_("format")
        out = []
        for e in list(sc.values())[:MAX_GAMES]:
            e = {str(k).lower(): v for k, v in e.items()} if isinstance(e, dict) else {}
            if not e.get("appname"):
                continue
            tags = [str(t) for t in (e.get("tags") or {}).values()] if isinstance(e.get("tags"), dict) else []
            out.append(_rec(e["appname"], 0, False, e.get("lastplaytime") or 0, tags,
                            _exe(str(e.get("exe") or "").strip('"')), bool(e.get("launchoptions"))))
        return out
    cfg = _json(p)
    if not isinstance(cfg, list):
        raise ImportError_("format")
    out = []
    for c in cfg:
        rd = c.get("romDirectory") if isinstance(c, dict) else None
        if not rd or ".." in Path(str(rd)).parts or not Path(str(rd)).is_dir():
            continue
        name = str(c.get("configTitle") or c.get("parserType") or "").strip()
        # comandi del parser (executableArgs/executableModifier): non si importano, si segnalano
        scripts = bool(c.get("executableArgs") or c.get("executableModifier"))
        for f in sorted(Path(rd).iterdir())[:MAX_GAMES - len(out)]:
            if f.is_file() and not f.is_symlink() and not f.name.startswith("."):
                out.append(_rec(f.stem, collections=[name] if name else [], scripts=scripts))
    return out


# ------------------------------------------------------------------ RetroArch
def _lpl(f: Path) -> list[dict]:
    try:
        d = json.loads(read_bytes(f, (".lpl",)).decode("utf-8-sig", "replace"))
    except json.JSONDecodeError as e:
        raise ImportError_("json") from e  # il vecchio formato a 6 righe per voce non e' JSON
    if not isinstance(d, dict) or not isinstance(d.get("items"), list):
        raise ImportError_("format")
    stem = f.stem
    special = stem.lower() in ("content_favorites", "content_history", "content_image_history",
                               "content_music_history", "content_video_history")
    out = []
    for it in d["items"][:MAX_GAMES]:
        if not isinstance(it, dict) or not str(it.get("label") or "").strip():
            continue
        secs = (float(it.get("runtime_hours") or 0) * 3600 + float(it.get("runtime_minutes") or 0) * 60
                + float(it.get("runtime_seconds") or 0))
        last = 0.0
        if it.get("last_played_year"):
            try:
                last = datetime(int(it["last_played_year"]), int(it.get("last_played_month") or 1), int(it.get("last_played_day") or 1),
                                int(it.get("last_played_hour") or 0), int(it.get("last_played_minute") or 0)).timestamp()
            except (ValueError, OverflowError, OSError):
                pass
        out.append(_rec(str(it["label"]).strip(), secs, stem.lower() == "content_favorites", last, [] if special else [stem]))
    return out


def parse_retroarch(path) -> list[dict]:
    """Playlist `.lpl` (JSON) di RetroArch, o la cartella playlists: ogni playlist e' una raccolta (content_favorites
    = preferiti, content_history ignorata). Tempo di gioco e ultimo avvio se presenti. I ROM non si toccano."""
    p = Path(str(path or "").strip().strip('"'))
    if p.is_dir():
        p = _folder(p)
        files = sorted(f for f in p.glob("*.lpl") if not f.is_symlink())
        if not files:
            raise ImportError_("format")
    else:
        files = [p]
    merged: dict[str, dict] = {}
    for f in files:
        for r in _lpl(f):
            m = merged.setdefault(r["title"].lower(), r)
            if m is not r:
                m["favorite"] |= r["favorite"]
                m["playtime"] = max(m["playtime"], r["playtime"])
                m["last_played"] = max(m["last_played"], r["last_played"])
                m["collections"] += [c for c in r["collections"] if c not in m["collections"]]
    return list(merged.values())[:MAX_GAMES]


PARSERS = {"playnite": parse_playnite, "launchbox": parse_launchbox, "lutris": parse_lutris,
           "heroic": parse_heroic, "pegasus": parse_pegasus, "srm": parse_srm, "retroarch": parse_retroarch}
