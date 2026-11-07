"""Script e azioni automatiche per gioco (prima dell'avvio / dopo la chiusura) e script globali sugli eventi.

Sono comandi scritti dall'utente sul proprio PC: si salvano solo dall'API del desktop (mai dalle rotte del telefono).
Le azioni di sistema (risoluzione, piano energetico, HDR, chiusura processi) sono solo Windows e vengono SEMPRE
ripristinate a fine sessione dal chiamante (`finally`), anche se il gioco si chiude male.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

KEY = "auto"  # chiave del profilo del gioco (userdata) che contiene la configurazione
GLOBAL_KEY = "scripts"  # cfg.app["scripts"] = {game_started, game_stopped, download_finished}: comandi
GLOBAL_EVENTS = {"game_started": "game_started", "game_stopped": "game_stopped", "game_downloaded": "download_finished"}
WAIT_MAX = 120  # secondi massimi di attesa di uno script con «aspetta che finisca», poi viene chiuso
# mai chiusi dall'elenco «chiudi processi»: sistema, shell e Pozzo stesso
PROTECTED = {"system", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
             "explorer.exe", "dwm.exe", "fontdrvhost.exe", "python.exe", "pythonw.exe", "pozzo.exe"}
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def clean(body: dict) -> dict:
    """Configurazione ricevuta dalla UI -> solo campi validi e non vuoti (ValueError se un valore e' sbagliato)."""
    b = body or {}
    out: dict = {}
    for w in ("before", "after"):
        if cmd := str(b.get(f"{w}_cmd") or "").strip():
            out[f"{w}_cmd"] = cmd
            if cwd := str(b.get(f"{w}_cwd") or "").strip().strip('"'):
                out[f"{w}_cwd"] = cwd
            out[f"{w}_wait"] = bool(b.get(f"{w}_wait", w == "before"))
    if res := str(b.get("res") or "").strip():
        if not re.fullmatch(r"\d{3,5}x\d{3,5}(@\d{2,3})?", res):
            raise ValueError("res")
        out["res"] = res
    if power := str(b.get("power") or "").strip():
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", power):
            raise ValueError("power")
        out["power"] = power
    kill = [n.strip().strip('"') for n in re.split(r"[,;\n]", str(b.get("kill") or "")) if n.strip()]
    if kill:
        out["kill"] = [n for n in kill if re.fullmatch(r"[\w .()+-]+\.exe", n, re.I)]
    if b.get("hdr"):
        out["hdr"] = True
    if b.get("archive"):  # archivio estratto in temp a ogni avvio (vedi archiverun)
        out["archive"] = True
    if mp := str(b.get("magpie") or "").strip():
        if mp not in ("fsr", "anime4k", "integer", "lanczos"):
            raise ValueError("magpie")
        out["magpie"] = mp
    return out


def env_for(event: str, key: str, title: str, platform: str, exe: str | None, **extra) -> dict:
    return {**os.environ, "POZZO_GAME_ID": key or "", "POZZO_TITLE": title or "", "POZZO_PLATFORM": platform or "",
            "POZZO_EXE": exe or "", "POZZO_EVENT": event, **{k: str(v) for k, v in extra.items()}}


def run(cmd: str, cwd: str | None, env: dict, wait: bool) -> str | None:
    """Esegue il comando; ritorna il testo dell'errore o None. Con wait aspetta la fine (max WAIT_MAX s)."""
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd or None, env=env, creationflags=_NOWIN)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    if not wait:
        return None
    try:
        code = p.wait(WAIT_MAX)
    except subprocess.TimeoutExpired:
        p.kill()
        return f"interrotto dopo {WAIT_MAX} s"
    return f"codice {code}" if code else None


# ---------------------------------------------------------------- azioni di sistema (Windows)

def display_mode():
    """Modalita' video corrente (da ripristinare) o None."""
    import ctypes
    dm = _devmode()
    return dm if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)) else None


def set_display(w: int, h: int, hz: int | None):
    import ctypes
    dm = display_mode()
    if dm is None:
        raise OSError("EnumDisplaySettingsW")
    dm.dmPelsWidth, dm.dmPelsHeight, dm.dmFields = w, h, 0x80000 | 0x100000 | 0x400000
    if hz:
        dm.dmDisplayFrequency = hz
    # CDS_FULLSCREEN: modo temporaneo, non scritto nel registro (un riavvio lo azzera comunque)
    if ctypes.windll.user32.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, 4, None):
        raise OSError(f"Modalita' video {w}x{h} non accettata")


def restore_display(saved):
    import ctypes
    u = ctypes.windll.user32
    if saved is None or u.ChangeDisplaySettingsExW(None, ctypes.byref(saved), None, 4, None):
        u.ChangeDisplaySettingsExW(None, None, None, 0, None)  # ripiego: impostazioni del registro


