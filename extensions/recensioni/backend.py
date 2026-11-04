"""Recensioni e punteggi: Metacritic (gia' nei dati del gioco), OpenCritic (RapidAPI, serve una chiave) e recensioni
degli utenti Steam (senza chiave).

GET  /plugin-api/recensioni/scores/<id gioco>
     -> {"metacritic": {score, url}|null, "opencritic": {score, recommended, tier, url}|null,
         "steam": {desc, positive, total, percent, url}|null}
GET  /plugin-api/recensioni/stato                          -> {"opencritic": true|false}
POST /plugin-api/recensioni/chiave {"opencritic_key": "."}  (vuota = rimuovi)

Ogni fonte e' in cache su disco (cache/recensioni/<id>.json): 7 giorni il risultato, 1 giorno un errore.
La cache di OpenCritic si rinnova da sola quando cambia la chiave.
"""

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Body, HTTPException

OC_HOST = "https://opencritic-api.p.rapidapi.com"
STEAM_API = "https://store.steampowered.com/appreviews/{}"
TTL_OK, TTL_FAIL = 7 * 86400, 86400


def norm(s) -> str:
    """Nome senza maiuscole, accenti e punteggiatura: per riconoscere lo stesso gioco."""
    s = unicodedata.normalize("NFD", str(s or "")).lower()
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def metacritic(row) -> dict | None:
    """Voto gia' presente nei dati del gioco (RAWG, vedi pozzo/library/ratings.py): nessuna richiesta."""
    if row["rating_critics"] is None:
        return None
    return {"score": round(row["rating_critics"] * 100),
            "url": "https://www.metacritic.com/search/" + quote(row["title"] or "", safe="") + "/"}


def steam_appid(row) -> str | None:
    m = re.search(r"(?:steam:|steampowered\.com/app/)(\d+)",f"{row['key']} {row['page'] or ''} {row['store_pages'] or ''}")
    return m.group(1) if m else None


def parse_steam(j: dict) -> dict | None:
    q = j.get("query_summary") or {}
    total = int(q.get("total_reviews") or 0)
    if not total:
        return None
    pos = int(q.get("total_positive") or 0)
    return {"desc": q.get("review_score_desc") or "", "positive": pos, "total": total, "percent": round(100 * pos / total)}


def parse_oc_game(g: dict) -> dict | None:
    s = g.get("topCriticScore")
    if not isinstance(s, (int, float)) or s < 0:  # -1 = non ancora punteggiato
        return None
    rec = g.get("percentRecommended")
    return {"score": round(s), "recommended": round(rec) if isinstance(rec, (int, float)) and rec >= 0 else None,
            "tier": g.get("tier") or None, "url": g.get("url") or f"https://opencritic.com/game/{g.get('id')}"}


def pick_oc(found, title: str) -> int | None:
    """Id del gioco con lo stesso nome: mai un titolo simile ma diverso (es. un sequel)."""
    want = norm(title)
    return next((g.get("id") for g in (found if isinstance(found, list) else []) if norm(g.get("name")) == want), None)


def _json(r: httpx.Response):
    if r.status_code in (401, 403):
        raise PermissionError("chiave RapidAPI non valida o quota esaurita")
    r.raise_for_status()
    return r.json()


def fetch_opencritic(key: str, title: str) -> dict | None:
    h = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "opencritic-api.p.rapidapi.com"}
    with httpx.Client(timeout=10, headers=h) as c:
        gid = pick_oc(_json(c.get(OC_HOST + "/game/search", params={"criteria": title})), title)
        if gid is None:
            return None
        return parse_oc_game(_json(c.get(f"{OC_HOST}/game/{gid}")))


def fetch_steam(appid: str) -> dict | None:
    with httpx.Client(timeout=10) as c:
        r = c.get(STEAM_API.format(appid), params={"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0})
        r.raise_for_status()
        d = parse_steam(r.json())
    return d and {**d, "url": f"https://store.steampowered.com/app/{appid}/"}


def cached(store: dict, name: str, fn, now: float, ident: str = "", log=print):
    """Risultato di `fn` tenuto in store[name]. Un errore non rompe la pagina: viene ricordato per un giorno."""
    e = store.get(name) or {}
    if e.get("ident") == ident and now - e.get("at", 0) < e.get("ttl", 0):
        return e.get("data")
    try:
        data, ttl = fn(), TTL_OK
    except Exception as ex:  # rete, chiave errata, risposta illeggibile
        data, ttl = None, TTL_FAIL
        log(f"Recensioni, {name}: {type(ex).__name__}: {ex}")
    store[name] = {"at": now, "ttl": ttl, "ident": ident, "data": data}
    return data


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(p: Path, store: dict):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store), encoding="utf-8")
    except OSError:  # cache non scrivibile: si richiede di nuovo la prossima volta
        pass


def register(gs):
    cache = Path(gs.cfg.cache) / "recensioni"

    def chiave() -> str:
        return str(gs.settings.get("opencritic_key") or "").strip()

    @gs.route("scores/{game_id}")
    def scores(game_id: int):
        db = Path(gs.cfg.cache) / "library.db"
        if not db.exists():
            raise HTTPException(404, "Libreria non ancora costruita")
        lib = sqlite3.connect(db)
        lib.row_factory = sqlite3.Row
        try:
            row = lib.execute("SELECT id, title, key, page, store_pages, rating_critics FROM games WHERE id=?",
                              (game_id,)).fetchone()
        finally:
            lib.close()
        if row is None:
            raise HTTPException(404, "Gioco non trovato")
        now, f, store = time.time(), cache / f"{game_id}.json", _load(cache / f"{game_id}.json")
        key = chiave()
        ident = hashlib.sha1(key.encode()).hexdigest()[:12] if key else ""
        oc = cached(store, "opencritic", lambda: fetch_opencritic(key, row["title"]), now, ident, gs.log) if key else None
        appid = steam_appid(row)
        st = cached(store, "steam", lambda: fetch_steam(appid), now, appid, gs.log) if appid else None
        _save(f, store)
        return {"metacritic": metacritic(row), "opencritic": oc, "steam": st}

    @gs.route("stato")
    def stato():
        return {"opencritic": bool(chiave())}

    @gs.route("chiave", methods=("POST",))
    def imposta(body: dict = Body(...)):
        k = str(body.get("opencritic_key") or "").strip()[:200]
        gs.save_settings({"opencritic_key": k})
        return {"opencritic": bool(k)}
