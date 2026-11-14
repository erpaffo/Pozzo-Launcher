"""Helper macOS condivisi (mouse/tastiera, schermo, finestre) via ctypes, senza pyobjc.

Ogni funzione ritorna None/False fuori da macOS o a qualunque errore: mai eccezioni.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys


_FW = "/System/Library/Frameworks/%s.framework/%s"
_libs: dict = {}

_MOUSE = {  # azione -> (CGEventType, CGMouseButton)
    "move": (5, 0), "left_down": (1, 0), "left_up": (2, 0),
    "right_down": (3, 1), "right_up": (4, 1),
}


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                ("w", ctypes.c_double), ("h", ctypes.c_double)]


def _lib(name: str):
    """Carica un framework una volta sola; la tipizzazione e' fatta in _setup."""
    if name not in _libs:
        lib = ctypes.cdll.LoadLibrary(_FW % (name, name))
        _setup(name, lib)
        _libs[name] = lib
    return _libs[name]


def _setup(name: str, lib) -> None:
    vp, i32, u32 = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32
    sig = {}
    if name == "ApplicationServices":
        sig = {"AXIsProcessTrusted": (ctypes.c_bool, [])}
    elif name == "CoreGraphics":
        sig = {
            "CGMainDisplayID": (u32, []),
            "CGDisplayPixelsWide": (ctypes.c_size_t, [u32]),
            "CGDisplayPixelsHigh": (ctypes.c_size_t, [u32]),
            "CGEventCreateMouseEvent": (vp, [vp, u32, CGPoint, u32]),
            "CGEventCreateKeyboardEvent": (vp, [vp, ctypes.c_uint16, ctypes.c_bool]),
            "CGEventSetFlags": (None, [vp, ctypes.c_uint64]),
            "CGEventPost": (None, [u32, vp]),
            "CGWindowListCopyWindowInfo": (vp, [u32, u32]),
            "CGRectMakeWithDictionaryRepresentation": (ctypes.c_bool, [vp, ctypes.POINTER(CGRect)]),
        }
    elif name == "CoreFoundation":
        sig = {
            "CFRelease": (None, [vp]),
            "CFArrayGetCount": (ctypes.c_long, [vp]),
            "CFArrayGetValueAtIndex": (vp, [vp, ctypes.c_long]),
            "CFDictionaryGetValue": (vp, [vp, vp]),
            "CFStringCreateWithCString": (vp, [vp, ctypes.c_char_p, u32]),
            "CFNumberGetValue": (ctypes.c_bool, [vp, ctypes.c_int, vp]),
        }
    for fn, (res, args) in sig.items():
        f = getattr(lib, fn)
        f.restype, f.argtypes = res, args


def _darwin() -> bool:
    return sys.platform == "darwin"


def osascript(script: str, timeout=5, runner=subprocess.run) -> str | None:
    if not _darwin():
        return None
    try:
        r = runner(["/usr/bin/osascript", "-e", script], capture_output=True, text=True,
                   timeout=timeout, check=False)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def screen_size() -> tuple[int, int] | None:
    if not _darwin():
        return None
    try:
        cg = _lib("CoreGraphics")
        d = cg.CGMainDisplayID()
        w, h = int(cg.CGDisplayPixelsWide(d)), int(cg.CGDisplayPixelsHigh(d))
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def _post(event) -> bool:
    if not event:
        return False
    try:
        _lib("CoreGraphics").CGEventPost(0, event)  # kCGHIDEventTap
        return True
    finally:
        _lib("CoreFoundation").CFRelease(event)


def post_mouse(x: float, y: float, button: str = "move") -> bool:
    if not _darwin() or button not in _MOUSE:
        return False
    try:
        etype, btn = _MOUSE[button]
        _lib("CoreFoundation")
        ev = _lib("CoreGraphics").CGEventCreateMouseEvent(None, etype, CGPoint(x, y), btn)
        return _post(ev)
    except Exception:
        return False


def post_key(keycode: int, down: bool, flags: int = 0) -> bool:
    if not _darwin():
        return False
    try:
        _lib("CoreFoundation")
        cg = _lib("CoreGraphics")
        ev = cg.CGEventCreateKeyboardEvent(None, keycode, bool(down))
        if ev and flags:
            cg.CGEventSetFlags(ev, flags)
        return _post(ev)
    except Exception:
        return False


def ax_trusted() -> bool:
    if not _darwin():
        return False
    try:
        return bool(_lib("ApplicationServices").AXIsProcessTrusted())
    except Exception:
        return False


def frontmost_pid() -> int | None:
    out = osascript('tell application "System Events" to get unix id of first process whose frontmost is true')
    try:
        return int(out) if out else None
    except ValueError:
        return None


def window_id_for_pid(pid: int) -> int | None:
    """CGWindowID della finestra layer 0 piu' grande on-screen del processo."""
    if not _darwin():
        return None
    try:
        cg, cf = _lib("CoreGraphics"), _lib("CoreFoundation")
        keys = {k: cf.CFStringCreateWithCString(None, k.encode(), 0x08000100)  # UTF8
                for k in ("kCGWindowOwnerPID", "kCGWindowLayer", "kCGWindowNumber", "kCGWindowBounds")}
        arr = cg.CGWindowListCopyWindowInfo(1 | 16, 0)  # OnScreenOnly | ExcludeDesktopElements
        if not arr:
            return None

        def num(d, k):
            ref = cf.CFDictionaryGetValue(d, keys[k])
            v = ctypes.c_int64()
            if ref and cf.CFNumberGetValue(ref, 4, ctypes.byref(v)):  # kCFNumberSInt64Type
                return v.value
            return None

        best, best_area = None, -1.0
        try:
            for i in range(cf.CFArrayGetCount(arr)):
                d = cf.CFArrayGetValueAtIndex(arr, i)
                if num(d, "kCGWindowOwnerPID") != pid or num(d, "kCGWindowLayer") != 0:
                    continue
                r = CGRect()
                b = cf.CFDictionaryGetValue(d, keys["kCGWindowBounds"])
                if not (b and cg.CGRectMakeWithDictionaryRepresentation(b, ctypes.byref(r))):
                    continue
                if r.w * r.h > best_area:
                    best, best_area = num(d, "kCGWindowNumber"), r.w * r.h
        finally:
            cf.CFRelease(arr)
            for k in keys.values():
                cf.CFRelease(k)
        return best
    except Exception:
        return None
