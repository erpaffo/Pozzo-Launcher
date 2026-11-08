"""Adattatore Dolphin: GameSettings/<ID>.ini, render e giro apply/restore (offline)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import dolphin as dol  # noqa: E402


def _env(d: Path):
    for k, v in (("HOME", d), ("USERPROFILE", d), ("APPDATA", d / "appdata"),
                 ("XDG_DATA_HOME", d / "xdg"), ("DOLPHIN_EMU_USERPATH", None)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)


def test_target_portable_and_installed():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="_dol-") as d:
            d = Path(d).resolve()
            _env(d)
            exe = d / "dol" / "Dolphin.exe"
            exe.parent.mkdir()
            (exe.parent / "portable.txt").write_text("", encoding="utf-8")
            t = dol.target(str(exe), "gale01")
            assert t.resolve() == (exe.parent / "User" / "GameSettings" / "GALE01.ini").resolve()
            (exe.parent / "portable.txt").unlink()
            if sys.platform == "win32":
                user = d / "appdata" / "Dolphin Emulator"
            elif sys.platform == "darwin":
                user = d / "Library" / "Application Support" / "Dolphin"
            else:
                user = d / "xdg" / "dolphin-emu"
            user.mkdir(parents=True)
            t = dol.target(str(exe), "GALE01")
            assert t.resolve() == (user / "GameSettings" / "GALE01.ini").resolve()
            for bad in (None, "", "../x", "AB", "GALE01.ini"):
                assert dol.target(str(exe), bad) is None
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("ok  target portatile e installato")


def test_render_preserves_adds_and_is_idempotent():
    values = {"Video_Settings": {"InternalResolution": "2"}, "Video_Enhancements": {"MaxAnisotropy": "2"}}
    src = "# mio\n[Core]\nCPUCore = 1\n[Video_Settings]\nInternalResolution = 1\nMSAA = 4\n"
    out = dol.render(src, values)
    assert "# mio" in out and "CPUCore = 1" in out and "MSAA = 4" in out
    assert "InternalResolution = 2" in out and "[Video_Enhancements]\nMaxAnisotropy = 2" in out
    assert dol.render(out, values) == out
    crlf = dol.render(src.replace("\n", "\r\n"), values)
    assert "\n" not in crlf.replace("\r\n", "")
    assert "[Video_Settings]" in dol.render("", values)
    print("ok  render conserva il resto, aggiunge sezioni, idempotente")


def test_full_cycle_byte_identical():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="_dol-") as d:
            d = Path(d)
            _env(d)
            exe = d / "dol" / "Dolphin.exe"
            exe.parent.mkdir()
            (exe.parent / "portable.txt").write_text("", encoding="utf-8")
            f = dol.target(str(exe), "GALE01")
            f.parent.mkdir(parents=True)
            original = b"# patch\r\n[Core]\r\nCPUCore = 1\r\n"
            f.write_bytes(original)
            assert emucfg.apply_for_game("dolphin", str(exe), "GALE01", "quality", cfg_running=False)
            data = f.read_bytes()
            assert b"InternalResolution = 2" in data and b"CPUCore = 1" in data
            assert emucfg.restore_for_game("dolphin", str(exe), "GALE01")
            assert f.read_bytes() == original
            f.unlink()
            assert emucfg.apply_for_game("dolphin", str(exe), "GALE01", "performance", cfg_running=False)
            assert emucfg.restore_for_game("dolphin", str(exe), "GALE01") and not f.exists()
            for level in emucfg.LEVELS:
                assert level in emucfg.presets_for("dolphin")
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("ok  apply + restore identico al byte")


if __name__ == "__main__":
    test_target_portable_and_installed()
    test_render_preserves_adds_and_is_idempotent()
    test_full_cycle_byte_identical()
