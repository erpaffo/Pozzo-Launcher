"""Gusto personale, serie dei giochi, consigli e classifica delle ROM: collegano al profilo attivo i moduli puri
pozzo/taste.py, franchise.py, similar.py e rankings.py. La libreria e' sempre quella condivisa: del profilo sono
solo le righe personali (ore, voti, stati) e quali giochi vede.

franchise.group e similar.recommend confrontano i titoli per somiglianza e crescono piu' che linearmente: con 160.000
voci passerebbero decine di secondi. Per questo ricevono solo i giochi che c'entrano (`related`, `shortlist`)."""

from __future__ import annotations

import threading
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from ... import franchise, ownership as OW, profilecfg as PC, rankings, similar, taste
from ...matching import normalize

AMATO_VOTO = 4  # un gioco e' «amato» con 4 stelle o piu', preferito, o finito con qualche ora di gioco
AMATO_ORE = 5
MAX_AMATI = 60
CANDIDATI = 3000  # candidati che arrivano a similar.recommend, scelti con un punteggio economico
COLLEGATI = 1500  # una parola in piu' titoli di cosi' non identifica una serie (vedi `related`)
CACHE_MAX = 16
PAROLE_VUOTE = {"the", "of", "and", "for", "with", "il", "lo", "la", "le", "di", "del", "della", "dei", "and", "to"}


def tokens(title: str) -> set[str]:
    """Parole che identificano un titolo (niente articoli, numeri e parole brevi): servono a trovare i giochi collegati."""
    return {t for t in normalize(title or "").split() if len(t) >= 4 and t not in PAROLE_VUOTE and not t.isdigit()}


