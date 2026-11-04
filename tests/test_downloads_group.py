"""Gruppo di una voce della coda: base, aggiornamenti e DLC dello stesso gioco hanno la stessa chiave. Nessuna rete."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402


def _mgr(tmp):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


def _add(m, name, tmp):
    return m.add(f"https://example.com/files/{name.replace(' ', '%20')}.zip", str(tmp / "out"), name=name)


def test_gioco_aggiornamento_e_dlc_condividono_il_gruppo(tmp):
    m = _mgr(tmp)
    base = _add(m, "Game", tmp)
    upd = _add(m, "Game Update v1.0.2", tmp)
    dlc = _add(m, "Game DLC Pack", tmp)
    other = _add(m, "Unrelated Title", tmp)
    assert (base.kind, upd.kind, dlc.kind, other.kind) == ("base", "update", "dlc", "base")
    assert base.group == upd.group == dlc.group == "game"
    assert base.group_title == upd.group_title == dlc.group_title == "Game"
    assert other.group == "unrelatedtitle"  # da solo, non si aggancia a «Game»


def test_vista_e_salvataggio_portano_i_campi(tmp):
    m = _mgr(tmp)
    t = _add(m, "Game DLC Pack", tmp)
    v = t.view()
    assert {v["kind"], v["group"], v["group_title"]} == {"dlc", "game", "Game"}
    saved = m.store.load()
    assert [(s.kind, s.group) for s in saved if s.id == t.id] == [("dlc", "game")]


def test_titolo_dalla_sorgente_senza_nome(tmp):
    t = T.DownloadTask(source="https://example.com/a/Game%20Update%20v2.0.zip", save_path=str(tmp))
    t.classify()
    assert (t.kind, t.group) == ("update", "game")
    mag = T.DownloadTask(source="magnet:?xt=urn:btih:abc&dn=Game+DLC+Pack", save_path=str(tmp))
    mag.classify()
    assert (mag.kind, mag.group_title) == ("dlc", "Game")


def test_senza_titolo_nessun_gruppo(tmp):
    t = T.DownloadTask(source="https://example.com/", save_path=str(tmp))
    t.classify()
    assert (t.group, t.group_title) == ("", "")
