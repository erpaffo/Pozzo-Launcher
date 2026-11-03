"""Attivita' in corso e API del telefono."""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse

from ... import platforms as P
from ..server import STATIC, _asset_version


def build_router(ctx) -> APIRouter:
    _rebuild, _start_store_refresh, activity_hidden, api_scan_start, bulk_job, job = ctx._rebuild, ctx._start_store_refresh, ctx.activity_hidden, ctx.api_scan_start, ctx.bulk_job, ctx.job
    launcher, lib, phone_hub, state = ctx.launcher, ctx.lib, ctx.phone_hub, ctx.state
    router = APIRouter()

    # ------------------------------------------------------------ telefono: attività e comandi remoti
    def _job_rows() -> list[dict]:
        """Lavori in corso o appena finiti, in forma compatta per il telefono."""
        def row(jid, name, state: dict, kind: str = "job") -> dict | None:
            if not state or state.get("status") in (None, "idle"):
                return None
            prog = None
            tasks = state.get("tasks") or []
            if tasks:
                tot = sum(t.get("total") or 0 for t in tasks)
                done = sum(t.get("done") or 0 for t in tasks)
                prog = (done / tot) if tot else None
            elif state.get("total"):
                prog = (state.get("done") or 0) / state["total"]
            log = state.get("log") or []
            if jid in activity_hidden:
                return None
            return {"id": jid, "name": name, "kind": kind, "status": state.get("status"),
                    "phase": state.get("phase") or state.get("message") or "",
                    "progress": round(prog, 3) if prog is not None else None,
                    "started": state.get("started") or 0, "finished": state.get("finished") or 0,
                    "stoppable": (jid in job_stops or jid.startswith("netmeta:")) and state.get("status") == "running"
                    and state.get("stoppable", True) and not state.get("stopping"),
                    "last": log[-1] if log else ""}

        rows = [
            row("scan", "Ricerca nuovi giochi", job["current"].state()),
            row("stores", "Store ufficiali", job["stores"].state()),
            row("storemeta", "Metadati degli store", job["storemeta"].state()),
            row("pcstores", "Store PC", job["pcstores"].state()),
            row("catalogs", "Store online", job["store_refresh"].state()),
            *(row(k, f"Copertine e descrizioni · {P.PLATFORMS[k[8:]].name if k[8:] in P.PLATFORMS else k[8:]}",
                  j.state()) for k, j in list(job.items()) if k.startswith("netmeta:")),
            row("hltb", "Durate (HowLongToBeat)", job["hltb"].state()),
            row("top", "Migliori giochi", job["top"].state()),
            row("collart", "Immagini delle collezioni", job["collart"].state()),
            row("bulk", "Database locali", bulk_job),
        ]
        if state["building"]:
            rows.append({"id": "build", "name": "Libreria", "kind": "build", "status": "running",
                         "phase": "Ricostruzione della libreria", "progress": None, "started": state["build_started"],
                         "finished": 0, "stoppable": False, "last": (state["build_log"] or [""])[-1]})
        if state["thumbs_done"] < state["thumbs_total"]:
            rows.append({"id": "thumbs", "name": "Miniature", "kind": "build", "status": "running",
                         "phase": f"{state['thumbs_done']:,} / {state['thumbs_total']:,}",
                         "progress": round(state["thumbs_done"] / state["thumbs_total"], 3),
                         "started": state["thumbs_started"], "finished": 0, "stoppable": False, "last": ""})
        rows += _download_rows()
        rows += _install_rows()
        return [r for r in rows if r]

    def _download_rows() -> list[dict]:
        """Un download per riga; la coda nasce dopo questo modulo (routes.ORDER): si legge al momento."""
        mgr = getattr(ctx, "downloads", None)
        out = []
        for t in mgr.list() if mgr else []:
            jid = "dl:" + t["id"]
            if jid in activity_hidden:
                continue
            status = {"completed": "done", "error": "error", "paused": "cancelled"}.get(t["status"], "running")
            speed = f" · {t['speed'] / 1048576:.1f} MB/s" if t["status"] == "running" and t["speed"] else ""
            seeding = bool(t["options"].get("seeding"))
            phase = {"queued": "In coda", "paused": "In pausa", "completed": "Completato · in condivisione" if seeding else "Completato",
                     "error": t["error"] or "Errore"}.get(t["status"], f"{t['progress']:.0%}{speed}")
            out.append({"id": jid, "name": f"Download · {t['name'] or t['source'][:60]}", "kind": "download",
                        "status": status, "phase": phase, "progress": round(t["progress"], 3),
                        "started": t["created"], "finished": t["finished"],
                        "stoppable": t["status"] in ("queued", "running") or seeding, "last": t["save_path"]})
        return out

    def _install_rows() -> list[dict]:
        """Installazioni di repack: l'avanzamento del setup non si legge da fuori, si mostra il tempo trascorso."""
        from ...downloads import install
        out = []
        for r in install.rows():
            jid = "inst:" + r["id"]
            if jid in activity_hidden:
                continue
            out.append({"id": jid, "name": f"Installazione · {r['name']}", "kind": "install", "status": r["status"],
                        "phase": r["phase"], "progress": r["progress"], "started": r["started"],
                        "finished": r["finished"], "stoppable": False, "last": r["last"]})
        return out

    def _stop_flag(name):
        return lambda: setattr(job[name], "stop", True)

    # id della riga -> come interromperla (gli altri lavori non hanno un punto di arresto sicuro)
    job_stops = {"scan": lambda: job["current"].cancel(), "catalogs": lambda: job["store_refresh"].stop_now(),
                 **{k: _stop_flag(k) for k in ("storemeta", "hltb", "top", "collart")}}

    @router.get("/api/activity")
    def api_activity():
        """Tutte le operazioni in corso o appena finite (pannello Attivita' e sua finestra separata)."""
        return {"jobs": _job_rows(), "now": time.time()}

    @router.post("/api/activity/{jid}/stop")
    def api_activity_stop(jid: str):
        if jid.startswith("dl:") and getattr(ctx, "downloads", None):  # «Ferma» su un download = pausa
            try:
                ctx.downloads.pause(jid[3:])
            except KeyError:
                raise HTTPException(404, "Download non trovato")
            return api_activity()
        if jid.startswith("netmeta:") and jid in job:  # un lavoro per console, creato al primo avvio
            _stop_flag(jid)()
            return api_activity()
        if jid not in job_stops:
            raise HTTPException(400, "Questa operazione non si puo' interrompere")
        job_stops[jid]()
        return api_activity()

    @router.post("/api/activity/{jid}/remove")
    def api_activity_remove(jid: str):
        rows = {r["id"]: r for r in _job_rows()}
        row = rows.get(jid)
        if not row:
            raise HTTPException(404, "Attività non trovata")
        if row["status"] == "running":
            raise HTTPException(409, "Non puoi rimuovere un'attività in corso")
        activity_hidden.add(jid)
        return api_activity()

    @router.post("/api/activity/clear")
    def api_activity_clear(body: dict = Body(default={})):
        mode = body.get("mode") or "finished"
        allowed = {"done", "error", "cancelled"} if mode == "finished" else {"done", "error"}
        for row in _job_rows():
            if row["status"] in allowed:
                activity_hidden.add(row["id"])
        return api_activity()

    @router.get("/activity")
    def activity_page():
        html = (STATIC / "activity.html").read_text(encoding="utf-8").replace("{{v}}", _asset_version())
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @router.get("/api/mobile/state")
    def api_mobile_state():
        """Stato compatto per l'app del telefono: gioco in corso, lavori attivi, comandi disponibili."""
        run = launcher.running()
        return {"running": run, "jobs": _job_rows(),
                "counts": {"games": len(lib.games), "groups": len(lib.groups),
                           "online": sum(1 for g in lib.games if g.get("store") == "online")}}

    @router.post("/api/mobile/action")
    def api_mobile_action(body: dict = Body(...)):
        """Comandi dal telefono: aggiorna store, cerca nuovi giochi, ricostruisci, chiudi il gioco."""
        action = str(body.get("action") or "")
        if action == "stores":
            added = _start_store_refresh(manual=True)
            return {"ok": True, "queued": added, "state": api_mobile_state()}
        if action == "scan":
            api_scan_start({"mode": "missing"})
            return {"ok": True, "state": api_mobile_state()}
        if action == "rebuild":
            threading.Thread(target=_rebuild, daemon=True).start()
            return {"ok": True, "state": api_mobile_state()}
        if action == "stop-game":
            return {"ok": launcher.stop(), "state": api_mobile_state()}
        if action == "stop-scan":
            job["current"].cancel()
            return {"ok": True, "state": api_mobile_state()}
        if action == "key":
            # telecomando: volume, play/pausa, Esc, Invio, Alt+Tab... (elenco chiuso in remote/keyboard.py)
            try:
                phone_hub.key_input(str(body.get("key") or ""))
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "state": api_mobile_state()}
        raise HTTPException(400, "Comando sconosciuto")

    vars(ctx).update(_job_rows=_job_rows, api_mobile_action=api_mobile_action)
    return router
