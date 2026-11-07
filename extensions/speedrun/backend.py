"""Speedrun: record del mondo e link a speedrun.com per i giochi della libreria.

GET /plugin-api/speedrun/record?id=<id gioco>
    -> {"nome", "link", "categorie": [{"nome", "giocatore", "tempo", "link"}], "errore": ""}

Rete solo verso www.speedrun.com (API v1, senza chiave). Cache su disco per gioco (TTL 24 ore). Su errore si tengono i dati
vecchi e si aspetta prima di riprovare (backoff esponenziale per gioco). Almeno MIN_GAP secondi tra due richieste.
"""

import json
import sqlite3
import time
from pathlib import Path

import httpx
from fastapi import HTTPException

API = "https://www.speedrun.com/api/v1"
UA = "PozzoLauncher/1.0"
TTL = 24 * 3600
BACKOFF_BASE = 15 * 60
BACKOFF_MAX = 6 * 3600
MIN_GAP = 1.0      # secondi tra due richieste di rete (limite di frequenza del sito)
CATEGORIE = 3      # categorie per gioco: basta il record delle principali
_ultimo = 0.0


def _tempo(secondi: float) -> str:
    s = int(round(secondi))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02}:{sec:02}" if h else f"{m}:{sec:02}"


def _get(client: httpx.Client, path: str, params: dict):
    global _ultimo
    attesa = MIN_GAP - (time.time() - _ultimo)
    if attesa > 0:
        time.sleep(attesa)
    _ultimo = time.time()
    r = client.get(API + path, params=params, headers={"User-Agent": UA})
    if r.status_code != 200:
        raise httpx.HTTPError(f"HTTP {r.status_code}")
    return r.json()["data"]


def _giocatore(ref: dict, embedded: list[dict]) -> str:
    if ref.get("rel") == "guest":
        return ref.get("name") or "ospite"
    for p in embedded:
        if p.get("id") == ref.get("id"):
            return (p.get("names") or {}).get("international") or "?"
    return "?"


def wr(client: httpx.Client, titolo: str) -> dict:
    """Record del mondo: il primo risultato della ricerca per nome su speedrun.com e il primo posto delle categorie principali."""
    # shortcut: il primo risultato della ricerca puo' essere un gioco simile; quando serve, scegliere il gioco a mano
    trovati = _get(client, "/games", {"name": titolo, "max": 1})
    if not trovati:
        return {"nome": titolo, "link": "", "categorie": []}
    g = trovati[0]
    cats = _get(client, f"/games/{g['id']}", {"embed": "categories"})["categories"]["data"]
    out = []
    for c in [c for c in cats if c.get("type") == "per-game"][:CATEGORIE]:
        lb = _get(client, f"/leaderboards/{g['id']}/category/{c['id']}", {"top": 1, "embed": "players"})
        if not lb.get("runs"):
            continue
        run = lb["runs"][0]["run"]
        out.append({"nome": c["name"], "giocatore": _giocatore(run["players"][0], lb["players"]["data"]),
                    "tempo": _tempo(run["times"]["primary_t"]), "link": run.get("weblink", "")})
    return {"nome": (g.get("names") or {}).get("international") or titolo, "link": g.get("weblink", ""), "categorie": out}


def record(client: httpx.Client, cache: Path, gid: int, titolo: str, now: float, log=print) -> dict:
    p = cache / f"{gid}.json"
    meta = json.loads(p.read_text("utf-8")) if p.exists() else {}
    vuoto = {"nome": titolo, "link": "", "categorie": []}
    if not (meta.get("data") and now - meta.get("fetched_at", 0) < TTL) and now >= meta.get("next_allowed_at", 0):
        try:
            meta = {"fetched_at": now, "data": wr(client, titolo), "fails": 0, "next_allowed_at": 0, "error": ""}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as e:
            fails = meta.get("fails", 0) + 1
            log(f"[speedrun] {titolo}: {e}")
            meta.update(fails=fails, error=str(e)[:200] or type(e).__name__,
                        next_allowed_at=now + min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (fails - 1)))
        p.write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
    return {**(meta.get("data") or vuoto), "errore": meta.get("error", "")}


def _titolo(cfg, gid: int) -> str:
    p = Path(cfg.cache) / "library.db"
    if not p.exists():
        return ""
    db = sqlite3.connect(p)
    try:
        r = db.execute("SELECT title FROM games WHERE id=?", (gid,)).fetchone()
    finally:
        db.close()
    return r[0] if r else ""


def register(gs):
    from pozzo.app.extensions import user_dir
    cache = user_dir(gs.cfg, "speedrun-cache")

    @gs.route("record")
    def record_route(id: int):
        titolo = _titolo(gs.cfg, id)
        if not titolo:
            raise HTTPException(404, "gioco non in libreria")
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            return record(client, cache, id, titolo, time.time(), gs.log)
