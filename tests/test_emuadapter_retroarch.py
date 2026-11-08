"""Adattatore RetroArch: percorsi, render e giro apply/restore (offline, in cartelle temporanee)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import retroarch as ra  # noqa: E402


def _env(d: Path):
    for k, v in (("HOME", d), ("USERPROFILE", d), ("XDG_CONFIG_HOME", d / "xdg"), ("APPDATA", d / "appdata")):
        os.environ[k] = str(v)


def test_target_portable_and_installed():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="_ra-") as d:
            d = Path(d).resolve()
            _env(d)
            exe = d / "portable" / "retroarch.exe"
            exe.parent.mkdir()
            # nessun retroarch.cfg: non determinabile
            assert ra.target(str(exe), "x", core="snes9x", game_name="Mario") is None
            (exe.parent / "retroarch.cfg").write_text("", encoding="utf-8")
            t = ra.target(str(exe), "x", core="snes9x", game_name="Super Mario (USA)")
            assert t.resolve() == (exe.parent / "config" / "snes9x" / "Super Mario (USA).cfg").resolve()
            if sys.platform != "win32":  # installato: ~/.config/retroarch
                inst = d / "bin" / "retroarch"
                inst.parent.mkdir()
                (d / ".config" / "retroarch").mkdir(parents=True)
                (d / ".config" / "retroarch" / "retroarch.cfg").write_text("", encoding="utf-8")
                t = ra.target(str(inst), "x", core="snes9x", game_name="G")
                assert t.resolve() == (d / ".config" / "retroarch" / "config" / "snes9x" / "G.cfg").resolve()
            for core, name in ((None, "G"), ("snes9x", None), ("..", "G"), ("snes9x", "a/b"), ("snes9x", "..")):
                assert ra.target(str(exe), "x", core=core, game_name=name) is None
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("ok  target portatile e installato")


def test_render_preserves_adds_and_is_idempotent():
    values = {"": {"video_vsync": "true", "video_threaded": "false"}}
    src = '# nota\r\naudio_sync = "false"\r\nvideo_vsync = "false" # c\r\n'
    out = ra.render(src, values)
    assert out == '# nota\r\naudio_sync = "false"\r\nvideo_vsync = "true" # c\r\nvideo_threaded = "false"\r\n'
    assert ra.render(out, values) == out
    assert ra.render("", values) == 'video_vsync = "true"\nvideo_threaded = "false"\n'
    print("ok  render conserva il resto, aggiunge, idempotente")


def test_full_cycle_byte_identical():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="_ra-") as d:
            d = Path(d)
            _env(d)
            exe = d / "ra" / "retroarch.exe"
            exe.parent.mkdir()
            (exe.parent / "retroarch.cfg").write_text("", encoding="utf-8")
            kw = dict(core="snes9x", game_name="Game")
            f = ra.target(str(exe), "g", **kw)
            f.parent.mkdir(parents=True)
            original = b'# mio\r\nvideo_threaded = "false"\r\nfoo = "1"\r\n'
            f.write_bytes(original)
            assert emucfg.apply_for_game("retroarch", str(exe), "g", "performance", cfg_running=False, **kw)
            data = f.read_bytes()
            assert b'video_threaded = "true"' in data and b'foo = "1"' in data
            assert emucfg.restore_for_game("retroarch", str(exe), "g", **kw)
            assert f.read_bytes() == original
            f.unlink()  # file inesistente: creato e poi rimosso
            assert emucfg.apply_for_game("retroarch", str(exe), "g", "faithful", cfg_running=False, **kw)
            assert f.is_file() and emucfg.restore_for_game("retroarch", str(exe), "g", **kw) and not f.exists()
            for level in emucfg.LEVELS:
                assert level in emucfg.presets_for("retroarch")
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("ok  apply + restore identico al byte")


if __name__ == "__main__":
    test_target_portable_and_installed()
    test_render_preserves_adds_and_is_idempotent()
    test_full_cycle_byte_identical()
