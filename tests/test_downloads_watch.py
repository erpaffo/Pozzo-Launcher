"""Cartella sorvegliata dei .torrent: aggiunti una volta sola e rinominati in .added; doppioni, file a meta' e cartella
sparita non rompono ne' bloccano il ciclo. Nessuna rete."""
import logging
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

lt = pytest.importorskip("libtorrent")

from pozzo import net  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "max_active": 0, **dl}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _torrent(path: Path, seed: bytes = b"a", old=True) -> Path:
    src = path.parent / f"src-{path.stem}"
    src.mkdir(exist_ok=True)
    (src / "f.bin").write_bytes(seed * 40000)
    ct = lt.create_torrent(lt.list_files(str(src)), 16384)
    lt.set_piece_hashes(ct, str(src.parent))
    path.write_bytes(lt.bencode(ct.generate()))
    if old:  # oltre WATCH_QUIET: la copia e' finita
        os.utime(path, (time.time() - 60, time.time() - 60))
    return path


def test_torrent_nella_cartella_si_aggiunge_una_volta(tmp):
    w = tmp / "watch"
    w.mkdir()
    m = _mgr(tmp, watch_dir=str(w))
    f = _torrent(w / "gioco.torrent")
    assert m.watch_check(str(w)) == 1 and len(m.tasks) == 1
    assert not f.exists() and (w / "gioco.torrent.added").is_file()
    t = next(iter(m.tasks.values()))
    assert Path(t.source).is_file() and Path(t.source).parent == m.uploads  # la copia, non il file rinominato
    assert m.watch_check(str(w)) == 0 and len(m.tasks) == 1


def test_doppione_rinominato_e_non_aggiunto(tmp):
    w = tmp / "watch"
    w.mkdir()
    m = _mgr(tmp)
    a = _torrent(w / "a.torrent")
    m.watch_check(str(w))
    b = w / "b.torrent"
    b.write_bytes((w / "a.torrent.added").read_bytes())
    os.utime(b, (time.time() - 60, time.time() - 60))
    assert m.watch_check(str(w)) == 0 and len(m.tasks) == 1
    assert not b.exists() and (w / "b.torrent.added").is_file() and not a.exists()
    assert len(list(m.uploads.glob("*.torrent"))) == 1  # la copia del doppione e' stata tolta


def test_file_a_meta_o_non_valido_resta_e_si_logga_una_volta(tmp, caplog):
    w = tmp / "watch"
    w.mkdir()
    m = _mgr(tmp)
    bad = w / "rotto.torrent"
    bad.write_bytes(b"d4:infod")
    os.utime(bad, (time.time() - 60, time.time() - 60))
    new = _torrent(w / "nuovo.torrent", b"b", old=False)  # appena scritto: si aspetta
    with caplog.at_level(logging.WARNING, logger="pozzo.downloads"):
        for _ in range(3):
            assert m.watch_check(str(w)) == 0
    assert bad.exists() and new.exists() and not m.tasks
    assert len([r for r in caplog.records if "rotto.torrent" in r.getMessage()]) == 1
    os.utime(new, (time.time() - 60, time.time() - 60))  # ora e' fermo
    assert m.watch_check(str(w)) == 1 and bad.exists()


def test_cartella_mancante_non_solleva_e_non_blocca_il_ciclo(tmp):
    m = _mgr(tmp)
    assert m.watch_check(str(tmp / "non-c-e")) == 0
    # una cartella lenta (disco di rete) tiene occupato solo il thread dl-watch: il tick torna subito
    go = threading.Event()
    m.watch_check = lambda folder: go.wait(5) and 0
    m.cfg.app["downloads"]["watch_dir"] = str(tmp)
    t0 = time.monotonic()
    m._tick()
    assert time.monotonic() - t0 < 2 and m._watch_run
    m._tick()  # un solo controllo alla volta
    go.set()
    for _ in range(100):
        if not m._watch_run:
            break
        time.sleep(0.05)
    assert not m._watch_run


def test_impostazione_vuota_non_fa_nulla(tmp):
    w = tmp / "watch"
    w.mkdir()
    _torrent(w / "a.torrent")
    m = _mgr(tmp)
    seen = []
    m.watch_check = lambda folder: seen.append(folder)
    m._tick()
    assert not seen and not m._watch_run and (w / "a.torrent").is_file()
    assert m.update_settings({"watch_dir": ""})["watch_dir"] == "" and m.settings()["watch_dir"] == ""
