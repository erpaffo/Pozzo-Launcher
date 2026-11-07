"""Remap del pad per i giochi PC: un thread legge il pad fisico (XInput), applica la mappatura del gioco e
la inoltra a un controller Xbox 360 virtuale (ViGEmBus). Il gioco deve vedere solo quello virtuale: se HidHide e'
installato il pad fisico viene nascosto per la durata della partita (e SEMPRE ripristinato: finally + atexit).

Configurazione nel profilo del gioco: auto["pad"] = {map: {da: a}, deadzone: 0-30, swap, invert_y, turbo: {tasto: Hz}}.
"""

from __future__ import annotations

import atexit
import json
import logging
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

BTN = {"up": 0x0001, "down": 0x0002, "left": 0x0004, "right": 0x0008, "start": 0x0010, "back": 0x0020, "ls": 0x0040,
       "rs": 0x0080, "lb": 0x0100, "rb": 0x0200, "a": 0x1000, "b": 0x2000, "x": 0x4000, "y": 0x8000}
NAMES = (*BTN, "lt", "rt")  # lt/rt: grilletti, trattati come tasti quando sono mappati su altro
TRIG_ON = 30  # soglia (0-255) oltre la quale un grilletto conta come premuto
HIDHIDE_URL = "https://github.com/nefarius/HidHide/releases"
POLL = 0.004  # 250 Hz
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pairs(v, conv) -> dict:
    if isinstance(v, dict):
        return {str(k).lower(): conv(str(x).lower()) for k, x in v.items()}
    out = {}
    for part in str(v or "").replace(";", ",").split(","):
        if part.strip():
            a, _, b = part.replace(":", "=").partition("=")
            out[a.strip().lower()] = conv(b.strip().lower())
    return out


def clean(body: dict) -> dict:
    """Configurazione dalla UI (mappa/turbo come testo «a=b, x=y» o dict) -> valida; ValueError se sbagliata. {} = disattivo."""
    b = body or {}
    if not b.get("enabled"):
        return {}
    m = _pairs(b.get("map"), str)
    t = _pairs(b.get("turbo"), lambda s: int(float(s)))
    if any(k not in NAMES or v not in NAMES for k, v in m.items()) or any(k not in NAMES or not 1 <= v <= 30 for k, v in t.items()):
        raise ValueError("pad")
    out = {"enabled": True, "map": {k: v for k, v in m.items() if k != v}, "turbo": t,
           "deadzone": max(0, min(30, int(float(b.get("deadzone") or 0))))}
    out.update({k: True for k in ("swap", "invert_y") if b.get(k)})
    return out


def _dead(x: int, y: int, dz: int) -> tuple[int, int]:
    """Zona morta radiale in % con riscalo, cosi' non c'e' salto all'uscita dalla zona."""
    lim, m = dz * 32767 / 100, math.hypot(x, y)
    if m <= lim or m == 0:
        return 0, 0
    k = min(1.0, (m - lim) / (32767 - lim)) * 32767 / m
    return int(x * k), int(y * k)


def remap(st: dict, conf: dict, now: float) -> dict:
    """Stato XInput {buttons, lt, rt, lx, ly, rx, ry} -> stato mappato (puro). Il turbo da' un'onda quadra al 50% a N Hz."""
    mp = conf.get("map") or {}
    src = {n for n, bit in BTN.items() if st["buttons"] & bit}
    src |= {n for n in ("lt", "rt") if st[n] >= TRIG_ON}
    out = {n: 0 for n in NAMES}  # 0/1 per i tasti, 0-255 per i grilletti
    for n in src:
        d = mp.get(n, n)
        analog = n in ("lt", "rt") and d in ("lt", "rt")
        out[d] = max(out[d], st[n] if analog else (255 if d in ("lt", "rt") else 1))
    for n, hz in (conf.get("turbo") or {}).items():
        if out[n] and int(now * hz * 2) % 2:
            out[n] = 0
    lx, ly = _dead(st["lx"], st["ly"], conf.get("deadzone", 0))
    rx, ry = _dead(st["rx"], st["ry"], conf.get("deadzone", 0))
    if conf.get("swap"):
        lx, ly, rx, ry = rx, ry, lx, ly
    if conf.get("invert_y"):
        ly, ry = min(32767, -ly), min(32767, -ry)
    return {"buttons": sum(BTN[n] for n in BTN if out[n]), "lt": out["lt"], "rt": out["rt"], "lx": lx, "ly": ly, "rx": rx, "ry": ry}


def pick_physical(connected: list[int], virtual: set[int]) -> int | None:
    """Primo indice XInput collegato che non e' un nostro controller virtuale."""
    return next((i for i in connected if i not in virtual), None)


# ---------------------------------------------------------------- HidHide

def hidhide_cli() -> str | None:
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
        for sub in ("x64", ""):
            p = Path(root or "C:\\Program Files") / "Nefarius Software Solutions" / "HidHide" / sub / "HidHideCLI.exe"
            if p.is_file():
                return str(p)
    return None


