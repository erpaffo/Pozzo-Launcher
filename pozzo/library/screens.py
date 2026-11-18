"""Schermate dei giochi: catturate dall'app durante il gioco o importate dagli emulatori e da Steam.

Tre modi per averle nell'app (tutte copiate in <cache>/screens, gli originali non vengono toccati):
  1. scorciatoia dell'app mentre si gioca: tastiera (predefinita Ctrl+Shift+S) o controller
     (Select/View + R1/RB): cattura la finestra del gioco, con qualsiasi emulatore;
  2. a fine sessione si importano le schermate fatte con il tasto dell'emulatore stesso, cercando
     nelle cartelle in cui le salva (RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, Cemu, Ryujinx, ...)
     e nella cartella di Xbox Game Bar: solo i file creati durante la sessione;
  3. schermate di Steam dei giochi Steam della libreria (userdata/<utente>/760/remote/<appid>).
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)
IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".webm", ".mkv"}  # clip: non copiati, si registra il file originale
SCHEMA = """
CREATE TABLE IF NOT EXISTS screenshots(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, file TEXT, taken REAL,
                                       source TEXT, origin TEXT UNIQUE, w INT, h INT);
CREATE INDEX IF NOT EXISTS screenshots_key ON screenshots(key);
"""
DEFAULTS = {"hotkey": "ctrl+shift+s", "pause_hotkey": "ctrl+shift+p", "pad": True, "import_emulator": True}


def settings(cfg) -> dict:
    return {**DEFAULTS, **(cfg.app.get("screenshots") or {})}


class Shots:
    """Archivio delle schermate (file in <cache>/screens, elenco in userdata.db)."""

    def __init__(self, cache_folder, db_path):
        self.root = Path(cache_folder) / "screens"
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        if "kind" not in {r[1] for r in self.db.execute("PRAGMA table_info(screenshots)")}:
            self.db.execute("ALTER TABLE screenshots ADD COLUMN kind TEXT NOT NULL DEFAULT 'image'")
            self.db.commit()
        self.lock = threading.Lock()

    def _dest(self, key: str, taken: float, ext: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:80]
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(taken))
        d = self.root / safe
        d.mkdir(parents=True, exist_ok=True)
        p, i = d / f"{stamp}{ext}", 1
        while p.exists():
            p, i = d / f"{stamp}-{i}{ext}", i + 1
        return p

    def _insert(self, key, path: Path, taken, source, origin, w=0, h=0, kind="image") -> int | None:
        # video: path assoluto del file originale (non copiato); immagini: relativo a <cache>/screens
        rel = str(path) if kind == "video" else path.relative_to(self.root).as_posix()
        with self.lock:
            try:
                cur = self.db.execute("INSERT INTO screenshots(key, file, taken, source, origin, w, h, kind) VALUES(?,?,?,?,?,?,?,?)",
                                      (key, rel, taken, source, origin, w, h, kind))
                self.db.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:  # gia' importata
                if kind == "image":  # mai cancellare l'originale di un video
                    path.unlink(missing_ok=True)
                return None

    def add_image(self, key: str, img, source: str = "PozzoLauncher") -> int | None:
        taken = time.time()
        p = self._dest(key, taken, ".png")
        img.save(p, "PNG")
        return self._insert(key, p, taken, source, f"capture:{p.name}:{taken}", img.width, img.height)

    def add_file(self, key: str, src: Path, source: str) -> int | None:
        origin = f"file:{os.path.normcase(str(src.resolve()))}:{int(src.stat().st_mtime)}"
        with self.lock:
            if self.db.execute("SELECT 1 FROM screenshots WHERE origin=?", (origin,)).fetchone():
                return None
        taken = src.stat().st_mtime
        p = self._dest(key, taken, src.suffix.lower())
        shutil.copy2(src, p)
        w = h = 0
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
        except Exception:
            pass
        return self._insert(key, p, taken, source, origin, w, h)

    def add_clip(self, key: str, src: Path, source: str) -> int | None:
        origin = f"file:{os.path.normcase(str(src.resolve()))}:{int(src.stat().st_mtime)}"
        with self.lock:
            if self.db.execute("SELECT 1 FROM screenshots WHERE origin=?", (origin,)).fetchone():
                return None
        taken = src.stat().st_mtime
        return self._insert(key, src.resolve(), taken, source, origin, kind="video")

    def list(self, keys: list[str] | None = None, limit: int = 5000) -> list[dict]:
        with self.lock:
            if keys is None:
                rows = self.db.execute("SELECT id, key, file, taken, source, w, h, kind FROM screenshots ORDER BY taken DESC LIMIT ?",
                                       (limit,)).fetchall()
            else:
                if not keys:
                    return []
                q = ",".join("?" * len(keys))
                rows = self.db.execute(f"SELECT id, key, file, taken, source, w, h, kind FROM screenshots WHERE key IN ({q}) "  # nosec B608 - solo nomi/placeholder fissi, valori via parametri
                                       "ORDER BY taken DESC", keys).fetchall()
        return [{"id": r[0], "key": r[1], "file": r[2], "taken": r[3], "source": r[4], "w": r[5], "h": r[6], "kind": r[7]}
                for r in rows]

    def counts(self) -> dict[str, int]:
        with self.lock:
            return dict(self.db.execute("SELECT key, COUNT(*) FROM screenshots GROUP BY key").fetchall())

    def path(self, sid: int) -> Path | None:
        with self.lock:
            r = self.db.execute("SELECT file FROM screenshots WHERE id=?", (sid,)).fetchone()
        if not r:
            return None
        p = Path(r[0])
        return p if p.is_absolute() else self.root / p

    def delete(self, sid: int):
        p = self.path(sid)
        with self.lock:
            kind = self.db.execute("SELECT kind FROM screenshots WHERE id=?", (sid,)).fetchone()
            self.db.execute("DELETE FROM screenshots WHERE id=?", (sid,))
            self.db.commit()
        if p and kind and kind[0] == "image":  # il video originale resta dov'e'
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------- cattura della finestra del gioco
def _mac_capture(pid: int | None = None, runner=subprocess.run):
    """screencapture della finestra del gioco (o di quella in primo piano), altrimenti tutto lo schermo."""
    from PIL import Image

    from .. import macos
    wid = macos.window_id_for_pid(pid or macos.frontmost_pid() or 0)
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        # -o: niente ombra; -x: niente suono (il nostro lo fa beep())
        for argv in ([["screencapture", "-x", "-o", "-l", str(wid), tmp]] if wid else []) + [["screencapture", "-x", tmp]]:
            runner(argv, capture_output=True, timeout=15, check=False)
            if os.path.getsize(tmp) > 0:
                with Image.open(tmp) as im:
                    im.load()
                    return im.copy()
        # file vuoto: manca il permesso Registrazione schermo
        raise OSError("screencapture non ha prodotto l'immagine (permesso Registrazione schermo?)")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def capture_foreground(pid: int | None = None):
    """Immagine della finestra in primo piano (Windows) o del gioco (macOS); su Linux tutto lo schermo."""
    if sys.platform == "darwin":
        return _mac_capture(pid)
    from PIL import ImageGrab
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        hwnd = user32.GetForegroundWindow()
        rect = wintypes.RECT()
        # bordi reali della finestra (senza ombra), poi in alternativa GetWindowRect
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        ok = False
        try:
            ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                                            ctypes.sizeof(rect)) == 0
        except Exception:
            ok = False
        if not ok:
            ok = bool(user32.GetWindowRect(hwnd, ctypes.byref(rect)))
        if ok and rect.right - rect.left > 50 and rect.bottom - rect.top > 50:
            return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
        return ImageGrab.grab(all_screens=True)
    return ImageGrab.grab()


def beep():
    if sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:  # in background: non deve rallentare il gioco
            subprocess.Popen(["afplay", "/System/Library/Sounds/Pop.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# ---------------------------------------------------------------- scorciatoia da tastiera (Windows, macOS)
_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(s: str) -> tuple[int, int] | None:
    """'ctrl+shift+s' -> (modificatori, codice tasto virtuale)."""
    parts = [p.strip().lower() for p in (s or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            return None
        mods |= _MODS[p]
    k = parts[-1]
    if len(k) == 1 and k.isalnum():
        vk = ord(k.upper())
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", k):
        vk = 0x70 + int(k[1:]) - 1
    else:
        vk = {"printscreen": 0x2C, "print": 0x2C, "pause": 0x13, "insert": 0x2D, "home": 0x24, "end": 0x23}.get(k)
        if vk is None:
            return None
    return mods | 0x4000, vk  # 0x4000 = MOD_NOREPEAT


# macOS: codice tasto virtuale Windows -> kVK (tastiera ANSI); Stamp/Pausa/Ins su F13/F15/Help come le tastiere Apple
_MAC_KEYS = {
    **dict(zip(b"ASDFHGZXCV", range(10))), **dict(zip(b"BQWERYT", range(11, 18))),
    ord("1"): 0x12, ord("2"): 0x13, ord("3"): 0x14, ord("4"): 0x15, ord("6"): 0x16, ord("5"): 0x17,
    ord("9"): 0x19, ord("7"): 0x1A, ord("8"): 0x1C, ord("0"): 0x1D, ord("O"): 0x1F, ord("U"): 0x20,
    ord("I"): 0x22, ord("P"): 0x23, ord("L"): 0x25, ord("J"): 0x26, ord("K"): 0x28, ord("N"): 0x2D, ord("M"): 0x2E,
    **dict(zip(range(0x70, 0x84), (0x7A, 0x78, 0x63, 0x76, 0x60, 0x61, 0x62, 0x64, 0x65, 0x6D, 0x67, 0x6F,
                                   0x69, 0x6B, 0x71, 0x6A, 0x40, 0x4F, 0x50, 0x5A))),  # F1-F20
    0x2C: 0x69, 0x13: 0x71, 0x2D: 0x72, 0x24: 0x73, 0x23: 0x77,
}
# MOD_ALT/CONTROL/SHIFT/WIN -> maschere CGEventFlags (Alt, Ctrl, Shift, Cmd)
_MAC_MODS = ((0x1, 0x80000), (0x2, 0x40000), (0x4, 0x20000), (0x8, 0x100000))
_MAC_MOD_MASK = 0x80000 | 0x40000 | 0x20000 | 0x100000


def mac_hotkey(combo: str) -> tuple[int, int] | None:
    """'ctrl+shift+s' -> (kVK, flag dei modificatori) per il tap di macOS."""
    hk = parse_hotkey(combo)
    if not hk or hk[1] not in _MAC_KEYS:
        return None
    return _MAC_KEYS[hk[1]], sum(f for m, f in _MAC_MODS if hk[0] & m)


def mac_match(keycode: int, flags: int, want: tuple[int, int]) -> bool:
    # modificatori esatti: Ctrl+Shift+S non deve scattare con Cmd+Ctrl+Shift+S
    return keycode == want[0] and (flags & _MAC_MOD_MASK) == want[1]


_TAP_CB = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p)
_tap_warned = False


def _mac_libs():
    # istanze proprie (non quelle di pozzo.macos): argtypes indipendenti
    vp, u32 = ctypes.c_void_p, ctypes.c_uint32
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    for lib, fn, res, args in (
            (cg, "CGEventTapCreate", vp, [u32, u32, u32, ctypes.c_uint64, _TAP_CB, vp]),
            (cg, "CGEventTapEnable", None, [vp, ctypes.c_bool]),
            (cg, "CGEventGetIntegerValueField", ctypes.c_int64, [vp, u32]),
            (cg, "CGEventGetFlags", ctypes.c_uint64, [vp]),
            (cf, "CFMachPortCreateRunLoopSource", vp, [vp, vp, ctypes.c_long]),
            (cf, "CFRunLoopGetCurrent", vp, []),
            (cf, "CFRunLoopAddSource", None, [vp, vp, vp]),
            (cf, "CFRunLoopRun", None, []),
            (cf, "CFRunLoopStop", None, [vp]),
            (cf, "CFRelease", None, [vp])):
        f = getattr(lib, fn)
        f.restype, f.argtypes = res, args
    return cg, cf


class Hotkey:
    """Scorciatoia globale (funziona anche con il gioco in primo piano). Windows e macOS."""

    def __init__(self, combo: str, callback):
        self.combo, self.callback = combo, callback
        self.tid = None
        self.thread = None
        self._rl = self._tap = self._cb = None

    def start(self) -> bool:
        if sys.platform == "darwin":
            return self._mac_start()
        if sys.platform != "win32" or not parse_hotkey(self.combo):
            return False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    # ---- macOS: CGEventTap in sola lettura su un thread con il suo CFRunLoop
    def _mac_start(self) -> bool:
        want = mac_hotkey(self.combo)
        if not want:
            return False
        ready, ok = threading.Event(), []
        self.thread = threading.Thread(target=self._mac_loop, args=(want, ready, ok), daemon=True)
        self.thread.start()
        ready.wait(5)
        return bool(ok)

    def _mac_loop(self, want, ready, ok):
        global _tap_warned
        try:
            cg, cf = _mac_libs()

            def cb(proxy, etype, event, info):
                if etype in (0xFFFFFFFE, 0xFFFFFFFF):  # tap disattivato dal sistema (timeout/input): riattiva
                    cg.CGEventTapEnable(self._tap, True)
                elif etype == 10 and not cg.CGEventGetIntegerValueField(event, 8) \
                        and mac_match(cg.CGEventGetIntegerValueField(event, 9), cg.CGEventGetFlags(event), want):
                    # fuori dal tap: una cattura lenta lo farebbe disattivare per timeout
                    threading.Thread(target=self._fire, daemon=True).start()
                return event  # 8 = autorepeat (come MOD_NOREPEAT), 9 = keycode

            self._cb = _TAP_CB(cb)  # riferimento tenuto: altrimenti il GC libera la callback
            # sessione, in testa, sola lettura, solo KeyDown
            self._tap = cg.CGEventTapCreate(1, 0, 1, 1 << 10, self._cb, None)
            if not self._tap:
                if not _tap_warned:
                    _tap_warned = True
                    log.warning("scorciatoia globale non disponibile: serve il permesso Monitoraggio input/Accessibilita'")
                return
            src = cf.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._rl = cf.CFRunLoopGetCurrent()
            cf.CFRunLoopAddSource(self._rl, src, ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes"))
            cg.CGEventTapEnable(self._tap, True)
            ok.append(True)
            ready.set()
            cf.CFRunLoopRun()
            cg.CGEventTapEnable(self._tap, False)
            cf.CFRelease(src)
            cf.CFRelease(self._tap)
            self._tap = None
        except Exception:
            log.debug("tap tastiera macOS", exc_info=True)
        finally:
            ready.set()

    def _fire(self):
        try:
            self.callback()
        except Exception:
            pass

    def _loop(self):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        mods, vk = parse_hotkey(self.combo)
        self.tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, mods, vk):
            return  # scorciatoia gia' usata da un altro programma
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:  # WM_HOTKEY
                    try:
                        self.callback()
                    except Exception:
                        pass
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self):
        if self._rl and sys.platform == "darwin":
            try:
                _, cf = _mac_libs()
                cf.CFRunLoopStop(self._rl)  # il thread disattiva e rilascia il tap uscendo da CFRunLoopRun
            except Exception:
                pass
            self._rl = None
            return
        if self.tid and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)  # WM_QUIT


# ---------------------------------------------------------------- cartelle delle schermate degli emulatori
def _home(*parts) -> Path:
    return Path.home().joinpath(*parts)


def _env(var, *parts) -> Path | None:
    v = os.environ.get(var)
    return Path(v).joinpath(*parts) if v else None


def emulator_dirs(emulator: str, exe: str | None) -> list[Path]:
    """Cartelle in cui l'emulatore salva le schermate (versione portatile e installata)."""
    base = Path(exe).parent if exe else None
    docs = _home("Documents")
    c: list[Path | None] = []
    e = (emulator or "").lower()
    if e == "retroarch":
        c += [base / "screenshots" if base else None, _home("Library", "Application Support", "RetroArch", "screenshots")]
        cfgf = base / "retroarch.cfg" if base else None
        if cfgf and cfgf.exists():
            m = re.search(r'^screenshot_directory\s*=\s*"([^"]*)"', cfgf.read_text(encoding="utf-8", errors="ignore"), re.M)
            if m and m.group(1) and m.group(1) != "default":
                d = m.group(1).replace(":\\", str(base) + "\\", 1) if m.group(1).startswith(":") else m.group(1)
                c.append(Path(d))
    elif e == "dolphin":
        c += [base / "User" / "ScreenShots" if base else None, docs / "Dolphin Emulator" / "ScreenShots",
              _env("APPDATA", "Dolphin Emulator", "ScreenShots"), _home(".local", "share", "dolphin-emu", "ScreenShots"),
              _home("Library", "Application Support", "Dolphin", "ScreenShots")]
    elif e == "pcsx2":
        c += [base / "snaps" if base else None, docs / "PCSX2" / "snaps", _home(".config", "PCSX2", "snaps"),
              _home("Library", "Application Support", "PCSX2", "snaps")]
    elif e == "duckstation":
        c += [base / "screenshots" if base else None, docs / "DuckStation" / "screenshots",
              _home(".local", "share", "duckstation", "screenshots"),
              _home("Library", "Application Support", "DuckStation", "screenshots")]
    elif e == "ppsspp":
        c += [base / "memstick" / "PSP" / "SCREENSHOT" if base else None, docs / "PPSSPP" / "PSP" / "SCREENSHOT",
              _home("Library", "Application Support", "PPSSPP", "PSP", "SCREENSHOT")]
    elif e == "ryujinx":
        c += [_home("Pictures", "Ryujinx"), base / "portable" / "screenshots" if base else None]
    elif e in ("eden", "yuzu", "suyu", "citron"):
        # famiglia yuzu: <dati>/screenshots, cartella "user" accanto all'exe se portatile; percorso scelto in qt-config.ini
        roots = [base / "user" if base else None, _env("APPDATA", e), _home(".local", "share", e)]
        c += [r / "screenshots" if r else None for r in roots]
        for r in roots:
            ini = r / "config" / "qt-config.ini" if r else None
            if ini and ini.is_file():
                m = re.search(r"^Screenshots\\screenshot_path=(.+)$", ini.read_text(encoding="utf-8", errors="ignore"), re.M)
                if m and m.group(1).strip():
                    c.append(Path(m.group(1).strip()))
    elif e in ("azahar", "lime3ds", "citra"):
        name = {"azahar": "Azahar", "lime3ds": "Lime3DS", "citra": "Citra"}[e]
        c += [base / "user" / "screenshots" if base else None, _env("APPDATA", name, "screenshots")]
    elif e in ("cemu", "rpcs3", "xenia", "vita3k", "shadps4", "flycast", "xemu", "melonds"):
        c += [base / "screenshots" if base else None, base / "ScreenShots" if base else None]
    if base:  # generiche, per gli emulatori non previsti
        c += [base / "screenshots", base / "Screenshots", base / "snaps"]
    c += [_home("Videos", "Captures")]  # Xbox Game Bar (Win+Alt+Stamp)
    seen, out = set(), []
    for d in c:
        if d and d.is_dir() and os.path.normcase(str(d)) not in seen:
            seen.add(os.path.normcase(str(d)))
            out.append(d)
    return out


