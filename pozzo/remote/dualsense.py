"""DualSense / DualShock 4: batteria e barra luminosa via HID (ctypes, solo Windows, nessuna dipendenza).

Ogni operazione apre il dispositivo, scrive/legge e lo richiude: non si tiene mai occupato, i giochi lo usano
liberamente. Offset da hid-playstation.c (Linux). Le funzioni pure (parse_battery, build_led) sono testate
senza hardware; la parte HID no.
"""

from __future__ import annotations

import sys
import zlib

SONY = 0x054C
DS_PIDS = {0x0CE6, 0x0DF2}  # DualSense, DualSense Edge
DS4_PIDS = {0x05C4, 0x09CC}  # DualShock 4 v1, v2


def _bt_crc(buf: bytearray) -> bytes:
    return zlib.crc32(b"\xA2" + bytes(buf[:74])).to_bytes(4, "little")  # seed 0xA2 per i report di uscita Bluetooth


def parse_battery(ds4: bool, bt: bool, rep: bytes) -> dict | None:
    """{'percent', 'charging', 'full'} da un report di ingresso (id compreso), None se non e' quello atteso."""
    if not rep:
        return None
    if ds4:
        i = 32 if bt else 30
        if rep[0] != (0x11 if bt else 0x01) or len(rep) <= i:
            return None
        lvl, cable = rep[i] & 0x0F, bool(rep[i] & 0x10)
        pct = min(lvl * 100 // 11, 100) if cable else min(lvl * 10 + 5, 100)
        return {"percent": pct, "charging": cable and lvl < 11, "full": cable and lvl >= 11}
    i = 54 if bt else 53
    if rep[0] != (0x31 if bt else 0x01) or len(rep) <= i:
        return None
    lvl, st = rep[i] & 0x0F, rep[i] >> 4
    if st > 2:  # 0xA/0xB/0xF: errore di lettura
        return None
    return {"percent": 100 if st == 2 else min(lvl * 10 + 5, 100), "charging": st == 1, "full": st == 2}


def hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(color)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def build_led(ds4: bool, bt: bool, rgb: tuple[int, int, int], seq: int = 0) -> bytes:
    """Report di uscita che cambia solo il colore della barra (flag dei motori a 0: nessuna vibrazione)."""
    r, g, b = rgb
    if ds4:
        if bt:
            buf = bytearray(78)
            buf[0], buf[1], buf[3] = 0x11, 0xC4, 0x02  # 0xC4 = HID+CRC32+poll; 0x02 = barra valida
            buf[8:11] = bytes((r, g, b))
            buf[74:78] = _bt_crc(buf)
            return bytes(buf)
        buf = bytearray(32)
        buf[0], buf[1] = 0x05, 0x02
        buf[6:9] = bytes((r, g, b))
        return bytes(buf)
    if bt:
        buf = bytearray(78)
        buf[0], buf[1], buf[2] = 0x31, (seq & 0xF) << 4, 0x10
        buf[4] = 0x04  # valid_flag1: controllo barra luminosa
        buf[47:50] = bytes((r, g, b))
        buf[74:78] = _bt_crc(buf)
        return bytes(buf)
    buf = bytearray(63)
    buf[0], buf[2] = 0x02, 0x04
    buf[45:48] = bytes((r, g, b))
    return bytes(buf)


# ---------------------------------------------------------------- HID (Windows)
def _k32():
    import ctypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    return k


def _open(k32, path: str, access: int):
    import ctypes
    h = k32.CreateFileW(path, access, 3, None, 3, 0, None)  # condiviso in lettura e scrittura: mai esclusivo
    return None if h in (None, ctypes.c_void_p(-1).value) else h


def _hid_paths():
    """[(path, ds4, bt)] dei pad Sony collegati (interfaccia Gamepad)."""
    import ctypes
    from ctypes import wintypes as W
    hid, setup, k32 = ctypes.WinDLL("hid"), ctypes.WinDLL("setupapi"), _k32()

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

    class IFACE(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("g", GUID), ("flags", W.DWORD), ("res", ctypes.c_void_p)]

    class ATTR(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("vid", ctypes.c_ushort), ("pid", ctypes.c_ushort), ("ver", ctypes.c_ushort)]

    class CAPS(ctypes.Structure):
        _fields_ = [("usage", ctypes.c_ushort), ("page", ctypes.c_ushort), ("inlen", ctypes.c_ushort), ("outlen", ctypes.c_ushort),
                    ("rest", ctypes.c_ushort * 20)]

    setup.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setup.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, W.LPCWSTR, W.HWND, W.DWORD]
    setup.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    for f in (hid.HidD_GetAttributes, hid.HidD_GetPreparsedData, hid.HidP_GetCaps):
        f.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(guid))
    info = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # PRESENT | DEVICEINTERFACE
    out, i = [], 0
    while True:
        itf = IFACE()
        itf.cb = ctypes.sizeof(IFACE)
        if not setup.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), i, ctypes.byref(itf)):
            break
        i += 1
        n = W.DWORD()
        setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(itf), None, 0, ctypes.byref(n), None)
        buf = ctypes.create_string_buffer(n.value)
        ctypes.c_ulong.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6  # cbSize di DETAIL_DATA_W
        if not setup.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(itf), buf, n, None, None):
            continue
        path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
        h = _open(k32, path, 0)  # accesso 0: basta per interrogare
        if h is None:
            continue
        try:
            at = ATTR()
            at.size = ctypes.sizeof(ATTR)
            if not hid.HidD_GetAttributes(h, ctypes.byref(at)) or at.vid != SONY or at.pid not in DS_PIDS | DS4_PIDS:
                continue
            pp, caps = ctypes.c_void_p(), CAPS()
            if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                hid.HidP_GetCaps(pp, ctypes.byref(caps))
                hid.HidD_FreePreparsedData(pp)
            if caps.usage != 5:  # solo l'interfaccia Gamepad (Generic Desktop, usage 5)
                continue
            out.append((path, at.pid in DS4_PIDS, caps.outlen == 78))  # 78 byte di uscita = Bluetooth
        finally:
            k32.CloseHandle(h)
    setup.SetupDiDestroyDeviceInfoList(info)
    return out


