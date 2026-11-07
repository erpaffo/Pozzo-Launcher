"""RetroAchievements, HowLongToBeat per gioco, export per altri frontend, Switch."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import platforms as P
from ... import profilecfg as PC
from ... import i18n as I


def build_router(ctx) -> APIRouter:
    cfg, lib = ctx.cfg, ctx.lib
    router = APIRouter()

    # ------------------------------------------------------------ RetroAchievements: obiettivi dei giochi retro
    from ... import retroachievements as RA

    def _ra_conf() -> dict:
        return dict(PC.get(cfg, "retroachievements", {}))

    @router.get("/api/ra")
    def api_ra_state():
        c = _ra_conf()
        return {"username": c.get("username", ""), "has_key": bool(c.get("key"))}

    @router.post("/api/ra")
    def api_ra_save(body: dict = Body(...)):
        """Salva nome utente e Web API key (profilo di retroachievements.org) dopo averli provati con una richiesta."""
        c = _ra_conf()
        if "username" in body:
            c["username"] = str(body.get("username") or "").strip()
        if body.get("key"):
            c["key"] = str(body["key"]).strip()
        if c.get("username") and c.get("key"):
            try:
                with RA.client(c["username"], c["key"]) as rc:
                    RA.user_progress(rc, count=1)
            except RA.RAError as e:
                raise HTTPException(400, str(e))
        PC.set(cfg, "retroachievements", c)
        return api_ra_state()

    @router.get("/api/game/{gid}/hltb")
    def api_game_hltb(gid: int):
        """Durata di un gioco da HowLongToBeat, cercata al volo se non e' gia' in cache (stessa chiave del job)."""
        from ...cache import Cache
        from ... import hltb as H
        g = lib.game(gid)
        if g.get("store") == "online":
            return {}
        if g.get("hltb"):
            return json.loads(g["hltb"])
        key = H.cache_key(g["title"], g["platform"])
        cache = Cache(cfg.cache)
        try:
            hit = cache.kv_get(key)
            if hit is not None and time.time() - (hit.get("t") or 0) < (H.FOUND_TTL if hit.get("main") or hit.get("extra") or hit.get("complete") else H.MISS_TTL):
                return {k: v for k, v in hit.items() if k != "t"}
            client = H.Client()
            try:
                res = H.lookup(g["title"], g["platform"], search=client.search)
            except H.RateLimited as e:
                return {"error": str(e)}
            finally:
                client.close()
            cache.kv_set(key, {**res, "t": time.time()})
            return res
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        finally:
            cache.close()

    @router.get("/api/game/{gid}/ra")
    def api_game_ra(gid: int, force: int = 0):
        """Obiettivi del gioco e progresso dell'utente. Cache: catalogo della console 7 giorni, abbinamento 30 giorni,
        progresso 30 minuti (force=1 lo riscarica)."""
        g = lib.game(gid)  # serve il nome canonico
        conf = _ra_conf()
        if not (conf.get("username") and conf.get("key")):
            return {"configured": False}
        try:
            cid = RA.resolve_console_id(g["platform"])
        except KeyError:
            return {"configured": True, "supported": False}
        from ...cache import Cache
        cache = Cache(cfg.cache)
        try:
            with RA.client(conf["username"], conf["key"]) as rc:
                mk = f"ra_match:{g['key']}"
                ra_id = cache.kv_get(mk, max_age=30 * 86400)
                if ra_id is None:
                    catalog = cache.kv_get(f"ra_gamelist:{cid}", max_age=7 * 86400)
                    if catalog is None:
                        catalog = RA.game_list(rc, cid)
                        cache.kv_set(f"ra_gamelist:{cid}", catalog)
                    f = Path(g["files"][0]) if g.get("files") else None
                    # il titolo in libreria puo' essere tradotto ("Versione Smeraldo"): RetroAchievements usa i nomi
                    # inglesi, come il nome canonico (No-Intro) e di solito il nome del file
                    from ...scanner import clean_title
                    names = [n for n in dict.fromkeys([g["title"], g.get("canonical") or "", clean_title(f.stem) if f else ""]) if n]
                    md5 = None
                    if g["platform"] in RA._RAW_MD5_CONSOLES | {"snes"}:
                        # cartucce senza intestazione: l'hash RA e' l'MD5 della ROM, gia' noto dal DAT No-Intro (anche per gli .zip)
                        for p in g.get("files") or []:
                            row = cache.db.execute("SELECT data FROM files WHERE path=?", (p,)).fetchone()
                            d = json.loads(row[0]) if row else {}
                            md5 = (d.get("dat_md5") or d.get("md5") or "").lower() or None
                            if md5:
                                break
                    md5 = md5 or (RA.rom_hash(f, g["platform"]) if f else None)
                    hit = next((h for h in (RA.match_game(n, catalog, rom_md5=md5) for n in names) if h), None)
                    ra_id = hit["id"] if hit else 0
                    cache.kv_set(mk, ra_id)
                if not ra_id:
                    return {"configured": True, "supported": True, "found": False}
                pk = f"ra_prog:{conf['username']}:{ra_id}"
                prog = None if force else cache.kv_get(pk, max_age=1800)
                if prog is None:
                    prog = RA.game_progress(rc, ra_id)
                    cache.kv_set(pk, prog)
        except RA.RAError as e:
            return {"configured": True, "supported": True, "error": str(e)}
        finally:
            cache.close()
        return {"configured": True, "supported": True, "found": True, "game": prog,
                "url": f"https://retroachievements.org/game/{ra_id}"}

    # ------------------------------------------------------------ obiettivi Steam / GOG / Epic (forma unica, vedi achievements.py)
    from ... import achievements as ACH
    import threading

    def _ach_fetch(src: str, sid: str, creds: dict) -> dict:
        """Chiama il provider giusto (rete: un thread o la richiesta stessa). creds: dati gia' letti dal profilo attivo."""
        with ACH.http() as c:
            if src == "steam":
                return ACH.steam(c, creds["key"], creds["steamid"], sid)
            if src == "gog":
                t = ACH.gog_token(c, creds["refresh"])
                PC.set(cfg, "gog", {**creds["acct"], "refresh_token": t.get("refresh_token") or creds["refresh"]})
                return ACH.gog(c, t["access_token"], creds["client_id"], creds["user_id"], sid)
            t = ACH.epic_token(c, creds["refresh"])
            PC.set(cfg, "epic", {**creds["acct"], "refresh_token": t.get("refresh_token") or creds["refresh"]})
            return ACH.epic(c, t["access_token"], creds["acct"]["account_id"], creds["sandbox"], sid)

    def _ach_creds(g: dict, src: str, sid: str):
        """(creds, None) oppure (None, motivo): il motivo e' una chiave di f.ach.need.* per l'interfaccia."""
        if src == "steam":
            c = PC.get(cfg, "steam", {})
            return ({"key": c["api_key"], "steamid": c["steamid"]}, None) if c.get("api_key") and c.get("steamid") else (None, "steam_key")
        acct = dict(PC.get(cfg, src, {}))
        if not acct.get("refresh_token"):
            return None, "login"
        if src == "gog":
            cid = ACH.gog_client_id(g.get("install_dir") or "", sid)
            if not cid:
                return None, "gog_install"
            return {"refresh": acct["refresh_token"], "acct": acct, "client_id": cid, "user_id": acct.get("user_id")}, None
        ns = ACH.epic_namespace(sid)
        if not ns or not acct.get("account_id"):
            return None, "epic_install"
        return {"refresh": acct["refresh_token"], "acct": acct, "sandbox": ns}, None

    @router.get("/api/game/{gid}/achievements")
    def api_game_achievements(gid: int, force: int = 0):
        """Obiettivi del gioco di uno store (Steam, GOG, Epic). Cache 1 ora: se e' scaduta si risponde subito con i dati
        vecchi e si aggiorna in un thread (la scheda li ricarica col pulsante), senza cache o con force=1 si chiede alla rete."""
        from ...cache import Cache
        g = lib.game(gid)
        src, _, sid = (g.get("key") or "").partition("/")[2].partition(":")
        if src not in ("steam", "gog", "epic") or not sid:
            return {"supported": False}
        creds, need = _ach_creds(g, src, sid)
        if need:
            return {"supported": True, "need": need, "source": src}
        k = f"ach:{src}:{sid}"
        cache = Cache(cfg.cache)
        try:
            fresh = None if force else cache.kv_get(k, max_age=3600)
            if fresh:
                return {"supported": True, "data": fresh}
            stale = None if force else cache.kv_get(k)

            pid = PC.active(cfg)

            def run():
                c2 = Cache(cfg.cache)
                try:
                    with PC.override(pid):  # il thread non eredita il profilo del dispositivo (serve a salvare il token rinnovato)
                        c2.kv_set(k, {**_ach_fetch(src, sid, creds), "title": g["title"]})
                except ACH.AchError:
                    pass  # i dati vecchi restano
                finally:
                    c2.close()
            if stale:
                threading.Thread(target=run, daemon=True).start()
                return {"supported": True, "data": stale, "refreshing": True}
            try:
                data = {**_ach_fetch(src, sid, creds), "title": g["title"]}
            except ACH.AchError as e:
                return {"supported": True, "source": src, "error": str(e)}
            cache.kv_set(k, data)
            return {"supported": True, "data": data}
        finally:
            cache.close()

    @router.get("/api/achievements")
    def api_achievements():
        """Totali per store dei giochi di cui gli obiettivi sono gia' in cache (si caricano aprendo la scheda del gioco)."""
        from ...cache import Cache
        cache = Cache(cfg.cache)
        try:
            rows = cache.db.execute("SELECT v FROM kv WHERE k LIKE 'ach:%'").fetchall()
        finally:
            cache.close()
        stores: dict[str, dict] = {}
        games = []
        for (v,) in rows:
            d = json.loads(v)
            if not d.get("total"):
                continue
            s = stores.setdefault(d["source"], {"games": 0, "total": 0, "unlocked": 0, "perfect": 0})
            s["games"] += 1
            s["total"] += d["total"]
            s["unlocked"] += d["unlocked"]
            s["perfect"] += d["unlocked"] == d["total"]
            games.append({"source": d["source"], "title": d.get("title") or d["game_id"], "total": d["total"], "unlocked": d["unlocked"]})
        games.sort(key=lambda x: (-x["unlocked"] / x["total"], x["title"].lower()))
        return {"stores": stores, "games": games}

    # ------------------------------------------------------------ esportazione per altri frontend (ES-DE, Pegasus)
    export_state = {"running": False}

    @router.post("/api/export/frontend")
    def api_export_frontend(body: dict = Body(...)):
        from ... import frontends
        fmt = body.get("format")
        if fmt not in ("esde", "pegasus", "html"):
            raise HTTPException(400, I.tr("s.gameinfo.formatInvalid"))
        raw = str(body.get("out_dir") or "").strip().strip('"')
        out = Path(os.path.expandvars(os.path.expanduser(raw))) if raw else Path(cfg.output) / fmt
        if export_state["running"]:
            raise HTTPException(409, I.tr("s.gameinfo.exportBusy"))
        export_state["running"] = True
        try:
            out.mkdir(parents=True, exist_ok=True)
            plats = [p for p in body.get("platforms") or [] if p in P.PLATFORMS] or None
            if fmt == "html":
                summary = frontends.export_html(Path(cfg.cache), out, plats,
                                               title=str(body.get("title") or "La mia libreria"))
            else:
                fn = frontends.export_esde if fmt == "esde" else frontends.export_pegasus
                summary = fn(Path(cfg.cache), out, plats)
        except OSError as e:
            raise HTTPException(400, I.tr("s.gameinfo.folderNotWritable", err=e))
        finally:
            export_state["running"] = False
        return {"ok": True, "summary": summary, "games": sum(summary.values()), "out_dir": str(out),
                "index": str(out / "index.html") if fmt == "html" else None}

    # ------------------------------------------------------------ Switch: aggiornamento e DLC presenti nella cartella
    switch_keys: dict = {}

    @router.get("/api/game/{gid}/switch")
    def api_game_switch(gid: int):
        """{update, dlc} dalla cache della fonte nsp; se mancano (gioco scansionato prima) si leggono dalla cartella."""
        g = lib.get(gid)
        if g["platform"] != "switch" or not g.get("files"):
            return {}
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            nsp = (c.all_resources([g["key"]]).get(g["key"]) or {}).get("nsp") or {}
        finally:
            c.close()
        if "switch_update" in nsp or "switch_dlc" in nsp:
            return {"update": nsp.get("switch_update"), "dlc": int(nsp.get("switch_dlc") or 0)}
        folder = Path(g["files"][0])
        if not folder.is_dir():
            return {}
        from ... import switchmeta
        try:
            if "k" not in switch_keys:
                switch_keys["k"] = switchmeta.load_keys(getattr(cfg, "switch_keys", ""))
            fc = switchmeta.folder_contents(folder, switch_keys["k"])
        except Exception as e:  # chiavi mancanti o pacchetto illeggibile: nessuna informazione, nessun errore
            return {"error": f"{type(e).__name__}: {e}"[:160]}
        return {"update": fc.get("update_display") or (str(fc["update"]) if fc.get("update") is not None else None),
                "dlc": fc.get("dlc") or 0}

    return router