def _devmode():
    import ctypes
    from ctypes import wintypes as w

    class DEVMODEW(ctypes.Structure):
        _fields_ = [("dmDeviceName", w.WCHAR * 32), ("dmSpecVersion", w.WORD), ("dmDriverVersion", w.WORD),
                    ("dmSize", w.WORD), ("dmDriverExtra", w.WORD), ("dmFields", w.DWORD),
                    ("dmPosition", w.LONG * 2), ("dmDisplayOrientation", w.DWORD), ("dmDisplayFixedOutput", w.DWORD),
                    ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short), ("dmFormName", w.WCHAR * 32),
                    ("dmLogPixels", w.WORD), ("dmBitsPerPel", w.DWORD), ("dmPelsWidth", w.DWORD),
                    ("dmPelsHeight", w.DWORD), ("dmDisplayFlags", w.DWORD), ("dmDisplayFrequency", w.DWORD),
                    ("dmICMMethod", w.DWORD), ("dmICMIntent", w.DWORD), ("dmMediaType", w.DWORD),
                    ("dmDitherType", w.DWORD), ("dmReserved1", w.DWORD), ("dmReserved2", w.DWORD),
                    ("dmPanningWidth", w.DWORD), ("dmPanningHeight", w.DWORD)]
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(DEVMODEW)
    return dm


def active_plan() -> str | None:
    out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, creationflags=_NOWIN).stdout
    m = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", out or "")
    return m.group(0) if m else None


def set_plan(guid: str):
    subprocess.run(["powercfg", "/setactive", guid], check=True, capture_output=True, creationflags=_NOWIN)


def toggle_hdr():
    from ..remote import keyboard
    keyboard.press("hdr")  # Win+Alt+B


def kill_processes(names: list[str]) -> list[str]:
    """Chiude i processi con questi nomi (mai quelli di sistema/protetti). Ritorna i nomi chiusi."""
    import psutil
    want = {n.lower() for n in names} - PROTECTED
    sysroot = os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows")) + os.sep
    done = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            name = (p.info.get("name") or "").lower()
            exe = os.path.normcase(p.info.get("exe") or "")
            if name in want and p.pid != os.getpid() and not exe.startswith(sysroot):
                p.terminate()
                done.append(name)
        except Exception:
            pass
    return done


class Session:
    """Una partita: begin() prima dell'avvio, end() sempre alla fine (ripristina e poi lancia lo script «dopo»)."""

    def __init__(self, conf: dict, env_fn, report):
        self.conf, self.env_fn, self.report = conf, env_fn, report
        self.undo: list = []
        self.done = False

    def begin(self):
        c = self.conf
        if c.get("before_cmd"):
            if err := run(c["before_cmd"], c.get("before_cwd"), self.env_fn("before"), c.get("before_wait", True)):
                self._err("Script «prima dell'avvio» non riuscito", err)
        if sys.platform != "win32":
            return
        steps = [("chiusura processi", lambda: c.get("kill") and kill_processes(c["kill"])),
                 ("risoluzione", self._res), ("piano energetico", self._power), ("HDR", self._hdr)]
        for name, fn in steps:
            try:
                fn()
            except Exception as e:  # un'azione fallita non impedisce di giocare
                self._err(f"Azione «{name}» non riuscita", f"{type(e).__name__}: {e}")

    def _res(self):
        if res := self.conf.get("res"):
            m = re.fullmatch(r"(\d+)x(\d+)(?:@(\d+))?", res)
            saved = display_mode()
            set_display(int(m[1]), int(m[2]), int(m[3]) if m[3] else None)
            self.undo.append(lambda: restore_display(saved))  # solo se il cambio e' riuscito

    def _power(self):
        if guid := self.conf.get("power"):
            prev = active_plan()
            set_plan(guid)
            if prev and prev.lower() != guid.lower():
                self.undo.append(lambda: set_plan(prev))

    def _hdr(self):
        if self.conf.get("hdr"):
            toggle_hdr()
            # shortcut: Win+Alt+B inverte lo stato senza poterlo leggere; se l'HDR era gia' acceso lo spegne (e a fine partita lo riaccende)
            self.undo.append(toggle_hdr)

    def end(self):
        if self.done:  # chiamato sia a fine partita sia nel finally
            return
        self.done = True
        for fn in reversed(self.undo):
            try:
                fn()
            except Exception as e:
                log.warning("ripristino automazione fallito: %s", e)
        self.undo.clear()
        c = self.conf
        if c.get("after_cmd"):
            if err := run(c["after_cmd"], c.get("after_cwd"), self.env_fn("after"), c.get("after_wait", False)):
                self._err("Script «dopo la chiusura» non riuscito", err)

    def _err(self, what: str, err: str):
        log.warning("%s: %s", what, err)
        self.report(f"{what}: {err}")


def register_global(events, cfg):
    """Script globali (cfg.app["scripts"]) su game_started, game_stopped e download finito. Ogni evento parte in un thread."""
    def hook(name: str, setting: str):
        def fire(data: dict):
            cmd = ((cfg.app.get(GLOBAL_KEY) or {}).get(setting) or "").strip()
            if not cmd:
                return
            env = env_for(setting, data.get("key", ""), data.get("title", ""), data.get("emulator", ""), data.get("exe"),
                          **({"POZZO_DOWNLOAD_NAME": data.get("title", "")} if setting == "download_finished" else {}))
            threading.Thread(target=lambda: (e := run(cmd, None, env, False)) and log.warning("script globale %s: %s", setting, e),
                             daemon=True).start()
        events.on(name, fire)
    for name, setting in GLOBAL_EVENTS.items():
        hook(name, setting)
