"""Installazione dei repack: setup riconosciuto, avvio, gioco trovato a fine installazione. Nessun vero installer."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from pozzo.downloads import install  # noqa: E402
from pozzo.downloads.task import COMPLETED, DownloadTask  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_runs():
    """Le installazioni restano in memoria finche' il launcher e' aperto: un test non deve sporcare il successivo."""
    install._RUNS.clear()
    yield
    install._RUNS.clear()


def test_find_setup_il_piu_in_alto_e_niente_disinstallatori(tmp):
    (tmp / "repack" / "redist").mkdir(parents=True)
    setup = tmp / "repack" / "setup.exe"
    setup.write_bytes(b"x")
    (tmp / "repack" / "redist" / "dxsetup.exe").write_bytes(b"x")
    (tmp / "repack" / "unins000.exe").write_bytes(b"x")
    (tmp / "repack" / "fg-01.bin").write_bytes(b"x")
    files = [p for p in tmp.rglob("*") if p.is_file()]
    assert install.find_setup(files) == setup


def test_find_setup_senza_setup(tmp):
    (tmp / "gioco.exe").write_bytes(b"x")
    assert install.find_setup(list(tmp.rglob("*"))) is None


def test_detect_usa_le_app_installate_nuove(monkeypatch, tmp):
    game = tmp / "Program Files" / "Gioco" / "gioco.exe"
    game.parent.mkdir(parents=True)
    game.write_bytes(b"x")
    apps = {"Vecchio": {"DisplayName": "Vecchio", "InstallLocation": str(tmp)}}
    monkeypatch.setattr(install, "_registry_apps", lambda: {**apps, "Gioco": {"DisplayName": "Gioco", "InstallLocation": str(game.parent)}})
    monkeypatch.setattr(install, "_listing", lambda: set())
    assert install.detect({"apps": apps, "dirs": []}) == {"title": "Gioco", "exe": game}


def test_detect_cartella_nuova_se_il_repack_non_si_registra(monkeypatch, tmp):
    folder = tmp / "Program Files" / "Gioco"
    folder.mkdir(parents=True)
    (folder / "gioco.exe").write_bytes(b"xx")
    (folder / "unins000.exe").write_bytes(b"x")
    monkeypatch.setattr(install, "_registry_apps", lambda: {})
    monkeypatch.setattr(install, "_listing", lambda: {str(folder)})
    assert install.detect({"apps": {}, "dirs": []}) == {"title": "Gioco", "exe": folder / "gioco.exe"}


def test_detect_niente_di_nuovo(monkeypatch):
    monkeypatch.setattr(install, "_registry_apps", lambda: {"Gia'": {"DisplayName": "Gia'", "InstallLocation": ""}})
    monkeypatch.setattr(install, "_listing", lambda: set())
    assert install.detect({"apps": {"Gia'": {}}, "dirs": []}) is None


class User:
    def __init__(self):
        self.added = []

    def add_manual(self, title, exe, args, cwd="", kind="game", meta=None):
        self.added.append((title, exe))
        return 7


def _task(tmp):
    setup = tmp / "dl" / "setup.exe"
    setup.parent.mkdir(parents=True)
    setup.write_bytes(b"x")
    return DownloadTask(source="https://x/repack", save_path=str(tmp / "dl"), name="Gioco", status=COMPLETED,
                        options={"setup": {"exe": str(setup), "dir": str(setup.parent)}})


def _row(tid):
    return next(r for r in install.rows() if r["id"] == tid)


def _wait(tid):
    for _ in range(200):
        if _row(tid)["status"] != "running":
            return _row(tid)
        time.sleep(0.02)
    return _row(tid)


def test_installazione_finita_mette_il_gioco_in_libreria(monkeypatch, tmp):
    t = _task(tmp)
    refreshed = []
    ctx = SimpleNamespace(lib=None, user=User(), _refresh_manual=refreshed.append)
    mgr = SimpleNamespace(_poke=lambda: None, store=SimpleNamespace(save=lambda ts: None))
    exe = tmp / "Program Files" / "Gioco" / "gioco.exe"
    monkeypatch.setattr(install, "_snapshot", lambda: {"apps": {}, "dirs": []})
    monkeypatch.setattr(install, "_launch", lambda e: 0)
    monkeypatch.setattr(install, "detect", lambda before: {"title": "Gioco installato", "exe": exe})
    install.start(t, mgr, ctx)
    row = _wait(t.id)
    assert ctx.user.added == [("Gioco", str(exe))] and refreshed == [7], ctx.user.added
    assert row["status"] == "done" and t.options["setup"]["installed"] and row["finished"]


def test_installazione_senza_gioco_riconosciuto(monkeypatch, tmp):
    t = _task(tmp)
    ctx = SimpleNamespace(lib=None, user=User(), _refresh_manual=None)
    mgr = SimpleNamespace(_poke=lambda: None, store=SimpleNamespace(save=lambda ts: None))
    monkeypatch.setattr(install, "_snapshot", lambda: {"apps": {}, "dirs": []})
    monkeypatch.setattr(install, "_launch", lambda e: 0)
    monkeypatch.setattr(install, "detect", lambda before: None)
    install.start(t, mgr, ctx)
    assert _wait(t.id)["status"] == "error" and not ctx.user.added



def test_senza_setup_non_parte(tmp):
    t = DownloadTask(source="https://x/a", save_path=str(tmp), name="a", status=COMPLETED, options={})
    try:
        install.start(t, SimpleNamespace(_poke=lambda: None, store=SimpleNamespace(save=lambda ts: None)), SimpleNamespace())
    except ValueError as e:
        assert "Nessun setup" in str(e)
    else:
        raise AssertionError("doveva rifiutare")
