"""Tasti e tasti multimedia del PC premuti dal telefono (volume, play/pausa, Esc, Invio, Alt+Tab).

Windows (SendInput), macOS (CGEvent) e Linux (xdotool). Si manda un tocco (premi e rilascia), non un tasto tenuto: basta per i menu dei giochi
e per il telecomando. L'elenco e' chiuso di proposito: il telefono non puo' digitare testo arbitrario.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from ctypes import wintypes

# nome usato dal telefono -> tasti da premere in ordine (Virtual-Key code); il rilascio va al contrario
KEYS: dict[str, tuple[int, ...]] = {
    "vol_up": (0xAF,), "vol_down": (0xAE,), "mute": (0xAD,),
    "play": (0xB3,), "next": (0xB0,), "prev": (0xB1,), "stop_media": (0xB2,),
    "esc": (0x1B,), "enter": (0x0D,), "space": (0x20,), "backspace": (0x08,), "tab": (0x09,),
    "shift_tab": (0x10, 0x09), "alt_tab": (0x12, 0x09), "alt_f4": (0x12, 0x73),
    "win": (0x5B,), "f11": (0x7A,), "hdr": (0x5B, 0x12, 0x42),  # hdr = Win+Alt+B (automazioni di Pozzo)
    "left": (0x25,), "right": (0x27,), "up": (0x26,), "down": (0x28,),
}
# tasti "estesi" (E0): multimedia, frecce, Windows. Senza il flag alcuni programmi li ignorano
_EXTENDED = {0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0x5B, 0x25, 0x26, 0x27, 0x28}
# shortcut: un tocco = premi e rilascia, niente tasti tenuti; se un gioco chiede di tenere premuto, aggiungere down/up

_KEYUP, _EXTENDEDKEY = 0x0002, 0x0001


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):  # solo per la dimensione: l'unione di INPUT deve essere quella piu' grande
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


# macOS: nome -> CGKeyCode (kVK_*); i modificatori (55 Cmd, 56 Shift, 58 Option, 59 Control) diventano flag
# win -> Cmd, alt_tab -> Cmd+Tab, alt_f4 -> Cmd+Q. Mancano di proposito hdr e stop_media (nessun equivalente)
_MAC_KEYS: dict[str, tuple[int, ...]] = {
    "esc": (53,), "enter": (36,), "space": (49,), "backspace": (51,), "tab": (48,),
    "shift_tab": (56, 48), "alt_tab": (55, 48), "alt_f4": (55, 12), "win": (55,), "f11": (103,),
    "left": (123,), "right": (124,), "down": (125,), "up": (126,),
}
_MAC_FLAGS = {55: 0x100000, 56: 0x20000, 58: 0x80000, 59: 0x40000}
# media: su macOS passano da mediakeys (AppleScript), non da CGEvent
_MAC_MEDIA = {"vol_up": "volume_up", "vol_down": "volume_down", "mute": "mute",
              "play": "play_pause", "next": "next", "prev": "previous"}
# Linux: nomi keysym di xdotool, combinazioni con "+"
_LINUX_KEYS = {"vol_up": "XF86AudioRaiseVolume", "vol_down": "XF86AudioLowerVolume", "mute": "XF86AudioMute",
               "play": "XF86AudioPlay", "next": "XF86AudioNext", "prev": "XF86AudioPrev", "stop_media": "XF86AudioStop",
               "esc": "Escape", "enter": "Return", "space": "space", "backspace": "BackSpace", "tab": "Tab",
               "shift_tab": "shift+Tab", "alt_tab": "alt+Tab", "alt_f4": "alt+F4", "win": "Super_L", "f11": "F11",
               "hdr": "super+alt+b", "left": "Left", "right": "Right", "up": "Up", "down": "Down"}


def _press_mac(name: str) -> bool:
    from .. import macos
    if name in _MAC_MEDIA:
        from .. import mediakeys
        return bool(mediakeys.send(_MAC_MEDIA[name], platform="darwin").get("ok"))
    combo = _MAC_KEYS.get(name)
    if not combo or not macos.ax_trusted():  # senza Accessibilita' macOS scarta gli eventi in silenzio
        return False
    flags, ok = 0, True
    downs = []
    for code in combo:
        flags |= _MAC_FLAGS.get(code, 0)
        downs.append((code, flags))
        ok = macos.post_key(code, True, flags) and ok
    for code, f in reversed(downs):
        ok = macos.post_key(code, False, f) and ok
    return ok


def _press_linux(name: str) -> bool:
    exe, key = shutil.which("xdotool"), _LINUX_KEYS.get(name)
    if not exe or not key:
        return False
    try:
        return subprocess.run([exe, "key", "--clearmodifiers", key], capture_output=True, timeout=3, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def press(name: str) -> bool:
    """Preme e rilascia il tasto (o la combinazione) `name`; ValueError se non e' nell'elenco.

    True se mandato; False se il sistema lo scarta (permesso Accessibilita', xdotool o tasto assente)."""
    combo = KEYS.get(str(name or ""))
    if not combo:
        raise ValueError("Tasto non previsto")
    if sys.platform == "darwin":
        return _press_mac(name)
    if sys.platform.startswith("linux"):
        return _press_linux(name)
    if sys.platform != "win32":
        return False
    events = [(vk, _EXTENDEDKEY if vk in _EXTENDED else 0) for vk in combo]
    events += [(vk, flags | _KEYUP) for vk, flags in reversed(events)]
    arr = (INPUT * len(events))(*[INPUT(type=1, ki=KEYBDINPUT(vk, 0, flags, 0, 0)) for vk, flags in events])
    ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    return True
