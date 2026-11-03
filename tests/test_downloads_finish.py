"""Dopo il download: estrazione, cartella ROM giusta, libreria, pulizia. Nessuna rete."""

import sys
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo.downloads import finish  # noqa: E402
from pozzo.downloads.task import COMPLETED, DownloadTask  # noqa: E402
from test_downloads_ingest import make_cfg, make_ctx  # noqa: E402


class Mgr:
    def __init__(self, **s):
        self._s = {"auto_extract": True, "delete_archive": True, **s}
        self.store = SimpleNamespace(save=lambda tasks: None)
        self.lock = threading.Lock()

    def settings(self):
        return self._s

    def _poke(self):
        pass


def _task(tmp, name, **opts):
    dl = tmp / "dl"
    dl.mkdir(exist_ok=True)
    return DownloadTask(source="https://x/" + name, save_path=str(dl), name=name, status=COMPLETED,
                        options={"game_id": 7, **opts})


def _ctx(tmp):
    cfg = make_cfg(tmp)
    ctx, calls, got = make_ctx(cfg, online={"id": 7, "title": "Gioco", "key": "online/7", "platform": "switch",
                                            "store": "online", "files": []})
    return ctx, calls, got, cfg


def test_zip_estratto_e_messo_nella_cartella_rom(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    z = tmp / "dl" / "Gioco.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Gioco/Gioco [0100AAAA].xci", b"x" * 50)
        f.writestr("Gioco/leggimi.txt", "ciao")
    t = _task(tmp, "Gioco.zip")
    finish.run(t, Mgr(), ctx)
    placed = list((cfg.roms).rglob("*.xci"))
    assert len(placed) == 1, [str(p) for p in cfg.roms.rglob("*")]
    assert calls == [{"platforms": ["switch"]}] and got, (calls, got)
    assert not z.exists()  # archivio tolto a gioco messo a posto
    assert t.options["post_done"] and any("Nella libreria" in l["msg"] for l in t.log_after(0)[0])
    assert Path(t.options["placed"]) == placed[0], "«Apri cartella» porta al gioco, non all'archivio cancellato"


def test_senza_estrazione_automatica_non_tocca_l_archivio(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    z = tmp / "dl" / "Gioco.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Gioco.xci", b"x")
    finish.run(_task(tmp, "Gioco.zip"), Mgr(auto_extract=False), ctx)
    assert z.exists() and not list(cfg.roms.rglob("*.xci")) and not calls


def test_file_di_gioco_gia_scaricato_va_in_libreria(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    (tmp / "dl").mkdir()
    (tmp / "dl" / "Gioco.xci").write_bytes(b"x" * 20)
    finish.run(_task(tmp, "Gioco.xci"), Mgr(), ctx)
    assert len(list(cfg.roms.rglob("*.xci"))) == 1 and calls


def test_volumi_mancanti_aspetta(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    (tmp / "dl").mkdir()
    (tmp / "dl" / "g.part1.rar").write_bytes(b"x")
    (tmp / "dl" / "g.part3.rar").write_bytes(b"x")  # manca il 2
    t = _task(tmp, "g.part1.rar")
    finish.run(t, Mgr(), ctx)
    assert any("Mancano" in l["msg"] for l in t.log_after(0)[0]) and not calls
    assert (tmp / "dl" / "g.part1.rar").exists()


def test_senza_gioco_estrae_e_basta(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    z = tmp / "dl" / "x.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("a.txt", "ciao")
    t = _task(tmp, "x.zip")
    t.options.pop("game_id")
    finish.run(t, Mgr(), ctx)
    assert (tmp / "dl" / "x" / "a.txt").exists() and not calls and z.exists()


def test_passi_in_libreria_nel_log_con_secondi_e_attesa_breve(tmp, monkeypatch):
    ctx, calls, got, cfg = _ctx(tmp)
    ctx.api_scan_start = lambda body: {}  # la libreria non si aggiorna mai
    real, phases = finish.I.ingest, []
    monkeypatch.setattr(finish.I, "ingest", lambda *a, **k: real(*a, **{**k, "timeout": 0.05, "poll": 0.01}))
    (tmp / "dl").mkdir()
    (tmp / "dl" / "Gioco.xci").write_bytes(b"x" * 20)
    t = _task(tmp, "Gioco.xci")
    mgr = Mgr()
    mgr._poke = lambda: phases.append(t.phase)
    finish.run(t, mgr, ctx)
    msgs = [(l["level"], l["msg"]) for l in t.log_after(0)[0]]
    assert any(m.startswith("Aggiungo alla libreria: scansione") and m.endswith(" s)") for _, m in msgs), msgs
    assert any(l == "warn" and "prossima scansione" in m for l, m in msgs), msgs
    assert any(p.startswith("Aggiungo alla libreria") for p in phases) and t.phase == "" and t.options["post_done"]


def _unlinked(tmp, name, member):
    ctx, calls, got, cfg = _ctx(tmp)
    z = tmp / "dl" / name
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(member, b"x" * 50)
    t = _task(tmp, name)
    t.options.pop("game_id")
    finish.run(t, Mgr(), ctx)
    return t, calls, cfg, z


def test_link_incollato_console_dalle_estensioni(tmp):
    t, calls, cfg, z = _unlinked(tmp, "Gioco.zip", "Gioco/Gioco [0100AAAA].xci")
    assert len(list(cfg.roms.rglob("*.xci"))) == 1 and calls and not z.exists()
    assert any("Console riconosciuta" in l["msg"] for l in t.log_after(0)[0])


def test_link_incollato_estensione_ambigua_non_indovina(tmp):
    t, calls, cfg, z = _unlinked(tmp, "Altro.zip", "Altro/Altro.iso")
    assert not calls and z.exists() and any("non capisco" in l["msg"] for l in t.log_after(0)[0])


def test_repack_pc_estratto_lascia_il_setup_da_avviare(tmp):
    """Il setup di un repack non entra in libreria: si avvia dal launcher (downloads/install.py)."""
    cfg = make_cfg(tmp)
    ctx, calls, got = make_ctx(cfg, online={"id": 7, "title": "Gioco PC", "key": "windows/net:7",
                                            "platform": "windows", "store": "online", "files": []})
    z = tmp / "dl" / "Repack.zip"
    z.parent.mkdir()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Repack/setup.exe", b"x")
        f.writestr("Repack/fg-01.bin", b"x")
    t = _task(tmp, "Repack.zip")
    finish.run(t, Mgr(), ctx)
    setup = Path(t.options["setup"]["exe"])
    assert setup.name == "setup.exe" and setup.is_file(), t.options
    assert not calls and z.exists()  # niente libreria, archivio tenuto finche' non si installa
    assert any("Repack pronto" in l["msg"] for l in t.log_after(0)[0])

