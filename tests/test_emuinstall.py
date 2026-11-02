"""Test dell'installazione degli emulatori dalle release ufficiali: scelta del file, impostazione dell'eseguibile,
aggiornamento che conserva i file dell'utente, indirizzo costruito dalla versione, core di RetroArch. Nessuna rete.

Esegui: python tests/test_emuinstall.py
"""
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config  # noqa: E402
from pozzo import emuinstall as EI  # noqa: E402
from pozzo import ports as PT  # noqa: E402

if sys.platform != "win32":  # l'installer degli emulatori è solo Windows x64 (vedi emuinstall.py)
    if __name__ == "__main__":
        print("-- saltato: installer degli emulatori solo Windows")
        sys.exit(0)
    import pytest
    pytest.skip("installer degli emulatori solo Windows", allow_module_level=True)


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
        elif "RetroArch" in url:
            data = _zip({"RetroArch-Win64/retroarch.exe": b"ra"})
        else:
            data = _zip({"DuckStation/duckstation-qt-x64-ReleaseLTCG.exe": tag["v"].encode()})
        Path(dest).write_bytes(data)

    saved = (PT.releases, PT._download)
    PT.releases, PT._download = releases, download
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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_install(Path(t))
    print("TUTTI I TEST OK")
