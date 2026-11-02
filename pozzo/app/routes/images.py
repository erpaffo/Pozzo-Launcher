"""Copertine e miniature, immagini remote in cache, media personalizzati."""

from __future__ import annotations

import hashlib
import httpx
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, Response

from ..server import THUMB_WIDTHS, _REMOTE_DOWN, _REMOTE_MISS, _REMOTE_SEM


def build_router(ctx) -> APIRouter:
    cfg, lib, state, thumbs_dir, user = ctx.cfg, ctx.lib, ctx.state, ctx.thumbs_dir, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ immagini
    def _thumb(src: Path, w: int) -> Path:
        h = hashlib.sha1(f"{src}:{src.stat().st_mtime_ns}".encode()).hexdigest()[:20]
        out = thumbs_dir / str(w) / f"{h}.webp"
        if out.exists():
            return out
        from ... import imgopt
        return imgopt.thumb(src, w, quality=82, dest=out, tall=3)

    def _media(g: dict) -> dict:
        """Immagini del gioco: quelle scelte dall'utente hanno la precedenza su quelle delle fonti."""
        return {**g["media"], **user.media_overrides(g["key"])}

    @router.post("/api/game/{gid}/media")
    def api_media_set(gid: int, body: dict = Body(...)):
        """Imposta un'immagine (copertina, sfondo, schermata...) scaricandola da un indirizzo scelto dall'utente."""
        g = lib.get(gid)
        kind, url_ = str(body.get("kind") or ""), str(body.get("url") or "").strip()
        if kind not in ("cover", "hero", "screenshot", "title", "wheel", "fanart", "marquee", "header", "logo", "icon"):
            raise HTTPException(400, "Tipo di immagine non valido")
        if not url_.startswith(("http://", "https://")):
            raise HTTPException(400, "Indirizzo non valido")
        rel = _fetch_remote(url_)
        if not rel:
            raise HTTPException(400, "Immagine non scaricabile")
        user.set_media(g["key"], kind, rel)
        return {"media": {k: f"/img/{gid}/{k}" for k in _media(g)}}

    @router.get("/img/{gid}/{kind}")
    def api_img(gid: int, kind: str, request: Request, w: int = 0, q: int = 0):
        """q=1 (griglia): un'immagine remota non ancora scaricata risponde subito 202 e va in coda; la pagina la
        ridisegna quando e' pronta. Senza q si aspetta il download (scheda del gioco, telefono, API)."""
        g = lib.get(gid)
        rel = _media(g).get(kind)
        if not rel:
            raise HTTPException(404)
        if rel.startswith("url:"):  # immagine remota (giochi degli store online): scaricata solo quando serve
            url_ = rel[4:]
            if q:
                rel = _remote_cached(url_)
                if not rel:
                    if _REMOTE_MISS.get(url_, 0) > time.time():
                        raise HTTPException(404)
                    _queue_cover(url_, gid)
                    return Response(status_code=202, headers={"Cache-Control": "no-store"})
            else:
                rel = _fetch_remote(url_)
            if not rel:
                raise HTTPException(404)
        src = Path(cfg.cache) / rel
        if not src.exists():
            raise HTTPException(404)
        # i numeri dei giochi cambiano quando la libreria viene ricostruita: il browser deve sempre
        # ricontrollare. L'ETag identifica il FILE (percorso + data + dimensione): se e' lo stesso si
        # risponde 304 e il browser usa la sua copia, altrimenti riceve l'immagine giusta.
        st = src.stat()
        etag = '"' + hashlib.sha1(f"{rel}:{st.st_mtime_ns}:{st.st_size}:{w}".encode()).hexdigest()[:20] + '"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        if w:
            w = min(THUMB_WIDTHS, key=lambda x: abs(x - w))
            try:
                return FileResponse(_thumb(src, w), media_type="image/webp", headers=headers)
            except Exception:
                pass  # immagine non decodificabile: si serve l'originale
        return FileResponse(src, headers=headers)

    from ...net import MAGIC, UA
    remote_exts = list(dict.fromkeys([ext for _, ext in MAGIC] + ["mp4"]))
    # un solo client per tutte le copertine: httpx.get() ne crea uno (con il suo contesto SSL) a ogni immagine e,
    # scorrendo migliaia di giochi degli store, la memoria del server cresceva di decine di MB ogni mille copertine
    remote_http = httpx.Client(timeout=httpx.Timeout(10, connect=4), follow_redirects=True, headers={"User-Agent": UA},
                               limits=httpx.Limits(max_connections=8, max_keepalive_connections=4))

    def _remote_cached(url_: str) -> str | None:
        """Immagine remota gia' scaricata (percorso relativo alla cache) o None. Niente glob: la cartella ha
        decine di migliaia di file e la griglia ne chiede decine al secondo."""
        h = hashlib.sha1(url_.encode()).hexdigest()
        folder = Path(cfg.cache) / "media" / "net"
        hit = next((p for p in (folder / f"{h}.{e}" for e in remote_exts) if p.exists()), None)
        return hit.relative_to(cfg.cache).as_posix() if hit else None

    def _fetch_remote(url_: str) -> str | None:
        from ...net import sniff
        from urllib.parse import urlparse
        h = hashlib.sha1(url_.encode()).hexdigest()
        folder = Path(cfg.cache) / "media" / "net"
        hit = _remote_cached(url_)
        if hit:
            return hit
        # piu' indirizzi separati da "|": si prova il primo che risponde (es. copertine GameTDB
        # in regioni diverse, dove non tutte esistono)
        candidates = [u.strip() for u in url_.split("|") if u.strip()][:4]
        for candidate in candidates:
            host = urlparse(candidate).hostname or ""
            with _REMOTE_SEM:
                # un host irraggiungibile (es. CDN che blocca l'IP) non deve tenere appese decine di richieste: il browser
                # ha pochi collegamenti verso l'app e le copertine dei giochi resterebbero in coda dietro a queste
                if _REMOTE_DOWN.get(host, 0) > time.time():
                    continue
                try:
                    r = remote_http.get(candidate)
                except httpx.HTTPError as e:
                    if isinstance(e, (httpx.ConnectTimeout, httpx.ConnectError)):
                        _REMOTE_DOWN[host] = time.time() + 300
                    continue
            ext = sniff(r.content[:16]) if r.status_code == 200 else None
            if not ext:
                continue
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{h}.{ext}"
            dest.write_bytes(r.content)
            if ext in ("png", "jpg", "bmp"):  # non video/animate; se non conviene o fallisce resta l'originale
                try:
                    from ... import imgopt
                    dest = imgopt.optimize(dest)
                except Exception:
                    pass
            return dest.relative_to(cfg.cache).as_posix()
        return None

    # copertine remote della griglia, scaricate in sottofondo: prima le ultime chieste (quelle sullo schermo).
    # Prima ogni richiesta restava appesa al download: con decine di copertine in coda si occupavano i thread del
    # server e i 6 collegamenti del browser, e si fermava tutta l'app (anche le pagine che non c'entrano)
    cover_q: dict[str, int] = {}  # url -> id del gioco, in ordine di richiesta
    cover_cv = threading.Condition()

    def _queue_cover(url_: str, gid: int):
        with cover_cv:
            cover_q.pop(url_, None)
            cover_q[url_] = gid
            while len(cover_q) > 300:  # le piu' vecchie sono gia' fuori dallo schermo: si richiedono se si torna li'
                del cover_q[next(iter(cover_q))]
            cover_cv.notify()

    def _cover_worker():
        while True:
            with cover_cv:
                while not cover_q:
                    cover_cv.wait()
                url_, gid = cover_q.popitem()
            try:
                ok = _fetch_remote(url_)
            except Exception:
                ok = None
            if ok:
                lib.touch([gid])
            else:
                now = time.time()
                if len(_REMOTE_MISS) > 5000:  # scorrendo tutto il catalogo diventerebbero centinaia di migliaia
                    for k in [k for k, until in _REMOTE_MISS.items() if until <= now]:
                        _REMOTE_MISS.pop(k, None)
                _REMOTE_MISS[url_] = now + 3600  # non esiste (o host giu'): non si riprova per un'ora

    for _ in range(3):  # 3 dei 4 posti di _REMOTE_SEM: uno resta libero per port, giochi gratis e schede
        threading.Thread(target=_cover_worker, daemon=True).start()

    def _pregen_thumbs():
        """Genera in background le miniature delle copertine, cosi' lo scorrimento e' fluido da subito."""
        with lib.lock:
            srcs = [Path(cfg.cache) / g["media"]["cover"] for g in lib.games
                    if "cover" in g["media"] and not g["media"]["cover"].startswith("url:")]
        state["thumbs_total"], state["thumbs_done"], state["thumbs_started"] = len(srcs), 0, time.time()

        def one(s):
            try:
                if s.exists():
                    _thumb(s, 300)
            except Exception:
                pass
            state["thumbs_done"] += 1

        with ThreadPoolExecutor(max(1, (os.cpu_count() or 4) // 2)) as ex:
            list(ex.map(one, srcs))

    REMOTE_HOSTS = ("cdn.allkeyshop.com", "www.gamerpower.com", "gamerpower.com", "cdn1.epicgames.com",
                    "shared.akamai.steamstatic.com", "cdn.akamai.steamstatic.com", "assets.isthereanydeal.com",
                    "cdn.cloudflare.steamstatic.com", "m.media-amazon.com",  # copertine Prime (feed LootScraper)
                    "media.retroachievements.org",  # icone degli obiettivi
                    "cdn2.steamgriddb.com", "ccdn.thunderstore.io", "gcdn.thunderstore.io")  # port PC e mod

    @router.get("/remote-img")
    def remote_img(u: str):
        from urllib.parse import urlparse
        if urlparse(u).hostname not in REMOTE_HOSTS:
            raise HTTPException(400)
        rel = _fetch_remote(u)
        if not rel:
            raise HTTPException(404)
        return FileResponse(Path(cfg.cache) / rel, headers={"Cache-Control": "public, max-age=604800"})

    vars(ctx).update(_media=_media, _pregen_thumbs=_pregen_thumbs, _thumb=_thumb)
    return router
