"""Notifiche, giochi gratis, controllo periodico."""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Body

from ... import config as C, i18n as I
from ...matching import normalize


def build_router(ctx) -> APIRouter:
    _job_rows, app, cfg, job, launcher, lib = ctx._job_rows, ctx.app, ctx.cfg, ctx.job, ctx.launcher, ctx.lib
    state, user = ctx.state, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ avvisi di Windows e coda finita
    def _notify(title: str, body: str = "", action=None):
        try:
            from ... import notify
            notify.send(cfg, title, body, action)
        except Exception:  # una notifica non deve mai fermare un lavoro
            pass

    def _busy() -> bool:
        from .. import ports_api
        return (state["building"] or any(j.status == "running" for j in job.values())
                or ports_api.PORT_JOB["status"] == "running")

    def _free_alerts():
        """Nuovi giochi gratis (non gia' visti e non posseduti): un solo avviso per quelli usciti insieme."""
        from ... import freegames as fg
        fs = C.read_settings(cfg)
        notified = set(fs.get("free_notified") or [])
        seen = set((fs.get("free_state") or {}).get("seen") or [])
        owned = {normalize(g["title"]) for g in lib.games if g.get("store") != "online"}
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            d = fg.get(c)
        finally:
            c.close()
        items = d.get("items") or []
        ids = {_free_id(i) for i in items}
        fresh = [i for i in items if _free_id(i) not in seen and _free_id(i) not in notified
                 and normalize(i.get("title") or "") not in owned]
        # la memoria si tiene solo per le offerte ancora in elenco: non cresce all'infinito
        C.set_setting(cfg, "free_notified", sorted((notified & ids) | {_free_id(i) for i in fresh}))
        if fresh and fs.get("free_state") is not None:  # la prima volta si registra e basta
            titles = [f"• {i.get('title')} ({i.get('source') or i.get('console') or ''})".strip() for i in fresh[:4]]
            extra = "\n" + I.tr("s.notify.more", n=len(fresh) - 4) if len(fresh) > 4 else ""
            _notify("🎁 " + I.tr("s.notify.freeNew", n=len(fresh)), "\n".join(titles) + extra)

    def _port_alerts():
        """Aggiornamenti dei port PC installati: un avviso per ogni versione nuova, non a ogni controllo."""
        from ... import ports as pt
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            tok = pt._token(cfg)
            inst = pt.all_installed(cfg)
            seen = dict(C.read_settings(cfg).get("ports_seen") or {})
            fresh, fresh_slugs = [], []
            for slug, man in inst.items():
                info = pt.update_info(c, man, tok)
                tag = info.get("latest") or ""
                if info.get("update") and seen.get(slug) != tag:
                    fresh.append(f"• {man.get('name') or slug} {tag}")
                    fresh_slugs.append(slug)
                    seen[slug] = tag
        finally:
            c.close()
        seen = {s: t for s, t in seen.items() if s in inst}  # port disinstallati: si toglie la memoria
        C.set_setting(cfg, "ports_seen", seen)
        if fresh:
            # un solo port: il clic apre la sua pagina; piu' port: il catalogo dei port
            _notify("🕹 " + I.tr("s.notify.portsUpdate", n=len(fresh)), "\n".join(fresh[:4]),
                    {"view": "ports", "port": fresh_slugs[0] if len(fresh_slugs) == 1 else None})

    app.state.alerts = {"free": _free_alerts, "ports": _port_alerts}  # per i test (avvisi senza rete)

    def _watch_loop():
        """Ogni 20 s: avvisi quando un lavoro finisce e, a coda vuota, spegnimento/sospensione scelti
        in Impostazioni. In sottofondo (ogni 6 e 12 ore) i controlli di giochi gratis e port aggiornati."""
        from ... import power
        prev = {r["id"]: r["status"] for r in _job_rows()}
        busy_before = False
        next_free, next_ports = time.time() + 180, time.time() + 300
        while True:
            time.sleep(20)
            try:
                rows = _job_rows()
                for r in rows:
                    if prev.get(r["id"]) == "running" and r["status"] in ("done", "error", "cancelled"):
                        _notify(r["name"], r["phase"] or (I.tr("s.notify.completed") if r["status"] == "done" else r["status"]))
                prev = {r["id"]: r["status"] for r in rows}
                if _busy():
                    busy_before = True
                    continue
                game = (launcher.running() or {}).get("status") in ("starting", "extracting", "running")
                if busy_before and not game:
                    busy_before = False
                    mode = str(cfg.app.get("after_jobs") or "none")
                    if mode in ("sleep", "shutdown"):
                        try:
                            power.schedule(mode)
                            _notify(I.tr("s.notify.jobsDone"), I.tr("s.notify.sleepSoon") if mode == "sleep"
                                    else I.tr("s.notify.shutdownSoon"))
                        except ValueError:
                            pass
                now = time.time()
                if now >= next_free:
                    next_free = now + 6 * 3600
                    _free_alerts()
                if now >= next_ports:
                    next_ports = now + 12 * 3600
                    _port_alerts()
            except Exception:  # un giro andato male non ferma i successivi
                pass

    threading.Thread(target=_watch_loop, daemon=True).start()

    # ------------------------------------------------------------ giochi gratis
    from ... import freegames as FG

    @router.get("/api/free")
    def api_free(force: int = 0):
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            d = FG.get(c, force=bool(force))
        finally:
            c.close()
        owned = {normalize(g["title"]) for g in lib.games if g.get("store") != "online"}
        wished = {normalize(w["title"]) for w in user.wishlist()}
        fs = C.read_settings(cfg).get("free_state") or {}
        seen, claimed = set(fs.get("seen") or []), set(fs.get("claimed") or [])
        items = [{**i, "owned": normalize(i["title"]) in owned, "wished": normalize(i["title"]) in wished,
                  "new": _free_id(i) not in seen, "claimed": _free_id(i) in claimed, "id": _free_id(i)}
                 for i in d.get("items", [])]
        new = sum(1 for i in items if i["new"] and not i["owned"] and not i["claimed"])
        return {"items": items, "time": d.get("time"), "errors": d.get("errors", []), "stale": d.get("stale", False),
                "new": new, "first": not fs}

    def _free_id(i: dict) -> str:
        return f"{i.get('source')}|{i.get('console')}|{normalize(i.get('title') or '')}"

    @router.post("/api/free/mark")
    def api_free_mark(body: dict = Body(...)):
        """seen=true: tutti quelli in elenco non sono piu' «nuovi»; claim=<id> + value: riscattato si/no."""
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            current = {_free_id(i) for i in (c.kv_get("freegames") or {}).get("items", [])}
        finally:
            c.close()
        fs = C.read_settings(cfg).get("free_state") or {}
        seen, claimed = set(fs.get("seen") or []), set(fs.get("claimed") or [])
        if body.get("seen"):
            seen |= current
        if body.get("claim"):
            (claimed.add if body.get("value", True) else claimed.discard)(str(body["claim"]))
        # si tengono solo le offerte ancora in elenco: le liste non crescono all'infinito
        C.set_setting(cfg, "free_state", {"seen": sorted(seen & current), "claimed": sorted(claimed & current)})
        return {"ok": True}

    vars(ctx).update(_notify=_notify)
    return router
