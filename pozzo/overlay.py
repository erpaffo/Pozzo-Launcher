"""Overlay in gioco: una seconda finestra pywebview (senza bordi, trasparente, sempre in primo piano) che si mostra
con una scorciatoia o con Select+R3 e riporta il fuoco al gioco quando si chiude; piu' un «toast» (finestra
piccola che non prende il fuoco) per gli avvisi, come gli obiettivi sbloccati.

shortcut: non si disegna sopra i giochi a schermo intero ESCLUSIVO (serve un hook nel renderer); funziona con
finestra e schermo intero senza bordi."""

from __future__ import annotations

import json
import sys
import threading
import time

DEFAULTS = {"hotkey": "ctrl+shift+o", "achievements": True, "sound": "soft", "hud": False, "hud_corner": "tl"}
SOUNDS = ("none", "soft", "classic")
CORNERS = ("tl", "tr", "bl", "br")  # il toast sta in alto a destra: il default dell'HUD e' in alto a sinistra
HUD_W, HUD_H = 190, 64
TOAST_SECONDS = 5.0
TOAST_MAX = 6  # code piu' lunghe scartano le piu' vecchie: un avviso in ritardo di un minuto non serve
XINPUT_BACK, XINPUT_R3 = 0x0020, 0x0080


def settings(cfg) -> dict:
    return {**DEFAULTS, **(cfg.app.get("overlay") or {})}


def clean(body: dict, cur: dict) -> dict:
    """Impostazioni aggiornate dal corpo della richiesta; ValueError se la scorciatoia o il suono non sono validi."""
    from .library import screens
    out = dict(cur)
    if "hotkey" in body:
        hk = str(body.get("hotkey") or "").strip().lower()
        if hk and not screens.parse_hotkey(hk):
            raise ValueError("hotkey")
        out["hotkey"] = hk
    if "achievements" in body:
        out["achievements"] = bool(body["achievements"])
    if "sound" in body:
        if body["sound"] not in SOUNDS:
            raise ValueError("sound")
        out["sound"] = body["sound"]
    if "hud" in body:
        out["hud"] = bool(body["hud"])
    if "hud_corner" in body:
        if body["hud_corner"] not in CORNERS:
            raise ValueError("hud_corner")
        out["hud_corner"] = body["hud_corner"]
    return out


class ToastQueue:
    """Coda di avvisi: stesso id = uno solo, al massimo TOAST_MAX (si scartano i piu' vecchi)."""

    def __init__(self, limit: int = TOAST_MAX):
        self.limit, self.items = limit, []
        self.lock = threading.Lock()

    def push(self, item: dict):
        with self.lock:
            if item.get("id") is not None and any(i.get("id") == item["id"] for i in self.items):
                return
            self.items.append(item)
            del self.items[:-self.limit]

    def pop(self) -> dict | None:
        with self.lock:
            return self.items.pop(0) if self.items else None


def _screen() -> tuple[int, int]:
    if sys.platform != "win32":
        return 1920, 1080
    import ctypes
    u = ctypes.windll.user32
    return u.GetSystemMetrics(0), u.GetSystemMetrics(1)


