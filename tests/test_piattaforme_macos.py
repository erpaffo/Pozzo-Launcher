"""Comportamento per piattaforma (macOS/Linux) di power, watchhook, sunshine, scanner, extract e media-locale.
Sistema, subprocess e font finti: nessun comando reale. Windows: gli argv devono restare quelli di sempre.

Esegui: PYTHONUTF8=1 python tests/test_piattaforme_macos.py
"""
import ctypes
import importlib.util
import os
import plistlib
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import power  # noqa: E402
from pozzo.downloads import extract as E  # noqa: E402
from pozzo.library import watchhook as WH  # noqa: E402
from pozzo.remote import sunshine as SU  # noqa: E402
from pozzo import scanner as SC  # noqa: E402


@contextmanager
def platform(name):
    old = sys.platform
    sys.platform = name
    try:
        yield
    finally:
        sys.platform = old


def fake_run(calls, stdout=b""):
    def run(argv, *a, **kw):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=b"")
    return run


def test_power():
    # Windows: argv invariati
    for plat, mode, want in (
        ("win32", "shutdown", ["shutdown", "/s", "/t", "0"]),
        ("win32", "sleep", ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]),
        ("darwin", "sleep", ["pmset", "sleepnow"]),
        ("darwin", "shutdown", ["osascript", "-e", 'tell application "System Events" to shut down']),
        ("linux", "sleep", ["systemctl", "suspend"]),
        ("linux", "shutdown", ["systemctl", "poweroff"]),
    ):
        calls = []
        with platform(plat), mock.patch.object(power.subprocess, "run", fake_run(calls)):
            power._state.update(mode=mode, at=0.0, timer=None)
            power._do(mode)
        assert calls == [want], (plat, mode, calls)
    # schedule accetta macOS/Linux e rifiuta gli altri sistemi
    with platform("darwin"):
        assert power.schedule("sleep", 600)["mode"] == "sleep"
        assert power.cancel() is True
    with platform("freebsd"):
        try:
            power.schedule("sleep", 600)
            raise AssertionError("doveva rifiutare")
        except ValueError:
            pass
    print("ok  power: comandi per piattaforma")


def test_sunshine_percorsi(tmp_path):
    home = tmp_path / "home"
    (home / ".config" / "sunshine").mkdir(parents=True)
    (home / ".config" / "sunshine" / "sunshine.conf").write_text("port = 47989\n", encoding="utf-8")
    real_exists = Path.exists
    target = "/opt/homebrew/bin/sunshine"
    with platform("darwin"), mock.patch.object(SU.shutil, "which", lambda n: None), \
            mock.patch.object(Path, "exists", lambda self: str(self) == target or real_exists(self)), \
            mock.patch.dict(os.environ, {"HOME": str(home)}):
        assert SU.install_dir() == Path("/opt/homebrew/bin")
        assert SU.read_conf() == {"port": "47989"}
    with platform("darwin"), mock.patch.object(SU.shutil, "which", lambda n: None), \
            mock.patch.object(Path, "exists", lambda self: False):
        assert SU.install_dir() is None
    # Windows: sotto Program Files/Sunshine/config
    pf = tmp_path / "pf"
    (pf / "Sunshine" / "config").mkdir(parents=True)
    (pf / "Sunshine" / "sunshine.exe").write_text("", encoding="utf-8")
    (pf / "Sunshine" / "config" / "sunshine.conf").write_text("a = b\n", encoding="utf-8")
    with platform("win32"), mock.patch.dict(os.environ, {"ProgramFiles": str(pf), "ProgramFiles(x86)": ""}):
        assert SU.install_dir() == pf / "Sunshine"
        assert SU.read_conf() == {"a": "b"}
    print("ok  sunshine: rilevamento e config per piattaforma")


