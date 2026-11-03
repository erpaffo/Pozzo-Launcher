"""Override emulatori offline: catalogo, precedenza, backup e ripristino (con adattatore finto)."""

import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg, emuadapters  # noqa: E402

CATALOG = {
    "schema_version": 1,
    "emulator": "fake",
    "presets": {
        "quality": {"name": "Qualità", "values": {"": {"vsync": "true", "res": "4"}},
                    "sources": ["https://example.org/q"]},
        "performance": {"name": "Prestazioni", "values": {"": {"vsync": "false", "res": "1"}},
                        "sources": ["https://example.org/p"]},
    },
    "games": {
        "G1": {"values": {"": {"res": "2"}}, "reason": "Troppo pesante a 4x",
               "sources": ["https://example.org/g1"]},
    },
}


class Env:
    """Cartella temporanea + adattatore finto registrato al posto di emuadapters.get."""

    def __init__(self, data=None):
        self.data = data or CATALOG

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent)
        self.dir = Path(self.tmp.name)
        (self.dir / "cat").mkdir()
        (self.dir / "cat" / "fake.json").write_text(json.dumps(self.data), encoding="utf-8")
        self.file = self.dir / "games" / "G1.cfg"
        self.adapter = types.SimpleNamespace(
            NAME="fake",
            target=lambda exe, gid, core=None, game_name=None: self.file,
            render=lambda existing, values: emucfg._patch(existing, values[""]),
            running_names=lambda: ("fake.exe",),
        )
        self.old = (emuadapters.get, emucfg.PRESETS_DIR)
        emuadapters.get = lambda name: self.adapter if name == "fake" else self.old[0](name)
        emucfg.PRESETS_DIR = self.dir / "cat"
        return self

    def __exit__(self, *exc):
        emuadapters.get, emucfg.PRESETS_DIR = self.old
        self.tmp.cleanup()


def test_shipped_catalogs_are_valid():
    for name in emuadapters.ADAPTER_MODULES:
        if (emucfg.PRESETS_DIR / f"{name}.json").exists():
            emucfg.catalog(name)
    assert emuadapters.get("non-esiste") is None
    assert emuadapters.get("ryujinx") is None or hasattr(emuadapters.get("ryujinx"), "render")
    assert "quality" in emucfg.presets_for("retroarch")
    print("ok  cataloghi inclusi validi; adattatore mancante = None")


def test_precedence_game_over_console_over_leave():
    with Env():
        r = emucfg.resolve
        assert r("fake", "X") is None
        assert r("fake", "X", None, "quality")["preset"] == "quality"
        assert r("fake", "X", "inherit", "quality")["preset"] == "quality"
        assert r("fake", "X", "performance", "quality")["preset"] == "performance"
        assert r("fake", "X", "leave", "quality") is None
        assert r("fake", "X", None, "leave") is None
        assert r("fake", "X", "inherit", "inherit") is None
        merged = r("fake", "G1", None, "quality")
        assert merged["values"][""] == {"vsync": "true", "res": "2"}  # override gioco vince
        assert merged["reason"] and "https://example.org/g1" in merged["sources"]
        assert emucfg.preview("fake", "X")["values"] == {}
        assert emucfg.supported("fake") and not emucfg.supported("non-esiste")
    print("ok  precedenza gioco > console > leave, override per gioco, preview")


def test_apply_restore_byte_identical_and_after_restart():
    with Env() as e:
        e.file.parent.mkdir()
        original = b"# commento\r\nvsync = false\r\nextra = 7\r\n"
        e.file.write_bytes(original)
        b = emucfg.apply_for_game("fake", None, "X", None, "quality", cfg_running=False)
        assert b and b.changed and b.existed and b.backup_path.read_bytes() == original
        changed = e.file.read_bytes()
        assert b"vsync = true\r\n" in changed and b"extra = 7\r\n" in changed and b"res = 4" in changed
        # secondo apply con altro livello: l'originale resta quello vero
        emucfg.apply_for_game("fake", None, "X", "performance", None, cfg_running=False)
        # «riavvio»: nessun token, solo parametri
        assert emucfg.restore_for_game("fake", None, "X")
        assert e.file.read_bytes() == original
        assert not emucfg.restore_for_game("fake", None, "X")
    print("ok  backup + ripristino identico al byte, anche senza token")