class Overlay:
    def __init__(self, cfg, launcher):
        self.cfg, self.launcher = cfg, launcher
        self.url = None  # base dell'app, impostata da attach() quando c'e' una finestra nativa
        self.wins: dict = {}
        self.visible = False
        self.hud_on = False
        self.active = False  # sessione di gioco in corso: scorciatoia e pad attivi
        self.queue = ToastQueue()
        self._wake = threading.Event()
        self._toaster = None
        self._hotkey = None
        self.lock = threading.Lock()

    def attach(self, url: str):
        self.url = url.rstrip("/") + "/"

    # ------------------------------------------------------------ sessione (eventi del launcher)
    def game_started(self, _st=None):
        from .library import screens
        self.active = True
        hk = settings(self.cfg).get("hotkey")
        if hk:
            self._hotkey = screens.Hotkey(hk, self.toggle)
            self._hotkey.start()
        threading.Thread(target=self._watch_pad, daemon=True).start()
        threading.Thread(target=self.show_hud, daemon=True).start()

    def game_stopped(self, _st=None):
        self.active = False
        self.hide_hud()
        if self._hotkey:
            self._hotkey.stop()
            self._hotkey = None
        self.hide(refocus=False)

    def _watch_pad(self):
        """Select+R3 sul controller (XInput legge anche quando il gioco ha il fuoco)."""
        from .library import launcher as L
        read = L._xinput()
        if not read or not self.cfg.app.get("screenshots", {}).get("pad", True):
            return
        held = False
        while self.active:
            now = bool((p := read()) & XINPUT_BACK and p & XINPUT_R3)
            if now and not held:
                threading.Thread(target=self.toggle, daemon=True).start()
            held = now
            time.sleep(0.05)

    # ------------------------------------------------------------ finestre
    def _win(self, which: str):
        import webview
        w = self.wins.get(which)
        if w is not None and w in webview.windows:
            return w
        sw, sh = _screen()
        common = dict(frameless=True, on_top=True, transparent=True, hidden=True, easy_drag=False, shadow=False,
                      resizable=False, background_color="#000000")
        if which == "overlay":  # a tutto schermo: sfondo scurito e scheda al centro
            w = webview.create_window("Pozzo Overlay", f"{self.url}overlay", x=0, y=0, width=sw, height=sh, **common)
        elif which == "hud":
            m = 16
            c = settings(self.cfg)["hud_corner"]
            x = m if c[1] == "l" else sw - HUD_W - m
            y = m if c[0] == "t" else sh - HUD_H - m
            w = webview.create_window("Pozzo HUD", f"{self.url}overlay/hud", x=x, y=y, width=HUD_W, height=HUD_H, focus=False, **common)
        else:  # focus=False: WS_EX_NOACTIVATE, il toast non ruba mai il fuoco al gioco
            w = webview.create_window("Pozzo Toast", f"{self.url}overlay/toast", x=sw - 420, y=24, width=400,
                                      height=110, focus=False, **common)
        self.wins[which] = w
        return w

    def _front(self, w):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            u.keybd_event(0x12, 0, 0, 0)  # un tasto finto (Alt) sblocca SetForegroundWindow da un hotkey globale
            u.keybd_event(0x12, 0, 2, 0)
            u.SetForegroundWindow(w.native.Handle.ToInt64())
        except Exception:
            pass

    def _click_through(self, w):
        """WS_EX_TRANSPARENT | LAYERED | NOACTIVATE: l'HUD non intercetta ne' clic ne' fuoco."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            h = w.native.Handle.ToInt64()
            u.SetWindowLongPtrW(h, -20, u.GetWindowLongPtrW(h, -20) | 0x20 | 0x80000 | 0x8000000)
        except Exception:
            pass

    def show_hud(self):
        if not self.url or not settings(self.cfg)["hud"]:
            return
        try:
            w = self._win("hud")
            w.events.loaded.wait(5)
            self._click_through(w)
            w.show()
            self.hud_on = True
        except Exception:
            pass

    def hide_hud(self):
        w = self.wins.get("hud")
        if w is None or not self.hud_on:
            return
        self.hud_on = False
        try:
            w.hide()
        except Exception:
            pass

    def apply_hud(self):
        """Dopo un cambio di impostazioni: la finestra si ricrea per cambiare angolo, o si nasconde se spenta."""
        w = self.wins.pop("hud", None)
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
        self.hud_on = False
        if self.active:
            threading.Thread(target=self.show_hud, daemon=True).start()

    def show(self) -> bool:
        if not self.url or self.launcher.running().get("status") != "running":
            return False
        with self.lock:
            try:
                w = self._win("overlay")
                w.events.loaded.wait(5)  # prima apertura: finestra appena creata, senza attesa si vede bianco finche' la pagina non carica
                w.show()
                self._front(w)
                w.evaluate_js("window.ovRefresh && ovRefresh()")
            except Exception:
                return False
            self.visible = True
        return True

    def hide(self, refocus: bool = True) -> bool:
        with self.lock:
            w = self.wins.get("overlay")
            if not self.visible or w is None:
                return False
            self.visible = False
            try:
                w.evaluate_js("window.ovHide && ovHide()")  # ferma timer e polling della pagina prima di nasconderla
                w.hide()
            except Exception:
                pass
        if refocus:  # il fuoco torna alla finestra piu' grande del gioco (come alla ripresa dalla pausa)
            try:
                from .library import launcher as L
                L._focus_pids(set(self.launcher._session_pids()))
            except Exception:
                pass
        return True

    def toggle(self) -> bool:
        return self.hide() if self.visible else self.show()

    # ------------------------------------------------------------ toast
    def toast(self, item: dict):
        """item: {id, title, text, icon, sound}. Mostrato per TOAST_SECONDS, uno alla volta."""
        if not self.url:
            return
        self.queue.push(item)
        self._wake.set()
        if not self._toaster:
            self._toaster = threading.Thread(target=self._toast_loop, daemon=True)
            self._toaster.start()

    def _toast_loop(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            while (it := self.queue.pop()) is not None:
                try:
                    w = self._win("toast")
                    w.events.loaded.wait(5)
                    w.evaluate_js(f"window.showToast && showToast({json.dumps(it)})")
                    w.show()
                    time.sleep(TOAST_SECONDS)
                    w.hide()
                except Exception:
                    pass
