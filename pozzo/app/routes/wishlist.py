"""Lista desideri."""

from __future__ import annotations

import httpx
import json
import threading
import time

from fastapi import APIRouter, Body, HTTPException

from ... import config as C, profilecfg as PC, stores as STORES
from ...matching import normalize


def build_router(ctx) -> APIRouter:
    _notify, cfg, events, lib, user = ctx._notify, ctx.cfg, ctx.events, ctx.lib, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ lista dei desideri
    from ... import wishlist as W
    wish_state = {"checking": False, "last": 0.0, "log": []}

    def _wish_payload():
        s = W.settings(cfg)
        items = user.wishlist()
        owned = {normalize(g["title"]) for g in lib.games if g.get("store") != "online"
                 and (g.get("store") is None or g.get("installed") or g.get("store"))}
        hist = user.wish_history()
        for w in items:
            w["owned"] = normalize(w["title"]) in owned
            w["history"] = hist.get(w["id"], [])
            w["steam"] = json.loads(w.pop("aks") or "{}").get("steam")  # le offerte complete arrivano con il dettaglio del gioco
        return {"items": items, "settings": {"country": s["country"], "threshold": s["threshold"],
                                             "has_key": bool(s["itad_key"]), "has_gg": bool(s["gg_key"])},
                "unseen": sum(1 for w in items if w["alert"] and not w["seen"]), "checking": wish_state["checking"],
                "log": wish_state["log"][-3:]}

    def _wish_check(force=False):
        if wish_state["checking"]:
            return
        wish_state["checking"] = True
        try:
            r = W.check(cfg, user, log=lambda m: wish_state["log"].append(m), force=force)
            wish_state["last"] = time.time()
            if r["alerts"]:
                events.emit("wishlist_alerts", r)
                _notify(f"💸 {len(r['alerts'])} giochi sotto la soglia di prezzo",
                        "\n".join(f"• {t}" for t in r["alerts"][:4]))
        except Exception as e:
            wish_state["log"].append(f"{type(e).__name__}: {e}")
        finally:
            wish_state["checking"] = False

    @router.get("/api/wishlist")
    def api_wishlist():
        return _wish_payload()

    @router.post("/api/wishlist/search")
    def api_wishlist_search(body: dict = Body(...)):
        q = (body.get("q") or "").strip()
        if len(q) < 2:
            return {"results": []}
        try:
            return {"results": W.search(cfg, q)}
        except Exception as e:
            raise HTTPException(502, f"Ricerca non riuscita: {e}")

    @router.post("/api/wishlist/add")
    def api_wishlist_add(body: dict = Body(...)):
        title = (body.get("title") or "").strip()
        if not title:
            raise HTTPException(400, "Serve un titolo")
        wid = body.get("id") or ("steam:" + body["steam_appid"] if body.get("steam_appid") else "t:" + normalize(title))
        target = body.get("target")
        user.wish_add(wid, title, str(body.get("steam_appid") or ""), str(body.get("itad_id") or ""),
                      float(target) if target not in (None, "") else None, str(body.get("cover") or ""))
        threading.Thread(target=_wish_check, daemon=True).start()
        return _wish_payload()

    @router.post("/api/wishlist/import-steam")
    def api_wishlist_import():
        prov = next((p for p in STORES.PROVIDERS if p.id == "steam"), None)
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            sid = prov(cfg, c, None, lambda *a: None).steamid() if prov else ""
        finally:
            c.close()
        if not sid:
            raise HTTPException(400, "Account Steam non trovato: collegalo in Impostazioni › Account")
        try:
            items = W.steam_wishlist(sid)
        except Exception as e:
            raise HTTPException(502, str(e))
        for it in items:
            user.wish_add("steam:" + it["steam_appid"], it["title"], it["steam_appid"])
        threading.Thread(target=_wish_check, daemon=True).start()
        return {**_wish_payload(), "imported": len(items)}

    @router.post("/api/wishlist/check")
    def api_wishlist_check(body: dict = Body(default={})):
        threading.Thread(target=_wish_check, kwargs={"force": bool(body.get("force", True))}, daemon=True).start()
        return {"ok": True}

    @router.post("/api/wishlist/settings")
    def api_wishlist_settings(body: dict = Body(...)):
        cur = dict(PC.get(cfg, "wishlist", {}))
        for k in ("itad_key", "gg_key"):
            if k in body:
                cur[k] = (body.get(k) or "").strip() or None
        if body.get("country"):
            cur["country"] = str(body["country"]).strip().upper()[:2]
        if body.get("threshold") not in (None, ""):
            cur["threshold"] = max(5, min(95, int(body["threshold"])))
        PC.put(cfg, "wishlist", cur, mirror=True)
        return _wish_payload()

    @router.post("/api/wishlist/seen")
    def api_wishlist_seen():
        for w in user.wishlist():
            if not w["seen"]:
                user.wish_update(w["id"], seen=1)
        return _wish_payload()

    @router.post("/api/wishlist/item/{wid:path}")
    def api_wishlist_edit(wid: str, body: dict = Body(...)):
        t = body.get("target")
        user.wish_update(wid, target=float(t) if t not in (None, "") else None, alert="", seen=1)
        threading.Thread(target=_wish_check, kwargs={"force": True}, daemon=True).start()
        return _wish_payload()

    @router.delete("/api/wishlist/item/{wid:path}")
    def api_wishlist_delete(wid: str):
        user.wish_delete(wid)
        return _wish_payload()

    @router.get("/api/wishlist/prices/{wid:path}")
    def api_wishlist_prices(wid: str):
        """Dettaglio dei prezzi di un gioco: Steam, key piu' economica (GG.deals), offerte degli store (ITAD) e storico."""
        w = next((x for x in user.wishlist() if x["id"] == wid), None)
        if not w:
            raise HTTPException(404, "Gioco non nella lista")
        d = json.loads(w["aks"] or "{}")
        s = W.settings(cfg)
        if s["itad_key"] and w["itad_id"] and time.time() - (d.get("hist_at") or 0) > 24 * 3600:
            try:  # storico di Steam da ITAD: una volta al giorno
                with httpx.Client(headers=W.UA, timeout=20) as c:
                    d["hist"], d["hist_at"] = W.itad_history(c, s["itad_key"], w["itad_id"], s["country"]), time.time()
                user.wish_update(wid, aks=json.dumps(d))
            except (httpx.HTTPError, ValueError) as e:
                wish_state["log"].append(f"IsThereAnyDeal, storico: {type(e).__name__}: {e}")
        return {"id": wid, "title": w["title"], "steam_appid": w["steam_appid"], "checked": w["checked"],
                "currency": w["currency"] or "EUR", "detail": d, "history": user.wish_history(3650).get(wid, []),
                "key_low": w["key_low"], "key_url": w["key_url"], "has_itad": bool(s["itad_key"]), "has_gg": bool(s["gg_key"])}

    def _wish_loop():
        time.sleep(30)
        while True:
            if user.wishlist() and time.time() - wish_state["last"] > 12 * 3600:
                _wish_check()
            time.sleep(1800)

    threading.Thread(target=_wish_loop, daemon=True).start()

    return router
