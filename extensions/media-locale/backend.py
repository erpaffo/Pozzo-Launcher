"""Media locale: film, serie e musica dalle cartelle scelte dall'utente.

Funzioni pure (importabili e testate come parse_feed di Notizie):
    identify(relpath) -> {kind: "film"|"episodio"|"brano", title, series?, season?, episode?, year?, album?}
    parse_movie(name) -> {kind: "film", title, year}
    parse_episode(parts) -> {kind: "episodio", ...} | None
    parse_anime_episode(parts) -> {kind: "episodio", ...} | None
    parse_track(parts) -> {kind: "brano", ...}

Contratto «fonte di media» (identico in media-server):
    list(kind, query) -> [MediaItem]
    detail(id) -> MediaItem
    play_target(id) -> {url|path, resume_pos}
    set_progress(id, pos, seen)
    MediaItem = {id, kind, title, series?, season?, episode?, year?, duration?, poster?, backdrop?, overview?,
                 source, resume_pos?, seen?}

Rotte (/plugin-api/media-locale/...):
    GET  list?kind=&query=&limit= -> [MediaItem]        (kind: film|episodio|brano, vuoto = tutti)
    GET  detail?id=               -> MediaItem
    GET  play_target?id=          -> {"url"|"path", "resume_pos", "external", "mime"}
    POST set_progress             <- {"id", "pos", "seen", "duration"?}  (accetta anche i parametri in query)
    GET  artwork?id=              -> poster.jpg/folder.jpg accanto al file (immagine)
    GET  stream?id=               -> il file, con Range (per il player <video>)
    POST external                 <- {"id"}  apre il file in mpv/VLC se presenti, altrimenti nel lettore di sistema
    GET  roots                    -> {"roots": [{path, items}]}
    POST roots                    <- {"add": path} oppure {"remove": path}
    POST scan                     -> {"ok": true, "items": n}
    POST enrich                   <- {"id"?} arricchisce locandine e trame da AniList / TMDB

Dati: <cartella config>/media-locale-cache/media.db (SQLite separato: mai nella libreria dei giochi).
I metadati base vengono dai nomi di file e cartelle e dal poster locale; arricchibili via enrich.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from fastapi import Body, HTTPException
from fastapi.responses import FileResponse

try:
    from .metadata import enrich_item
except Exception:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from metadata import enrich_item

VIDEO = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".wmv", ".ts", ".m2ts", ".mpg", ".mpeg", ".ogv", ".flv"}
AUDIO = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma"}
MEDIA = VIDEO | AUDIO
# formati che il motore della finestra (Chromium/WebView2) legge da solo: gli altri vanno al lettore esterno
BROWSER = {".mp4", ".m4v", ".webm", ".ogv", ".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav"}
MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg",
        ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".opus": "audio/ogg", ".wav": "audio/wav", ".aac": "audio/aac"}
ART_NAMES = ("poster.jpg", "poster.png", "folder.jpg", "folder.png", "cover.jpg", "cover.png", "fanart.jpg")
SKIP_DIRS = {"$recycle.bin", "system volume information", "@eadir", ".git", "node_modules", "__pycache__"}
KINDS = ("film", "episodio", "brano")
THEME_ANIME = {"anime", "animazione"}
THEME_SERIE = {"serie", "serie tv", "serietv", "tv shows", "tv show", "tv", "shows"}
THEME_FILM = {"film", "movies", "movie"}
THEME_DIRS = THEME_ANIME | THEME_SERIE | THEME_FILM

# Token che annunciano la fine del titolo nei nomi «da release». Volutamente stretti: "web", "ts" e "dd" da soli
# sarebbero anche parole di titoli veri (es. «Charlotte's Web»).
JUNK = re.compile(
    r"(?i)\b(?:2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|bdrip|brrip|dvdrip|dvd5|dvd9|hdrip|webrip|web-dl|webdl"
    r"|hdtv|remux|x264|x265|h264|h265|hevc|avc|xvid|divx|aac|ac3|eac3|dts|truehd|atmos|ddp5\.1|dd5\.1|ddp|10bit"
    r"|hdr10|hdr|proper|repack|remastered|extended|unrated|multi|subs|ita|eng|sub[-_]?ita|subita|sub[-_]?eng|subeng|raw)\b"
)
YEAR_PAR = re.compile(r"[\(\[]((?:18|19|20)\d{2})[\)\]]")
YEAR_END = re.compile(r"\b((?:19|20)\d{2})[\s._-]*$")
BRACKETS = re.compile(r"[\[\{][^\]\}]*[\]\}]")
EPISODE = (
    re.compile(r"(?i)\bs(\d{1,2})[._ ]?e(\d{1,4})(?:[._ ]?e\d{1,4})*\b"),
    re.compile(r"(?i)\b(\d{1,2})x(\d{1,4})\b"),
    re.compile(r"(?i)\b(?:season|stagione)[._ ]?(\d{1,2})[._ ]*(?:episode|episodio|ep|e)[._ ]?(\d{1,4})\b"),
)
EPISODE_LEADING = re.compile(r"^(\d{1,4})\s*[-._ ]+\s*(.+)$")
EPISODE_TRAILING = re.compile(r"[\s._-]+(?:ep)?[\s._-]?(\d{1,4})\s*$")
SEASON_DIR = re.compile(r"(?i)^(?:season|stagione|s)[._ ]?(\d{1,3})$")
TRACK_PREFIX = re.compile(r"^(\d{1,3})\s*[-._ ]+\s*(.+)$")
DISC_DIR = re.compile(r"(?i)^(?:cd|disc|disco|dvd)[._ ]?\d{1,2}$")


# ---------------------------------------------------------------- nomi dei file
def clean(text: str) -> str:
    """Punti e underscore dei nomi «da release» diventano spazi; via le parentesi quadre e i trattini ai lati."""
    s = BRACKETS.sub(" ", text or "")
    s = re.sub(r"\.(?=\S)", " ", s)  # «Film.2020» sì, «feat. X» e «Dr. Strange» no
    s = re.sub(r"\s+", " ", s.replace("_", " "))
    s = re.sub(r"[\(\[]\s*$", "", s)  # parentesi rimasta aperta dal taglio dei tag di qualità
    return s.strip(" -–—.")


def _year(text: str) -> int | None:
    found = YEAR_PAR.findall(text) or YEAR_END.findall(text)
    return int(found[-1]) if found else None


def parse_movie(name: str) -> dict:
    """«Film (2020).mkv», «Film.2020.1080p.BluRay.x264-GRP.mkv», «1917.mkv»."""
    stem = BRACKETS.sub(" ", Path(name).stem)  # i gruppi [1080p] non fanno parte del titolo
    cut = JUNK.search(stem)
    head = stem[: cut.start()] if cut else stem
    # limite noto: un numero finale del titolo («Blade Runner 2049») viene letto come anno, come in Plex/Jellyfin
    year = _year(head) or _year(stem)
    text = clean(head) or clean(stem)
    title = YEAR_PAR.sub(" ", text) if YEAR_PAR.search(text) else YEAR_END.sub(" ", text)
    return {"kind": "film", "title": clean(title) or clean(stem), "year": year}


def _season_dir(parts: list[str]) -> tuple[int | None, str]:
    """Stagione dalla cartella genitore («Season 01», «Stagione 1», «S01») e nome della serie."""
    season, series = None, ""
    for p in reversed(parts[:-1]):
        m = SEASON_DIR.match(p)
        if m:
            season = int(m.group(1))
        elif not series:
            series = p
        if season is not None and series:
            break
    return season, series


def _anime_folder_info(parts: list[str]) -> tuple[int | None, str]:
    """Cerca stagione e serie risalendo le cartelle, ignorando cartelle tematiche anime."""
    season, series = None, ""
    for p in reversed(parts[:-1]):
        m = SEASON_DIR.match(p)
        if m and season is None:
            season = int(m.group(1))
            continue
        if p.lower() in THEME_ANIME:
            continue
        if not series:
            series = p
            break
    return season, series


def parse_anime_episode(parts: str | list[str]) -> dict | None:
    """«Anime/One Piece/One Piece - 1050.mkv», «[Sub-ITA] One Piece 1050.mkv», «One Piece 01.mp4», «1050.mkv»."""
    parts = [parts] if isinstance(parts, str) else list(parts)
    if not parts:
        return None
    raw_stem = Path(parts[-1]).stem
    folder_season, folder_series = _anime_folder_info(parts)
    folder_parts_lower = [p.lower() for p in parts[:-1]]
    is_anime_folder = any(p in THEME_ANIME or p.startswith(("anime", "animazione")) for p in folder_parts_lower)
    is_op = "one piece" in raw_stem.lower() or "one piece" in folder_series.lower()
    has_anime_tag = bool(re.search(r"(?i)\[(?:sub[-_]?ita|sub[-_]?eng|subs|fansub|erai-raws|horriblesubs|judas)\]", raw_stem))
    has_large_ep = bool(re.search(r"(?i)(?:^|[\s._-])(?:e|ep|ep\.|episode|episodio)?\s*#?\s*(\d{3,4})\b", raw_stem))

    if not (is_anime_folder or is_op or has_anime_tag or has_large_ep):
        return None

    season = folder_season or 1
    series = folder_series

    # Pulisci brackets e junk
    stem = BRACKETS.sub(" ", raw_stem)
    cut = JUNK.search(stem)
    if cut:
        stem = stem[: cut.start()]
    stem = clean(stem)

    episode = None
    ep_title = ""
    extracted_series = ""

    # 1. Pattern espliciti SxxExx
    m = re.search(r"(?i)\bs(\d{1,2})[._ ]?e(\d{1,4})\b", raw_stem)
    if m:
        season = int(m.group(1))
        episode = int(m.group(2))
        extracted_series = clean(raw_stem[: m.start()])
        ep_title = clean(raw_stem[m.end():])

    # 2. Pattern esplicito E1050 o Ep 1050
    if episode is None:
        m = re.search(r"(?i)\b(?:e|ep|ep\.|episode|episodio)\s*#?\s*(\d{1,4})(?:v\d)?\b", stem)
        if m:
            episode = int(m.group(1))
            extracted_series = clean(stem[: m.start()])
            ep_title = clean(stem[m.end():])

    # 3. Separato da trattino: 'One Piece - 1050' o 'One Piece - 1050 - Titolo' o '1050 - Titolo'
    if episode is None and (" - " in stem or "-" in stem):
        chunks = [c.strip() for c in re.split(r"\s*[-–—]\s*", stem) if c.strip()]
        for i, c in enumerate(chunks):
            num_m = re.match(r"^(\d{1,4})(?:v\d)?$", c)
            if num_m:
                val = int(num_m.group(1))
                if 1888 <= val <= 2099 and not (is_anime_folder or is_op) and not folder_series:
                    continue
                episode = val
                extracted_series = " - ".join(chunks[:i])
                ep_title = " - ".join(chunks[i + 1:])
                break

    # 4. Numero isolato o trailing: '1050' o 'One Piece 1050' o 'One Piece 01'
    if episode is None:
        m = re.match(r"^(\d{1,4})(?:v\d)?$", stem)
        if m:
            val = int(m.group(1))
            if not (1888 <= val <= 2099 and not (is_anime_folder or is_op) and not folder_series):
                episode = val
        else:
            m = re.search(r"^(.*?)\s+(\d{1,4})(?:v\d)?$", stem)
            if m:
                val = int(m.group(2))
                cand_series = m.group(1).strip()
                if not (1888 <= val <= 2099 and not (is_anime_folder or is_op) and cand_series.lower() != "one piece"):
                    episode = val
                    extracted_series = cand_series

    # Se non c'è numero episodio trovato: se è One Piece o Anime folder, default ep 1
    if episode is None:
        if is_op or is_anime_folder:
            episode = 1
            extracted_series = stem
        else:
            return None

    if not series and extracted_series:
        series = clean(YEAR_PAR.sub(" ", extracted_series))

    if not series and folder_series:
        series = folder_series

    if not series and is_op:
        series = "One Piece"

    # Titolo episodio
    cut_title = JUNK.search(ep_title)
    if cut_title:
        ep_title = ep_title[: cut_title.start()]
    ep_title = clean(ep_title)

    if series and ep_title.lower().startswith(series.lower()):
        ep_title = clean(ep_title[len(series):])

    if not ep_title or SEASON_DIR.match(ep_title) or ep_title.lower() == (series or "").lower():
        ep_title = f"Episodio {episode}"

    res = {"kind": "episodio", "title": ep_title, "season": season, "episode": episode}
    if series:
        res["series"] = series
        y = _year(series)
        if y:
            res["year"] = y
    return res


def parse_episode(parts: str | list[str]) -> dict | None:
    """«Serie/Season 01/S01E02 - Titolo.mkv», «Serie/Stagione 1/02 - Titolo.mkv», «Serie/1x02.mkv»."""
    parts = [parts] if isinstance(parts, str) else list(parts)
    stem = Path(parts[-1]).stem
    season, episode, rest = None, None, stem
    for pattern in EPISODE:
        m = pattern.search(stem)
        if m:
            season, episode = int(m.group(1)), int(m.group(2))
            rest = stem[: m.start()] + " " + stem[m.end():]
            break
    folder_season, series = _season_dir(parts)
    is_serie_dir = any(p.lower() in THEME_SERIE for p in parts[:-1])
    eff_folder_season = folder_season or (1 if is_serie_dir else None)
    if episode is None:
        m = EPISODE_LEADING.match(stem)  # «Season 01/02 - Titolo.mkv»
        if m and eff_folder_season is not None:
            season, episode, rest = eff_folder_season, int(m.group(1)), m.group(2)
        else:  # «Season 01/Titolo - 02.mkv», convenzione degli anime
            m = EPISODE_TRAILING.search(stem)
            if not m or eff_folder_season is None:
                return None
            season, episode, rest = eff_folder_season, int(m.group(1)), stem[: m.start()]
    if season is None:
        season = eff_folder_season
    name = clean(YEAR_PAR.sub(" ", clean(series))) if series else ""
    title = clean(rest)
    cut = JUNK.search(title)  # «Serie.S01E02.Titolo.1080p.WEB-DL» -> «Serie Titolo»
    if cut:
        title = clean(title[: cut.start()])
    if name and title.lower().startswith(name.lower()):
        after = title[len(name):len(name) + 1]
        if not after or not after.isalnum():  # «Serie.Titolo», «Serie - Titolo»: la serie era anche nel nome file
            title = title[len(name):].strip(" -–—.:")
    title = title.strip(" -")
    if not title or SEASON_DIR.match(title):
        title = f"Episodio {episode}"
    out = {"kind": "episodio", "title": title, "season": season, "episode": episode}
    if name:
        out["series"] = name
    year = _year(series) if series else None
    if year:
        out["year"] = year
    return out


def parse_track(parts: str | list[str]) -> dict:
    """«Artista/Album/01 - Titolo.flac»; l'artista e' la prima cartella, l'album la piu' profonda (salvo «CD1»)."""
    parts = [parts] if isinstance(parts, str) else list(parts)
    stem = Path(parts[-1]).stem
    track, title = None, clean(stem)
    m = TRACK_PREFIX.match(stem)
    if m:
        track, title = int(m.group(1)), clean(m.group(2))
    dirs = parts[:-1]
    artist = clean(dirs[0]) if len(dirs) > 1 else ""
    album = next((clean(d) for d in reversed(dirs[1:]) if not DISC_DIR.match(d)), "")
    if " - " in title:  # «Artista - Titolo»: la prima parte è l'artista, se non lo conosciamo già
        head, tail = (x.strip() for x in title.split(" - ", 1))
        if head and (not artist or head.lower() == artist.lower()):
            artist, title = artist or head, tail
    out = {"kind": "brano", "title": title or clean(stem), "album": album}
    if artist:
        out["series"] = artist
    if track is not None:
        out["track"] = track
    return out


def identify(relpath: str | Path) -> dict:
    """Percorso relativo alla cartella scelta -> metadati (dizionario vuoto se non e' un media riconosciuto)."""
    parts = [str(p) for p in Path(relpath).parts if str(p) not in ("", ".")]
    if not parts:
        return {}
    ext = Path(parts[-1]).suffix.lower()
    if ext in AUDIO:
        return parse_track(parts)
    if ext in VIDEO:
        folder_parts_lower = [p.lower() for p in parts[:-1]]
        is_film = any(p in THEME_FILM for p in folder_parts_lower)
        is_anime = any(p in THEME_ANIME or p.startswith(("anime", "animazione")) for p in folder_parts_lower)
        is_serie = any(p in THEME_SERIE for p in folder_parts_lower)

        # 1. Se la cartella e' Film/Movies, prioritariamente e' un film
        if is_film:
            return parse_movie(parts[-1])

        # 2. Riconoscimento anime (pattern o One Piece o cartella anime)
        anime = parse_anime_episode(parts)
        if anime:
            return anime

        # 3. Episodio standard (s01e02, 1x02, ecc.)
        ep = parse_episode(parts)
        if ep:
            return ep

        # 4. Se la cartella e' Anime o Serie, non farlo MAI ricadere in parse_movie
        if is_anime:
            stem = Path(parts[-1]).stem
            _, series = _anime_folder_info(parts)
            return {"kind": "episodio", "title": clean(stem) or "Episodio 1", "series": series or clean(stem), "season": 1, "episode": 1}

        if is_serie:
            stem = Path(parts[-1]).stem
            season, series = _season_dir(parts)
            out = {"kind": "episodio", "title": clean(stem) or "Episodio 1", "season": season or 1, "episode": 1}
            if series:
                out["series"] = series
            return out

        # 5. Fallback a film
        return parse_movie(parts[-1])
    return {}


# ---------------------------------------------------------------- archivio
WATCHLIST_STATUSES = ("plan_to_watch", "watching", "on_hold", "completed", "dropped")
WATCHLIST_PRIORITIES = ("high", "medium", "low")

SCHEMA = """
CREATE TABLE IF NOT EXISTS roots(path TEXT PRIMARY KEY, added REAL);
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, series TEXT DEFAULT '', album TEXT DEFAULT '',
  season INTEGER, episode INTEGER, track INTEGER, year INTEGER, duration REAL,
  path TEXT NOT NULL, poster TEXT DEFAULT '', root TEXT NOT NULL, size INTEGER, mtime REAL,
  backdrop TEXT DEFAULT '', overview TEXT DEFAULT '', genres TEXT DEFAULT '',
  pos REAL DEFAULT 0, seen INTEGER DEFAULT 0, updated REAL);
CREATE INDEX IF NOT EXISTS items_kind ON items(kind);
CREATE INDEX IF NOT EXISTS items_root ON items(root);
CREATE TABLE IF NOT EXISTS watchlist (
    item_key TEXT PRIMARY KEY,
    item_id TEXT,
    source TEXT DEFAULT 'media-locale',
    title TEXT NOT NULL,
    kind TEXT DEFAULT 'film',
    series TEXT,
    poster TEXT,
    backdrop TEXT,
    year INTEGER,
    genre TEXT,
    overview TEXT,
    url TEXT,
    status TEXT DEFAULT 'plan_to_watch',
    priority TEXT DEFAULT 'medium',
    rating INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    added_at REAL,
    updated_at REAL
);
"""

# colonne aggiunte dopo la prima versione dello schema: i database gia' sul disco si aggiornano al primo uso
MIGRAZIONI = (
    ("size", "INTEGER"),
    ("mtime", "REAL"),
    ("backdrop", "TEXT DEFAULT ''"),
    ("overview", "TEXT DEFAULT ''"),
    ("genres", "TEXT DEFAULT ''"),
)
_MIGRATI: set[str] = set()


def db_path(cfg) -> Path:
    from pozzo.app.extensions import user_dir
    return user_dir(cfg, "media-locale-cache") / "media.db"


def connect(path: Path) -> sqlite3.Connection:
    """Connessione nuova a ogni uso: le rotte girano su thread diversi del server."""
    c = sqlite3.connect(str(path), timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    if str(path) not in _MIGRATI:
        colonne = {r["name"] for r in c.execute("PRAGMA table_info(items)")}
        for nome, tipo in MIGRAZIONI:
            if nome not in colonne:
                c.execute(f"ALTER TABLE items ADD COLUMN {nome} {tipo}")
        c.commit()
        _MIGRATI.add(str(path))
    return c


def _poster(dirpath: str, names: dict[str, str]) -> str:
    for art in ART_NAMES:
        if art in names:
            return str(Path(dirpath) / names[art])
    return ""


def scan(path: Path, roots: list[str], log=print) -> int:
    """(Ri)legge le cartelle: upsert degli item, via quelli spariti. Ritorna quanti file media ha visto.

    Incrementale: un file con percorso, dimensione, data e poster invariati non viene rianalizzato
    (`identify` non viene chiamato), quindi la scansione periodica non costa quanto la prima.
    """
    db = connect(path)
    seen = 0
    try:
        for root in roots:
            base = Path(root)
            if not base.is_dir():
                continue
            noti = {r["id"]: (r["size"], r["mtime"], r["poster"]) for r in
                    db.execute("SELECT id, size, mtime, poster FROM items WHERE root=?", (str(base),))}
            for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: log(f"media-locale: {e}")):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d.lower() not in SKIP_DIRS)
                poster = _poster(dirpath, {f.lower(): f for f in filenames})
                for fn in sorted(filenames):
                    p = Path(dirpath) / fn
                    if p.suffix.lower() not in MEDIA:
                        continue
                    item_id = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:12]
                    try:
                        st = p.stat()
                    except OSError:  # file sparito mentre si legge la cartella
                        continue
                    if noti.get(item_id) == (st.st_size, st.st_mtime, poster):
                        seen += 1
                        continue
                    info = identify(p.relative_to(base))
                    if not info:
                        continue
                    db.execute(
                        "INSERT INTO items(id, kind, title, series, album, season, episode, track, year, path, poster,"
                        " root, size, mtime, updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
                        " kind=excluded.kind, title=excluded.title, series=excluded.series, album=excluded.album,"
                        " season=excluded.season, episode=excluded.episode, track=excluded.track, year=excluded.year,"
                        " path=excluded.path, poster=excluded.poster, root=excluded.root, size=excluded.size,"
                        " mtime=excluded.mtime, updated=excluded.updated",
                        (item_id, info["kind"], info["title"], info.get("series") or "", info.get("album") or "",
                         info.get("season"), info.get("episode"), info.get("track"), info.get("year"),
                         str(p), poster, str(base), st.st_size, st.st_mtime, time.time()))
                    seen += 1
            db.commit()
            gone = [r["id"] for r in db.execute("SELECT id, path FROM items WHERE root=?", (str(base),))
                    if not Path(r["path"]).is_file()]
            db.executemany("DELETE FROM items WHERE id=?", [(i,) for i in gone])
            db.commit()
    finally:
        db.close()
    return seen


