"""Job degli strumenti e adozione del file prodotto."""
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.tools import adopt as A, jobs as J, space, trash

tmp = Path(tempfile.mkdtemp())


def wait(jid):
    for _ in range(100):
        if J.JOBS[jid]["status"] != "running":
            return J.JOBS[jid]
        time.sleep(0.05)
    raise SystemExit("job bloccato")


def slow(s, d, pr, c, o):
    c.wait(2)
    raise InterruptedError()


try:
    src = tmp / "g.iso"
    src.write_bytes(b"x" * 100)

    def run(s, d, progress, cancel, o):
        progress(50)
        o = d / "g.chd"
        o.write_bytes(b"y" * 40)
        return o

    J.register(J.Tool("t", "T", lambda p, f: f.suffix == ".iso", lambda s, o: s.stat().st_size, run))
    assert J.available("psx", src) == ["t"] and J.available("psx", tmp / "a.bin") == []
    j = wait(J.start("t", src)["id"])
    assert j["status"] == "done" and Path(j["out"]).exists() and "_cancel" not in J.public(j)

    # spazio insufficiente: rifiutato PRIMA di partire e il lock resta libero
    J.register(J.Tool("big", "B", lambda p, f: True, lambda s, o: 10**18, run))
    try:
        J.start("big", src)
        raise SystemExit("doveva rifiutare")
    except space.NoSpace:
        pass
    # occupato + annullamento
    J.register(J.Tool("slow", "S", lambda p, f: True, lambda s, o: 1, slow))
    sj = J.start("slow", src)
    try:
        J.start("t", src)
        raise SystemExit("doveva essere occupato")
    except J.Busy:
        pass
    assert J.cancel(sj["id"]) and wait(sj["id"])["status"] == "cancelled"
    J.register(J.Tool("info", "I", lambda p, f: True, lambda s, o: 0, lambda s, d, pr, c, o: {"ok": o.get("x")}))
    ij = wait(J.start("info", src, options={"x": 7})["id"])
    assert ij["result"] == {"ok": 7} and ij["out"] is None
    J.register(J.Tool("err", "E", lambda p, f: True, lambda s, o: 1, lambda *a: 1 / 0))
    assert wait(J.start("err", src)["id"])["status"] == "error"

    # adopt: dati spostati alla nuova chiave, originale in .pozzo-trash solo se richiesto
    cache = tmp / "cache"
    cache.mkdir()
    old, new = tmp / "Gioco.iso", tmp / "Gioco.chd"
    old.write_bytes(b"a" * 10)
    new.write_bytes(b"b" * 5)
    db = sqlite3.connect(cache / "library.db")
    db.execute("CREATE TABLE games(key TEXT, platform TEXT, title TEXT, files TEXT, size INT, store TEXT)")
    db.execute("INSERT INTO games VALUES('OLD','psx','Gioco',?,10,NULL)", (json.dumps([str(old)]),))
    db.commit()
    db.close()
    cfg = SimpleNamespace(cache=cache)
    with mock.patch.object(A.RL, "apply") as ap, \
         mock.patch.object(trash, "_fixed_drive", return_value=False), \
         mock.patch.object(trash.Path, "anchor", new_callable=mock.PropertyMock, return_value=str(tmp)):
        r = A.adopt(cfg, "psx", old, new, move_old=False)
        assert r == {"relinked": True, "trashed": None} and old.exists()
        pair = ap.call_args[0][1][0]
        assert pair[0] == "OLD" and pair[1] != "OLD"
        r = A.adopt(cfg, "psx", old, new, move_old=True)
        assert not old.exists() and Path(r["trashed"]).exists()
    try:
        A.adopt(cfg, "psx", new, tmp / "manca.chd", True)
        raise SystemExit("doveva fallire")
    except ValueError:
        assert new.exists()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok")
