"""Tappe «pronto a giocare»: stati, ready_eta, salvataggio."""
import json
import time

from pozzo.downloads import task as T
from pozzo.downloads.task import COMPLETED, RUNNING, DownloadTask


def mk(name="Gioco.zip", **kw):
    return DownloadTask(source="https://x.test/f", save_path="/tmp", name=name, **kw)


def states(t):
    return {s["id"]: s["state"] for s in t.view()["stages"]}


def test_archive_flow():
    t = mk(status=RUNNING, size=1000, done=500)
    v = t.view()
    assert [s["id"] for s in v["stages"]] == ["download", "extract", "library", "data"]
    assert v["stages"][0]["state"] == "active" and v["stages"][0]["pct"] == 50
    assert not v["ready"] and v["ready_eta"] is None  # velocita' ignota
    t.status = COMPLETED
    assert states(t)["download"] == "done"
    t.set_stage("extract", "active", 40)
    assert t.view()["stages"][1]["pct"] == 40
    t.set_stage("extract", "done")
    t.set_stage("library", "done")
    t.set_stage("data", "done")
    v = t.view()
    assert v["ready"] and v["ready_eta"] is None


def test_non_archive_skips_extract():
    assert states(mk("Gioco.nsp"))["extract"] == "skip"
    assert states(mk("Gioco.7z"))["extract"] == "todo"


def test_ready_eta_math(monkeypatch):
    monkeypatch.setattr(T, "_RATES", [])
    monkeypatch.setattr(T, "RATE_FILE", None)
    mb = 1048576
    t = mk(status=RUNNING, size=400 * mb, done=200 * mb, speed=10 * mb)  # 20 s di scarico
    now = time.time()
    eta = t.view()["ready_eta"]
    assert abs(eta - (now + 20 + 400 / 40 + 20 + 20)) < 2  # + estrazione a 40 MB/s + libreria + dati
    T.record_extract(100 * mb, 1)  # 100 MB/s misurati
    assert abs(t.view()["ready_eta"] - (time.time() + 20 + 4 + 40)) < 2
    t.set_stage("extract", "skip")
    assert abs(t.view()["ready_eta"] - (time.time() + 20 + 40)) < 2


def test_persistence_round_trip():
    t = mk(status=COMPLETED, size=10)
    t.set_stage("extract", "done")
    t.set_stage("library", "active")
    back = DownloadTask(**json.loads(json.dumps(t.data())))
    assert states(back) == {"download": "done", "extract": "done", "library": "active", "data": "todo"}


def test_rate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "_RATES", [])
    monkeypatch.setattr(T, "RATE_FILE", tmp_path / "r.json")
    T.record_extract(50, 1)
    monkeypatch.setattr(T, "_RATES", [])
    assert T.extract_rate() == 50


def test_note_and_eta_unknown():
    t = mk(type="torrent", status=T.QUEUED)
    assert t.view()["ready_eta"] is None  # niente velocita' ne' dimensione
    t.set_stage("library", "active", note="In attesa della scansione")
    assert t.view()["stages"][2]["note"] == "In attesa della scansione" and not t.ready
    t.set_stage("library", "done")
    assert "note" not in t.view()["stages"][2] and t.ready


def test_mark_ready_needs_game(tmp_path):
    from types import SimpleNamespace
    from pozzo.downloads.manager import Manager
    m = Manager(SimpleNamespace(cache=str(tmp_path), app={}))
    t = mk(status=COMPLETED, options={"pending_files": [str(tmp_path / "g.iso")]})
    m.tasks[t.id] = t
    t.set_stage("library", "active")
    import threading
    lib = SimpleNamespace(lock=threading.Lock(), games=[])
    sent = []
    m.ctx = SimpleNamespace(lib=lib, events=SimpleNamespace(emit=lambda n, d: sent.append((n, d))))
    assert not m.mark_ready(t.id) and not t.ready
    lib.games.append({"id": 7, "title": "G", "key": "g", "files": [str(tmp_path / "g.iso")]})
    assert m.mark_ready(t.id) and t.ready and states(t)["data"] == "done"
    assert [(n, d["game_id"]) for n, d in sent] == [("game_downloaded", 7)]  # webhook download_finito
    assert not m.mark_ready(t.id) and len(sent) == 1, "una volta sola"