def to_item(r) -> dict:
    """Riga del database -> MediaItem del contratto."""
    it = {"id": r["id"], "kind": r["kind"], "title": r["title"], "source": "media-locale", "seen": bool(r["seen"])}
    if r["series"]:
        it["series"] = r["series"]
    if r["album"]:
        it["album"] = r["album"]
    for key in ("season", "episode", "year"):
        if r[key] is not None:
            it[key] = r[key]
    if r["duration"]:
        it["duration"] = round(float(r["duration"]), 1)
    if r["poster"]:
        p = str(r["poster"])
        it["poster"] = p if p.startswith(("http://", "https://")) else f"/plugin-api/media-locale/artwork?id={r['id']}"
    for key in ("backdrop", "overview", "genres"):
        try:
            if r[key]:
                it[key] = r[key]
        except (IndexError, KeyError):
            pass
    if r["pos"]:
        it["resume_pos"] = round(float(r["pos"]), 1)
    return it


def inside(path: Path, roots: list[Path]) -> bool:
    """Il file sta davvero dentro una cartella scelta dall'utente (nessun percorso arbitrario dalle rotte)."""
    try:
        p = path.resolve()
    except OSError:
        return False
    return any(p == r or r in p.parents for r in roots)


def _roots(conn) -> list[Path]:
    return [Path(r["path"]) for r in conn.execute("SELECT path FROM roots ORDER BY path")]


