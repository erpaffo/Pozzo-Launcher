"""Sincronizzazione tra PC."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request



def build_router(ctx) -> APIRouter:
    PH, SY, app, cfg, phone_hub, sync = ctx.PH, ctx.SY, ctx.app, ctx.cfg, ctx.phone_hub, ctx.sync
    router = APIRouter()

    # ------------------------------------------------------------ sincronizzazione tra PC
    def _sync_loop():
        time.sleep(15)  # dopo l'avvio, senza rallentarlo
        while True:
            c = SY.conf(cfg)
            if c.get("folder") or c.get("peers"):
                sync.run()
            time.sleep(SY.INTERVAL)

    def _sync_state():
        c = SY.conf(cfg)
        return {"folder": c.get("folder") or "", "what": c.get("what") or "personal", "pc": sync.pc(),
                "peers": [{k: p.get(k) for k in ("id", "name", "url")} for p in c.get("peers") or []],
                "pcs": [d for d in phone_hub.devices() if d.get("kind") == "pc"],
                "server": phone_hub.running(), "urls": [u.removesuffix("/m/") for u in phone_hub.urls()],
                "last": sync.last, "busy": sync.busy}

    @router.get("/api/sync")
    def api_sync():
        return _sync_state()

    @router.post("/api/sync")
    def api_sync_save(body: dict = Body(...)):
        c = SY.conf(cfg)
        if "folder" in body:
            f = str(body.get("folder") or "").strip()
            if f and not Path(f).is_dir():
                raise HTTPException(400, f"Cartella non trovata: {f}")
            c["folder"] = f
        if body.get("what") in ("personal", "all"):
            c["what"] = body["what"]
        SY.save_conf(cfg, c)
        return _sync_state()

    @router.post("/api/sync/now")
    def api_sync_now():
        sync.run()
        return _sync_state()

    @router.post("/api/sync/code")
    def api_sync_code():
        """Codice per abbinare un altro PC a questo (accende il server HTTPS sulla rete di casa se serve)."""
        if not phone_hub.running() and not phone_hub.start(app):
            raise HTTPException(500, phone_hub.error or "Server di rete non avviato")
        return {"code": phone_hub.new_code(), "minutes": PH.CODE_TTL // 60, **_sync_state()}

    @router.post("/api/sync/peer")
    def api_sync_peer(body: dict = Body(...)):
        """Abbina questo PC a un altro (che ha mostrato il codice): da qui partono gli scambi, nei due sensi."""
        raw = str(body.get("url") or "").strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if not raw:
            raise HTTPException(400, "Serve l'indirizzo dell'altro PC")
        url = f"https://{raw if ':' in raw else raw + ':' + str(PH.PORT)}"
        try:
            r = SY.request(url, "/api/sync/pair", {"code": str(body.get("code") or ""), "name": sync.pc()["pc_name"]})
        except Exception as e:
            raise HTTPException(400, f"Abbinamento non riuscito: {e}")
        c = SY.conf(cfg)
        peer = {"id": r["pc"]["pc_id"], "name": r["pc"].get("pc_name") or raw, "url": url, "token": r["token"], "fp": r["_fp"]}
        c["peers"] = [p for p in c.get("peers") or [] if p["id"] != peer["id"]] + [peer]
        SY.save_conf(cfg, c)
        threading.Thread(target=sync.run, daemon=True).start()
        return _sync_state()

    @router.delete("/api/sync/peer/{pid}")
    def api_sync_peer_delete(pid: str):
        c = SY.conf(cfg)
        c["peers"] = [p for p in c.get("peers") or [] if p["id"] != pid]
        SY.save_conf(cfg, c)
        return _sync_state()

    @router.delete("/api/sync/pcs/{did}")
    def api_sync_pc_revoke(did: str):
        phone_hub.revoke(did)
        return _sync_state()

    # raggiungibili dagli altri PC tramite il server HTTPS (remote/phone.py: PUBLIC e rotte dei PC abbinati)
    @router.post("/api/sync/pair")
    def api_sync_pair(body: dict = Body(...)):
        try:
            token = phone_hub.pair(str(body.get("code") or ""), str(body.get("name") or "PC"), kind="pc")
        except ValueError as e:
            raise HTTPException(403, str(e))
        return {"token": token, "pc": sync.pc()}

    @router.post("/api/sync/exchange")
    def api_sync_exchange(request: Request, body: dict = Body(...)):
        dev = getattr(request.state, "phone_device", None)
        if not any(d["id"] == dev and d.get("kind") == "pc" for d in phone_hub.conf["devices"]):
            raise HTTPException(403, "Solo per i PC abbinati")
        try:
            merged = sync.receive(body.get("bundles") or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"bundles": sync.bundles(), "merged": merged}

    vars(ctx).update(_sync_loop=_sync_loop)
    return router
