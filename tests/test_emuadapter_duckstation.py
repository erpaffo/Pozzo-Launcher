import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import duckstation  # noqa: E402
from pozzo.remote import emusetup  # noqa: E402

SERIAL = "SLUS-00594"
ORIG = "# commento\n[GPU]\nResolutionScale = 2\nPGXPEnable = true\n\n[Display]\nAspectRatio = 4:3\n"


class Home:
    """Cartelle utente finte dentro tmp (HOME, USERPROFILE, XDG, LOCALAPPDATA, Documents)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="_duck-", dir=Path(__file__).parent)
        self.dir = Path(self.tmp.name).resolve()
        keys = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "LOCALAPPDATA")
        self.env = {k: os.environ.get(k) for k in keys}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.dir / "home")
        os.environ["LOCALAPPDATA"] = str(self.dir / "home" / "Local")
        os.environ.pop("XDG_CONFIG_HOME", None)
        self.docs = emusetup.documents_dir
        emusetup.documents_dir = lambda: self.dir / "home" / "Documents"
        return self

    def __exit__(self, *exc):
        emusetup.documents_dir = self.docs
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()


def test_target_portable_and_installed():
    with Home() as h:
        app = h.dir / "app"
        app.mkdir()
        exe = str(app / "duckstation-qt.exe")
        installed = duckstation.target(exe, SERIAL)
        assert installed.name == f"{SERIAL}.ini" and installed.parent.name == "gamesettings"
        assert (h.dir / "home") in installed.parents
        (app / "portable.txt").write_text("", encoding="utf-8")
        assert duckstation.target(exe, SERIAL).resolve() == (app / "gamesettings" / f"{SERIAL}.ini").resolve()
        assert duckstation.target(exe, "../x") is None and duckstation.target(exe, "") is None


def test_render_preserves_and_idempotent():
    values = {"GPU": {"ResolutionScale": "3", "TextureFilter": "Bilinear"}, "Nuova": {"a": "b"}}
    out = duckstation.render(ORIG, values)
    assert "# commento" in out and "PGXPEnable = true" in out and "AspectRatio = 4:3" in out
    assert "ResolutionScale = 3" in out and "TextureFilter = Bilinear" in out and "[Nuova]" in out
    assert duckstation.render(out, values) == out


def test_full_roundtrip():
    with Home() as h:
        app = h.dir / "app"
        app.mkdir()
        (app / "portable.txt").write_text("", encoding="utf-8")
        exe = str(app / "duckstation-qt.exe")
        f = duckstation.target(exe, SERIAL)
        f.parent.mkdir(parents=True)
        f.write_text(ORIG, encoding="utf-8")
        before = f.read_bytes()
        assert emucfg.apply_for_game("duckstation", exe, SERIAL, "quality", cfg_running=False).changed
        assert "ResolutionScale = 3" in f.read_text(encoding="utf-8")
        assert emucfg.restore_for_game("duckstation", exe, SERIAL)
        assert f.read_bytes() == before
        # file inesistente: creato e poi eliminato
        f.unlink()
        emucfg.apply_for_game("duckstation", exe, SERIAL, "performance", cfg_running=False)
        assert f.exists() and emucfg.restore_for_game("duckstation", exe, SERIAL) and not f.exists()


def test_catalog_valid():
    assert set(emucfg.catalog("duckstation")["presets"]) == {"quality", "performance", "faithful"}


if __name__ == "__main__":
    test_target_portable_and_installed()
    test_render_preserves_and_idempotent()
    test_full_roundtrip()
    test_catalog_valid()
    print("TUTTI I TEST OK")