def _check_root(raw) -> Path:
    raw = str(raw or "").strip()
    if not raw or len(raw) > 1000:
        raise HTTPException(400, "percorso mancante o troppo lungo")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise HTTPException(400, "serve un percorso assoluto")
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise HTTPException(400, "la cartella non esiste")
    if not p.is_dir():
        raise HTTPException(400, "il percorso non è una cartella")
    if p.parent == p:  # la radice di un disco: scansionarla intera bloccherebbe l'app per ore
        raise HTTPException(400, "scegli una cartella, non la radice del disco")
    return p


def _row(conn, item_id: str):
    row = conn.execute("SELECT * FROM items WHERE id=?", (str(item_id or ""),)).fetchone()
    if row is None:
        raise HTTPException(404, "contenuto non trovato")
    return row


def _media_file(conn, item_id: str, column: str) -> Path:
    """Percorso di un file dell'item, solo se sta dentro una cartella scelta dall'utente."""
    p = Path(_row(conn, item_id)[column] or "")
    if not p.is_file() or not inside(p, _roots(conn)):
        raise HTTPException(404, "file non disponibile")
    return p


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


VLC_PATHS = (r"C:\Program Files\VideoLAN\VLC\vlc.exe", r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe")


def find_external_player() -> str | None:
    """mpv o VLC se ci sono (PATH, poi i percorsi standard di VLC su Windows): niente transcodifica."""
    for name in ("mpv", "vlc"):
        exe = shutil.which(name)
        if exe:
            return exe
    for exe in VLC_PATHS:
        if Path(exe).is_file():
            return exe
    return None


def open_external(path: Path) -> None:
    """Riproduzione nel lettore predefinito del sistema (niente transcodifica, niente HLS)."""
    player = find_external_player()
    if player:
        subprocess.Popen([player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "win32" and hasattr(os, "startfile"):
        os.startfile(str(path))  # noqa: S606 - percorso validato: sta in una cartella scelta dall'utente
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def register(gs):
    path = db_path(gs.cfg)
    connect(path).close()

    gs.add_library_kind({"id": "film", "label": "Film", "icon": "🎬"})
    gs.add_library_kind({"id": "serie", "label": "Serie", "icon": "📺"})
    gs.add_library_kind({"id": "musica", "label": "Musica", "icon": "🎵"})
    gs.add_player({"id": "integrato", "label": "Lettore integrato", "mode": "integrato"})
    gs.add_player({"id": "esterno", "label": "Lettore esterno (mpv, VLC o sistema)", "mode": "esterno"})

    def roots_payload() -> dict:
        conn = connect(path)
        try:
            return {"roots": [{"path": str(r), "items": conn.execute(
                "SELECT COUNT(*) FROM items WHERE root=?", (str(r),)).fetchone()[0]} for r in _roots(conn)]}
        finally:
            conn.close()

    @gs.route("list")
    def media_list(kind: str = "", query: str = "", q: str = "", limit: int = 1000):
        kind = kind if kind in KINDS else ""
        term = (query or q or "").strip()[:200]
        sql, args, where = "SELECT * FROM items", [], []
        if kind:
            where.append("kind=?")
            args.append(kind)
        if term:
            where.append("(COALESCE(title, '') LIKE ? ESCAPE '\\' OR COALESCE(series, '') LIKE ? ESCAPE '\\' OR COALESCE(album, '') LIKE ? ESCAPE '\\' OR COALESCE(overview, '') LIKE ? ESCAPE '\\')")
            like = "%" + re.sub(r"([%_\\])", r"\\\1", term) + "%"
            args += [like, like, like, like]
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY kind, COALESCE(NULLIF(series, ''), title), season, episode, track, title LIMIT ?"
        args.append(max(1, min(limit, 5000)))
        conn = connect(path)
        try:
            return [to_item(r) for r in conn.execute(sql, args)]
        finally:
            conn.close()

    @gs.route("detail")
    def media_detail(id: str = ""):
        conn = connect(path)
        try:
            return to_item(_row(conn, id))
        finally:
            conn.close()

    @gs.route("play_target")
    def media_play_target(id: str = ""):
        conn = connect(path)
        try:
            row = _row(conn, id)
            file = _media_file(conn, row["id"], "path")
            ext = file.suffix.lower()
            out = {"resume_pos": 0.0 if row["seen"] else round(float(row["pos"] or 0), 1),
                   "external": ext not in BROWSER, "mime": MIME.get(ext, "application/octet-stream"),
                   "path": str(file)}  # il percorso serve al lettore esterno, «url» al player integrato
            if ext in BROWSER:
                out["url"] = f"/plugin-api/media-locale/stream?id={row['id']}"
            return out
        finally:
            conn.close()

    @gs.route("set_progress", methods=("POST",))
    def media_set_progress(body: dict | None = Body(None), id: str = "", pos: float | None = None,
                           seen: bool | None = None, duration: float | None = None):
        data = body if isinstance(body, dict) else {}
        item_id = str(data.get("id") or id or "").strip()
        position = _num(data.get("pos", pos), 0.0)
        flag = data.get("seen", seen)
        length = _num(data.get("duration", duration), 0.0)
        conn = connect(path)
        try:
            row = _row(conn, item_id)
            known = length if length > 0 else float(row["duration"] or 0)
            watched = bool(flag) if flag is not None else bool(row["seen"])
            if known > 0 and position >= known * 0.9:  # «visto» oltre il 90%, come fa Jellyfin
                watched = True
            conn.execute("UPDATE items SET pos=?, seen=?, duration=?, updated=? WHERE id=?",
                         (0.0 if watched else max(0.0, position), 1 if watched else 0, known or None,
                          time.time(), item_id))
            conn.commit()
            return {"ok": True, "item": to_item(_row(conn, item_id))}
        finally:
            conn.close()

    @gs.route("artwork")
    def media_artwork(id: str = ""):
        conn = connect(path)
        try:
            file = _media_file(conn, id, "poster")
        finally:
            conn.close()
        return FileResponse(file, headers={"Cache-Control": "max-age=3600"})

    @gs.route("stream")
    def media_stream(id: str = ""):
        conn = connect(path)
        try:
            file = _media_file(conn, id, "path")
        finally:
            conn.close()
        return FileResponse(file, media_type=MIME.get(file.suffix.lower(), "application/octet-stream"))

    @gs.route("external", methods=("POST",))
    def media_external(body: dict | None = Body(None), id: str = ""):
        data = body if isinstance(body, dict) else {}
        conn = connect(path)
        try:
            file = _media_file(conn, str(data.get("id") or id or ""), "path")
        finally:
            conn.close()
        try:
            open_external(file)
        except OSError as e:
            raise HTTPException(500, f"il lettore esterno non si è aperto: {e}")
        return {"ok": True}

    @gs.route("roots")
    def media_roots():
        return roots_payload()

    @gs.route("roots", methods=("POST",))
    def media_roots_save(body: dict = Body(...)):
        conn = connect(path)
        try:
            if "add" in body and body["add"] is not None:
                root = _check_root(body["add"])
                if conn.execute("SELECT 1 FROM roots WHERE path=?", (str(root),)).fetchone() is None:
                    conn.execute("INSERT INTO roots(path, added) VALUES(?, ?)", (str(root), time.time()))
                    conn.commit()
            if "remove" in body and body["remove"] is not None:
                root = Path(str(body["remove"])).expanduser()
                try:
                    root = root.resolve()
                except OSError:
                    pass
                conn.execute("DELETE FROM items WHERE root=?", (str(root),))
                conn.execute("DELETE FROM roots WHERE path=?", (str(root),))
                conn.commit()
        finally:
            conn.close()
        return {"ok": True, **roots_payload()}

    @gs.route("scan", methods=("POST",))
    def media_scan():
        conn = connect(path)
        try:
            roots = [str(r) for r in _roots(conn)]
        finally:
            conn.close()
        return {"ok": True, "items": scan(path, roots, gs.log), **roots_payload()}

    @gs.route("enrich", methods=("POST",))
    def media_enrich(body: dict | None = Body(None), id: str = ""):
        data = body if isinstance(body, dict) else {}
        target_id = str(data.get("id") or id or "").strip()
        conn = connect(path)
        count = 0
        try:
            if target_id:
                rows = conn.execute("SELECT * FROM items WHERE id=?", (target_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM items WHERE poster='' OR overview='' OR overview IS NULL").fetchall()
            for r in rows:
                it = dict(r)
                updated = enrich_item(it)
                backdrop_val = updated.get("backdrop") or (r["backdrop"] if "backdrop" in r.keys() else "") or ""
                overview_val = updated.get("overview") or (r["overview"] if "overview" in r.keys() else "") or ""
                genres_val = updated.get("genres") or (r["genres"] if "genres" in r.keys() else "") or ""
                conn.execute(
                    "UPDATE items SET poster=?, backdrop=?, overview=?, genres=?, updated=? WHERE id=?",
                    (updated.get("poster") or r["poster"] or "",
                     backdrop_val,
                     overview_val,
                     genres_val,
                     time.time(), r["id"])
                )
                count += 1
            conn.commit()
            return {"ok": True, "enriched": count}
        finally:
            conn.close()

    @gs.route("watchlist")
    def media_watchlist_list(status: str = "", priority: str = ""):
        sql, args, where = "SELECT * FROM watchlist", [], []
        status = (status or "").strip()
        priority = (priority or "").strip()
        if status and status in WATCHLIST_STATUSES:
            where.append("status = ?")
            args.append(status)
        if priority and priority in WATCHLIST_PRIORITIES:
            where.append("priority = ?")
            args.append(priority)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY CASE priority WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, updated_at DESC"
        conn = connect(path)
        try:
            rows = conn.execute(sql, args).fetchall()
            return {"items": [dict(row) for row in rows]}
        finally:
            conn.close()

    @gs.route("watchlist", methods=("POST",))
    def media_watchlist_save(body: dict | None = Body(None)):
        data = body if isinstance(body, dict) else {}
        source = str(data.get("source") or "").strip() or "media-locale"
        item_id = str(data.get("item_id") or data.get("id") or "").strip()
        item_key = str(data.get("item_key") or "").strip()
        if not item_key and item_id:
            item_key = f"{source}:{item_id}"
        if not item_key:
            raise HTTPException(400, "item_key o id mancante")

        now = time.time()
        conn = connect(path)
        try:
            existing = conn.execute("SELECT * FROM watchlist WHERE item_key = ?", (item_key,)).fetchone()
            ex = dict(existing) if existing else {}

            def _pick_str(field, fallback="", allow_empty=False):
                if field in data and data[field] is not None:
                    val = str(data[field])
                    if allow_empty or val.strip():
                        return val
                return ex.get(field) if ex.get(field) is not None else fallback

            final_source = _pick_str("source", source) or "media-locale"
            final_item_id = str(data.get("item_id") or data.get("id") or ex.get("item_id") or "").strip()
            if not final_item_id and ":" in item_key:
                final_item_id = item_key.split(":", 1)[1]
            final_title = _pick_str("title", "").strip() or ex.get("title") or final_item_id or item_key
            final_kind = _pick_str("kind", "film").strip() or "film"
            final_series = _pick_str("series", ex.get("series") or "")
            final_poster = _pick_str("poster", ex.get("poster") or "")
            final_backdrop = _pick_str("backdrop", ex.get("backdrop") or "")
            final_genre = _pick_str("genre", "") or _pick_str("genres", "") or ex.get("genre") or ""
            final_overview = _pick_str("overview", ex.get("overview") or "")
            final_url = _pick_str("url", ex.get("url") or "")

            raw_year = data.get("year") if "year" in data and data.get("year") not in (None, "") else ex.get("year")
            try:
                final_year = int(raw_year) if raw_year is not None and str(raw_year).strip() != "" else None
            except (TypeError, ValueError):
                final_year = ex.get("year")

            raw_status = str(data.get("status") if "status" in data and data.get("status") is not None else (ex.get("status") or "plan_to_watch")).strip()
            final_status = raw_status if raw_status in WATCHLIST_STATUSES else (ex.get("status") if ex.get("status") in WATCHLIST_STATUSES else "plan_to_watch")

            raw_priority = str(data.get("priority") if "priority" in data and data.get("priority") is not None else (ex.get("priority") or "medium")).strip()
            final_priority = raw_priority if raw_priority in WATCHLIST_PRIORITIES else (ex.get("priority") if ex.get("priority") in WATCHLIST_PRIORITIES else "medium")

            if "rating" in data and data.get("rating") is not None:
                try:
                    final_rating = max(0, min(10, int(round(float(data["rating"])))))
                except (TypeError, ValueError):
                    final_rating = int(ex.get("rating") or 0)
            else:
                final_rating = int(ex.get("rating") or 0)

            final_notes = str(data["notes"]) if "notes" in data and data["notes"] is not None else (ex.get("notes") or "")
            added_at = ex.get("added_at") if existing and ex.get("added_at") is not None else now

            conn.execute(
                """INSERT INTO watchlist (
                    item_key, item_id, source, title, kind, series, poster, backdrop,
                    year, genre, overview, url, status, priority, rating, notes, added_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_key) DO UPDATE SET
                    item_id=excluded.item_id, source=excluded.source, title=excluded.title, kind=excluded.kind,
                    series=excluded.series, poster=excluded.poster, backdrop=excluded.backdrop, year=excluded.year,
                    genre=excluded.genre, overview=excluded.overview, url=excluded.url, status=excluded.status,
                    priority=excluded.priority, rating=excluded.rating, notes=excluded.notes,
                    added_at=excluded.added_at, updated_at=excluded.updated_at""",
                (
                    item_key, final_item_id, final_source, final_title, final_kind, final_series,
                    final_poster, final_backdrop, final_year, final_genre, final_overview, final_url,
                    final_status, final_priority, final_rating, final_notes, added_at, now
                ),
            )
            conn.commit()
            updated_row = conn.execute("SELECT * FROM watchlist WHERE item_key = ?", (item_key,)).fetchone()
            return {"ok": True, "item": dict(updated_row)}
        finally:
            conn.close()

    @gs.route("watchlist/remove", methods=("POST",))
    def media_watchlist_remove(body: dict | None = Body(None)):
        data = body if isinstance(body, dict) else {}
        key = str(data.get("item_key") or data.get("id") or data.get("item_id") or "").strip()
        if not key:
            raise HTTPException(400, "item_key o id mancante")
        conn = connect(path)
        try:
            conn.execute("DELETE FROM watchlist WHERE item_key = ? OR item_id = ?", (key, key))
            conn.commit()
            return {"ok": True, "removed": key}
        finally:
            conn.close()

    def scansione():
        conn = connect(path)
        try:
            roots = [str(r) for r in _roots(conn)]
        finally:
            conn.close()
        if roots:
            scan(path, roots, gs.log)

    gs.job("scansione-media", scansione, every=6 * 3600)
