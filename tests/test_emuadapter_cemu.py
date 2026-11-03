"""Adattatore Cemu: percorso del profilo, render INI, giro completo apply/restore."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import cemu  # noqa: E402

TID = "00050000101C9500"
ENV = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "APPDATA")


class Home:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="_cemu-", dir=Path(__file__).parent)
        self.dir = Path(self.tmp.name).resolve()
        self.old = {k: os.environ.get(k) for k in ENV}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.dir / "home")
        os.environ["XDG_CONFIG_HOME"] = str(self.dir / "xdg")
        os.environ["APPDATA"] = str(self.dir / "appdata")
        (self.dir / "app").mkdir()
        self.exe = self.dir / "app" / "Cemu.exe"
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()


def test_target():
    with Home() as h:
        name = f"{TID.lower()}.ini"
        user = {"win32": h.dir / "appdata" / "Cemu",
                "darwin": h.dir / "home" / "Library" / "Application Support" / "Cemu"}.get(
                    sys.platform, h.dir / "xdg" / "Cemu")
        assert cemu.target(str(h.exe), TID) == user / "gameProfiles" / name
        (h.exe.parent / "portable").mkdir()
        assert cemu.target(str(h.exe), TID) == h.exe.parent / "portable" / "gameProfiles" / name
        assert cemu.target(str(h.exe), "nope") is None and cemu.target(str(h.exe), None) is None


def test_render():
    old = "# Gioco\n[General]\nloadSharedLibraries = true\n\n[Graphics]\naccurateShaderMul = true\n"
    out = cemu.render(old, {"Graphics": {"accurateShaderMul": "false"}})
    assert out == old.replace("accurateShaderMul = true", "accurateShaderMul = false")
    assert cemu.render(out, {"Graphics": {"accurateShaderMul": "false"}}) == out
    assert cemu.render("", {"Graphics": {"accurateShaderMul": "true"}}) == "[Graphics]\naccurateShaderMul = true\n"
    try:
        cemu.render("<xml>\n", {"Graphics": {"a": "1"}})
    except ValueError:
        return
    raise AssertionError("atteso ValueError")


def test_roundtrip():
    with Home() as h:
        path = cemu.target(str(h.exe), TID)
        for original in (None, b"# Gioco\r\n[Graphics]\r\naccurateShaderMul = true\r\n"):
            if original is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            b = emucfg.apply_for_game("cemu", str(h.exe), TID, "performance", cfg_running=False)
            assert b and b.changed and b"false" in path.read_bytes()
            assert emucfg.apply_for_game("cemu", str(h.exe), TID, "performance", cfg_running=False) is None
            assert emucfg.restore_for_game("cemu", str(h.exe), TID)
            if original is None:
                assert not path.exists()
            else:
                assert path.read_bytes() == original


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