class HidHide:
    """Nasconde i pad presenti all'avvio (quindi non il nostro virtuale); restore() ripristina ed e' idempotente."""

    def __init__(self, cli: str, run=None):
        self.run = run or (lambda args: subprocess.run([cli, *args], capture_output=True, text=True, timeout=15,
                                                      creationflags=_NOWIN).stdout)
        self.hidden: list[str] = []
        self.app: str | None = None
        self.cloak_was: bool | None = None

    def gaming_devices(self) -> list[str]:
        try:
            groups = json.loads(self.run(["--dev-gaming"]) or "[]")
        except ValueError:
            return []
        return [d["deviceInstancePath"] for g in groups for d in g.get("devices", [])
                if d.get("present", True) and d.get("deviceInstancePath")]

    def hide(self, devices: list[str], app: str):
        """Registra l'app (Pozzo continua a leggere il pad), nasconde i dispositivi, attiva il cloak."""
        atexit.register(self.restore)  # prima di toccare qualcosa: anche un'uscita brusca ripristina
        try:
            self.cloak_was = (self.run(["--cloak-state"]) or "").strip().lower() == "true"
            self.run(["--app-reg", app])
            self.app = app
            for d in devices:
                self.run(["--dev-hide", d])
                self.hidden.append(d)
            self.run(["--cloak-on"])
        except BaseException:
            self.restore()
            raise

    def restore(self):
        todo = [["--dev-unhide", d] for d in self.hidden]
        if self.app:
            todo.append(["--app-unreg", self.app])
        if self.cloak_was is False:
            todo.append(["--cloak-off"])
        self.hidden, self.app, self.cloak_was = [], None, None
        for args in todo:
            try:
                self.run(args)
            except Exception as e:  # noqa: BLE001 - si prova comunque con tutti gli altri
                log.warning("HidHide %s: %s", args[0], e)


# ---------------------------------------------------------------- XInput + thread

def _xinput():
    import ctypes
    from ctypes import wintypes as w

    class PAD(ctypes.Structure):
        _fields_ = [("wButtons", w.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                    ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

    class STATE(ctypes.Structure):
        _fields_ = [("pkt", w.DWORD), ("pad", PAD)]

    class VIB(ctypes.Structure):
        _fields_ = [("l", w.WORD), ("r", w.WORD)]
    lib = ctypes.windll.xinput1_4

    def get(i):
        s = STATE()
        if lib.XInputGetState(i, ctypes.byref(s)):
            return None
        g = s.pad
        return {"buttons": g.wButtons, "lt": g.bLeftTrigger, "rt": g.bRightTrigger, "lx": g.sThumbLX, "ly": g.sThumbLY,
                "rx": g.sThumbRX, "ry": g.sThumbRY}

    def rumble(i, large, small):
        lib.XInputSetState(i, ctypes.byref(VIB(large * 257, small * 257)))
    return get, rumble


class Remapper:
    def __init__(self, conf: dict, report):
        self.conf, self.report = conf, report
        self.stop_evt = threading.Event()
        self.thread: threading.Thread | None = None
        self.pad = None
        self.hh: HidHide | None = None

    def start(self):
        from ..remote import vigem
        get, rumble = _xinput()
        cli = hidhide_cli()
        devs = []
        if cli:
            self.hh = HidHide(cli)
            devs = self.hh.gaming_devices()  # prima di creare il pad virtuale: cosi' non nasconde il nostro
        else:
            self.report(f"HidHide non installato: il gioco potrebbe vedere due controller ({HIDHIDE_URL})")
        self.pad = vigem.VirtualPad()  # ViGEmError con il link di installazione se manca il driver
        try:
            time.sleep(0.2)  # Windows assegna l'indice XInput al pad virtuale con un po' di ritardo
            idx = pick_physical([i for i in range(4) if get(i)], vigem.virtual_indices())
            if idx is None:
                raise RuntimeError("nessun controller fisico collegato")
            self.pad.on_rumble = lambda large, small: rumble(idx, large, small)
            if self.hh:
                self.hh.hide(devs, sys.executable)
        except BaseException:
            self.stop()
            raise
        self.thread = threading.Thread(target=self._loop, args=(get, idx), daemon=True)
        self.thread.start()

    def _loop(self, get, idx):
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)  # senza, wait(4 ms) dura ~15 ms
        last = None
        try:
            while not self.stop_evt.wait(POLL):
                st = get(idx)
                if st is None:  # pad scollegato: si resta in attesa che torni
                    continue
                o = remap(st, self.conf, time.monotonic())
                if o != last:
                    self.pad.update(o["buttons"], o["lt"] / 255, o["rt"] / 255, o["lx"] / 32767, o["ly"] / 32767,
                                    o["rx"] / 32767, o["ry"] / 32767)
                    last = o
        finally:
            ctypes.windll.winmm.timeEndPeriod(1)

    def stop(self):
        self.stop_evt.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(2)
        try:
            self.pad and self.pad.close()
        finally:
            self.pad = None
            if self.hh:
                self.hh.restore()
