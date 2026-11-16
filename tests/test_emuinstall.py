"""Test dell'installazione degli emulatori dalle release ufficiali: scelta del file, impostazione dell'eseguibile,
aggiornamento che conserva i file dell'utente, indirizzo costruito dalla versione, core di RetroArch. Nessuna rete.

Esegui: python tests/test_emuinstall.py
"""
import contextlib
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config  # noqa: E402
from pozzo import emuinstall as EI  # noqa: E402
from pozzo import ports as PT  # noqa: E402

import py7zr  # noqa: E402 - importati col sistema vero: sotto un sys.platform finto sceglierebbero i moduli sbagliati
try:
    import psutil  # noqa: E402, F401
except ImportError:
    pass


@contextlib.contextmanager
def _os(plat: str, arch: str = "x64"):
    """Fa girare l'installer come su `plat` con il processore `arch` (file della release, estrazione, core)."""
    saved = (sys.platform, EI.SOURCES, EI.KNOWN, EI.ARCH)
    sys.platform, EI.ARCH = plat, arch
    EI.SOURCES, EI.KNOWN = EI._for_os(plat, arch), EI._for_os(plat)
    try:
        yield
    finally:
        sys.platform, EI.SOURCES, EI.KNOWN, EI.ARCH = saved


def _zip(files: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return b.getvalue()


def test_install(tmp: Path):
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    tag = {"v": "v0.1"}
    asset = lambda n: {"name": n, "url": n, "size": 0}  # noqa: E731
    urls = []

    def releases(provider, repo, token=""):
        return [{"tag": tag["v"], "prerelease": False, "url": "",
                 "assets": [asset("duckstation-linux-x64.AppImage"), asset("duckstation-windows-arm64-release.zip"),
                            asset("duckstation-windows-x64-release.zip"), asset("RetroArch-source.zip")]}]

    def download(url, dest, progress=None, token=""):
        urls.append(url)
        if url.endswith("_libretro.dll.zip"):
            name = url.rsplit("/", 1)[-1][:-4]
            data = _zip({name: b"core"})
        elif "RetroArch" in url:  # un .7z vero: py7zr (senza 7-Zip installato)
            with py7zr.SevenZipFile(dest, "w") as z:
                z.writestr(b"ra", "RetroArch-Win64/retroarch.exe")
            return
        else:
            data = _zip({"DuckStation/duckstation-qt-x64-ReleaseLTCG.exe": tag["v"].encode()})
        Path(dest).write_bytes(data)

    saved = (PT.releases, PT._download)
    PT.releases, PT._download = releases, download
    with _os("win32"):  # nomi dei file e percorsi di Windows anche su macOS/Linux
        try:
            exe = EI.install(cfg, "duckstation", say=lambda m: None)
            assert urls[-1] == "duckstation-windows-x64-release.zip", "file x64 per Windows"
            assert cfg.emulators["duckstation"] == exe and Path(exe).read_bytes() == b"v0.1"
            assert Path(exe).is_relative_to(EI.emus_dir(cfg) / "duckstation")
            assert next(x for x in EI.catalog(cfg) if x["id"] == "duckstation")["version"] == "v0.1"

            (Path(exe).parent / "portable.txt").write_text("mio")  # file dell'utente
            n = len(urls)
            EI.install(cfg, "duckstation", say=lambda m: None)
            assert len(urls) == n, "gia' all'ultima versione: niente download"
            tag["v"] = "v0.2"
            EI.install(cfg, "duckstation", say=lambda m: None)
            assert Path(exe).read_bytes() == b"v0.2" and (Path(exe).parent / "portable.txt").read_text() == "mio"

            tag["v"] = "v1.21.0"
            ra = EI.install(cfg, "retroarch", say=lambda m: None)
            assert urls[-1] == "https://buildbot.libretro.com/stable/1.21.0/windows/x86_64/RetroArch.7z"
            assert Path(ra).name == "retroarch.exe" and cfg.emulators["retroarch"] == ra

            cores = EI.missing_cores(cfg, ["snes", "psx", "ps2", "nes"])
            assert cores == ["snes9x", "mesen"], "psx ha gia' DuckStation, ps2 non usa RetroArch"
            assert EI.install_cores(cfg, cores, say=lambda m: None) == cores
            assert (Path(ra).parent / "cores" / "snes9x_libretro.dll").is_file()
            assert EI.missing_cores(cfg, ["snes", "nes"]) == []
        finally:
            PT.releases, PT._download = saved
    print("ok  emulatori installati, aggiornati (file dell'utente conservati) e core di RetroArch")


def _app(where: Path, name: str, data: bytes = b"bin"):
    """Bundle .app finto con Info.plist e un link simbolico interno (come i Framework veri)."""
    (where / f"{name}.app" / "Contents" / "MacOS").mkdir(parents=True)
    (where / f"{name}.app" / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": name}))
    (where / f"{name}.app" / "Contents" / "MacOS" / name).write_bytes(data)
    (where / f"{name}.app" / "Contents" / "Current").symlink_to("MacOS")


def test_install_macos(tmp: Path):
    if os.name == "nt":  # link simbolici, permessi posix e HOME: ha senso solo fuori da Windows
        print("-- saltato: solo fuori da Windows")
        return
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    asset = lambda n: {"name": n, "url": n, "size": 0}  # noqa: E731
    urls, cmds, ver = [], [], {"v": "v1.0"}

    def releases(provider, repo, token=""):
        if repo == "libretro/RetroArch":
            return [{"tag": "v1.22.2", "prerelease": False, "url": "", "assets": []}]
        return [{"tag": ver["v"], "prerelease": False, "url": "",
                 "assets": [asset("duckstation-windows-x64-release.zip"), asset("DuckStation-x64.AppImage"),
                            asset("duckstation-mac-release.zip")]}]

    def download(url, dest, progress=None, token=""):
        urls.append(url)
        if url.endswith(".dylib.zip"):
            Path(dest).write_bytes(_zip({url.rsplit("/", 1)[-1][:-4]: b"core"}))
        else:  # zip e .dmg: li «apre» run() qui sotto
            Path(dest).write_bytes(b"archivio")

    def run(argv, check=False, capture_output=False):  # hdiutil/ditto/xattr finti
        cmds.append(argv)
        if argv[:2] == ["hdiutil", "attach"]:
            _app(Path(argv[-2]), "RetroArch")
            (Path(argv[-2]) / "Applications").symlink_to("/Applications")
        elif argv[:3] == ["ditto", "-x", "-k"]:
            _app(Path(argv[4]), "DuckStation", ver["v"].encode())
        elif argv[0] == "ditto":
            shutil.copytree(argv[1], argv[2], symlinks=True)
        return subprocess.CompletedProcess(argv, 0)

    saved = (PT.releases, PT._download, EI._run, os.environ.get("HOME"))
    PT.releases, PT._download, EI._run, os.environ["HOME"] = releases, download, run, str(tmp / "home")
    with _os("darwin", "arm64"):
        try:
            assert "dolphin" in EI.SOURCES and "xenia" not in EI.SOURCES, "Xenia non ha build per macOS"
            exe = EI.install(cfg, "duckstation", say=lambda m: None)
            assert urls[-1] == "duckstation-mac-release.zip"
            assert Path(exe) == EI.emus_dir(cfg) / "duckstation" / "DuckStation.app" / "Contents" / "MacOS" / "DuckStation"
            assert (Path(exe).parents[1] / "Current").is_symlink(), "link del bundle conservati"
            (Path(exe).parents[1] / "vecchio.txt").write_text("x")  # file della versione vecchia nel bundle
            ver["v"] = "v1.1"
            assert EI.install(cfg, "duckstation", say=lambda m: None) == exe and Path(exe).read_bytes() == b"v1.1"
            assert not (Path(exe).parents[1] / "vecchio.txt").exists(), "aggiornamento: .app sostituito intero"

            ra = EI.install(cfg, "retroarch", say=lambda m: None)
            assert urls[-1] == "https://buildbot.libretro.com/stable/1.22.2/apple/osx/universal/RetroArch_Metal.dmg"
            mnt = cmds[-4][-2]
            assert cmds[-4][:5] == ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint"]
            assert cmds[-3][0] == "ditto" and cmds[-3][1] == str(Path(mnt) / "RetroArch.app")
            assert cmds[-2] == ["hdiutil", "detach", mnt], "il .dmg si smonta sempre"
            assert cmds[-1][:3] == ["xattr", "-dr", "com.apple.quarantine"]
            assert ra.endswith("RetroArch.app/Contents/MacOS/RetroArch") and Path(ra).is_file()

            assert EI.install_cores(cfg, ["snes9x"], say=lambda m: None) == ["snes9x"]
            assert urls[-1].endswith("/latest/snes9x_libretro.dylib.zip") and "/apple/osx/" in urls[-1]
            cores = tmp / "home" / "Library" / "Application Support" / "RetroArch" / "cores"
            assert (cores / "snes9x_libretro.dylib").is_file() and cfg.emulators["retroarch_cores"] == str(cores)
        finally:
            PT.releases, PT._download, EI._run = saved[:3]
            os.environ["HOME"] = saved[3] or ""
    print("ok  macOS: .app da zip e da .dmg (hdiutil/ditto), core .dylib nella cartella di RetroArch")


def test_install_linux(tmp: Path):
    if os.name == "nt":  # link simbolici, permessi posix e HOME: ha senso solo fuori da Windows
        print("-- saltato: solo fuori da Windows")
        return
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    asset = lambda n: {"name": n, "url": n, "size": 0}  # noqa: E731
    urls = []

    def releases(provider, repo, token=""):
        return [{"tag": "v2.0", "prerelease": False, "url": "",
                 "assets": [asset("pcsx2-v2.0-windows-x64-Qt.7z"), asset("pcsx2-v2.0-macos-Qt.tar.xz"),
                            asset("pcsx2-v2.0-linux-flatpak-x64-Qt.flatpak"),
                            asset("pcsx2-v2.0-linux-appimage-x64-Qt.AppImage")]}]

    def get(url, params=None, token=""):  # /releases/latest di RPCS3
        assert url.endswith("/RPCS3/rpcs3-binaries-linux/releases/latest")
        return {"tag_name": "build-1", "assets": [{"name": "rpcs3-v0.0.43-1_linux64.AppImage",
                                                   "browser_download_url": "rpcs3.AppImage"}]}

    def download(url, dest, progress=None, token=""):
        urls.append(url)
        Path(dest).write_bytes(b"#!/bin/sh\n")

    saved = (PT.releases, PT._download, PT._get)
    PT.releases, PT._download, PT._get = releases, download, get
    with _os("linux"):
        try:
            assert "dolphin" not in EI.SOURCES, "Dolphin non ha build Linux ufficiali: non installabile"
            exe = Path(EI.install(cfg, "pcsx2", say=lambda m: None))
            assert urls[-1] == "pcsx2-v2.0-linux-appimage-x64-Qt.AppImage" and exe.name == urls[-1]
            assert exe.stat().st_mode & 0o777 == 0o755, "AppImage eseguibile"
            exe = Path(EI.install(cfg, "rpcs3", say=lambda m: None))
            assert urls[-1] == "rpcs3.AppImage" and exe.suffix == ".AppImage"
            assert EI.CORES_URL[("linux", "x64")].endswith("/linux/x86_64/latest/{core}_libretro.so.zip")
        finally:
            PT.releases, PT._download, PT._get = saved
    print("ok  Linux: AppImage eseguibile, RPCS3 da /releases/latest, Dolphin non disponibile")


def test_checksum(tmp: Path):
    """Asset di una release GitHub senza digest: rifiutato prima di scaricarlo. Fonti che non pubblicano
    checksum (sito del progetto, GitLab, Codeberg): si installa, ma il log lo dice."""
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    urls = []

    def download(url, dest, progress=None, token=""):
        urls.append(url)
        Path(dest).write_bytes(_zip({"DuckStation/duckstation-qt-x64-ReleaseLTCG.exe": b"x"}))

    saved = PT._download
    PT._download = download
    try:
        gh = {"name": "d.zip", "url": "https://github.com/o/r/releases/download/v1/d.zip", "sum": ""}
        try:
            EI._stage(cfg, gh, "duckstation")
            raise AssertionError("asset GitHub senza digest accettato")
        except RuntimeError as e:
            assert "checksum" in str(e)
        assert urls == []
        said = []
        saved_latest = EI._latest
        EI._latest = lambda cfg, src: ("v1", {"name": "d.zip", "url": "https://esempio.org/d.zip"})
        try:
            with _os("win32"):
                EI.install(cfg, "duckstation", say=said.append)
        finally:
            EI._latest = saved_latest
        assert any("non verificat" in m for m in said), said
    finally:
        PT._download = saved
    print("ok  checksum obbligatorio per le release GitHub, avviso per le fonti senza")


# nomi veri delle release (novembre 2026): ogni processore deve prendere il suo file e solo quello
_REAL = {
    "ppsspp": ["PPSSPP-v1.20.4-anylinux-aarch64.AppImage", "PPSSPP-v1.20.4-anylinux-aarch64.AppImage.zsync",
               "PPSSPP-v1.20.4-anylinux-x86_64.AppImage", "PPSSPP-v1.20.4-Windows-ARM64.zip",
               "PPSSPP-v1.20.4-Windows-x64.zip", "PPSSPPSDL-macOS-v1.20.4.zip"],
    "duckstation": ["DuckStation-arm64.AppImage", "DuckStation-armhf.AppImage", "duckstation-mac-release.zip",
                    "duckstation-windows-arm64-release-symbols.7z", "duckstation-windows-arm64-release.zip",
                    "duckstation-windows-x64-release.zip", "DuckStation-x64-SSE2.AppImage", "DuckStation-x64.AppImage"],
    "vita3k": ["macos-arm64-latest.dmg", "macos-latest.dmg", "ubuntu-aarch64-latest.zip", "ubuntu-latest.zip",
               "Vita3K-aarch64.AppImage", "Vita3K-x86_64.AppImage", "windows-arm64-latest.zip", "windows-latest.zip"],
    "melonds": ["melonDS-1.1-appimage-aarch64.zip", "melonDS-1.1-appimage-x86_64.zip", "melonDS-1.1-macOS-universal.zip",
                "melonDS-1.1-windows-aarch64.zip", "melonDS-1.1-windows-x86_64.zip"],
    "xemu": ["xemu-0.8.139-aarch64.AppImage", "xemu-0.8.139-dbg-aarch64.AppImage", "xemu-0.8.139-windows-arm64.zip",
             "xemu-0.8.139-dbg-windows-arm64.zip", "xemu-0.8.139-x86_64.AppImage", "xemu-win-aarch64-release.zip",
             "xemu-win-x86_64-release.zip", "xemu-0.8.139-macos-universal.zip"],
    "eden": ["Eden-Linux-v0.2.1-aarch64-gcc-standard.AppImage", "Eden-Linux-aarch64-gcc-standard.AppImage.zsync",
             "Eden-Linux-v0.2.1-amd64-gcc-standard.AppImage", "Eden-Windows-v0.2.1-amd64-msvc-standard.zip",
             "Eden-Windows-v0.2.1-arm64-clang-pgo.zip", "Eden-Windows-v0.2.1-arm64-clang-standard.zip",
             "Eden-macOS-v0.2.1.dmg"],
    "mgba": ["mGBA-0.10.5-appimage-arm64.appimage", "mGBA-0.10.5-appimage-x64.appimage", "mGBA-0.10.5-macos.dmg"],
    "mesen": ["Mesen_2.1.1_Linux_ARM64.zip", "Mesen_2.1.1_Linux_x64.zip", "Mesen_2.1.1_macOS_ARM64_AppleSilicon.zip",
              "Mesen_2.1.1_macOS_x64_Intel.zip", "Mesen_2.1.1_Windows.zip"],
    "ryujinx": ["ryujinx-1.3.3-arm64.AppImage", "ryujinx-1.3.3-linux_arm64.tar.gz", "ryujinx-1.3.3-x64.AppImage",
                "ryujinx-1.3.3-macos_universal.app.tar.gz", "ryujinx-1.3.3-win_x64.zip"],
    "rpcs3": ["rpcs3-v0.0.37-18146-ffeb16fe_macos.7z", "rpcs3-v0.0.37-18146-ffeb16fe_macos_arm64.7z",
              "rpcs3-v0.0.42-19759-ffc50905_linux_aarch64.AppImage", "rpcs3-v0.0.37-18146-ffeb16fe_linux64.AppImage"],
}
_WANT = {
    ("win32", "arm64"): {"ppsspp": "PPSSPP-v1.20.4-Windows-ARM64.zip", "duckstation": "duckstation-windows-arm64-release.zip",
                         "vita3k": "windows-arm64-latest.zip", "melonds": "melonDS-1.1-windows-aarch64.zip",
                         "xemu": "xemu-win-aarch64-release.zip", "eden": "Eden-Windows-v0.2.1-arm64-clang-standard.zip"},
    ("linux", "arm64"): {"ppsspp": "PPSSPP-v1.20.4-anylinux-aarch64.AppImage", "duckstation": "DuckStation-arm64.AppImage",
                         "vita3k": "Vita3K-aarch64.AppImage", "melonds": "melonDS-1.1-appimage-aarch64.zip",
                         "xemu": "xemu-0.8.139-aarch64.AppImage", "eden": "Eden-Linux-v0.2.1-aarch64-gcc-standard.AppImage",
                         "mgba": "mGBA-0.10.5-appimage-arm64.appimage", "mesen": "Mesen_2.1.1_Linux_ARM64.zip",
                         "ryujinx": "ryujinx-1.3.3-arm64.AppImage",
                         "rpcs3": "rpcs3-v0.0.42-19759-ffc50905_linux_aarch64.AppImage"},
    ("darwin", "x64"): {"vita3k": "macos-latest.dmg", "rpcs3": "rpcs3-v0.0.37-18146-ffeb16fe_macos.7z"},
    ("darwin", "arm64"): {"vita3k": "macos-arm64-latest.dmg"},
}


def test_arch(tmp: Path):
    """Ogni processore prende il file giusto; senza build per quel processore l'emulatore e' bloccato."""
    for (plat, arch), want in _WANT.items():
        src = EI._for_os(plat, arch)
        for emu, name in want.items():
            got = EI._pick_asset([{"name": n, "url": n} for n in _REAL[emu]], src[emu])
            assert got and got["name"] == name, (plat, arch, emu, got)
    assert EI._for_os("win32", "arm64")["dolphin"]["url"].endswith("dolphin-{ver}-arm64.7z")
    assert "pcsx2" not in EI._for_os("win32", "arm64") and "pcsx2" not in EI._for_os("linux", "arm64")
    assert "retroarch" not in EI._for_os("linux", "arm64"), "nessuna build stabile ARM64 sul buildbot"
    assert "eden" not in EI._for_os("darwin", "x64") and "cemu" in EI._for_os("darwin", "arm64"), "Cemu: Rosetta"
    assert EI._for_os("win32", "x64") == EI._for_os("win32"), "Windows x64: tabella invariata"
    assert ("win32", "arm64") not in EI.CORES_URL and "/linux/aarch64/" in EI.CORES_URL[("linux", "arm64")]

    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    with _os("win32", "arm64"):
        cat = {x["id"]: x for x in EI.catalog(cfg)}
        assert cat["pcsx2"]["arch_ok"] is False and cat["dolphin"]["arch_ok"] is True, "bloccati ma visibili"
        assert EI.arch_blocked("pcsx2") and not EI.arch_blocked("dolphin") and not EI.arch_blocked("boh")
        try:
            EI.install(cfg, "pcsx2", say=lambda m: None)
            raise AssertionError("installato un emulatore senza build ARM64")
        except ValueError as e:
            assert "ARM64" in str(e), e
    print("ok  architetture: file giusto per x64/ARM64, emulatori senza build bloccati")


if __name__ == "__main__":
    for fn in (test_install, test_install_macos, test_install_linux, test_checksum, test_arch):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            fn(Path(t))
    print("TUTTI I TEST OK")
