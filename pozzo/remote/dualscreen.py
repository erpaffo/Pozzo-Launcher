"""Telefono come schermo touch per i giochi a due schermi (DS con melonDS, 3DS con Citra/Azahar/Lime3DS), su Windows
e macOS (su Linux solo i percorsi della configurazione: la cattura non c'e').

Con il telefono collegato al controller, prima dell'avvio si configura l'emulatore a finestre separate (lo leggono solo
all'avvio): lo schermo superiore a schermo intero sul PC, quello inferiore in una seconda finestra tenuta dietro, che
viene catturata e mandata al telefono; i tocchi tornano come clic inviati solo a quella finestra (il mouse del PC non si
muove). A fine partita la configurazione dell'emulatore torna com'era. Senza telefono non si tocca nulla.

melonDS 1.x (melonDS.toml):  [Instance0.Window0] ScreenSizing = 4 (TopOnly), [Instance0.Window1] Enabled + ScreenSizing = 5
Citra e derivati (qt-config.ini, QSettings): [Layout] layout_option=4 (SeparateWindows)
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import os
import re
import sys
from pathlib import Path

from .emusetup import backup, ini_get, ini_update

PLATFORMS = {"nds": "melon", "3ds": "citra"}
FAMILY = {"melonds": "melon", "citra": "citra", "azahar": "citra", "lime3ds": "citra"}
APPDATA_NAME = {"citra": "Citra", "azahar": "Azahar", "lime3ds": "Lime3DS"}
KEYS = {
    # HK_FastForwardToggle su Bloc Scorr (Qt Key_ScrollLock): il pulsante ⏩ del telefono lo manda alla finestra
    # (F1-F8 in melonDS caricano i salvataggi rapidi: meglio un tasto che non fa nulla)
    "melon": {"Instance0.Window0": {"ScreenSizing": "4"}, "Instance0.Window1": {"Enabled": "true", "ScreenSizing": "5"},
              "Instance0.Keyboard": {"HK_FastForwardToggle": "16777254"}},
    "citra": {"Layout": {"layout_option": "4", "layout_option\\default": "false"}},
}
SEP = {"melon": " = ", "citra": "="}
FULLSCREEN_ARG = "-f"  # melonDS e citra-qt: schermo intero all'avvio
MAX_SIDE = 640  # lato lungo dei fotogrammi mandati al telefono
PHONE_RECONNECT = 3.0  # secondi di grazia prima di riportare sul PC lo schermo di un telefono sparito


def show_on_pc(watching: bool, quiet: float, idle: float) -> bool:
    """Lo schermo inferiore va mostrato sul PC? Di norma resta nascosto dietro lo schermo principale: si mostra solo
    se il telefono non guarda piu' (dopo qualche secondo, il tempo di un riaggancio) oppure se non lo si usa da piu'
    di `idle` secondi (impostazione dell'app, 30 di default)."""
    return quiet > (float(idle) if watching else PHONE_RECONNECT)


def family(emulator_id: str) -> str | None:
    """Famiglia dell'emulatore («melon» o «citra») dal nome configurato, senza badare a maiuscole e spazi."""
    return FAMILY.get(str(emulator_id or "").strip().lower())


def supported() -> bool:
    return sys.platform in ("win32", "darwin")


def wanted(platform_id: str, emulator_id: str, enabled: bool, phone_connected: bool) -> bool:
    """Usare il telefono come schermo touch per questa partita?"""
    fam = family(emulator_id)
    return bool(supported() and enabled and phone_connected and fam and PLATFORMS.get(platform_id) == fam)


def config_file(emulator_id: str, exe: str) -> Path:
    eid = str(emulator_id or "").strip().lower()
    fam = family(eid)
    if fam is None:
        raise ValueError(f"emulatore non gestito per il doppio schermo: {emulator_id!r}")
    d = Path(exe).parent
    if fam == "melon":  # portatile se il file e' accanto all'exe (come quello dell'utente)
        if (d / "melonDS.toml").exists():
            return d / "melonDS.toml"
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", "")) / "melonDS" / "melonDS.toml"
        cands = _user_configs("melonDS")
        return next((p for p in cands if p.exists()), cands[0])
    if (d / "user").is_dir():
        return d / "user" / "config" / "qt-config.ini"
    name = APPDATA_NAME.get(eid, "Citra")
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / name / "config" / "qt-config.ini"
    cands = _user_configs(name)
    return next((p for p in cands if p.exists()), cands[0])


def _user_configs(name: str) -> list[Path]:
    """Dove melonDS (QStandardPaths::AppConfigLocation) e i Citra (cartella dati utente) tengono la configurazione
    fuori da Windows; il primo che esiste vince, se nessuno esiste si crea il primo."""
    h = Path.home()
    if sys.platform == "darwin":
        if name == "melonDS":  # Qt su macOS mette AppConfigLocation in Preferences; Application Support per sicurezza
            return [h / "Library" / "Preferences" / "melonDS" / "melonDS.toml",
                    h / "Library" / "Application Support" / "melonDS" / "melonDS.toml"]
        return [h / "Library" / "Application Support" / name / "config" / "qt-config.ini"]
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or h / ".config")
    if name == "melonDS":
        return [xdg / "melonDS" / "melonDS.toml"]
    return [xdg / f"{name.lower()}-emu" / "qt-config.ini"]


