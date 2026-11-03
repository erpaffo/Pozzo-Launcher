"""Chiave del gioco: serial PS1/PS2, game ID GC/Wii, title id Switch/Wii U; None se non ricavabile."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.library.gamekey import game_key  # noqa: E402


def _iso(cnf: bytes, name: bytes = b"SYSTEM.CNF;1") -> bytes:
    img = bytearray(2048 * 24)
    pvd = 16 * 2048
    img[pvd + 1:pvd + 6] = b"CD001"
    img[pvd + 158:pvd + 162] = (20).to_bytes(4, "little")
    img[pvd + 166:pvd + 170] = (2048).to_bytes(4, "little")
    rec = bytearray(33 + len(name) + (len(name) + 1) % 2)
    rec[0] = len(rec)
    rec[2:6] = (22).to_bytes(4, "little")
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    img[20 * 2048:20 * 2048 + len(rec)] = rec
    img[22 * 2048:22 * 2048 + len(cnf)] = cnf
    return bytes(img)


def _raw(iso: bytes, mode: int) -> bytes:
    out = b""
    for i in range(0, len(iso), 2048):
        hdr = b"\x00" + b"\xff" * 10 + b"\x00" + b"\x00\x00\x00" + bytes([mode])
        hdr += b"\x00" * 8 if mode == 2 else b""
        out += hdr + iso[i:i + 2048] + b"\x00" * (2352 - len(hdr) - 2048)
    return out


CNF = b"BOOT2 = cdrom0:\\SLUS_209.46;1\r\nVER = 1.00\r\n"


def test_ps2_iso_bin_cue(tmp_path: Path):
    (tmp_path / "a.iso").write_bytes(_iso(CNF))
    assert game_key("ps2", tmp_path / "a.iso") == "SLUS-20946"
    for mode in (1, 2):
        (tmp_path / f"m{mode}.bin").write_bytes(_raw(_iso(b"BOOT = cdrom:\\SCES_004.04;1"), mode))
        assert game_key("psx", tmp_path / f"m{mode}.bin") == "SCES-00404"
    (tmp_path / "g.cue").write_text('FILE "m2.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    assert game_key("psx", tmp_path / "g.cue") == "SCES-00404"


def test_gc_wii(tmp_path: Path):
    (tmp_path / "a.iso").write_bytes(b"GALE01" + b"\0" * 100)
    assert game_key("gc", tmp_path / "a.iso") == "GALE01"
    (tmp_path / "a.wbfs").write_bytes(b"WBFS" + b"\0" * 0x1FC + b"RSPE01" + b"\0" * 50)
    assert game_key("wii", tmp_path / "a.wbfs") == "RSPE01"
    (tmp_path / "a.rvz").write_bytes(b"RVZ\x01" + b"\0" * 0x54 + b"GM4E01" + b"\0" * 50)
    assert game_key("gc", tmp_path / "a.rvz") == "GM4E01"
    (tmp_path / "bad.iso").write_bytes(b"\0\0\0\0\0\0")
    assert game_key("gc", tmp_path / "bad.iso") is None


def test_switch_wiiu(tmp_path: Path):
    assert game_key("switch", tmp_path / "Zelda [0100abcdef012000][v0].nsp") == "0100ABCDEF012000"
    assert game_key("switch", tmp_path / "Zelda.nsp") is None
    d = tmp_path / "game"
    (d / "meta").mkdir(parents=True)
    (d / "meta" / "meta.xml").write_text(
        '<menu><title_id type="hexBinary" length="8">0005000010101d00</title_id></menu>', encoding="utf-8")
    assert game_key("wiiu", d) == "0005000010101D00"


def test_none_cases(tmp_path: Path):
    assert game_key("ps2", tmp_path / "missing.iso") is None
    (tmp_path / "t.iso").write_bytes(_iso(CNF)[:20000])
    assert game_key("ps2", tmp_path / "t.iso") is None
    (tmp_path / "a.chd").write_bytes(b"MComprHD")
    assert game_key("psx", tmp_path / "a.chd") is None
    assert game_key("snes", tmp_path / "a.sfc") is None
    (tmp_path / "e.cue").write_text("garbage")
    assert game_key("psx", tmp_path / "e.cue") is None


def test_read_only(tmp_path: Path):
    p = tmp_path / "a.iso"
    p.write_bytes(_iso(CNF))
    m = p.stat().st_mtime_ns
    game_key("ps2", p)
    assert p.read_bytes() == _iso(CNF) and p.stat().st_mtime_ns == m


if __name__ == "__main__":
    import tempfile
    for fn in (test_ps2_iso_bin_cue, test_gc_wii, test_switch_wiiu, test_none_cases, test_read_only):
        with tempfile.TemporaryDirectory() as t:
            fn(Path(t))
    print("ok")