def video_dirs() -> list[tuple[Path, str]]:
    """Clip: Xbox Game Bar, NVIDIA (ShadowPlay), AMD (ReLive) e le cartelle <gioco> sotto Videos."""
    v = _home("Videos")
    out = [(v / "Captures", "Xbox Game Bar"), (v / "NVIDIA", "NVIDIA"), (v / "Radeon ReLive", "AMD")]
    try:
        out += [(d, "Videos") for d in v.iterdir() if d.is_dir()]
    except OSError:
        pass
    seen, res = set(), []
    for d, label in out:
        if d.is_dir() and os.path.normcase(str(d)) not in seen:
            seen.add(os.path.normcase(str(d)))
            res.append((d, label))
    return res


def import_session(shots: Shots, key: str, emulator: str, exe: str | None, start: float, end: float) -> int:
    """Copia le schermate create durante la sessione nelle cartelle dell'emulatore; i clip video vengono solo registrati."""
    n = 0
    for d in emulator_dirs(emulator, exe):
        try:
            files = [f for f in d.rglob("*") if f.suffix.lower() in IMG_EXT and f.is_file()]
        except OSError:
            continue
        for f in files:
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if start - 5 <= mt <= end + 90:
                src = "Xbox Game Bar" if "Captures" in f.parts else emulator
                if shots.add_file(key, f, src):
                    n += 1
    for d, label in video_dirs():
        try:
            files = [f for f in d.rglob("*") if f.suffix.lower() in VIDEO_EXT and f.is_file()]
        except OSError:
            continue
        for f in files:
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if start - 5 <= mt <= end + 90 and shots.add_clip(key, f, label):
                n += 1
    return n


def steam_dirs(steam_root: Path) -> dict[str, list[Path]]:
    """{appid: [cartelle schermate]} dalle cartelle utente di Steam."""
    out: dict[str, list[Path]] = {}
    ud = steam_root / "userdata"
    if not ud.is_dir():
        return out
    for user in ud.iterdir():
        remote = user / "760" / "remote"
        if not remote.is_dir():
            continue
        for app in remote.iterdir():
            d = app / "screenshots"
            if d.is_dir():
                out.setdefault(app.name, []).append(d)
    return out


def import_steam(shots: Shots, steam_root: Path, keys_by_appid: dict[str, str]) -> int:
    n = 0
    for appid, dirs in steam_dirs(steam_root).items():
        key = keys_by_appid.get(appid)
        if not key:
            continue
        for d in dirs:
            for f in d.iterdir():  # niente sottocartella "thumbnails"
                if f.is_file() and f.suffix.lower() in IMG_EXT:
                    if shots.add_file(key, f, "Steam"):
                        n += 1
    return n

