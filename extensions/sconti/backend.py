"""Sconti e bundle: sconti sulla lista dei desideri, bundle attivi (IsThereAnyDeal) e giochi gratis ora.

GET /plugin-api/sconti/deals    -> {"deals": [{title, store, price, regular, cut_percent, url, historical_low}]}
GET /plugin-api/sconti/bundles  -> {"bundles": [{title, store, url, expiry, mine, games, tiers}], "error": ""}
                                   senza chiave ITAD: {"bundles": [], "need_key": true, "error": ""}
                                   tiers: [{price, currency, addon, games: [titoli]}]
GET /plugin-api/sconti/free     -> {"games": [...da pozzo/freegames.py], "error": ""}

Gli sconti vengono dalla lista dei desideri gia' aggiornata dall'app (nessuna richiesta in piu'). Bundle e giochi gratis
si tengono in cache su disco 6 ore; un errore si ricorda 30 minuti e non viene mai rilanciato alla pagina.
"""

import json
import sqlite3
import time
from pathlib import Path

import httpx

from pozzo import matching
from pozzo import wishlist as W

ITAD_BUNDLES = "https://api.isthereanydeal.com/bundles/v1"  # elenco dei bundle attivi (docs: routes/bundles/bundles.v1.yaml)
TTL = 6 * 3600
ERR_TTL = 30 * 60
PAGE = 50  # massimo dell'API per pagina
MAX_PAGES = 3
UA = {"User-Agent": "PozzoLauncher/1.0"}


# ---------------------------------------------------------------- sconti
def deals(rows: list[dict]) -> list[dict]:
    """Giochi della lista dei desideri in sconto (righe di UserData.wishlist()), dal piu' scontato."""
    out = []
    for w in rows:
        p, cut = w.get("price"), w.get("cut") or 0
        if p is None or cut <= 0:
            continue
        low = w.get("low")
        out.append({"title": w["title"], "store": w.get("shop") or "", "price": p, "regular": w.get("regular"),
                    "cut_percent": cut, "url": w.get("url") or "", "historical_low": low is not None and p <= low})
    return sorted(out, key=lambda d: -d["cut_percent"])


# ---------------------------------------------------------------- bundle
def parse_bundles(items: list) -> list[dict]:
    """Risposta di /bundles/v1 (lista di bundle) -> bundle normalizzati; i bundle per adulti non si mostrano."""
    out = []
    for b in items or []:
        if not isinstance(b, dict) or not b.get("title") or b.get("isMature"):
            continue
        tiers, names = [], []
        for t in b.get("tiers") or []:
            games = [g["title"] for g in t.get("games") or [] if isinstance(g, dict) and g.get("title")]
            price = t.get("price") or {}
            tiers.append({"price": price.get("amount"), "currency": price.get("currency"), "addon": bool(t.get("addon")),
                          "games": games})
            names += games
        out.append({"title": b["title"], "store": (b.get("page") or {}).get("name") or "",
                    "url": b.get("url") or b.get("details") or "", "expiry": b.get("expiry"), "tiers": tiers,
                    "games": list(dict.fromkeys(names))})
    return out


def mark_mine(bundles: list[dict], owned: set[str]) -> list[dict]:
    """mine = il bundle contiene un gioco della lista dei desideri o della libreria (titoli normalizzati)."""
    return [{**b, "mine": any(W.owned_match(g, owned) for g in b["games"])} for b in bundles]


def fetch_bundles(key: str, country: str) -> list[dict]:
    raw, offset = [], 0
    with httpx.Client(headers=UA, timeout=20) as c:
        for _ in range(MAX_PAGES):
            r = c.get(ITAD_BUNDLES, params={"key": key, "country": country, "offset": offset, "limit": PAGE,
                                            "sort": "-publish"})
            if r.status_code in (401, 403):
                raise RuntimeError("chiave IsThereAnyDeal non valida")
            if r.status_code != 200:
                raise RuntimeError(f"IsThereAnyDeal HTTP {r.status_code}")
            page = r.json() or []
            raw += page
            if len(page) < PAGE:
                break
            offset += PAGE
    return parse_bundles(raw)


# ---------------------------------------------------------------- cache su disco
def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cached(path: Path, build, now=time.time) -> dict:
    """{"time", "ok", "data", "error"}: dalla cache se recente (6 ore; 30 minuti dopo un errore), altrimenti build().
    Se build() fallisce resta il dato precedente, se c'e', e l'errore; non rilancia mai."""
    hit = _read(path)
    if hit and now() - hit.get("time", 0) < (TTL if hit.get("ok") else ERR_TTL):
        return hit
    try:
        rec = {"time": now(), "ok": True, "data": build(), "error": ""}
    except Exception as e:  # rete, chiave, formato inatteso: la pagina mostra il messaggio, non l'app
        rec = {"time": now(), "ok": False, "data": (hit or {}).get("data"), "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return rec


# ---------------------------------------------------------------- register
def register(gs):
    from pozzo.app.extensions import user_dir
    from pozzo.sync import open_profile

    cache = user_dir(gs.cfg, "sconti-cache")

    def wish_rows() -> list[dict]:
        user = open_profile(gs.cfg, gs.cfg.app.get("profile") or "default")
        try:
            return user.wishlist()
        finally:
            user.db.close()

    def owned(rows: list[dict]) -> set[str]:
        """Titoli normalizzati: lista dei desideri piu' libreria (giochi non online)."""
        names = {matching.normalize(w["title"]) for w in rows}
        db = Path(gs.cfg.cache) / "library.db"
        if db.exists():
            lib = sqlite3.connect(db)
            try:
                names |= {matching.normalize(t) for (t,) in lib.execute(
                    "SELECT title FROM games WHERE COALESCE(store,'') != 'online'") if t}
            except sqlite3.Error:
                pass
            finally:
                lib.close()
        return names

    @gs.route("deals")
    def deals_route():
        try:
            return {"deals": deals(wish_rows()), "error": ""}
        except Exception as e:
            return {"deals": [], "error": f"{type(e).__name__}: {e}"[:200]}

    @gs.route("bundles")
    def bundles_route():
        s = W.settings(gs.cfg)
        if not s["itad_key"]:
            return {"bundles": [], "need_key": True, "error": ""}
        rec = cached(cache / f"bundles-{s['country']}.json", lambda: fetch_bundles(s["itad_key"], s["country"]))
        try:
            mine = owned(wish_rows())
        except Exception:
            mine = set()
        return {"bundles": mark_mine(rec["data"] or [], mine), "error": rec["error"]}

    @gs.route("free")
    def free_route():
        from pozzo import freegames
        from pozzo.cache import Cache

        def build():
            c = Cache(gs.cfg.cache)
            try:
                d = freegames.get(c, log=gs.log)
            finally:
                c.close()
            if not d.get("items"):
                raise RuntimeError("; ".join(d.get("errors") or ["nessun gioco gratuito trovato"]))
            return d["items"]

        rec = cached(cache / "free.json", build)
        return {"games": rec["data"] or [], "error": rec["error"]}
