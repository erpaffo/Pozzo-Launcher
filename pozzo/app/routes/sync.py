"""Sincronizzazione tra PC."""

from __future__ import annotations

import base64
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

from ... import i18n as I



def build_router(ctx) -> APIRouter:
    PH, SY, app, cfg, phone_hub, sync = ctx.PH, ctx.SY, ctx.app, ctx.cfg, ctx.phone_hub, ctx.sync
    router = APIRouter()

    # ------------------------------------------------------------ salvataggi dei giochi (file veri)
    from ... import platforms as P
    from ...library import launcher as LA
    from ...library import saves as SV

    def _game(key: str) -> dict:
        try:
            return next((g for g in ctx.lib.games if g.get("key") == key), None) or {"key": key}
        except Exception:
            return {"key": key}

    def _saves_of(key: str, title: str) -> list[Path]:
        """Salvataggi del gioco come li vede la scheda del gioco: percorsi scelti a mano piu' quelli dell'emulatore
        che lo avvierebbe adesso."""
        out = list(SV.resolved_manual(cfg, key))
        g = _game(key)
        if g.get("store"):
            # shortcut: i giochi degli store usano solo i percorsi manuali, aggiungere il manifest di Ludusavi quando serve
            return out
        platform = g.get("platform") or ""
        p = P.PLATFORMS.get(platform)
        try:
            pl = LA.plan(cfg, p, ctx.user.profile(key)) if p else None
        except Exception:  # emulatore non configurato per questa console
            pl = None
        if pl:
            rom = Path(g["files"][0]) if g.get("files") else None
            try:
                found, shared = SV.game_saves(pl["emulator"], pl.get("exe"), rom_stem=rom.stem if rom else "",
                                              ids=SV.game_ids(platform, rom), rom_dir=str(rom.parent) if rom else "")
            except Exception:
                found, shared = [], []
            out.extend(found)
            out.extend(shared)
        return list(dict.fromkeys(out))

    def _playing() -> bool:
        """Gioco in esecuzione: i salvataggi non si toccano (l'emulatore li riscriverebbe)."""
        try:
            return ctx.launcher.running().get("status") in ("starting", "extracting", "running")
        except Exception:
            return True  # se non si sa, meglio non rischiare

    if hasattr(sync, "playing"):
        sync.playing = _playing
    if hasattr(sync, "saves_of"):
        sync.saves_of = _saves_of
    if hasattr(sync, "title_of"):
        sync.title_of = lambda key: _game(key).get("title") or key
    # il cancello del server di rete (remote/phone.py) lascia passare ai PC abbinati solo lo scambio: aggiunge la
    # richiesta dei singoli file di salvataggio
    try:
        if not any(p == r"/api/sync/saves/file" for _m, p in PH.PC_ALLOWED):
            PH.PC_ALLOWED = [*PH.PC_ALLOWED, ("POST", r"/api/sync/saves/file")]
            PH._PC_ALLOWED = [(m, re.compile(p + r"$")) for m, p in PH.PC_ALLOWED]
    except Exception:
        pass

    # ------------------------------------------------------------ sincronizzazione tra PC
    def _sync_loop():
        delay = 15  # dopo l'avvio, senza rallentarlo
        while not ctx.stop.wait(delay):  # esce all'arresto, prima che i database si chiudano
            c = SY.conf(cfg)
            if c.get("folder") or c.get("peers"):
                sync.run()
            delay = SY.INTERVAL

    def _sync_state():
        c = SY.conf(cfg)
        return {"folder": c.get("folder") or "", "what": c.get("what") or "personal", "pc": sync.pc(),
                "peers": [{k: p.get(k) for k in ("id", "name", "url")} for p in c.get("peers") or []],
                "pcs": [d for d in phone_hub.devices() if d.get("kind") == "pc"],
                "server": phone_hub.running(), "urls": [u.removesuffix("/m/") for u in phone_hub.urls()],
                "saves": {"enabled": bool(c.get("saves")), "games": list(c.get("saves_games") or [])},
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
                raise HTTPException(400, I.tr("s.sync.dirNotFound", f=f))
            c["folder"] = f
        if body.get("what") in ("personal", "all"):
            c["what"] = body["what"]
        if isinstance(body.get("saves"), bool):
            c["saves"] = body["saves"]
        if "saves_games" in body:
            raw = body.get("saves_games")
            if not isinstance(raw, list) or len(raw) > 2000:
                raise HTTPException(400, I.tr("s.sync.badGames"))
            keys = [k.strip() for k in raw if isinstance(k, str) and k.strip()]
            c["saves_games"] = list(dict.fromkeys(keys))[:2000]
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
            raise HTTPException(500, phone_hub.error or I.tr("s.sync.netDown"))
        return {"code": phone_hub.new_code(), "minutes": PH.CODE_TTL // 60, **_sync_state()}

    @router.post("/api/sync/peer")
    def api_sync_peer(body: dict = Body(...)):
        """Abbina questo PC a un altro (che ha mostrato il codice): da qui partono gli scambi, nei due sensi."""
        raw = str(body.get("url") or "").strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if not raw:
            raise HTTPException(400, I.tr("s.sync.needAddress"))
        url = f"https://{raw if ':' in raw else raw + ':' + str(PH.PORT)}"
        try:
            r = SY.request(url, "/api/sync/pair", {"code": str(body.get("code") or ""), "name": sync.pc()["pc_name"]})
        except Exception as e:
            raise HTTPException(400, I.tr("s.sync.pairFail", e=e))
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

    @router.get("/api/sync/saves")
    def api_sync_saves():
        """Giochi della libreria con salvataggi trovati, per scegliere cosa sincronizzare."""
        c = SY.conf(cfg)
        inc = set(c.get("saves_games") or [])
        out = []
        try:
            games = sorted(ctx.lib.games, key=lambda g: (g.get("title") or "").lower())[:500]
        except Exception:
            games = []
        for g in games:
            key = g.get("key") or ""
            if not key:
                continue
            try:
                files = sync.saves_files(key, g.get("title") or key)[0]
            except Exception:  # emulatore o cartella non raggiungibili: il gioco non compare
                files = []
            if not files:
                continue
            size = sum(f.stat().st_size for f, _rel in files if f.exists())
            out.append({"key": key, "title": g.get("title") or key, "files": len(files), "size": size,
                        "included": key in inc})
        return {"enabled": bool(c.get("saves")), "games": out}

    @router.post("/api/sync/saves/file")
    def api_sync_saves_file(request: Request, body: dict = Body(...)):
        """Un file di salvataggio per un PC abbinato, uno per richiesta (niente risposte enormi)."""
        dev = getattr(request.state, "phone_device", None)
        if not any(d["id"] == dev and d.get("kind") == "pc" for d in phone_hub.conf["devices"]):
            raise HTTPException(403, I.tr("s.sync.pcOnly"))
        key, rel = str(body.get("key") or ""), str(body.get("rel") or "")
        if not SY._safe_rel(rel):
            raise HTTPException(400, I.tr("s.sync.badSavePath"))
        if key not in (SY.conf(cfg).get("saves_games") or []):
            raise HTTPException(403, I.tr("s.sync.gameNotIncluded"))
        f = sync.saves_file(key, rel)
        if f is None:
            raise HTTPException(404, I.tr("s.sync.saveNotFound"))
        size = f.stat().st_size
        if size > SY.SAVE_REQ_MAX:
            raise HTTPException(413, I.tr("s.sync.tooBig", size=SY._mb(size), limit=SY._mb(SY.SAVE_REQ_MAX)))
        return {"data": base64.b64encode(f.read_bytes()).decode(), "sha1": SV._sha1(f), "size": size}

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
            raise HTTPException(403, I.tr("s.sync.pcOnly"))
        try:
            merged = sync.receive(body.get("bundles") or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
        out = {"bundles": sync.bundles(), "merged": merged}
        if SY.conf(cfg).get("saves"):
            # i byte li chiede chi ha avviato lo scambio (rotta /api/sync/saves/file), quindi li unisce lui
            out["saves"] = sync.saves_manifest()
        return out

    vars(ctx).update(_sync_loop=_sync_loop)
    return router
