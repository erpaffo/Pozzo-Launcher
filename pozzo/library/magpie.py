"""Upscaling con Magpie (github.com/Blinue/Magpie, GPL-3): ingrandisce il gioco in finestra a schermo intero (FSR, Anime4K...).

Magpie non ha una riga di comando «scala questa finestra»: Pozzo scrive nel suo config.json (modalita' portatile:
config\\config.json accanto a Magpie.exe) un profilo per l'exe del gioco con autoScale acceso, poi avvia Magpie nella
tray (`-t`) quando la finestra del gioco passa in primo piano; Magpie la scala da solo. Struttura del config verificata
sul sorgente (AppSettings.cpp, v0.13). Solo Windows 10 1903+ x64.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import config as C
from .. import ports as PT

log = logging.getLogger(__name__)

REPO = "Blinue/Magpie"
MODES = {"fsr": "FSR", "anime4k": "Anime4K", "integer": "Integer Scale 2x", "lanczos": "Lanczos"}  # nomi dei modi predefiniti di Magpie
AUTO_FULLSCREEN = 1  # Profile::AutoScale: 0 spento, 1 schermo intero, 2 in finestra
# modi predefiniti di un config nuovo (AppSettings::_SetInitialSettings); scalingType 1 = Fit
_SEED = [("Lanczos", [("Lanczos", 1)]), ("FSR", [("FSR\\FSR_EASU", 1), ("FSR\\FSR_RCAS", None)]), ("FSRCNNX", [("FSRCNNX\\FSRCNNX", None)]),
         ("CuNNy", [("CuNNy2\\CuNNy-4x12-NVL", None)]), ("Anime4K", [("Anime4K\\Anime4K_Upscale_Denoise_L", None)]),
         ("Integer Scale 2x", [("Nearest", 0)])]
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported() -> bool:
    return sys.platform == "win32" and sys.getwindowsversion().build >= 18362  # Windows 10 1903


def folder(cfg) -> Path:
    return C.settings_path(cfg).parent / "Magpie"


def exe_of(cfg) -> Path:
    return folder(cfg) / "Magpie.exe"


def pick(rels: list[dict]):
    """(release, asset) x64 stabile piu' recente, o None."""
    return PT.pick_release(rels, "x64")


def ensure(cfg, progress=None) -> Path:
    """Scarica Magpie (zip portatile x64) se manca. Ritorna il percorso di Magpie.exe."""
    exe = exe_of(cfg)
    if exe.exists():
        return exe
    from .. import emuinstall as EI
    got = pick(PT.releases("github", REPO, PT._token(cfg)))
    if not got:
        raise RuntimeError("nessun file x64 nelle release di Magpie")
    stage = EI._stage(cfg, got[1], "magpie", progress)
    try:
        src = next(stage.rglob("Magpie.exe")).parent  # lo zip puo' avere una cartella in piu'
        dest = folder(cfg)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest)
    except StopIteration:
        raise RuntimeError("Magpie.exe non trovato nel file scaricato") from None
    finally:
        shutil.rmtree(stage.parent, ignore_errors=True)
    return exe


def upsert_profile(conf: dict, exe: str, cls: str, name: str, mode: str) -> dict:
    """Aggiunge/aggiorna il profilo (exe + classe della finestra) nel config di Magpie lasciando intatti gli altri. Profilo 0 = predefinito."""
    profiles = conf.setdefault("profiles", [{"scalingMode": 0}])
    modes = conf.setdefault("scalingModes", [{"name": n, "effects": [
        {"name": e, **({"scalingType": t} if t is not None else {})} for e, t in fx]} for n, fx in _SEED])
    idx = next((i for i, m in enumerate(modes) if m.get("name") == MODES.get(mode, MODES["fsr"])), -1)
    want = {"name": name, "packaged": False, "pathRule": exe, "classNameRule": cls, "launcherPath": "",
            "autoScale": AUTO_FULLSCREEN, "launchParameters": "", "scalingMode": idx}
    # Magpie confronta classe e percorso per uguaglianza (ProfileService.cpp): un profilo per coppia exe+classe
    for p in profiles[1:]:
        if isinstance(p, dict) and not p.get("packaged") and str(p.get("pathRule", "")).lower() == exe.lower() and p.get("classNameRule") == cls:
            p.update(want)
            break
    else:
        profiles.append(want)
    return conf


def write_config(cfg, exe: str, cls: str, name: str, mode: str) -> None:
    path = folder(cfg) / "config" / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    conf = {}
    if path.exists():
        bak = path.with_name("config.json.pozzo.bak")
        if not bak.exists():  # copia di sicurezza una volta sola
            shutil.copy2(path, bak)
        conf = json.loads(path.read_text("utf-8-sig"))
    upsert_profile(conf, exe, cls, name, mode)
    tmp = path.with_name("config.json.new")
    tmp.write_text(json.dumps(conf, indent=2, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


def running() -> bool:
    import psutil
    return any((p.info.get("name") or "").lower() == "magpie.exe" for p in psutil.process_iter(["name"]))


def foreground_window(pid: int) -> tuple[str, str]:
    """(percorso exe, classe della finestra) della finestra in primo piano, se e' del processo `pid`; altrimenti ("", "")."""
    import ctypes
    import psutil
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    p = ctypes.c_ulong()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, buf, 256)
    return (psutil.Process(pid).exe(), buf.value) if p.value == pid else ("", "")


class Scaler:
    """Per una partita: prepare() scarica Magpie, start() (gioco in primo piano) scrive il profilo e lo avvia solo se non e' gia' aperto, stop() lo chiude se l'ha avviato Pozzo."""

    def __init__(self, cfg, name: str, mode: str, report, window=foreground_window):
        self.cfg, self.name, self.mode, self.report, self.window = cfg, name, mode, report, window
        self.proc: subprocess.Popen | None = None
        self.ok = False
        self.started = False

    def prepare(self):
        try:
            if not supported():
                raise RuntimeError("serve Windows 10 1903 o successivo")
            ensure(self.cfg, lambda d, t: self.report(f"Scarico Magpie... {d * 100 // t}%" if t else "Scarico Magpie..."))
            self.ok = True
        except Exception as e:  # senza upscaling si gioca lo stesso
            log.warning("magpie: %s", e)
            self.report(f"Upscaling non attivato: {type(e).__name__}: {e}")

    def start(self, pid: int = 0):
        if self.started or not self.ok:
            return
        try:
            exe, cls = self.window(pid)
            if not exe:
                return  # primo piano di altri: si riprova al prossimo evento
            self.started = True
            write_config(self.cfg, exe, cls, self.name, self.mode)
            if running():  # un Magpie gia' aperto non rilegge il config: va riavviato dall'utente
                self.report("Magpie e' gia' aperto: il profilo vale dal suo prossimo avvio")
                return
            mp = exe_of(self.cfg)
            self.proc = subprocess.Popen([str(mp), "-t"], cwd=str(mp.parent), creationflags=_NOWIN)
        except Exception as e:
            self.report(f"Magpie non avviato: {type(e).__name__}: {e}")

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