def _drop(text: str, section: str, key: str) -> str:
    """Toglie una chiave da una sezione (per rimettere com'era una chiave che prima non c'era)."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"\s*\[([^\]]+)\]\s*$", line)
        if m:
            cur = m.group(1)
        elif cur == section and "=" in line and line.split("=", 1)[0].strip() == key:
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def apply(emulator_id: str, exe: str) -> dict:
    """Scrive la configurazione a finestre separate; ritorna lo stato per restore() (valori originali)."""
    eid = str(emulator_id or "").strip().lower()
    fam = family(eid)
    if fam is None:
        raise ValueError(f"emulatore non gestito per il doppio schermo: {emulator_id!r}")
    p = config_file(eid, exe)
    text = p.read_text(encoding="utf-8-sig", errors="replace") if p.exists() else ""
    orig = {s: {k: ini_get(text, s, k) for k in kv} for s, kv in KEYS[fam].items()}
    backup(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ini_update(text, KEYS[fam], sep=SEP[fam]), encoding="utf-8")
    return {"emulator": eid, "file": str(p), "family": fam, "orig": orig}


def restore(state: dict) -> None:
    """Rimette i valori originali (chi non c'era viene tolto); il resto del file, salvato dall'emulatore, resta."""
    p = Path(state["file"])
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    keep = {s: {k: v for k, v in kv.items() if v is not None} for s, kv in state["orig"].items()}
    text = ini_update(text, {s: kv for s, kv in keep.items() if kv}, sep=SEP[state["family"]])
    for s, kv in state["orig"].items():
        for k, v in kv.items():
            if v is None:
                text = _drop(text, s, k)
    p.write_text(text, encoding="utf-8")


def client_point(x: float, y: float, w: int, h: int) -> tuple[int, int]:
    """Tocco normalizzato (0..1) sull'immagine del telefono -> punto nell'area client della finestra."""
    return min(w - 1, max(0, round(x * w))), min(h - 1, max(0, round(y * h)))


def screen_point(x: float, y: float, bounds: tuple[int, int, int, int], bar: int) -> tuple[int, int]:
    """macOS: tocco normalizzato -> punto sullo schermo, dai bordi della finestra (barra del titolo compresa in `bar`)."""
    left, top, right, bottom = bounds
    ax, ay, ax2, ay2 = screen_rect(right - left, bottom - top, bar)
    cx, cy = client_point(x, y, ax2 - ax, ay2 - ay)
    return left + ax + cx, top + ay + cy


# ---------------------------------------------------------------- finestre dell'emulatore (Win32)

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0200, 0x0201, 0x0202, 0x0001
WM_KEYDOWN, WM_KEYUP, VK_SCROLL, SC_SCROLL = 0x0100, 0x0101, 0x91, 0x46
HWND_TOPMOST, HWND_NOTOPMOST, HWND_BOTTOM = -1, -2, 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2


class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


def _user32():
    """user32 con i tipi dichiarati: su Windows a 64 bit HWND_TOPMOST (-1) e gli HWND vanno passati come puntatori."""
    from ctypes import wintypes
    u = ctypes.windll.user32
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               wintypes.UINT]
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
    u.ChildWindowFromPointEx.restype = wintypes.HWND
    u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u.MonitorFromWindow.restype = wintypes.HANDLE
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    for f in ("GetClientRect", "GetWindowRect"):
        getattr(u, f).argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    # gli handle non devono essere troncati a 32 bit (touch e primo piano fallirebbero a intermittenza)
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.SetForegroundWindow.argtypes = [wintypes.HWND]
    u.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]
    u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    return u


def _gdi32():
    from ctypes import wintypes
    g = ctypes.windll.gdi32
    g.CreateCompatibleDC.argtypes = [wintypes.HDC]
    g.CreateCompatibleDC.restype = wintypes.HDC
    g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    g.SelectObject.restype = wintypes.HGDIOBJ
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    g.DeleteDC.argtypes = [wintypes.HDC]
    g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wintypes.UINT]
    return g


def _windows(pids: set[int]) -> list[tuple[int, tuple[int, int, int, int]]]:
    """Finestre visibili e abbastanza grandi dei processi indicati: [(hwnd, (sinistra, alto, destra, basso))]."""
    from ctypes import wintypes
    u = _user32()
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and u.IsWindowVisible(h):
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 120 and r.bottom - r.top > 90:
                out.append((h, (r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumWindows(cb, 0)
    return out


def _owner(hwnd: int) -> int | None:
    """Finestra proprietaria (GW_OWNER): la seconda finestra dell'emulatore appartiene alla principale."""
    from ctypes import wintypes
    u = _user32()
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    return u.GetWindow(hwnd, 4) or None  # 4 = GW_OWNER


def screen_rect(w: int, h: int, bar: int) -> tuple[int, int, int, int]:
    """Dove l'emulatore disegna lo schermo (4:3, sia DS sia 3DS) nell'area client w x h con `bar` px di menu in alto:
    centrato e il piu' grande possibile nello spazio sotto il menu."""
    ph = max(1, h - bar)
    sw, sh = (w, w * 3 // 4) if w * 3 <= ph * 4 else (ph * 4 // 3, ph)
    x, y = (w - sw) // 2, bar + (ph - sh) // 2
    return x, y, x + sw, y + sh


# ---------------------------------------------------------------- finestre dell'emulatore (macOS, CoreGraphics)

_CG: dict = {}


def _cg():
    """CoreGraphics/CoreFoundation con le funzioni di cattura tipizzate (istanze proprie: macos.py resta com'e')."""
    if not _CG:
        from .. import macos
        vp, u32, sz = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t
        cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        for lib, fn, res, args in (
                (cg, "CGWindowListCreateImage", vp, [macos.CGRect, u32, u32, u32]),
                (cg, "CGWindowListCopyWindowInfo", vp, [u32, u32]),
                (cg, "CGRectMakeWithDictionaryRepresentation", ctypes.c_bool, [vp, ctypes.POINTER(macos.CGRect)]),
                (cg, "CGImageGetWidth", sz, [vp]), (cg, "CGImageGetHeight", sz, [vp]),
                (cg, "CGImageGetBytesPerRow", sz, [vp]), (cg, "CGImageGetDataProvider", vp, [vp]),
                (cg, "CGDataProviderCopyData", vp, [vp]), (cg, "CGImageRelease", None, [vp]),
                (cf, "CFDataGetBytePtr", vp, [vp]), (cf, "CFDataGetLength", ctypes.c_long, [vp]),
                (cf, "CFRelease", None, [vp]), (cf, "CFArrayGetCount", ctypes.c_long, [vp]),
                (cf, "CFArrayGetValueAtIndex", vp, [vp, ctypes.c_long]), (cf, "CFDictionaryGetValue", vp, [vp, vp]),
                (cf, "CFStringCreateWithCString", vp, [vp, ctypes.c_char_p, u32]),
                (cf, "CFNumberGetValue", ctypes.c_bool, [vp, ctypes.c_int, vp])):
            f = getattr(lib, fn)
            f.restype, f.argtypes = res, args
        _CG.update(cg=cg, cf=cf, rect=macos.CGRect, keys={  # chiavi create una volta e tenute: costanti di processo
            k: cf.CFStringCreateWithCString(None, k.encode(), 0x08000100)
            for k in ("kCGWindowOwnerPID", "kCGWindowLayer", "kCGWindowNumber", "kCGWindowBounds")})
    return _CG


def _cg_windows(pids: set[int] | None = None, wid: int = 0) -> list[tuple[int, tuple[int, int, int, int]]]:
    """Come _windows ma su macOS: finestre normali (layer 0) a schermo dei processi, o la sola finestra `wid`.
    Bordi in punti, origine in alto a sinistra: le stesse coordinate degli eventi del mouse."""
    c = _cg()
    cg, cf, keys = c["cg"], c["cf"], c["keys"]
    arr = cg.CGWindowListCopyWindowInfo(8, wid) if wid else cg.CGWindowListCopyWindowInfo(1 | 16, 0)
    if not arr:
        return []

    def num(d, k):
        ref, v = cf.CFDictionaryGetValue(d, keys[k]), ctypes.c_int64()
        return v.value if ref and cf.CFNumberGetValue(ref, 4, ctypes.byref(v)) else None  # kCFNumberSInt64Type

    out = []
    try:
        for i in range(cf.CFArrayGetCount(arr)):
            d = cf.CFArrayGetValueAtIndex(arr, i)
            if (pids is not None and num(d, "kCGWindowOwnerPID") not in pids) or num(d, "kCGWindowLayer") != 0:
                continue
            r, b = c["rect"](), cf.CFDictionaryGetValue(d, keys["kCGWindowBounds"])
            if b and cg.CGRectMakeWithDictionaryRepresentation(b, ctypes.byref(r)) and (wid or (r.w > 120 and r.h > 90)):
                x, y = round(r.x), round(r.y)
                out.append((num(d, "kCGWindowNumber"), (x, y, x + round(r.w), y + round(r.h))))
    finally:
        cf.CFRelease(arr)
    return out


def _cg_capture(wid: int):
    """Immagine (Pillow, RGBA) della sola finestra, anche se coperta; None se non si puo' catturare.
    CGWindowListCreateImage e' deprecata da macOS 14 ma funziona ancora (ScreenCaptureKit richiederebbe pyobjc).
    Senza il permesso Registrazione schermo torna NULL o un'immagine vuota (solo sfondo): conta come fallimento."""
    from PIL import Image
    c = _cg()
    cg, cf = c["cg"], c["cf"]
    null = c["rect"](float("inf"), float("inf"), 0.0, 0.0)  # CGRectNull: i bordi della finestra
    img = cg.CGWindowListCreateImage(null, 8, wid, 1 | 16)  # IncludingWindow; BoundsIgnoreFraming|NominalResolution
    if not img:
        return None
    try:
        w, h, stride = cg.CGImageGetWidth(img), cg.CGImageGetHeight(img), cg.CGImageGetBytesPerRow(img)
        data = cg.CGDataProviderCopyData(cg.CGImageGetDataProvider(img))
        if not data or w <= 0 or h <= 0:
            return None
        try:
            raw = ctypes.string_at(cf.CFDataGetBytePtr(data), cf.CFDataGetLength(data))
        finally:
            cf.CFRelease(data)
    finally:
        cg.CGImageRelease(img)
    out = Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRA", stride, 1)
    lo, hi = out.convert("L").getextrema()
    return None if lo == hi else out  # tutta di un colore: senza permesso (o finestra non ancora disegnata)


class Session:
    """Lo schermo inferiore di una partita: trovato, catturato, toccato, nascosto o in riquadro."""

    def __init__(self, pid: int, on_pc: bool = False):
        self.pid, self.hwnd, self.main, self.bar, self.down, self.last = pid, None, None, 0, False, None
        # «telefono come touch screen»: le finestre restano dove le mette l'emulatore (o l'utente), mai spostate ne' in
        # primo piano; tocchi (PostMessage) e cattura (PrintWindow) funzionano anche con la finestra coperta
        self.on_pc = on_pc
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # coordinate in pixel veri anche con lo zoom di Windows
            except Exception:
                pass

    def find(self) -> bool:
        """Le due finestre dell'emulatore. Su Windows lo schermo inferiore e' la finestra «di proprieta'» della principale
        (melonDS e Citra creano la seconda finestra figlia della prima): vale anche quando sono grandi uguali, come con
        «telefono come touch screen» (niente schermo intero). Altrimenti la piu' piccola (l'altra e' a schermo intero)."""
        try:
            import psutil
            pids = {self.pid, *(c.pid for c in psutil.Process(self.pid).children(recursive=True))}
        except Exception:
            pids = {self.pid}
        wins = _windows(pids) if sys.platform == "win32" else _cg_windows(pids)
        if len(wins) < 2:
            return False
        wins.sort(key=lambda w: (w[1][2] - w[1][0]) * (w[1][3] - w[1][1]))
        self.hwnd, self.main = wins[0][0], wins[-1][0]
        if sys.platform == "win32":
            hs = {h for h, _ in wins}
            owned = [(h, o) for h, _ in wins if (o := _owner(h)) in hs]
            if len(owned) == 1:
                self.hwnd, self.main = owned[0]
        self._measure()
        return True

    def _measure(self):
        """Altezza della barra dei menu (melonDS; Citra non ne ha): l'emulatore dimensiona la finestra sullo schermo,
        quindi l'area client in piu' rispetto al 4:3 e' la barra. Si misura finche' non la si trova, prima di ridimensionare."""
        if not self.bar:
            w, h = self._client()
            extra = h - w * 3 // 4
            self.bar = extra if 0 < extra <= 60 else 0

    def _client(self) -> tuple[int, int]:
        if sys.platform == "darwin":  # la finestra intera: in alto la barra del titolo fa da «barra dei menu»
            l, t, r, b = self._bounds()
            return r - l, b - t
        from ctypes import wintypes
        r = wintypes.RECT()
        _user32().GetClientRect(self.hwnd, ctypes.byref(r))
        return r.right, r.bottom

    def _bounds(self) -> tuple[int, int, int, int]:
        wins = _cg_windows(wid=self.hwnd)
        return wins[0][1] if wins else (0, 0, 0, 0)

    def _area(self) -> tuple[int, int, int, int]:
        return screen_rect(*self._client(), self.bar)

    def frame(self) -> bytes | None:
        """JPEG dello schermo inferiore (anche se la finestra e' coperta); None se uguale al precedente."""
        if sys.platform == "darwin":
            return self._frame_mac()
        from PIL import Image
        u, g = _user32(), _gdi32()
        w, h = self._client()
        if w <= 0 or h <= 0:
            return None
        hdc = u.GetDC(self.hwnd)
        mem = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, w, h)
        old = g.SelectObject(mem, bmp)
        try:
            u.PrintWindow(self.hwnd, mem, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            bi = _BMIH(ctypes.sizeof(_BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # altezza negativa = dall'alto in basso
            buf = ctypes.create_string_buffer(w * h * 4)
            g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
        finally:
            g.SelectObject(mem, old)
            g.DeleteObject(bmp)
            g.DeleteDC(mem)
            u.ReleaseDC(self.hwnd, hdc)
        digest = hashlib.blake2b(buf.raw, digest_size=16).digest()
        if digest == self.last:
            return None
        self.last = digest
        img = Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB").crop(self._area())
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()

    def _frame_mac(self) -> bytes | None:
        img = _cg_capture(self.hwnd)
        if img is None:
            return None
        digest = hashlib.blake2b(img.tobytes(), digest_size=16).digest()
        if digest == self.last:
            return None
        self.last = digest
        img = img.convert("RGB").crop(screen_rect(*img.size, self.bar))  # immagine in punti come i bordi: stessa barra
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()

    def touch(self, x: float, y: float, down: bool):
        """Pennino: clic alla sola finestra dell'emulatore (alla finestra figlia sotto il punto, se c'e')."""
        if sys.platform == "darwin":
            # shortcut: macOS non ha clic «solo a una finestra»: il cursore si sposta davvero e il clic va a cio'
            # che sta sopra in quel punto; servono il permesso Accessibilita' e la finestra visibile.
            from .. import macos
            px, py = screen_point(x, y, self._bounds(), self.bar)
            act = "left_down" if down and not self.down else "move" if down else "left_up" if self.down else None
            if act:
                macos.post_mouse(px, py, act)
            self.down = down
            return
        from ctypes import wintypes
        u = _user32()
        left, top, right, bottom = self._area()
        cx, cy = client_point(x, y, right - left, bottom - top)
        cx, cy = cx + left, cy + top  # dall'immagine (solo lo schermo) all'area client della finestra
        target = u.ChildWindowFromPointEx(self.hwnd, wintypes.POINT(cx, cy), 0x3) or self.hwnd  # salta invisibili/disattivate
        pt = wintypes.POINT(cx, cy)
        if target != self.hwnd:
            u.MapWindowPoints(self.hwnd, target, ctypes.byref(pt), 1)
        lp = (pt.y & 0xFFFF) << 16 | (pt.x & 0xFFFF)
        if down and not self.down:
            u.PostMessageW(target, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        elif down:
            u.PostMessageW(target, WM_MOUSEMOVE, MK_LBUTTON, lp)
        elif self.down:
            u.PostMessageW(target, WM_LBUTTONUP, 0, lp)
        self.down = down

    def fast_forward(self):
        """Avanzamento veloce acceso/spento (melonDS, HK_FastForwardToggle = Bloc Scorr): il tasto va alla sola finestra
        dell'emulatore, anche se non e' in primo piano."""
        if sys.platform != "win32" or not self.main:
            return
        u = _user32()
        lp = 1 | SC_SCROLL << 16
        u.PostMessageW(self.main, WM_KEYDOWN, VK_SCROLL, lp)
        u.PostMessageW(self.main, WM_KEYUP, VK_SCROLL, lp | 0xC0000000)

    def _place(self, after: int, x: int | None, y: int | None, width: int, flags: int):
        """Finestra con l'area client larga `width` e alta quanto lo schermo 4:3 (+ la barra dei menu)."""
        from ctypes import wintypes
        u = _user32()
        wr, (cw, ch) = wintypes.RECT(), self._client()
        u.GetWindowRect(self.hwnd, ctypes.byref(wr))
        bw, bh = (wr.right - wr.left) - cw, (wr.bottom - wr.top) - ch  # bordi e barra del titolo
        if x is None:
            flags |= SWP_NOMOVE
        u.SetWindowPos(self.hwnd, after, x or 0, y or 0, width + bw, width * 3 // 4 + self.bar + bh, flags)

    def hide(self):
        """Dietro lo schermo intero: sul PC si vede solo lo schermo superiore. Larga 640 px: immagine nitida sul telefono."""
        if self.on_pc or sys.platform != "win32":  # macOS: si lascia dov'e', i tocchi si mappano dai bordi veri della finestra
            return
        u = _user32()
        self._measure()
        self._place(HWND_NOTOPMOST, None, None, MAX_SIDE, SWP_NOACTIVATE)
        u.SetWindowPos(self.hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        if self.main:
            u.SetForegroundWindow(self.main)  # lo schermo superiore davanti a tutto, con i tasti

    def pip(self):
        """Telefono scollegato: lo schermo inferiore in un riquadro in basso a destra, sopra il gioco, usabile col mouse."""
        if self.on_pc or sys.platform != "win32":
            return
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]
        u = _user32()
        mi = MONITORINFO(ctypes.sizeof(MONITORINFO))
        u.GetMonitorInfoW(u.MonitorFromWindow(self.main or self.hwnd, 2), ctypes.byref(mi))
        r = mi.rcMonitor
        w = (r.right - r.left) * 3 // 10
        h = w * 3 // 4 + self.bar + 60  # per la posizione; la dimensione esatta la calcola _place
        self._place(HWND_TOPMOST, r.right - w - 40, r.bottom - h - 40, w, SWP_NOACTIVATE | SWP_SHOWWINDOW)
