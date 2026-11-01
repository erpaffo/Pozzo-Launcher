"""Registro delle fasi di avvio (pozzo/boot.py) e GET /api/boot: transizioni, ready, errore che non blocca.

Nessuna rete. Esegui: python tests/test_boot.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo.boot import BOOT, Registro, registro  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402


def _states(snap):
    return {s["id"]: s["state"] for s in snap["steps"]}


def test_transizioni_e_ready():
    r = Registro([("a", "Uno"), ("b", "Due")])
    snap = r.snapshot()
    assert snap["ready"] is False and snap["progress"] == 0 and _states(snap) == {"a": "pending", "b": "pending"}
    assert snap["steps"][0] == {"id": "a", "label": "Uno", "state": "pending"}, "forma dei passi"

    r.start("a")
    assert _states(r.snapshot())["a"] == "running"
    r.done("a")
    snap = r.snapshot()
    assert snap["progress"] == 0.5 and snap["ready"] is False

    r.start("b", "Due bis")
    r.done("b")
    snap = r.snapshot()
    assert snap["ready"] is True and snap["progress"] == 1.0
    assert snap["steps"][1]["label"] == "Due bis", "start con etichetta la aggiorna"
    print("ok  transizioni pending -> running -> done, ready e progresso")


def test_error_non_blocca_ready():
    r = Registro([("a", "Uno"), ("b", "Due")])
    r.start("a")
    r.fail("a", "rotto")
    snap = r.snapshot()
    assert _states(snap)["a"] == "error" and snap["ready"] is False, "ancora una fase in attesa"
    r.done("b")
    snap = r.snapshot()
    assert snap["ready"] is True and snap["progress"] == 1.0, "error conta come conclusa"
    print("ok  error: conta come conclusa e non tiene ready a falso")


def test_phase_context():
    r = Registro([("a", "Uno"), ("b", "Due")])
    with r.phase("a"):
        assert _states(r.snapshot())["a"] == "running"
    assert _states(r.snapshot())["a"] == "done"
    try:
        with r.phase("b", "Due"):
            raise OSError("disco pieno")
    except OSError:
        pass
    else:
        raise AssertionError("l'eccezione deve risalire")
    snap = r.snapshot()
    assert _states(snap)["b"] == "error" and snap["ready"] is True
    print("ok  with phase(): done a fine blocco, error e rilancio dell'eccezione")


def test_thread_safe():
    r = Registro([(f"f{i}", str(i)) for i in range(50)])

    def lavora(i):
        r.start(f"f{i}")
        r.done(f"f{i}")
    ts = [threading.Thread(target=lavora, args=(i,)) for i in range(50)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert r.snapshot()["ready"] is True
    print("ok  thread-safe: 50 fasi in parallelo")


def test_registro_lavoro_e_reset():
    a = registro("install-test-x")
    assert a is registro("install-test-x"), "stesso registro per stesso nome"
    a.start("download", "Scarico")
    assert registro("install-test-y").snapshot()["steps"] == [], "lavori separati"
    BOOT.reset()
    assert all(s["state"] == "pending" for s in BOOT.snapshot()["steps"])
    print("ok  registro dei lavori e reset")


def test_api_boot(tmp: Path):
    (tmp / "config.toml").write_text(f'[paths]\nroms = "{(tmp / "roms").as_posix()}"\ncache = "{(tmp / "cache").as_posix()}"\n',
                                     encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    app = create_app(cfg)  # senza "with": gli eventi di avvio non partono, le fasi sincrone sì
    snap = TestClient(app).get("/api/boot").json()
    assert set(snap) == {"ready", "progress", "steps"}, snap
    ids = [s["id"] for s in snap["steps"]]
    assert ids == ["server", "config", "library", "stores", "extensions"], ids
    assert all(s["state"] == "done" for s in snap["steps"]) and snap["ready"] is True, snap
    print("ok  GET /api/boot: fasi reali dell'avvio, tutte done")


def main():
    test_transizioni_e_ready()
    test_error_non_blocca_ready()
    test_phase_context()
    test_thread_safe()
    test_registro_lavoro_e_reset()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_api_boot(Path(t))
    print("TUTTI I TEST OK")


if __name__ == "__main__":
    main()
