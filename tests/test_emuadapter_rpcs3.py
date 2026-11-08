"""Adattatore RPCS3: percorso, render YAML, giro completo apply/restore (senza emulatore reale)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import rpcs3  # noqa: E402

SERIAL = "BLES00000"
ENV = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "RPCS3_CONFIG_DIR")


class Home:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="_rpcs3-")
        self.dir = Path(self.tmp.name).resolve()
        self.old = {k: os.environ.get(k) for k in ENV}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.dir / "home")
        os.environ["XDG_CONFIG_HOME"] = str(self.dir / "xdg")
        os.environ.pop("RPCS3_CONFIG_DIR", None)
        self.exe = self.dir / "app" / "rpcs3.exe"
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()


def test_target():
    with Home() as h:
        t = rpcs3.target(str(h.exe), SERIAL)
        if sys.platform == "win32":
            assert t == h.exe.parent / "config" / "custom_configs" / f"config_{SERIAL}.yml"
        elif sys.platform == "darwin":
            assert t == h.dir / "home" / "Library" / "Application Support" / "rpcs3" / "custom_configs" / f"config_{SERIAL}.yml"
        else:
            assert t == h.dir / "xdg" / "rpcs3" / "custom_configs" / f"config_{SERIAL}.yml"
        assert rpcs3.target(str(h.exe), None) is None
        assert rpcs3.target(str(h.exe), "../x") is None


def test_render():
    old = "# nota\nCore:\n  PPU Decoder: Recompiler (LLVM)\nVideo:\n  Renderer: Vulkan\n  Resolution Scale: 100\n"
    out = rpcs3.render(old, {"Video": {"Resolution Scale": "200", "Anisotropic Filter Override": "16"}})
    import yaml
    d = yaml.safe_load(out)
    assert d["Core"] == {"PPU Decoder": "Recompiler (LLVM)"}
    assert d["Video"] == {"Renderer": "Vulkan", "Resolution Scale": 200, "Anisotropic Filter Override": 16}
    assert rpcs3.render(out, {"Video": {"Resolution Scale": "200", "Anisotropic Filter Override": "16"}}) == out
    assert yaml.safe_load(rpcs3.render("", {"Video": {"Resolution Scale": "75"}})) == {"Video": {"Resolution Scale": 75}}
    for bad in ("- a\n- b\n", "Video: 3\n", "a: [unclosed\n"):
        try:
            rpcs3.render(bad, {"Video": {"Resolution Scale": "1"}})
        except ValueError:
            continue
        raise AssertionError(bad)


def test_roundtrip():
    with Home() as h:
        path = rpcs3.target(str(h.exe), SERIAL)
        for original in (None, b"Video:\r\n  Renderer: Vulkan\r\n"):
            if original is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
            b = emucfg.apply_for_game("rpcs3", str(h.exe), SERIAL, "quality", cfg_running=False)
            assert b and b.changed and path.exists()
            assert emucfg.apply_for_game("rpcs3", str(h.exe), SERIAL, "quality", cfg_running=False) is None
            assert emucfg.restore_for_game("rpcs3", str(h.exe), SERIAL)
            if original is None:
                assert not path.exists()
            else:
                assert path.read_bytes() == original


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
