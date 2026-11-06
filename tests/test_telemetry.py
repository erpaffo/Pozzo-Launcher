"""Registro errori locale: ring buffer, mascheratura percorsi, clear, export, endpoint.

Esegui: PYTHONUTF8=1 python tests/test_telemetry.py   (o pytest)
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import telemetry as T  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    T.set_path(None)
    T.clear()
    yield
    T.set_path(None)
    T.clear()


def test_ring_buffer_max_50():
    for i in range(60):
        T.log_error("m", f"e{i}")
    r = T.recent()
    assert len(r) == 50 and r[0]["message"] == "e10" and r[-1]["message"] == "e59"


def test_mask():
    assert T.mask("C:\\Users\\mario\\x\\y.py") == "~\\x\\y.py"
    assert T.mask("c:/users/mario/x") == "~/x"
    assert T.mask("/home/mario/x /Users/luca/y") == "~/x ~/y"
    assert T.mask("nessun percorso") == "nessun percorso"


def test_log_file_clear_export(tmp: Path):
    log = tmp / "sub" / "errors.log"
    T.set_path(log)
    T.log_error("scan", "boom", "File C:\\Users\\mario\\a.py")
    assert log.read_text(encoding="utf-8").count("\n") == 1
    rep = T.export_report()
    assert "boom" in rep and "mario" not in rep
    T.clear()
    assert T.recent() == [] and log.read_text(encoding="utf-8") == ""


def test_unwritable_path_never_raises(tmp: Path):
    T.set_path(tmp)  # una cartella: l'append fallisce
    T.log_error("m", "x")
    T.clear()
    assert T.recent() == []


def test_endpoints(tmp: Path):
    rom = tmp / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    with TestClient(create_app(tmp_cfg(tmp, rom)), base_url=BASE) as c:
        T.log_error("m", "ciao", "C:\\Users\\mario\\z")
        assert [e["message"] for e in c.get("/api/system/errors").json()["errors"]] == ["ciao"]
        exp = c.get("/api/system/errors/export")
        assert exp.status_code == 200 and "ciao" in exp.text and "mario" not in exp.text
        assert c.post("/api/system/errors/clear").json() == {"ok": True}
        assert c.get("/api/system/errors").json()["errors"] == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
