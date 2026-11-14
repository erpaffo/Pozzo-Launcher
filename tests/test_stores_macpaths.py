"""Percorsi di Steam, Epic e Minecraft su macOS/Linux; su Windows restano quelli di sempre."""
import importlib
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo.stores import epic, minecraft, steam  # noqa: E402

REAL_PLATFORM = sys.platform
steam.reg_get = lambda *a, **k: None  # niente registro fuori da Windows


def run(platform, home, fn):
    """Esegue fn con sys.platform e home finti, poi ripristina."""
    sys.platform = platform
    try:
        # Path.home() su Windows legge USERPROFILE, non HOME: si patcha direttamente
        with mock.patch.object(Path, "home", return_value=Path(home)):
            return fn()
    finally:
        sys.platform = REAL_PLATFORM


def steam_path(home, platform):
    fake = types.SimpleNamespace(settings={})  # path() usa solo self.settings
    return run(platform, home, lambda: steam.Steam.path(fake))


with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)

    # Steam: mac
    mac_root = home / "Library/Application Support/Steam"
    (mac_root / "steamapps").mkdir(parents=True)
    assert steam_path(home, "darwin") == mac_root
    assert steam.Steam.libraries(types.SimpleNamespace(path=lambda: mac_root)) == [mac_root]

    # Steam: linux, la prima radice esistente vince
    linux_root = home / ".local/share/Steam"
    linux_root.mkdir(parents=True)
    assert steam_path(home, "linux") == linux_root
    (home / ".steam/steam").mkdir(parents=True)
    assert steam_path(home, "linux") == home / ".steam/steam"

    # Steam: nessuna installazione
    empty = home / "vuoto"
    empty.mkdir()
    assert steam_path(empty, "darwin") is None

    # Steam: Windows senza registro resta None (nessun fallback)
    assert steam_path(home, "win32") is None

    # Epic: mac usa la cartella del launcher, Windows invariato
    run("darwin", home, lambda: importlib.reload(epic))
    assert epic.MANIFESTS == home / "Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests"
    run("win32", home, lambda: importlib.reload(epic))
    assert str(epic.MANIFESTS) == r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
    importlib.reload(epic)

    # Minecraft Java: mac, linux, Windows
    assert run("darwin", home, minecraft.java_dir) == str(home / "Library/Application Support/minecraft")
    assert run("linux", home, minecraft.java_dir) == str(home / ".minecraft")
    assert run("win32", home, minecraft.java_dir) == os.path.expandvars(r"%APPDATA%\.minecraft")

print("OK test_stores_macpaths")
