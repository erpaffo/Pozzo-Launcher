"""Chiave del gioco per le configurazioni per-gioco degli emulatori (sola lettura, pochi KB, nessun hash).

Restituisce None, mai eccezioni, se la chiave non si ricava o il formato non è supportato."""

import re
from pathlib import Path

_TID = re.compile(r"[\[(]([0-9A-Fa-f]{16})[\])]")
_BOOT = re.compile(r"^\s*BOOT2?\s*=\s*cdrom0?:\\*([A-Za-z]{4})[_-]?(\d{3})\.?(\d{2})", re.I | re.M)
_SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def game_key(platform_id: str, path: Path) -> str | None:
    try:
        path = Path(path)
        if platform_id in ("psx", "ps2"):
            return _serial(path)
        if platform_id in ("gc", "wii"):
            return _gc_id(path)
        if platform_id in ("switch", "wiiu"):
            return _title_id(platform_id, path)
    except Exception:  # noqa: BLE001 - contratto: mai eccezioni
        return None
    return None


def _serial(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".cue":
        m = re.search(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', path.read_text("utf-8", "replace"), re.I | re.M)
        if not m:
            return None
        path = path.parent / (m.group(1) or m.group(2))
        ext = path.suffix.lower()
    if ext not in (".iso", ".bin", ".img"):
        return None
    with open(path, "rb") as f:
        head = f.read(16)
        ss, off = 2048, 0
        if head[:12] == _SYNC:
            ss, off = 2352, (16 if head[15] == 1 else 24)

        def sector(n: int, count: int = 1) -> bytes:
            out = b""
            for i in range(count):
                f.seek((n + i) * ss + off)
                out += f.read(2048)
            return out

        pvd = sector(16)
        if pvd[1:6] != b"CD001":
            return None
        lba = int.from_bytes(pvd[158:162], "little")
        size = min(int.from_bytes(pvd[166:170], "little"), 64 * 2048)
        d = sector(lba, -(-size // 2048))[:size]
        pos = 0
        while pos < len(d):
            n = d[pos]
            if n == 0:  # i record non attraversano i settori: salta al successivo
                pos = (pos // 2048 + 1) * 2048
                continue
            name = d[pos + 33:pos + 33 + d[pos + 32]].split(b";")[0].upper()
            if name == b"SYSTEM.CNF":
                flba = int.from_bytes(d[pos + 2:pos + 6], "little")
                m = _BOOT.search(sector(flba).decode("ascii", "replace"))
                return f"{m.group(1).upper()}-{m.group(2)}{m.group(3)}" if m else None
            pos += n
    return None


def _gc_id(path: Path) -> str | None:
    ext = path.suffix.lower()
    # shortcut: layout WBFS (0x200) e RVZ/WIA (0x58 = 0x48 file head + 16 byte iniziali di disc) da specifiche, non verificati su file reali
    off = {".iso": 0, ".gcm": 0, ".wbfs": 0x200, ".rvz": 0x58, ".wia": 0x58}.get(ext)
    if off is None:
        return None
    with open(path, "rb") as f:
        magic = f.read(4)
        if ext in (".rvz", ".wia") and magic[:3] not in (b"RVZ", b"WIA"):
            return None
        if ext == ".wbfs" and magic != b"WBFS":
            return None
        f.seek(off)
        gid = f.read(6)
    s = gid.decode("ascii", "replace")
    return s if len(gid) == 6 and s.isascii() and s.isalnum() else None


def _title_id(platform_id: str, path: Path) -> str | None:
    if platform_id == "wiiu":
        meta = (path if path.is_dir() else path.parent) / "meta" / "meta.xml"
        if not meta.is_file() and path.is_file():
            meta = path.parent.parent / "meta" / "meta.xml"
        if meta.is_file():
            m = re.search(r"<title_id[^>]*>\s*([0-9A-Fa-f]{16})\s*<", meta.read_text("utf-8", "replace")[:65536])
            if m:
                return m.group(1).upper()
    m = _TID.search(path.name)
    return m.group(1).upper() if m else None