def test_sunshine_font(tmp_path):
    dest = tmp_path / "bp.png"
    seen = []

    from PIL import ImageFont
    real = ImageFont.truetype

    def truetype(name, size, index=0, **kw):
        if not (isinstance(name, str) and name.endswith((".ttc", ".ttf"))):
            return real(name, size, index=index, **kw)  # font di ripiego di PIL
        seen.append((name, size, index))
        raise OSError("font finto")  # il codice ripiega sul font di PIL, al primo tentativo

    with mock.patch.object(ImageFont, "truetype", truetype):
        with platform("darwin"):
            SU._make_bp_image(dest)
        assert seen == [("/System/Library/Fonts/Helvetica.ttc", 54, 1)], seen
        seen.clear()
        with platform("win32"):
            SU._make_bp_image(dest)
        assert seen == [("segoeuib.ttf", 54, 0)], seen
    print("ok  sunshine: font per piattaforma")


def test_scanner_disco(tmp_path):
    SC._DISK_CACHE.clear()
    calls = []
    with platform("darwin"), mock.patch.object(SC.subprocess, "run",
                                              fake_run(calls, plistlib.dumps({"SolidState": True}))), \
            mock.patch.object(SC, "_mount_of", lambda p: Path("/")):
        assert SC.disk_kind(tmp_path) == "ssd"
    assert calls == [["diskutil", "info", "-plist", "/"]], calls
    SC._DISK_CACHE.clear()
    with platform("darwin"), mock.patch.object(SC.subprocess, "run", fake_run([], plistlib.dumps({}))), \
            mock.patch.object(SC, "_mount_of", lambda p: Path("/")):
        assert SC.disk_kind(tmp_path) == "hdd"
    SC._DISK_CACHE.clear()
    # Windows: powershell con la lettera, come prima
    calls = []
    with platform("win32"), mock.patch.object(SC.subprocess, "run", fake_run(calls, "SSD\n")), \
            mock.patch.object(Path, "resolve", lambda self, *a, **k: PureWindowsPath("C:/giochi/x")):
        assert SC.disk_kind(Path("C:/giochi/x")) == "ssd"
    assert calls and calls[0][:2] == ["powershell", "-NoProfile"] and "-DriveLetter C" in calls[0][-1], calls
    SC._DISK_CACHE.clear()
    print("ok  scanner: disco macOS via diskutil, Windows invariato")


def test_extract_hint(tmp_path):
    src = tmp_path / "Gioco.zip"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("a.bin", b"x")

    def no_zip(*a, **k):
        raise E._Skip("forzato")

    msgs = []
    with mock.patch.object(E, "_zip", no_zip), mock.patch.object(E, "_sevenzip", lambda: None):
        for plat, want_hint in (("darwin", True), ("win32", False)):
            msgs.clear()
            with platform(plat):
                try:
                    E.extract(src, tmp_path / plat)
                    raise AssertionError("doveva fallire")
                except E.NoBackend as e:
                    msgs.append(str(e))
            assert ("brew install sevenzip" in msgs[0]) is want_hint, (plat, msgs)
            if not want_hint:
                assert msgs[0] == E.NO_BACKEND, msgs
    print("ok  extract: hint Homebrew solo su macOS")


def test_media_vlc(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "media_backend_test", Path(__file__).resolve().parent.parent / "extensions" / "media-locale" / "backend.py")
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except ImportError as e:  # dipendenze dell'estensione non installate: il test non e' applicabile
        print(f"skip media-locale ({e})")
        return
    vlc = "/Applications/VLC.app/Contents/MacOS/VLC"
    mpv = "/opt/homebrew/bin/mpv"
    real_is_file = Path.is_file
    with platform("darwin"), mock.patch.object(mod.shutil, "which", lambda n: None), \
            mock.patch.object(Path, "is_file", lambda self: str(self) in (vlc, mpv) or real_is_file(self)):
        assert mod.find_external_player() == mpv  # mpv prima di VLC
        with mock.patch.object(mod, "MPV_PATHS", ()):
            assert mod.find_external_player() == vlc
    assert mod.VLC_PATHS[0] == r"C:\Program Files\VideoLAN\VLC\vlc.exe"
    print("ok  media-locale: VLC e mpv su macOS")


if __name__ == "__main__":
    test_power()
    with tempfile.TemporaryDirectory() as t:
        test_sunshine_percorsi(Path(t))
        test_sunshine_font(Path(t))
        test_scanner_disco(Path(t))
        test_extract_hint(Path(t))
        test_media_vlc(Path(t))
    print("TUTTI I TEST OK")