def available() -> bool:
    return sys.platform == "win32"


def read_battery() -> dict:
    """{'present', 'name', 'percent', 'charging', 'full'}; present=False senza pad Sony (o fuori da Windows)."""
    if not available():
        return {"present": False}
    import ctypes
    try:
        pads, k32, hid = _hid_paths(), _k32(), ctypes.WinDLL("hid")
    except OSError:
        return {"present": False}
    hid.HidD_GetInputReport.argtypes = hid.HidD_GetFeature.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    for path, ds4, bt in pads:
        h = _open(k32, path, 0xC0000000)
        if h is None:
            continue
        try:
            if bt:  # in Bluetooth il report completo parte solo dopo aver letto il feature report di calibrazione
                f = (ctypes.c_ubyte * (37 if ds4 else 41))()
                f[0] = 0x02 if ds4 else 0x05
                hid.HidD_GetFeature(h, f, len(f))
            rid, size = (0x11, 547) if (ds4 and bt) else (0x31, 78) if bt else (0x01, 64)
            buf = (ctypes.c_ubyte * size)()
            for _ in range(5 if bt else 1):  # dopo lo switch il primo report puo' essere ancora quello semplice
                buf[0] = rid
                if hid.HidD_GetInputReport(h, buf, size):
                    b = parse_battery(ds4, bt, bytes(buf))
                    if b:
                        return {"present": True, "name": "DualShock 4" if ds4 else "DualSense", **b}
        finally:
            k32.CloseHandle(h)
    return {"present": bool(pads), "name": None}


_seq = [0]


def set_led(color: str) -> bool:
    """Imposta la barra luminosa di tutti i pad Sony collegati. True se almeno una scrittura e' riuscita."""
    if not available():
        return False
    import ctypes
    rgb = hex_rgb(color)
    try:
        pads, k32, hid = _hid_paths(), _k32(), ctypes.WinDLL("hid")
    except OSError:
        return False
    hid.HidD_SetOutputReport.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    ok = False
    for path, ds4, bt in pads:
        h = _open(k32, path, 0xC0000000)
        if h is None:
            continue
        try:
            _seq[0] = (_seq[0] + 1) & 0xF
            data = build_led(ds4, bt, rgb, _seq[0])
            buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
            n = ctypes.c_ulong()
            if k32.WriteFile(h, buf, len(data), ctypes.byref(n), None) or hid.HidD_SetOutputReport(h, buf, len(data)):
                ok = True
        finally:
            k32.CloseHandle(h)
    return ok