def build_index(games: list[dict]) -> dict[str, list[dict]]:
    """{parola: giochi che la contengono}: si costruisce una volta per libreria e profilo (vedi `shared`)."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for g in games:
        for t in tokens(g.get("title", "")):
            idx[t].append(g)
    return idx


def related(idx: dict[str, list[dict]], target: dict, cap: int = COLLEGATI) -> list[dict]:
    """Il gioco e i giochi che dividono con lui una parola rara del titolo: la serie sta qui dentro. Le parole che
    compaiono in piu' di `cap` titoli («super», «world», «final»…) non collegano nulla: se sono tutte cosi', contano
    solo i titoli che ne hanno almeno due insieme (o i primi `cap`)."""
    mine = tokens(target.get("title", ""))
    if not mine:
        return [target]
    posts = sorted((idx.get(t, []) for t in mine), key=len)
    out = {g["id"]: g for p in posts if len(p) <= cap for g in p}
    if not out and posts:
        due = {g["id"]: g for g in posts[0]}
        out = {g["id"]: g for g in posts[1]
               if g["id"] in due} if len(posts) > 1 else dict(list(due.items())[:cap])
        out = dict(list(out.items())[:cap])
    out[target["id"]] = target
    return list(out.values())


def shortlist(games: list[dict], gusto: dict, loved: list[dict], cap: int = CANDIDATI) -> list[dict]:
    """I `cap` candidati piu' promettenti con un punteggio economico (generi e decennio del gusto, sviluppatore e
    parole di titolo dei giochi amati). Non sostituisce similar.recommend: gli toglie solo la coda irrilevante."""
    def scala(voci):
        voci = list(voci)[:12]
        top = max((p for _, p in voci), default=0)
        return {n: p / top for n, p in voci if p > 0} if top > 0 else {}

    gen, dec = scala(gusto.get("genres", [])), scala(gusto.get("decades", []))
    devs = {str(g.get("developer") or "").strip().lower() for g in loved} - {""}
    parole = set().union(*(tokens(g.get("title", "")) for g in loved)) if loved else set()
    scored = []
    for g in games:
        s = sum(gen.get(x, 0) for x in g.get("genres") or [])
        if g.get("year"):
            s += 0.5 * dec.get(str(g["year"] // 10 * 10), 0)
        if devs and str(g.get("developer") or "").strip().lower() in devs:
            s += 2
        if parole and parole & tokens(g.get("title", "")):
            s += 1.5
        if s > 0:
            scored.append((s, g["id"], g))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [g for _, _, g in scored[:cap]]


def build_router(ctx) -> APIRouter:
    cfg, lib, user = ctx.cfg, ctx.lib, ctx.user
    router = APIRouter()
    cache: dict[tuple, object] = {}
    cache_lock = threading.Lock()

    def visible() -> list[dict]:
        """Un record per gruppo (la versione principale) tra quelli che il profilo attivo vede."""
        pid = PC.active(cfg)
        with lib.lock:
            games = [g for g in lib.games if g.get("is_primary", True)]
            if lib.has_owners:
                games = [g for g in games if OW.visible(g, pid)]
        return games

    def memo(name: str, extra: tuple, build, personal_data: bool = True):
        """Stesso profilo, stessa libreria (e, se serve, stessi dati personali): stessa risposta."""
        key = (name, PC.active(cfg), lib.built_at, lib.meta_rev, user.rev if personal_data else None, extra)
        with cache_lock:
            if key in cache:
                return cache[key]
        value = build()
        with cache_lock:
            if len(cache) >= CACHE_MAX:
                cache.clear()
            cache[key] = value
        return value

    def personal(games: list[dict]) -> tuple[dict, dict]:
        """({id: record}, {id: riga personale}) per i giochi che il profilo ha toccato (ore, voto, stato, preferito)."""
        rows = user.games()
        by_id = {g["id"]: g for g in games}
        mine = {g["id"]: rows[g["key"]] for g in games if g["key"] in rows}
        return by_id, mine

    @router.get("/api/taste")
    def api_taste():
        def build():
            by_id, mine = personal(visible())
            return taste.profile(by_id, mine)
        return memo("taste", (), build)

    @router.get("/api/franchise/{gid}")
    def api_franchise(gid: int):
        games = visible()
        target = next((g for g in games if g["id"] == gid), None)
        if target is None:
            raise HTTPException(404, "Gioco sconosciuto")
        idx = memo("index", (), lambda: build_index(games), personal_data=False)
        subset = related(idx, target)
        info = franchise.of(gid, subset)
        by_id = {g["id"]: g["title"] for g in subset}
        return {**info, "titles": {i: by_id[i] for i in [*info["order"], *info["owned"]] if i in by_id}}

    @router.get("/api/recommend")
    def api_recommend(limit: int = 20, unowned: bool = True):
        limit = max(1, min(limit, 100))

        def build():
            games = visible()
            by_id, mine = personal(games)
            gusto = taste.profile(by_id, mine)
            loved = []
            for g in games:
                row = mine.get(g["id"])
                if not row or g.get("store") == "online":
                    continue
                if row.get("favorite") or (row.get("my_rating") or 0) >= AMATO_VOTO or (
                        row.get("status") == "done" and (row.get("playtime") or 0) / 3600 >= AMATO_ORE):
                    loved.append({**g, **{k: row[k] for k in ("hidden", "status", "playtime", "my_rating", "favorite")}})
            loved.sort(key=lambda c: (c.get("my_rating") or 0, c.get("playtime") or 0), reverse=True)
            loved = loved[:MAX_AMATI]
            candidates = [{**c, **{k: mine[c["id"]][k] for k in ("hidden", "status", "playtime", "my_rating", "favorite")}}
                          if c["id"] in mine else c for c in shortlist(games, gusto, loved)]
            subset = {c["id"]: c for c in [*candidates, *loved]}
            return similar.recommend(candidates, gusto, loved, franchise.group(list(subset.values())), limit=limit,
                                     include_unowned=unowned)
        return {"items": memo("recommend", (limit, unowned), build)}

    @router.get("/api/top/roms")
    def api_top_roms(console: str = "all", limit: int = 100):
        limit = max(1, min(limit, 1000))
        return {"console": console, "items": rankings.top(console, visible(), limit)}

    return router
