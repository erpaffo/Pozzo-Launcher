"""Test dell'installazione «un clic» (pozzo/emuinstall_extra.py): emulatore dedicato, console RetroArch, gia'
installato, console non supportata, errore di rete simulato, progress chiamato. Nessuna rete: releases e download
sono sostituiti con funzioni finte.

Esegui: python tests/test_emuinstall_extra.py
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
from pozzo import emuinstall_extra as X  # noqa: E402
from pozzo import ports as PT  # noqa: E402


def _zip(files: dict) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)
    return b.getvalue()


def _cfg(tmp: Path):
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    return config.load(tmp / "config.toml")


def _finti(urls: list, rete=None):
    """releases/download finti: PCSX2 (zip), RetroArch e i core di libretro. rete: eccezione da sollevare."""
    asset = lambda n: {"name": n, "url": n, "size": 0}  # noqa: E731

    def releases(provider, repo, token=""):
        if rete:
            raise OSError(rete)
        if repo == "libretro/RetroArch":
            return [{"tag": "v1.21.0", "prerelease": False, "url": "", "assets": []}]
        return [{"tag": "v2.0.0", "prerelease": False, "url": "",
                 "assets": [asset("pcsx2-v2.0.0-windows-x64-qt.zip"), asset("pcsx2-v2.0.0-linux.AppImage")]}]

    def download(url, dest, progress=None, token=""):
        urls.append(url)
        if rete:
            raise ConnectionError(rete)
        if url.endswith("_libretro.dll.zip"):
            data = _zip({url.rsplit("/", 1)[-1][:-4]: b"core"})
        elif "RetroArch" in url:
            data = _zip({"RetroArch-Win64/retroarch.exe": b"ra"})
        else:
            data = _zip({"pcsx2-qt.exe": b"pcsx2"})
        Path(dest).write_bytes(data)
        if progress:
            progress(len(data) // 2, len(data))
            progress(len(data), len(data))

    return releases, download


def _con_finti(urls, rete=None):
    """Mette le funzioni finte al posto di quelle di rete. Ritorna il ripristino."""
    saved = (PT.releases, PT._download)
    PT.releases, PT._download = _finti(urls, rete)
    return lambda: setattr(PT, "releases", saved[0]) or setattr(PT, "_download", saved[1])


def test_consigliato_dedicato_e_retroarch(tmp: Path):
    cfg = _cfg(tmp)
    r = X.recommend("ps2", cfg)
    assert r["emulator"] == "pcsx2" and r["supported"] is True and r["installed"] is False
    assert "PCSX2" in r["reason"]
    r = X.recommend("nes", cfg)  # console RetroArch: il core migliore della lista
    assert r["emulator"] == "retroarch" and r["supported"] is True and "mesen" in r["reason"]


def test_gia_installato(tmp: Path):
    cfg = _cfg(tmp)
    exe = tmp / "pcsx2" / "pcsx2-qt.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"pcsx2")
    cfg.emulators["pcsx2"] = str(exe)
    cfg.app["emu_installed"] = {"pcsx2": {"version": "v2.0.0", "dir": str(exe.parent)}}
    assert X.recommend("ps2", cfg)["installed"] is True
    urls = []
    ripristina = _con_finti(urls)
    try:
        esito = X.install_recommended("ps2", cfg=cfg)
    finally:
        ripristina()
    assert urls == [], "gia' installato: nessun download"
    assert esito["ok"] is True and "già installato" in esito["message"] and esito["core_installed"] == []


def test_non_supportato(tmp: Path):
    cfg = _cfg(tmp)
    r = X.recommend("switch", cfg)  # Pozzo non sa installare ne' Ryujinx ne' Eden
    assert r["supported"] is False and r["emulator"] == "" and r["installed"] is False
    esito = X.install_recommended("switch", cfg=cfg)
    assert esito["ok"] is False and esito["core_installed"] == [] and "non sa installare" in esito["message"]


def test_console_sconosciuta(tmp: Path):
    try:
        X.recommend("console-che-non-esiste", _cfg(tmp))
    except ValueError as e:
        assert "console sconosciuta" in str(e)
    else:
        raise AssertionError("ci si aspetta ValueError")


def test_installa_emulatore_dedicato_con_progress(tmp: Path):
    cfg = _cfg(tmp)
    urls, fasi = [], []
    ripristina = _con_finti(urls)
    try:
        esito = X.install_recommended("ps2", progress=lambda f, v: fasi.append((f, v)), cfg=cfg)
    finally:
        ripristina()
    assert esito["ok"] is True and esito["emulator"] == "pcsx2" and esito["core_installed"] == []
    assert Path(cfg.emulators["pcsx2"]).read_bytes() == b"pcsx2"
    assert fasi and fasi[-1] == ("Fatto", 1.0), "progress chiamato in sincrono, fino alla fine"
    assert any(0 < v < 1 for _, v in fasi), "avanzamento del download"


def test_installa_retroarch_e_core(tmp: Path):
    cfg = _cfg(tmp)
    urls = []
    ripristina = _con_finti(urls)
    try:
        esito = X.install_recommended("nes", cfg=cfg)
    finally:
        ripristina()
    assert esito["ok"] is True and esito["emulator"] == "retroarch"
    assert esito["core_installed"] == ["mesen"], "il core del preset della console"
    assert any(u.endswith("mesen_libretro.dll.zip") for u in urls)
    assert "core installati: mesen" in esito["message"]


def test_errore_di_rete(tmp: Path):
    cfg = _cfg(tmp)
    ripristina = _con_finti([], rete="rete non raggiungibile")
    try:
        esito = X.install_recommended("ps2", cfg=cfg)
    finally:
        ripristina()
    assert esito["ok"] is False and esito["emulator"] == "pcsx2"
    assert "non riuscita" in esito["message"] and "rete non raggiungibile" in esito["message"]
    assert "pcsx2" not in cfg.emulators, "nulla impostato se il download fallisce"


if __name__ == "__main__":
    if sys.platform != "win32":  # l'installer degli emulatori è solo Windows x64 (vedi emuinstall.py)
        print("-- saltato: installer degli emulatori solo Windows")
        sys.exit(0)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_consigliato_dedicato_e_retroarch(Path(t))
    for fn in (test_gia_installato, test_non_supportato, test_console_sconosciuta,
               test_installa_emulatore_dedicato_con_progress, test_installa_retroarch_e_core, test_errore_di_rete):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            fn(Path(t))
    print("TUTTI I TEST OK")
