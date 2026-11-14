"""Mouse del PC mosso dal telefono (touchpad / pistola ottica): Windows, macOS (CGEvent) e Linux (xdotool).

Posizione assoluta sullo schermo principale (0..1), tasto sinistro tenuto finche' il dito tocca: serve alle
pistole ottiche degli emulatori (GunCon in DuckStation/PCSX2, Zapper in Dolphin), al pennino di DS/3DS e ai menu.
Da' il controllo del mouse a chi ha il telefono: si attiva solo dal PC (Impostazioni › Telefono).
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from ctypes import wintypes

MOVE, LEFTDOWN, LEFTUP, RIGHTDOWN, RIGHTUP, ABSOLUTE = 0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]  # MOUSEINPUT e' il membro piu' grande: la dimensione di INPUT resta giusta
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def to_abs(v: float) -> int:
    """0..1 -> coordinate assolute di SendInput (0..65535)."""
    return round(max(0.0, min(1.0, float(v))) * 65535)


def events(left: bool, right: bool, prev: tuple[bool, bool]) -> list[int]:
    """Flag degli eventi da mandare: movimento + i tasti che cambiano rispetto a prima."""
    out = [MOVE | ABSOLUTE]
    if left != prev[0]:
        out.append(LEFTDOWN if left else LEFTUP)
    if right != prev[1]:
        out.append(RIGHTDOWN if right else RIGHTUP)
    return out


def _mac_drag(x: float, y: float) -> bool:
    """Movimento a tasto sinistro premuto: macOS vuole l'evento LeftMouseDragged (6), non MouseMoved."""
    from .. import macos
    try:
        cg = macos._lib("CoreGraphics")
        macos._lib("CoreFoundation")
        return macos._post(cg.CGEventCreateMouseEvent(None, 6, macos.CGPoint(x, y), 0))
    except Exception:
        return False


def _xdotool(*args: str) -> bool:
    exe = shutil.which("xdotool")
    if not exe:
        return False
    try:
        return subprocess.run([exe, *args], capture_output=True, timeout=3, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Mouse:
    def __init__(self):
        self.prev = (False, False)

    def send(self, x: float, y: float, left: bool = False, right: bool = False) -> bool:
        """True se l'evento e' partito; False se il sistema lo scarta (permesso mancante, xdotool assente)."""
        if sys.platform == "darwin":
            return self._send_mac(x, y, left, right)
        if sys.platform.startswith("linux"):
            return self._send_linux(x, y, left, right)
        if sys.platform != "win32":
            return False
        flags = events(left, right, self.prev)
        self.prev = (left, right)
        _send([MOUSEINPUT(to_abs(x), to_abs(y), 0, f | ABSOLUTE, 0, 0) for f in flags])
        return True

    def _send_mac(self, x, y, left, right) -> bool:
        from .. import macos
        if not macos.ax_trusted():  # senza Accessibilita' macOS scarta gli eventi in silenzio
            return False
        w, h = screen_size()
        px, py = to_abs(x) / 65535 * (w - 1), to_abs(y) / 65535 * (h - 1)
        ok = (_mac_drag if self.prev[0] and left else macos.post_mouse)(px, py)
        for (now, before), name in (((left, self.prev[0]), "left"), ((right, self.prev[1]), "right")):
            if now != before:
                ok = macos.post_mouse(px, py, f"{name}_{'down' if now else 'up'}") and ok
        self.prev = (left, right)
        return ok

    def _send_linux(self, x, y, left, right) -> bool:
        w, h = screen_size()
        ok = _xdotool("mousemove", str(round(to_abs(x) / 65535 * (w - 1))), str(round(to_abs(y) / 65535 * (h - 1))))
        for (now, before), b in (((left, self.prev[0]), "1"), ((right, self.prev[1]), "3")):
            if now != before:
                ok = _xdotool("mousedown" if now else "mouseup", b) and ok
        self.prev = (left, right)
        return ok

    def release(self):
        """Rilascia i tasti tenuti (telefono scollegato) senza spostare il puntatore."""
        prev, self.prev = self.prev, (False, False)
        if sys.platform == "darwin" and any(prev):
            from .. import macos
            px, py = _mac_cursor()
            for held, name in zip(prev, ("left_up", "right_up")):
                if held:
                    macos.post_mouse(px, py, name)
            return
        if sys.platform.startswith("linux"):
            for held, b in zip(prev, ("1", "3")):
                if held:
                    _xdotool("mouseup", b)
            return
        flags = [LEFTUP] * prev[0] + [RIGHTUP] * prev[1]
        if flags and sys.platform == "win32":
            _send([MOUSEINPUT(0, 0, 0, f, 0, 0) for f in flags])


def _mac_cursor() -> tuple[float, float]:
    """Posizione attuale del cursore (serve a rilasciare i tasti senza spostarlo)."""
    from .. import macos
    try:
        cg = macos._lib("CoreGraphics")
        cg.CGEventCreate.restype, cg.CGEventCreate.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
        cg.CGEventGetLocation.restype, cg.CGEventGetLocation.argtypes = macos.CGPoint, [ctypes.c_void_p]
        ev = cg.CGEventCreate(None)
        p = cg.CGEventGetLocation(ev)
        macos._lib("CoreFoundation").CFRelease(ev)
        return p.x, p.y
    except Exception:
        return 0.0, 0.0


def _send(inputs: list[MOUSEINPUT]):
    arr = (INPUT * len(inputs))(*[INPUT(type=0, mi=m) for m in inputs])
    ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def screen_size() -> tuple[int, int]:
    if sys.platform == "darwin":
        from .. import macos
        return macos.screen_size() or (1920, 1080)
    if sys.platform.startswith("linux"):
        exe = shutil.which("xdotool")
        try:
            out = subprocess.run([exe, "getdisplaygeometry"], capture_output=True, text=True, timeout=3).stdout.split() if exe else []
            return (int(out[0]), int(out[1])) if len(out) == 2 and int(out[0]) > 0 and int(out[1]) > 0 else (1920, 1080)
        except (OSError, subprocess.SubprocessError, ValueError):
            return 1920, 1080
    if sys.platform != "win32":
        return 1920, 1080
    u = ctypes.windll.user32
    return int(u.GetSystemMetrics(0)) or 1920, int(u.GetSystemMetrics(1)) or 1080
