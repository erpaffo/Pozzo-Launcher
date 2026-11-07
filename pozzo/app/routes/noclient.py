"""Epic, GOG e Amazon senza client: installa / aggiorna / verifica / disinstalla, DLC, salvataggi cloud, accesso Amazon.

Il lavoro lungo passa dalla coda dei download (downloads/engines/cli.py); il resto e' una chiamata breve ai programmi
(legendary, gogdl, nile) scaricati da pozzo/noclient.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I, noclient as NC, profilecfg as PC, stores as STORES
from ...downloads.engines import cli as CLI

ACTIONS = ("install", "update", "verify")


def build_router(ctx) -> APIRouter:
    cfg, lib = ctx.cfg, ctx.lib
    router = APIRouter()
    NC.setup_env(cfg)  # l'avvio dei giochi installati da qui passa dal launcher, che eredita queste variabili
    login: dict = {}  # dati dell'accesso Amazon in corso (url, client_id, code_verifier, serial)

    def _prov(store: str):
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            return STORES.provider(store, cfg, c, None)
        finally:
            c.close()

    def _game(gid: int) -> tuple[dict, str, str]:
        """(gioco, store, id da dare al programma). 404 se non e' di Epic, GOG o Amazon."""
        g = lib.game(gid)
        store = g.get("store")
        if store not in NC.STORES:
            raise HTTPException(404, I.tr("s.noclient.notSupported"))
        sid = g["key"].split(":", 1)[1]
        if store == "epic":
            sid = NC.epic_app(g.get("install_uri") or "")
        elif store == "amazon":
            lib_ = NC.amazon_library(cfg)
            hit = next((e["id"] for e in lib_ if e["id"] == sid or e["title"].casefold() == g["title"].casefold()), "")
            sid = hit or sid
        if not sid:
            raise HTTPException(400, I.tr("s.noclient.noId"))
        return g, store, sid

    @router.get("/api/game/{gid}/noclient")
    def api_noclient_info(gid: int):
        g = lib.game(gid)
        store = g.get("store")
        if store not in NC.STORES:
            return {"supported": False}
        try:
            rid = _game(gid)[2]
        except HTTPException:  # senza nome interno non si puo' installare con il programma
            return {"supported": False}
        rec = NC.installed(cfg, store).get(rid)
        return {"supported": True, "store": store, "official": _prov(store).official(), "tool": NC.STORES[store][1],
                "tool_installed": NC.available(cfg, store), "tool_version": NC.version(cfg, store),
                "account": bool(_prov(store).account().get("connected")) and (store != "amazon" or bool(NC.amazon_user(cfg))),
                "by_pozzo": bool(rec), "dlc": store in ("epic", "gog"), "cloud": store == "epic",
                "path": str(NC.default_games_dir())}

    @router.post("/api/noclient/{store}/tool")
    def api_noclient_tool(store: str):
        """Scarica (o aggiorna) legendary / gogdl / nile dalla release GitHub."""
        if store not in NC.STORES:
            raise HTTPException(404, I.tr("s.noclient.notSupported"))
        try:
            return {"ok": True, "version": NC.install_cli(cfg, store)}
        except Exception as e:  # noqa: BLE001 - rete, GitHub, checksum: il messaggio basta
            raise HTTPException(502, I.tr("s.noclient.toolFailed", err=f"{type(e).__name__}: {e}"))

    @router.post("/api/game/{gid}/noclient/{action}")
    def api_noclient_action(gid: int, action: str, body: dict = Body(default={})):
        g, store, rid = _game(gid)
        if action == "uninstall":
            try:
                NC.uninstall(cfg, store, rid)
            except RuntimeError as e:
                raise HTTPException(400, str(e))
            ctx._start_store_job([store])  # l'elenco si rilegge: il gioco torna «non installato»
            return {"ok": True}
        if action not in ACTIONS:
            raise HTTPException(404)
        if not NC.available(cfg, store):
            raise HTTPException(409, I.tr("s.noclient.toolMissing", tool=NC.STORES[store][1]))
        path = str(body.get("path") or NC.default_games_dir())
        dlcs = [str(x) for x in body.get("dlcs") or []]
        # DLC Epic: ognuno e' un'app a se' (nome interno proprio); DLC GOG: un aggiornamento del gioco con la lista
        jobs = [(d, "install", []) for d in dlcs] if store == "epic" and dlcs else [(rid, "update" if dlcs else action, dlcs)]
        try:
            NC.prepare(cfg, store)
            tasks = [ctx.downloads.add(CLI.source_of(store, r), path, name=g["title"], store=store, game_id=r, action=a,
                                       path=path, title=g["title"], profile=PC.active(cfg), dlcs=dl,
                                       with_dlcs=bool(body.get("with_dlcs"))) for r, a, dl in jobs]
        except (RuntimeError, ValueError) as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "tasks": [t.view() for t in tasks]}

    @router.get("/api/game/{gid}/noclient/dlc")
    def api_noclient_dlc(gid: int):
        _, store, rid = _game(gid)
        if not NC.available(cfg, store):
            raise HTTPException(409, I.tr("s.noclient.toolMissing", tool=NC.STORES[store][1]))
        try:
            NC.prepare(cfg, store)
            out = NC.dlc_list(cfg, store, rid)
            NC.sync_back(cfg, store)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e))
        return {"dlc": out}

    @router.post("/api/game/{gid}/noclient/saves")
    def api_noclient_saves(gid: int, body: dict = Body(default={})):
        _, store, rid = _game(gid)
        if store != "epic":
            raise HTTPException(400, I.tr("s.noclient.noCloud"))
        if body.get("direction", "sync") not in ("sync", "download", "upload"):
            raise HTTPException(400)
        try:
            NC.prepare(cfg, store)
            msg = NC.sync_saves(cfg, store, rid, body.get("direction", "sync"))
            NC.sync_back(cfg, store)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e))
        return {"ok": True, "message": msg}

    # ---- accesso Amazon (nile): indirizzo da aprire nel browser, poi si incolla l'indirizzo su cui Amazon rimanda
    @router.post("/api/noclient/amazon/login")
    def api_amazon_login():
        try:
            if not NC.available(cfg, "amazon"):
                NC.install_cli(cfg, "amazon")
            login.clear()
            login.update(NC.amazon_login_data(cfg))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, I.tr("s.noclient.toolFailed", err=f"{type(e).__name__}: {e}"))
        return {"url": login["url"]}

    @router.post("/api/noclient/amazon/code")
    def api_amazon_code(body: dict = Body(...)):
        if not login:
            raise HTTPException(400, I.tr("s.noclient.loginFirst"))
        try:
            user = NC.amazon_register(cfg, login, body.get("code") or "")
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        login.clear()
        ctx._start_store_job(["amazon"])
        return {"ok": True, "user": user}

    return router
