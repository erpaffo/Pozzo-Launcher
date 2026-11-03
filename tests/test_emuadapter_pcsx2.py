import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402
from pozzo.emuadapters import pcsx2  # noqa: E402
from pozzo.remote import emusetup  # noqa: E402

SERIAL = "SLUS-20946"
ORIG = "; commento\n[EmuCore/GS]\nupscale_multiplier = 2\nVsync = 1\n\n[Other]\nx = 1\n"


class Home:
    """Cartelle utente finte dentro tmp (HOME, USERPROFILE, XDG, Documents)."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="_pcsx2-", dir=Path(__file__).parent)
        self.dir = Path(self.tmp.name).resolve()
        self.env = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.dir / "home")
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


def _make(root: Path, crc="1A2B3C4D", text=ORIG) -> Path:
    f = root / "gamesettings" / f"{SERIAL}_{crc}.ini"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return f


def test_target_portable_and_installed():
    with Home() as h:
        app = h.dir / "app"
        app.mkdir()
        exe = str(app / "pcsx2-qt.exe")
        (app / "portable.txt").write_text("", encoding="utf-8")
        assert pcsx2.target(exe, SERIAL) is None  # nessun file esistente: non supportato
        f = _make(app)
        assert pcsx2.target(exe, SERIAL).resolve() == f.resolve()
        assert pcsx2.target(exe, "SLUS-99999") is None
        assert pcsx2.target(exe, "../x") is None
        _make(app, crc="DEADBEEF")
        assert pcsx2.target(exe, SERIAL) is None  # due CRC: ambiguo
        # installato (senza portable.txt si usa la cartella utente)
        other = str(h.dir / "altro" / "pcsx2-qt.exe")
        root = pcsx2._data_root(other)
        assert root.name == "PCSX2" and (h.dir / "home") in root.parents
        g = _make(root)
        assert pcsx2.target(other, SERIAL).resolve() == g.resolve()


def test_render_preserves_and_idempotent():
    values = {"EmuCore/GS": {"upscale_multiplier": "3", "filter": "2"}, "Nuova": {"a": "b"}}
    out = pcsx2.render(ORIG, values)
    assert "; commento" in out and "Vsync = 1" in out and "[Other]\nx = 1" in out
    assert "upscale_multiplier = 3" in out and "filter = 2" in out and "[Nuova]" in out
    assert pcsx2.render(out, values) == out


def test_full_roundtrip():
    with Home() as h:
        app = h.dir / "app"
        app.mkdir()
        (app / "portable.txt").write_text("", encoding="utf-8")
        exe = str(app / "pcsx2-qt.exe")
        f = _make(app)
        before = f.read_bytes()
        b = emucfg.apply_for_game("pcsx2", exe, SERIAL, "quality", cfg_running=False)
        assert b.changed and f.read_bytes() != before
        assert "upscale_multiplier = 3" in f.read_text(encoding="utf-8")
        assert emucfg.restore_for_game("pcsx2", exe, SERIAL)
        assert f.read_bytes() == before


def test_catalog_valid():
    assert set(emucfg.catalog("pcsx2")["presets"]) == {"quality", "performance", "faithful"}


if __name__ == "__main__":
    test_target_portable_and_installed()
    test_render_preserves_and_idempotent()
    test_full_roundtrip()
    test_catalog_valid()
    print("TUTTI I TEST OK")
