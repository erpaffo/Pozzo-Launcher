"""Emulatori: BIOS e firmware richiesti, emulatore consigliato per console e installazione «un clic»."""

from __future__ import annotations

import threading
import time

import httpx
from fastapi import APIRouter, Body, HTTPException

from ... import bios as BI, config as C, emuinstall_extra as EX, platforms as P
from ...boot import registro

EMU_AUTOUPDATE_MODES = ("off", "notify", "install")


def _emu_mode(cfg) -> str:
    mode = cfg.app.get("emu_autoupdate", "notify")
    return mode if mode in EMU_AUTOUPDATE_MODES else "off"  # valore sconosciuto: nessuna installazione a sorpresa


def autoupdate_pass(cfg) -> list[str]:
    """Un giro del controllo: «notify» avvisa degli aggiornamenti, «install» li installa. Ritorna i nomi trattati."""
    from ... import emuinstall as EI, notify as N
    mode = _emu_mode(cfg)
    trattati = []
    if mode == "off":
        return trattati
    for u in EI.check_updates(cfg):
        if not u.get("update"):
            continue
        name, latest = u["name"], u["latest"]
        if mode == "notify":
            N.send(cfg, "Pozzo Launcher", f"Aggiornamento disponibile: {name} {latest}")
            trattati.append(name)
            continue
        try:
            EI.install(cfg, u["id"])
        except EI.EmulatorRunning:  # emulatore aperto: si riprova al prossimo giro
            continue
        except Exception:  # noqa: BLE001 - install() rimette la versione di prima
            N.send(cfg, "Pozzo Launcher", f"Aggiornamento di {name} fallito: resta la versione precedente")
        else:
            N.send(cfg, "Pozzo Launcher", f"Aggiornato {name} a {latest}")
        trattati.append(name)
    return trattati


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()

    def _errori(fn, *args):
        """ValueError (console sconosciuta, dati non validi) -> 400; rete o disco -> 502; altro -> 502 (mai 500 grezzo)."""
        try:
            return fn(*args)
        except ValueError as e:
            raise HTTPException(400, str(e) or "Richiesta non valida")
        except (OSError, httpx.HTTPError) as e:
            raise HTTPException(502, f"Connessione o disco non disponibili: {type(e).__name__}: {e}")
        except Exception as e:  # l'installazione non deve lasciare il registro bloccato su «in corso»
            raise HTTPException(502, f"Operazione non riuscita: {type(e).__name__}: {e}")

    @router.get("/api/emulators/bios")
    def api_emulators_bios(console: str = ""):
        return _errori(BI.check, console)

    @router.get("/api/game/{gid}/diagnose")
    def api_game_diagnose(gid: int):
        """«Perché non parte?»: controlli in sola lettura, mai un processo avviato."""
        from ... import diagnose as DG
        g = ctx.lib.game(gid)
        try:
            prof = ctx.launcher.profile_of(g["key"])
        except Exception:  # noqa: BLE001
            prof = None
        return DG.diagnose(cfg, g, prof)

    @router.get("/api/emulators/recommend")
    def api_emulators_recommend(console: str = ""):
        return _errori(EX.recommend, console, cfg)

    @router.get("/api/emulators/install-recommended")
    def api_emulators_install_status(console: str = ""):
        """Avanzamento dell'ultima installazione «un clic» della console (per chi non ha aspettato la risposta)."""
        return registro(f"install-{console}").snapshot()

    @router.post("/api/emulators/install-recommended")
    def api_emulators_install(body: dict = Body(default={})):
        console = str(body.get("console") or "")
        if console not in P.PLATFORMS:
            raise HTTPException(400, f"console sconosciuta: {console}")
        reg = registro(f"install-{console}")
        if not reg.snapshot()["ready"]:
            raise HTTPException(409, "Un'installazione è già in corso per questa console")
        reg.reset()

        def avanza(msg: str, _frazione: float):
            reg.start("installa", msg)

        try:
            esito = _errori(EX.install_recommended, console, avanza, cfg)
            if not esito["ok"]:
                raise HTTPException(502, esito["message"])
        except HTTPException as e:
            reg.fail("installa", str(e.detail))
            raise
        reg.done("installa")
        return esito

    @router.get("/api/emulators/updates")
    def api_emulators_updates():
        """Emulatori con una versione più recente (controllo in cache 12 ore) e modalità di aggiornamento."""
        from ... import emuinstall as EI
        return {"mode": _emu_mode(cfg), "updates": _errori(EI.check_updates, cfg)}

    @router.post("/api/emulators/autoupdate")
    def api_emulators_autoupdate(body: dict = Body(...)):
        mode = str(body.get("mode") or "")
        if mode not in EMU_AUTOUPDATE_MODES:
            raise HTTPException(400, "modalità sconosciuta: usa off, notify o install")
        C.save_settings(cfg, app={"emu_autoupdate": mode})
        return {"mode": mode}

    @router.post("/api/emulators/update/{emu}")
    def api_emulators_update(emu: str):
        """Aggiornamento subito di un emulatore (se è chiuso); con un guasto la versione precedente torna al suo posto."""
        from ... import emuinstall as EI
        return {"ok": True, "id": emu, "path": str(_errori(EI.install, cfg, emu))}

    def _emu_scheduler():
        """Controllo degli aggiornamenti: dieci minuti dopo l'avvio, poi una volta al giorno."""
        import datetime as _dt
        time.sleep(600)
        while True:
            try:
                oggi = _dt.date.today().isoformat()
                if _emu_mode(cfg) != "off" and cfg.app.get("emu_autoupdate_last") != oggi:
                    try:
                        autoupdate_pass(cfg)
                    finally:  # anche se la rete non c'e': il giro di oggi e' fatto, domani si riprova
                        C.save_settings(cfg, app={"emu_autoupdate_last": oggi})
            except Exception as e:
                print(f"Aggiornamenti emulatori: {e}")
            time.sleep(3600)

    threading.Thread(target=_emu_scheduler, daemon=True).start()

    return router
