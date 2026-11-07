"""Account degli store, aggiornamento delle librerie PC, metadati online, cataloghi."""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Body, HTTPException

from .. import jobs as J
from ... import config as C, platforms as P, profilecfg as PC, storerefresh as SR, stores as STORES
from ... import i18n as I
from ...library.build import build


def build_router(ctx) -> APIRouter:
    _claim, _pregen_thumbs, cfg, events, job, lib = ctx._claim, ctx._pregen_thumbs, ctx.cfg, ctx.events, ctx.job, ctx.lib
    state, = ctx.state,
    router = APIRouter()

    # ------------------------------------------------------------ account e store PC
    def _store_counts() -> dict:
        from ...cache import Cache
        out = {}
        c = Cache(cfg.cache)
        try:
            for p in STORES.PROVIDERS:
                snap = c.kv_get(STORES.snap_key(p.id, PC.active(cfg))) or []  # lista del profilo attivo
                out[p.id] = (len(snap), sum(1 for s in snap if s.get("installed")))
            out["_refreshed"] = c.kv_get("stores:refreshed") or 0
        finally:
            c.close()
        return out

    @router.get("/api/accounts")
    def api_accounts():
        from ...cache import Cache
        counts = _store_counts()
        c = Cache(cfg.cache)
        try:
            rows = []
            for P_ in STORES.PROVIDERS:
                prov = P_(cfg, c, None, lambda *a: None)
                try:
                    det, acc = prov.detected(), prov.account()
                except Exception as e:
                    det, acc = False, {"error": str(e)}
                total, inst = counts.get(P_.id, (0, 0))
                rows.append({"id": P_.id, "name": P_.name, "login": P_.login, "detected": det, "account": acc,
                             "enabled": STORES.enabled(cfg, P_.id), "games": total, "installed": inst,
                             "note": P_.owned_note, "login_url": getattr(P_, "login_url", None)})
        finally:
            c.close()
        return {"stores": rows, "refreshed": counts["_refreshed"], "job": job["stores"].state()}

    @router.post("/api/accounts/steam")
    def api_account_steam(body: dict = Body(...)):
        cur = dict(PC.get(cfg, "steam", {}))  # chiave API e id sono del profilo attivo
        for k in ("api_key", "steamid"):
            if k in body:
                cur[k] = (body[k] or "").strip()
        if cur.get("api_key") and cur.get("steamid"):  # prova la chiave (come RetroAchievements); la rete assente non blocca
            from ... import achievements as ACH
            try:
                with ACH.http(timeout=8) as c:
                    ACH.steam_check(c, cur["api_key"], cur["steamid"])
            except ACH.AchError as e:
                if "negato" in str(e):
                    raise HTTPException(400, str(e))
        PC.set(cfg, "steam", {k: v for k, v in cur.items() if v} or None)
        return api_accounts()

    @router.post("/api/accounts/{sid}/enabled")
    def api_account_enabled(sid: str, body: dict = Body(...)):
        if sid not in STORES.BY_ID:
            raise HTTPException(404)
        cur = dict(cfg.stores.get(sid, {}))
        cur["enabled"] = bool(body.get("enabled"))
        C.save_settings(cfg, stores={sid: cur})
        return api_accounts()

    @router.post("/api/accounts/{sid}/code")
    def api_account_code(sid: str, body: dict = Body(...)):
        """Completa il login (Epic/GOG) con il codice/pagina/URL ottenuti dalla pagina ufficiale."""
        import asyncio as _a
        from ...cache import Cache
        from ...net import make_client
        if sid not in ("epic", "gog"):
            raise HTTPException(404)

        async def go():
            c = Cache(cfg.cache)
            try:
                async with make_client() as client:
                    return await STORES.provider(sid, cfg, c, client).finish_login(body.get("code") or "")
            finally:
                c.close()
        try:
            user_name = _a.run(go())
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        _start_store_job([sid])
        return {"ok": True, "user": user_name}

    @router.post("/api/accounts/{sid}/logout")
    def api_account_logout(sid: str):
        if sid in PC.KV_KEYS:  # Epic e GOG: il token e' del profilo attivo
            PC.set(cfg, sid, None)
        return api_accounts()

    def _start_store_job(only=None):
        j = J.StoreJob(only=only)
        if not _claim("stores", j):
            raise HTTPException(409, I.tr("s.stores.storeUpdateBusy"))

        def after(stats):
            lib.load()
            events.emit("stores_refreshed", stats)
            events.emit("library_built", stats)
            threading.Thread(target=_pregen_thumbs, daemon=True).start()

        threading.Thread(target=j.run, args=(cfg, after), daemon=True).start()
        return j.state()

    @router.post("/api/stores/refresh")
    def api_stores_refresh(body: dict = Body(default={})):
        return _start_store_job(body.get("only"))

    @router.get("/api/stores/refresh")
    def api_stores_state():
        return job["stores"].state()

    @router.post("/api/stores/metadata")
    def api_storemeta_start(body: dict = Body(default={})):
        if job["stores"].status == "running":
            raise HTTPException(409, I.tr("s.stores.waitStoreUpdate"))
        j = J.StoreMetaJob(only_missing=bool(body.get("missing")))
        if not _claim("storemeta", j):
            raise HTTPException(409, I.tr("s.stores.metaBusy"))

        def after(stats):
            lib.load()
            events.emit("library_built", stats)

        threading.Thread(target=j.run, args=(cfg, after), daemon=True).start()
        return j.state()

    @router.get("/api/stores/metadata")
    def api_storemeta_state():
        return job["storemeta"].state()

    @router.post("/api/stores/metadata/cancel")
    def api_storemeta_cancel():
        job["storemeta"].stop = True
        return job["storemeta"].state()

    @router.get("/api/catalogs/{pid}")
    def api_catalog_get(pid: str):
        from ...cache import Cache
        from ...catalog import cached_info
        from ...storemeta import coverage
        c = Cache(cfg.cache)
        try:
            pages = []
            for u in cfg.catalogs.get(pid, []):
                d = cached_info(c, pid, u)
                pages.append({"url": u, "games": len(d["entries"]), "time": d["time"],
                              "type": d["type"] or (cfg.catalog_options.get(pid) or {}).get("type", "filelist"),
                              "total_pages": d["total_pages"]})
            cov = coverage(c, pid)
        finally:
            c.close()
        meta = job.get(f"netmeta:{pid}")
        return {"platform": pid, "pages": pages, "job": job["store_refresh"].state(),
                "meta": meta.state() if meta else J.NetMetaJob().state(), "meta_coverage": cov}

    @router.post("/api/catalogs/{pid}/netmeta")
    def api_catalog_netmeta(pid: str, body: dict = Body(default={})):
        """Copertine e descrizioni: GameTDB offline (subito) + lettura delle pagine dei siti.
        Un lavoro per console: piu' console possono girare insieme."""
        if pid not in P.PLATFORMS:
            raise HTTPException(404, I.tr("s.stores.consoleUnknown"))
        name = f"netmeta:{pid}"
        limit = int(body.get("limit") or 0)  # 0 = tutte le voci (circa 2 richieste al secondo)
        if not _claim(name, J.NetMetaJob(limit=max(0, min(limit, 50000)), only=[pid],
                                         search_ziperto=bool(body.get("ziperto", True)))):
            return job[name].state()
        j = job[name]
        threading.Thread(target=lambda: j.run(cfg, lambda stats: lib.load(), on_found=lib.patch_store_meta),
                         daemon=True).start()
        return j.state()

    @router.post("/api/catalogs/{pid}/netmeta/stop")
    def api_catalog_netmeta_stop(pid: str):
        j = job.get(f"netmeta:{pid}")
        if not j:
            return J.NetMetaJob().state()
        j.stop = True
        return j.state()

    @router.get("/api/pc-stores")
    def api_pc_stores():
        """Store PC non ufficiali configurati, con quanti giochi ha reso ciascun elenco."""
        from ...cache import Cache
        from ...catalog import cached_info
        c = Cache(cfg.cache)
        try:
            rows = []
            for it in (cfg.pc_stores or []):
                info = cached_info(c, "windows", it["url"])
                rows.append({"url": it["url"], "kind": it.get("kind", "direct"), "games": len(info["entries"]),
                             "type": info["type"], "time": info["time"]})
        finally:
            c.close()
        return {"stores": rows, "job": job["store_refresh"].state()}

    @router.post("/api/pc-stores")
    def api_pc_stores_set(body: dict = Body(...)):
        raw = body.get("stores") or []
        cleaned = []
        for it in raw:
            if not isinstance(it, dict):
                continue
            url = str(it.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            kind = str(it.get("kind") or "direct").lower()
            cleaned.append({"url": url, "kind": kind if kind in ("repack", "direct") else "direct"})
        C.set_setting(cfg, "pc_stores", cleaned)
        if body.get("refresh") and cleaned:
            _start_store_refresh(manual=True, only=[f"windows:{it['url']}" for it in cleaned])
        elif not cleaned:
            threading.Thread(target=lambda: (build(cfg, log=lambda m: None), lib.load()), daemon=True).start()
        return api_pc_stores()

    @router.post("/api/pc-stores/probe")
    async def api_pc_stores_probe(body: dict = Body(...)):
        """Anteprima di un indirizzo: formato, giochi nella pagina, pagine totali, primi titoli.

        Non salva nulla: serve a capire se l'elenco scelto contiene tutto il catalogo.
        """
        from ... import catalog, platforms as P
        from ...cache import Cache
        from ...net import make_client
        url = str(body.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, I.tr("s.stores.addressInvalid"))
        c = Cache(cfg.cache)
        try:
            async with make_client() as client:
                page = await catalog._get_page(cfg, c, client, "windows", url, log=lambda m: None)
        except Exception as e:
            raise HTTPException(502, I.tr("s.stores.pageUnreachable", err=f"{type(e).__name__}: {e}"))
        finally:
            c.close()
        info = catalog.describe_page(page, url, set(P.PLATFORMS["windows"].exts))
        info["url"] = url
        return info

    @router.post("/api/pc-stores/refresh")
    def api_pc_stores_refresh():
        """Anche «Leggi gli elenchi» passa dalla coda unica: se qualcosa sta girando, si accoda."""
        if not cfg.pc_stores:
            raise HTTPException(400, I.tr("s.stores.noPcStore"))
        _start_store_refresh(manual=True, only=[f"windows:{it['url']}" for it in cfg.pc_stores])
        return api_pc_stores()

    # ------------------------------------------------------------ aggiornamento di tutti gli store
    # Gli elenchi letti restano in cache.db: la libreria si ricostruisce da li', quindi all'avvio i
    # giochi degli store ci sono gia' e questo aggiornamento gira in sottofondo (in parallelo).

    def _start_store_refresh(manual: bool = False, only: list[str] | None = None) -> int:
        """Mette in coda gli store scelti (o tutti): la coda rispetta il limite «in parallelo»."""
        from ... import applog
        available = SR.targets(cfg)
        if only:
            wanted = {str(x) for x in only}
            available = [t for t in available if t["id"] in wanted or t["url"] in wanted]
            if not available:
                applog.write("piano", f"in coda rifiutato: nessuno store tra {only}")
                raise HTTPException(404, I.tr("s.stores.noneConfigured"))
        elif not available:
            applog.write("piano", "in coda rifiutato: nessuno store configurato")
            if manual:
                raise HTTPException(400, I.tr("s.stores.noStoreConfigured"))
            return 0
        added = job["store_refresh"].add(cfg, available, lambda stats: lib.load())
        applog.write("piano", f"in coda: {added} store" + (f" (scelti: {', '.join(map(str, only))})" if only
                                                           else " (tutti)"))
        return added

    @router.get("/api/store-refresh")
    def api_store_refresh():
        rows = SR.targets(cfg)
        return {"schedule": SR.settings(cfg), "last": cfg.app.get("store_schedule_last"),
                "stores": len(rows), "list": rows, "job": job["store_refresh"].state()}

    @router.post("/api/store-refresh")
    def api_store_refresh_set(body: dict = Body(...)):
        """Salva quando aggiornare gli store: all'avvio, ogni giorno a un'ora scelta, o solo a mano."""
        C.save_settings(cfg, app={"store_schedule": {"mode": str(body.get("mode") or "startup"),
                                                     "time": str(body.get("time") or "03:00"),
                                                     "workers": body.get("workers") or SR.DEFAULT_WORKERS}})
        return api_store_refresh()

    @router.post("/api/store-refresh/run")
    def api_store_refresh_run(body: dict = Body(default={})):
        """Avvio manuale: di tutti gli elenchi oppure solo di quelli indicati (`ids` o `urls`)."""
        ids = [str(x) for x in (body.get("ids") or []) + (body.get("urls") or [])]
        _start_store_refresh(manual=True, only=ids or None)
        return api_store_refresh()

    @router.post("/api/store-refresh/stop")
    def api_store_refresh_stop():
        from ... import applog
        job["store_refresh"].stop = True  # le pagine in corso finiscono, poi si ferma subito
        applog.write("piano", "interruzione richiesta")
        return job["store_refresh"].state()

    def _store_scheduler():
        """Aggiornamento automatico degli store: all'avvio oppure ogni giorno all'ora scelta."""
        import datetime as _dt

        from ... import applog
        started = False
        time.sleep(15)  # lascia finire l'avvio dell'app (libreria, plugin)
        while True:
            try:
                sch = SR.settings(cfg)
                if sch["mode"] != "manual":
                    applog.write("piano", f"controllo: modalita'={sch['mode']} ora={sch['time']} "
                                          f"ultimo={cfg.app.get('store_schedule_last')} building={state['building']}")
                if sch["mode"] == "startup" and not started:
                    if _start_store_refresh():
                        started = True
                        C.save_settings(cfg, app={"store_schedule_last": _dt.datetime.now().isoformat(timespec="minutes")})
                elif sch["mode"] == "daily":
                    now = _dt.datetime.now()
                    today = now.strftime("%Y-%m-%d")
                    if not str(cfg.app.get("store_schedule_last") or "").startswith(today):
                        hh, mm = (int(x) for x in sch["time"].split(":")[:2])
                        if now.hour * 60 + now.minute >= hh * 60 + mm and _start_store_refresh():
                            C.save_settings(cfg, app={"store_schedule_last": now.isoformat(timespec="minutes")})
                else:
                    started = True  # modalita' manuale: niente da fare
            except Exception as e:
                print(f"Pianificazione store: {e}")
                from ... import applog
                applog.write("piano", f"errore: {type(e).__name__}: {e}")
            time.sleep(60)

    threading.Thread(target=_store_scheduler, daemon=True).start()

    @router.post("/api/catalogs/{pid}")
    def api_catalog_set(pid: str, body: dict = Body(...)):
        if pid not in P.PLATFORMS:
            raise HTTPException(404, I.tr("s.stores.consoleUnknown"))
        urls = [u.strip() for u in body.get("urls", []) if u.strip().startswith(("http://", "https://"))]
        # il tipo di parser (e le eventuali classi CSS) restano quando si cambiano solo gli URL
        settings = dict(C.read_settings(cfg).get("catalogs", {}))
        current = settings.get(pid)
        opts = dict(current) if isinstance(current, dict) else {}
        opts.pop("urls", None)
        if body.get("type"):
            opts["type"] = str(body["type"])
        if urls:
            settings[pid] = {**opts, "urls": urls} if opts else urls
        else:  # nessun URL: la console esce dai cataloghi, con le sue opzioni
            settings.pop(pid, None)
        C.set_setting(cfg, "catalogs", settings)
        if body.get("refresh", True) and urls:
            _start_catalog_job(pid)
        elif not urls:
            threading.Thread(target=lambda: (build(cfg, log=lambda m: None), lib.load()), daemon=True).start()
        return api_catalog_get(pid)

    def _start_catalog_job(pid: str):
        """Anche la lettura di una console passa dalla coda unica degli store (niente più «già in corso»)."""
        urls = [f"{pid}:{u}" for u in (cfg.catalogs.get(pid) or [])]
        if not urls:
            raise HTTPException(400, I.tr("s.stores.noOnlineStore"))
        _start_store_refresh(manual=True, only=urls)

    @router.post("/api/catalogs/{pid}/refresh")
    def api_catalog_refresh(pid: str):
        _start_catalog_job(pid)
        return api_catalog_get(pid)

    vars(ctx).update(_start_store_job=_start_store_job, _start_store_refresh=_start_store_refresh)
    return router
