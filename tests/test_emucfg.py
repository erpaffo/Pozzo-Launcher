"""Override emulatori offline: catalogo, precedenza, backup e ripristino."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import emucfg  # noqa: E402


PRESET = "retroarch-sync"


def test_default_does_not_write():
    with tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent) as folder:
        target = Path(folder) / "game.cfg"
        assert emucfg.apply(target) is None
        assert emucfg.apply(target, "leave") is None
        assert not target.exists()
        assert not list(Path(folder).iterdir())
    print("ok  default Non toccare: nessuna scrittura o directory")


def test_catalog_is_offline_and_sources_are_present():
    data = emucfg.catalog()
    assert data["default"] == "leave"
    assert [p["id"] for p in data["presets"]] == [PRESET]
    profile = data["presets"][0]
    assert profile["emulator"] == "retroarch"
    assert profile["values"] == {
        "video_vsync": "true",
        "video_smooth": "true",
        "audio_sync": "true",
    }
    assert all(url.startswith("https://") for url in profile["sources"])
    print("ok  catalogo locale: un preset RetroArch con fonti HTTPS")


def test_game_selection_overrides_general_and_inherit_falls_back():
    assert emucfg.resolve(general=PRESET)["id"] == PRESET
    assert emucfg.resolve(game=PRESET, general="leave")["id"] == PRESET
    assert emucfg.resolve(game="leave", general=PRESET) is None
    assert emucfg.resolve(game="inherit", general=PRESET)["id"] == PRESET
    assert emucfg.resolve() is None
    print("ok  override gioco > generale, inherit e leave")


def test_apply_preserves_file_and_restore_recovers_original():
    with tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent) as folder:
        target = Path(folder) / "retroarch.cfg"
        original = b"# commento\r\nvideo_vsync = false\r\ncustom_option = 7\r\n"
        target.write_bytes(original)
        backup = emucfg.apply(target, PRESET)
        assert backup and backup.changed and backup.existed
        changed = target.read_bytes()
        assert b"# commento\r\n" in changed
        assert b"video_vsync = true\r\n" in changed
        assert b"video_smooth = true\r\n" in changed
        assert b"audio_sync = true\r\n" in changed
        assert b"custom_option = 7\r\n" in changed
        assert backup.backup_path and backup.backup_path.read_bytes() == original
        assert emucfg.restore(backup)
        assert target.read_bytes() == original
        print("ok  applicazione con backup e ripristino senza perdere il file")


def test_apply_new_file_and_noop_when_already_applied():
    with tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent) as folder:
        target = Path(folder) / "core" / "game.cfg"
        backup = emucfg.apply(target, PRESET)
        assert backup and not backup.existed and target.is_file()
        assert emucfg.apply(target, PRESET) is None
        assert emucfg.restore(backup)
        assert not target.exists()
        print("ok  file creato rimosso al restore; preset identico non riscrive")


def test_game_path_and_unknown_presets_are_safe():
    path = emucfg.retroarch_override_path("C:/config", "snes9x", "Super Mario World")
    assert path == Path("C:/config") / "snes9x" / "Super Mario World.cfg"
    for bad in ("..", "../outside", "core/name"):
        try:
            emucfg.retroarch_override_path("C:/config", bad, "Game")
            raise AssertionError(f"Nome non valido accettato: {bad}")
        except ValueError:
            pass
    with tempfile.TemporaryDirectory(prefix="_emucfg-", dir=Path(__file__).parent) as folder:
        target = Path(folder) / "game.cfg"
        try:
            emucfg.apply(target, "not-a-preset")
            raise AssertionError("Preset sconosciuto accettato")
        except ValueError:
            pass
        assert not target.exists()
    print("ok  percorso per-gioco confinato e preset sconosciuti senza scritture")


if __name__ == "__main__":
    test_default_does_not_write()
    test_catalog_is_offline_and_sources_are_present()
    test_game_selection_overrides_general_and_inherit_falls_back()
    test_apply_preserves_file_and_restore_recovers_original()
    test_apply_new_file_and_noop_when_already_applied()
    test_game_path_and_unknown_presets_are_safe()
    print("TUTTI I TEST OK")
