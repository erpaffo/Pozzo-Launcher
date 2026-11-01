"""Emulatori: BIOS e firmware richiesti, emulatore consigliato per console e installazione «un clic»."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Body, HTTPException

from ... import bios as BI, emuinstall_extra as EX, platforms as P
from ...boot import registro


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

    return router
