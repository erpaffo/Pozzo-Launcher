"""Emulatori: configurazione, rilevamento, installazione e core."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import config as C, emuinstall as EI, platforms as P
from ...library import launcher as L


def build_router(ctx) -> APIRouter:
    cfg, lib = ctx.cfg, ctx.lib
    router = APIRouter()

    # ------------------------------------------------------------ emulatori
    def _emu_row(pid: str) -> dict:
        p = P.PLATFORMS[pid]
        over = cfg.launch.get(pid, {})
        presets = L.PRESETS.get(pid, [])
        plan = L.plan(cfg, p)
        emu = over.get("emulator") or ""
        default_core = next((c for e, c in presets if e == L.RA), None)
        problem = None
        if not plan:
            if emu:
                exe = over.get("exe") or cfg.emulators.get(emu)
                if not exe:
                    problem = f"manca il percorso di {emu}"
                elif not Path(exe).exists():
                    problem = "eseguibile non trovato"
                elif emu == L.RA:
                    problem = f"core RetroArch non trovato: {over.get('core') or default_core}"
            else:
                ra_ok = cfg.emulators.get(L.RA) and Path(cfg.emulators[L.RA]).exists()
                ra_cores = [c for e, c in presets if e == L.RA and c]
                if ra_ok and ra_cores:
                    problem = f"RetroArch c'e', manca il core {' o '.join(ra_cores)} (scaricalo da RetroArch: Core > Scarica core)"
                elif presets:
                    problem = "installa uno tra: " + ", ".join(dict.fromkeys(e for e, _ in presets))
                else:
                    problem = "scegli un emulatore"
        if emu == L.RA:
            dargs = "-L {core} {rom}"
        else:
            dargs = " ".join(L.STANDALONE_ARGS.get(emu, ["{rom}"]))
        return {"platform": pid, "name": p.name, "emulator": emu,
                "core": over.get("core") or "", "args": " ".join(over.get("args") or []),
                "default_core": default_core or "", "default_args": dargs,
                "candidates": [e + (f" ({c})" if c else "") for e, c in presets],
                "effective": (plan["emulator"] + (f" ({plan['core']})" if plan["core"] else "")) if plan else None,
                "problem": problem}

    @router.get("/api/emulators")
    def api_emulators():
        with lib.lock:
            in_lib = sorted({g["platform"] for g in lib.games})
        pids = [p for p in in_lib if p in P.PLATFORMS]
        names = sorted(set(L.EMULATOR_NAMES) | {k for k in cfg.emulators if k != "retroarch_cores"}
                       | {v.get("emulator") for v in cfg.launch.values() if v.get("emulator")})
        return {"config": str(cfg.config_path or ""), "settings": str(C.settings_path(cfg)),
                "emulators": {k: v for k, v in cfg.emulators.items() if k != "retroarch_cores"},
                "retroarch_cores": cfg.emulators.get("retroarch_cores", ""),
                "known": names, "platforms": [_emu_row(p) for p in pids]}

    @router.post("/api/emulators")
    def api_emulators_save(body: dict = Body(...)):
        import shlex
        launch = {}
        for pid, v in (body.get("platforms") or {}).items():
            if pid not in P.PLATFORMS:
                continue
            emu = (v.get("emulator") or "").strip()
            if not emu:
                launch[pid] = None  # automatico: primo emulatore disponibile tra i preset
                continue
            entry = {"emulator": emu}
            if (v.get("core") or "").strip():
                entry["core"] = v["core"].strip()
            if (v.get("args") or "").strip():
                entry["args"] = [a.strip('"') for a in shlex.split(v["args"], posix=False)]
            launch[pid] = entry
        emus = {k: (v or "").strip() or None for k, v in (body.get("emulators") or {}).items()}
        if "retroarch_cores" in body:
            emus["retroarch_cores"] = (body.get("retroarch_cores") or "").strip() or None
        C.save_settings(cfg, launch=launch, emulators=emus)
        return api_emulators()

    @router.post("/api/emulators/detect")
    def api_emulators_detect(body: dict = Body(...)):
        folder = (body.get("folder") or "").strip()
        if not folder or not Path(folder).is_dir():
            raise HTTPException(400, "Cartella non valida")
        found = L.detect_emulators(Path(folder))
        if found:
            C.save_settings(cfg, emulators=found)
        return {"found": found, **api_emulators()}

    # installazione dalle release ufficiali: un lavoro alla volta, la pagina segue /api/emulators/job
    emu_job = {"status": "idle", "log": [], "emu": "", "done": 0, "total": 0}
    emu_lock = threading.Lock()

    def _start_emu_job(name: str, fn):
        def run():
            say = emu_job["log"].append
            try:
                fn(lambda done, total: emu_job.update(done=done, total=total), say)
                emu_job["status"] = "done"
            except Exception as e:
                say(f"Errore: {type(e).__name__}: {e}")
                emu_job["status"] = "error"
        with emu_lock:
            if emu_job["status"] == "running":
                raise HTTPException(409, "C'e' gia' un'installazione in corso")
            emu_job.update(status="running", log=[], emu=name, done=0, total=0)
        threading.Thread(target=run, daemon=True).start()
        return emu_job

    def _lib_pids():
        with lib.lock:
            return sorted({g["platform"] for g in lib.games})

    @router.get("/api/emulators/catalog")
    def api_emulators_catalog():
        return {"items": EI.catalog(cfg), "dir": str(EI.emus_dir(cfg)), "cores": EI.missing_cores(cfg, _lib_pids()),
                "retroarch": bool(cfg.emulators.get(L.RA) and Path(cfg.emulators[L.RA]).exists())}

    @router.get("/api/emulators/job")
    def api_emulators_job():
        return emu_job

    @router.post("/api/emulators/install")
    def api_emulators_install(body: dict = Body(...)):
        emu, folder = str(body.get("emu") or ""), (body.get("folder") or "").strip().strip('"')
        if emu not in EI.SOURCES:
            raise HTTPException(400, "Emulatore sconosciuto")
        if folder and not Path(folder).is_absolute():
            raise HTTPException(400, "Indica un percorso completo (es. D:\\Emulatori)")
        return _start_emu_job(emu, lambda progress, say: EI.install(cfg, emu, folder, progress, say))

    @router.post("/api/emulators/cores")
    def api_emulators_cores():
        cores = EI.missing_cores(cfg, _lib_pids())
        if not cores:
            raise HTTPException(400, "Nessun core da scaricare: le console della libreria hanno gia' un emulatore")
        return _start_emu_job("retroarch-cores", lambda progress, say: EI.install_cores(cfg, cores, progress, say))

    vars(ctx).update(_emu_row=_emu_row)
    return router