def test_new_file_is_deleted_on_restore():
    with Env() as e:
        b = emucfg.apply_for_game("fake", None, "X", "quality", cfg_running=False)
        assert b and not b.existed and e.file.is_file()
        assert emucfg.restore_for_game("fake", None, "X")
        assert not e.file.exists()
        assert [p.name for p in e.file.parent.iterdir()] == []
    print("ok  file non esistente: eliminato al ripristino")


def test_running_unchanged_and_leave():
    with Env() as e:
        try:
            emucfg.apply_for_game("fake", None, "X", "quality", cfg_running=lambda: True)
            raise AssertionError("emulatore aperto accettato")
        except emucfg.EmuCfgError as exc:
            assert "aperto" in str(exc)
        assert not e.file.exists()
        assert emucfg.apply_for_game("fake", None, "X", "leave", "quality", cfg_running=True) is None
        assert emucfg.apply_for_game("fake", None, "X", "quality", cfg_running=False)
        mtime = e.file.stat().st_mtime_ns
        assert emucfg.apply_for_game("fake", None, "X", "quality", cfg_running=False) is None
        assert e.file.stat().st_mtime_ns == mtime
        assert len(list(e.file.parent.glob("*.pozzo-*"))) == 0
    print("ok  processo aperto rifiutato; leave e contenuto invariato non scrivono")


def test_unsupported_and_undeterminable_target():
    with Env() as e:
        try:
            e.adapter.target = lambda *a, **k: None
            emucfg.apply_for_game("fake", None, "X", "performance", cfg_running=False)
            raise AssertionError("target None accettato")
        except emucfg.EmuCfgError:
            pass
    print("ok  target non determinabile = errore")


def test_invalid_catalog_raises():
    bad = []
    for mutate in (
        lambda d: d["presets"]["quality"].update(sources=["http://x"]),
        lambda d: d["presets"]["quality"].update(sources=[]),
        lambda d: d["presets"].update(turbo=d["presets"]["quality"]),
        lambda d: d["games"]["G1"].update(reason=""),
        lambda d: d["games"]["G1"].update(preset="nope"),
        lambda d: d["presets"]["quality"].update(values={"": {"k": 1}}),
        lambda d: d.update(emulator="altro"),
    ):
        data = json.loads(json.dumps(CATALOG))
        mutate(data)
        with Env(data):
            try:
                emucfg.catalog("fake")
                bad.append(data)
            except ValueError:
                pass
            assert not emucfg.supported("fake")
    assert not bad
    print("ok  catalogo non valido: errore")


def test_atomic_write_leaves_no_temp_and_keeps_old_on_failure():
    with tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent) as folder:
        target = Path(folder) / "a" / "x.cfg"
        emucfg._atomic_write(target, b"uno")
        emucfg._atomic_write(target, b"due")
        assert target.read_bytes() == b"due"
        assert [p.name for p in target.parent.iterdir()] == ["x.cfg"]
        real = emucfg.os.replace
        emucfg.os.replace = lambda *a: (_ for _ in ()).throw(OSError("boom"))
        try:
            emucfg._atomic_write(target, b"tre")
            raise AssertionError("errore ignorato")
        except OSError:
            pass
        finally:
            emucfg.os.replace = real
        assert target.read_bytes() == b"due"
        assert [p.name for p in target.parent.iterdir()] == ["x.cfg"]
    print("ok  scrittura atomica")


def test_retroarch_override_path_is_confined():
    path = emucfg.retroarch_override_path(Path("cfg"), "snes9x", "Super Mario World")
    assert path == Path("cfg") / "snes9x" / "Super Mario World.cfg"
    for bad in ("..", "../outside", "core/name"):
        try:
            emucfg.retroarch_override_path("cfg", bad, "Game")
            raise AssertionError(f"Nome non valido accettato: {bad}")
        except ValueError:
            pass
    print("ok  percorso per-gioco confinato")


if __name__ == "__main__":
    test_shipped_catalogs_are_valid()
    test_precedence_game_over_console_over_leave()
    test_apply_restore_byte_identical_and_after_restart()
    test_new_file_is_deleted_on_restore()
    test_running_unchanged_and_leave()
    test_unsupported_and_undeterminable_target()
    test_invalid_catalog_raises()
    test_atomic_write_leaves_no_temp_and_keeps_old_on_failure()
    test_retroarch_override_path_is_confined()
    print("TUTTI I TEST OK")
