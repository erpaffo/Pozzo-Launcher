"""Percorsi macOS/Linux degli emulatori: Eden, PCSX2, Dolphin, schermate e processi (HOME e sys.platform finti)."""

import contextlib
import os
import sys
import tempfile
import types
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import edenroom  # noqa: E402
from pozzo.emuadapters import eden  # noqa: E402
from pozzo.library import screens  # noqa: E402
from pozzo.remote import emusetup  # noqa: E402

_KEYS = ("HOME", "APPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "DOLPHIN_EMU_USERPATH")


@contextlib.contextmanager
def _sys(home: Path, platform: str, **env):
    saved_p = sys.platform
    saved = {k: os.environ.get(k) for k in _KEYS}
    for k in _KEYS:
        os.environ.pop(k, None)
    os.environ["HOME"] = str(home)
    os.environ.update(env)
    sys.platform = platform
    # su Windows Path.home() legge USERPROFILE, non HOME
    ph = mock.patch.object(Path, "home", return_value=Path(home))
    ph.start()
    try:
        yield
    finally:
        ph.stop()
        sys.platform = saved_p
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_eden_dati_per_os():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        with _sys(h, "darwin"):
            assert eden._base(None) == h / "Library" / "Application Support" / "eden"
        with _sys(h, "linux"):
            assert eden._base(None) == h / ".local" / "share" / "eden"
        with _sys(h, "linux", XDG_DATA_HOME=str(h / "xdg")):
            assert eden._base(None) == h / "xdg" / "eden"
        with _sys(h, "win32", APPDATA=str(h / "appdata")):
            assert eden._base(None) == h / "appdata" / "eden"  # Windows invariato


def test_eden_config_file_su_macos():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        ini = h / "Library" / "Application Support" / "eden" / "config" / "qt-config.ini"
        ini.parent.mkdir(parents=True)
        ini.write_text("[UI]\n", encoding="utf-8")
        with _sys(h, "darwin"):
            assert edenroom.config_file(None) == ini


def test_pcsx2_ini_per_os():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        with _sys(h, "darwin"):
            assert emusetup.pcsx2_ini(None) == h / "Library" / "Application Support" / "PCSX2" / "inis" / "PCSX2.ini"
        with _sys(h, "linux"):
            assert emusetup.pcsx2_ini(None) == h / ".config" / "PCSX2" / "inis" / "PCSX2.ini"
        with _sys(h, "linux", XDG_CONFIG_HOME=str(h / "cfg")):
            assert emusetup.pcsx2_ini(None) == h / "cfg" / "PCSX2" / "inis" / "PCSX2.ini"


def test_dolphin_dir_usa_adattatore_su_macos():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        with _sys(h, "darwin"):
            assert emusetup.dolphin_dir(None) == h / "Library" / "Application Support" / "Dolphin"
        with _sys(h, "linux"):
            assert emusetup.dolphin_dir(None) == h / ".local" / "share" / "dolphin-emu"


def test_running_ignora_exe_e_maiuscole():
    procs = [types.SimpleNamespace(info={"name": n}) for n in ("Dolphin", "pcsx2-qt.exe", "Other")]
    saved = sys.modules.get("psutil")
    sys.modules["psutil"] = types.SimpleNamespace(process_iter=lambda attrs: procs)
    try:
        assert emusetup._running(("dolphin", "dolphin-emu"))
        assert emusetup._running(("pcsx2-qt", "pcsx2"))
        assert emusetup._running(("pcsx2-qt.exe",))
        assert not emusetup._running(("eden", "eden.exe"))
    finally:
        if saved is None:
            sys.modules.pop("psutil", None)
        else:
            sys.modules["psutil"] = saved


def test_schermate_macos():
    with tempfile.TemporaryDirectory() as t:
        h = Path(t)
        sup = h / "Library" / "Application Support"
        dirs = {
            "dolphin": sup / "Dolphin" / "ScreenShots",
            "pcsx2": sup / "PCSX2" / "snaps",
            "duckstation": sup / "DuckStation" / "screenshots",
            "ppsspp": sup / "PPSSPP" / "PSP" / "SCREENSHOT",
            "retroarch": sup / "RetroArch" / "screenshots",
        }
        for d in dirs.values():
            d.mkdir(parents=True)
        with _sys(h, "darwin"):
            for emu, d in dirs.items():
                found = {os.path.normcase(str(x)) for x in screens.emulator_dirs(emu, None)}
                assert os.path.normcase(str(d)) in found, (emu, found)


if __name__ == "__main__":
    test_eden_dati_per_os()
    test_eden_config_file_su_macos()
    test_pcsx2_ini_per_os()
    test_dolphin_dir_usa_adattatore_su_macos()
    test_running_ignora_exe_e_maiuscole()
    test_schermate_macos()
    print("ok  percorsi macOS/Linux degli emulatori")
