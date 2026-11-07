"""Finestra in primo piano: dice alla UI quando il gioco passa davanti a Pozzo (e viceversa) e chiude lo splash di avvio."""

from __future__ import annotations

import sys
import threading

SPLASH_TIMEOUT = 60.0  # secondi: lo splash sparisce comunque
SPLASH_TIMEOUT_NOHOOK = 8.0  # shortcut: fuori da Windows non c'e' l'hook sul primo piano, lo splash dura poco


def is_game_pid(fg_pid: int, pids) -> bool:
    return bool(fg_pid) and fg_pid in set(pids)


def splash_timer(emit, seconds: float | None = None) -> threading.Timer:
    """Dopo `seconds` emette splash_end: l'avvio non resta mai coperto da uno splash che nessuno chiude."""
    if seconds is None:
        seconds = SPLASH_TIMEOUT if sys.platform == "win32" else SPLASH_TIMEOUT_NOHOOK
    t = threading.Timer(seconds, lambda: emit("splash_end", {"reason": "timeout"}))
    t.daemon = True
    t.start()
    return t


class Watcher:
    """SetWinEventHook(EVENT_SYSTEM_FOREGROUND) in un thread con il suo ciclo di messaggi. `pids()` da' i PID della
    sessione; emette game_foreground / game_background solo quando lo stato cambia."""

    def __init__(self, pids, emit):
        self.pids, self.emit = pids, emit
        self.fg: bool | None = None
        self._tid = 0
        self._th: threading.Thread | None = None

    def on_foreground(self, fg_pid: int):
        try:
            now = is_game_pid(fg_pid, self.pids())
        except Exception:
            return
        if now != self.fg:
            self.fg = now
            self.emit("game_foreground" if now else "game_background", {"pid": fg_pid})

    def start(self):
        if sys.platform != "win32" or self._th:
            return
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        if self._tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x12, 0, 0)  # WM_QUIT
        self._th = None

    def _loop(self):
        import ctypes
        from ctypes import wintypes
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        self._tid = k.GetCurrentThreadId()
        proto = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                   wintypes.LONG, wintypes.DWORD, wintypes.DWORD)

        def cb(_h, _ev, hwnd, *_):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self.on_foreground(pid.value)
        fn = proto(cb)  # riferimento tenuto vivo finche' gira il ciclo
        hook = u.SetWinEventHook(0x0003, 0x0003, None, fn, 0, 0, 0)  # EVENT_SYSTEM_FOREGROUND, OUTOFCONTEXT
        if not hook:
            return
        try:
            msg = wintypes.MSG()
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
        finally:
            u.UnhookWinEvent(hook)
            self._tid = 0
