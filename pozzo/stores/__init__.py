"""Aggiornamento di tutti gli store PC: elenco giochi (installati e posseduti), immagini, istantanea in cache.

Ogni store salva la propria lista in cache (kv "store:<id>"): se in un secondo momento un login
scade o un client viene disinstallato, i giochi gia' noti restano visibili.

Steam, Epic e GOG hanno un account per profilo: la lista di ogni profilo e' in "store:<id>:<profilo>" (la chiave
senza profilo e' del Principale). Un gioco installato sul PC e' di tutti, uno solo posseduto e' del suo profilo
(vedi ownership.py). load_snapshots() unisce le liste: lo stesso gioco in due profili e' una sola voce.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .. import matching
from ..matching import normalize
from ..net import RateLimiter, download_media, make_client, request
from .amazon import Amazon
from .base import StoreGame
from .battlenet import BattleNet
from .epic import Epic
from .gog import Gog
from .manual import Manual
from .minecraft import Minecraft
from .netstore import NetStore
from .ports import Ports
from .pozzoremote import PozzoRemote
from .riot import Riot
from .steam import Steam, images as steam_images
from .xbox import Xbox

PROVIDERS = [Steam, Epic, Gog, Amazon, BattleNet, Riot, Xbox, Minecraft, Ports, NetStore, PozzoRemote, Manual]
BY_ID = {p.id: p for p in PROVIDERS}
STORE_ORDER = [p.id for p in PROVIDERS]


def enabled(cfg, pid: str) -> bool:
    return (getattr(cfg, "stores", {}) or {}).get(pid, {}).get("enabled", True)


PER_PROFILE = ("steam", "epic", "gog")  # store con account per profilo


def snap_key(sid: str, pid: str = "default") -> str:
    return f"store:{sid}" if pid == "default" or sid not in PER_PROFILE else f"store:{sid}:{pid}"


def load_snapshots(cache, pids=None) -> list[dict]:
    """Giochi di tutti gli store e profili (`pids`; None = quelli che hanno una lista in cache), senza doppioni. Ogni voce ha "owners": [] = condivisa, altrimenti
    i profili proprietari."""
    out: dict[tuple, dict] = {}
    if pids is None:
        pids = ["default"] + sorted({r[0].rsplit(":", 1)[1] for r in cache.db.execute(
            "SELECT k FROM kv WHERE k LIKE 'store:%:%'")})
    for p in PROVIDERS:
        for pid in (pids if p.id in PER_PROFILE else ("default",)):
            for s in cache.kv_get(snap_key(p.id, pid)) or []:
                # condiviso: installato sul PC, store del sistema, gioco a mano senza proprietario
                own = pid if p.id in PER_PROFILE and not s.get("installed") else s.get("owner") or ""
                e = out.setdefault((p.id, s["id"]), {**s, "_owners": set()})
                e["_owners"].add(own)
                e["installed"] = e.get("installed") or s.get("installed")
    for e in out.values():
        o = e.pop("_owners")
        e["owners"] = [] if "" in o else sorted(o)
    return list(out.values())


# ---------------------------------------------------------------- immagini

async def _find_art(cfg, cache, client, title: str, limiter, skip_steam: str = "") -> dict:
    """Immagini per un gioco PC senza copertina: Steam (titolo esatto), poi IGDB. Risultato in cache."""
    key = "art:" + normalize(title) + (":nosteam" if skip_steam else "")
    hit = cache.kv_get(key, max_age=90 * 86400)
    if hit:  # trovato: valido 90 giorni
        return hit
    if hit is not None and cache.kv_get(key, max_age=7 * 86400) is not None:
        return hit  # non trovato di recente: si riprova dopo una settimana
    art: dict = {}
    try:
        r = await request(client, "GET", "https://store.steampowered.com/api/storesearch/",
                          params={"term": title, "cc": "IT", "l": "italian"}, limiter=limiter)
        if r is not None and r.status_code == 200:
            hit, _ = matching.best(title, r.json().get("items", []), key=lambda it: it.get("name", ""), min_score=90)
            if hit and str(hit["id"]) != skip_steam:
                art = steam_images(str(hit["id"]))
    except Exception:
        pass
    if not art and cfg.igdb.get("client_id"):
        try:
            from ..sources.base import Context
            from ..sources.igdb import IMG, Igdb
            ig = Igdb(Context(cfg, cache, client, lambda *a: None))
            if await ig.setup(set()):
                q = title.replace('"', '\\"')
                res = await ig._post("games", f'search "{q}"; fields name,cover.image_id,artworks.image_id,'
                                              f'screenshots.image_id; where platforms = (6); limit 10;')
                g, _ = matching.best(title, [x for x in res if x.get("cover")], key=lambda x: x.get("name", ""),
                                     min_score=85)
                if g:
                    art = {"cover": IMG.format(size="t_cover_big_2x", id=g["cover"]["image_id"])}
                    wide = (g.get("artworks") or g.get("screenshots") or [None])[0]
                    if wide:
                        art["hero"] = IMG.format(size="t_1080p", id=wide["image_id"])
        except Exception:
            pass
    cache.kv_set(key, art)
    return art


async def _download_images(cfg, cache, client, games: list[dict], log, progress=None):
    media_dir = Path(cache.media_dir) / "windows"
    lim = RateLimiter(0, 16)
    search_lim = RateLimiter(3, 3)

    # 1) copertine mancanti
    need = [g for g in games if not g["images"].get("cover")]
    if need:
        arts = await asyncio.gather(*(_find_art(cfg, cache, client, g["title"], search_lim) for g in need))
        for g, art in zip(need, arts):
            for k, v in art.items():
                g["images"].setdefault(k, v)

    # 2) download (solo quelli non gia' in cache)
    jobs = []
    for g in games:
        g.setdefault("media", {})
        for kind in ("cover", "hero", "logo", "header", "icon"):
            url = g["images"].get(kind)
            if not url or g["media"].get(kind):
                continue
            safe = f"{g['store']}_{g['id']}".replace(":", "_").replace("/", "_").replace("\\", "_")
            existing = list((media_dir / kind).glob(safe + ".*")) if (media_dir / kind).exists() else []
            if existing:
                g["media"][kind] = existing[0].relative_to(cache.folder).as_posix()
                continue
            jobs.append((g, kind, url, media_dir / kind / safe))
    task = progress.add_task("Immagini giochi PC", total=len(jobs)) if progress and jobs else None

    async def one(g, kind, url, dest):
        # giochi browser: l'URL dell'immagine arriva da una pagina web qualsiasi, si scarica solo da IP pubblici
        web = g["store"] == "manual" and (g.get("launch") or {}).get("type") == "uri"
        if web:
            from ..webmeta import safe_async_client
            async with safe_async_client(timeout=15, follow_redirects=True, headers=dict(client.headers)) as c:
                p = await download_media(c, url, dest, limiter=lim)
        else:
            p = await download_media(client, url, dest, limiter=lim)
        if p:
            g["media"][kind] = p.relative_to(cache.folder).as_posix()
        if task is not None:
            progress.advance(task)

    await asyncio.gather(*(one(*j) for j in jobs))

    # 3) copertina non scaricabile (es. giochi Steam recenti, con immagini in percorsi diversi):
    #    si riprova su IGDB, e su Steam per i giochi degli altri store
    still = [g for g in games if not g["media"].get("cover")]
    if still:
        arts = await asyncio.gather(*(_find_art(cfg, cache, client, g["title"], search_lim,
                                                skip_steam=g["id"] if g["store"] == "steam" else "")
                                      for g in still))
        retry = []
        for g, art in zip(still, arts):
            safe = f"{g['store']}_{g['id']}".replace(":", "_").replace("/", "_").replace("\\", "_")
            for kind, url in art.items():
                if not g["media"].get(kind) or kind == "cover":
                    retry.append((g, kind, url, media_dir / kind / safe))
        await asyncio.gather(*(one(*j) for j in retry))
    # Steam: alcuni giochi vecchi non hanno la copertina verticale -> si usa la testata
    for g in games:
        if not g["media"].get("cover") and g["media"].get("header"):
            g["media"]["cover_wide"] = g["media"]["header"]


async def refresh(cfg, cache, log=print, only: list[str] | None = None, progress=None, images: bool = True) -> dict:
    """Aggiorna gli store (tutti o solo `only`) e salva le istantanee in cache.
    images=False salta la ricerca e il download delle copertine (aggiunta rapida di giochi a mano)."""
    from .. import profilecfg as PC
    summary = {}
    async with make_client() as client:
        for P in PROVIDERS:
            if only and P.id not in only:
                continue
            if not enabled(cfg, P.id):
                continue
            # store con account: una lista per profilo (il principale sempre, gli altri solo con l'account collegato)
            for pid in PC.profile_ids(cfg) if P.id in PER_PROFILE else ["default"]:
                with PC.override(pid):
                    prov = P(cfg, cache, client, log)
                    k = snap_key(P.id, pid)
                    try:
                        if not prov.detected() or (pid != "default" and not prov.account().get("connected")):
                            if cache.kv_get(k):  # store disinstallato o account scollegato: niente giochi fantasma
                                cache.kv_set(k, [])
                            continue
                        games = [g.to_dict() for g in await prov.fetch()]
                    except Exception as e:
                        log(f"{P.name}: errore: {type(e).__name__}: {e}")
                        continue
                # conserva le immagini gia' scaricate
                old = {g["id"]: g for g in cache.kv_get(k) or []}
                for g in games:
                    if g["id"] in old:
                        g["media"] = old[g["id"]].get("media", {})
                for g in games:
                    g.setdefault("media", {})
                if images:
                    await _download_images(cfg, cache, client, games, log, progress)
                cache.kv_set(k, games)
                s = summary.setdefault(P.id, {"games": 0, "installed": 0})
                s["games"] += len(games)
                s["installed"] += sum(1 for g in games if g["installed"])
    cache.kv_set("stores:refreshed", time.time())
    return summary


def provider(pid: str, cfg, cache, client, log=print):
    return BY_ID[pid](cfg, cache, client, log)
