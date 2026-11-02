"""/api/game/{id}/verify e /api/verify/report: stato del dump salvato in library.db alla costruzione.
Libreria di prova, nessuna rete."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config  # noqa: E402


def test_rotte_verifica(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)

    c = TestClient(create_app(cfg))  # ROM non ancora confrontata col DAT: stato vuoto, niente badge
    gid = c.get("/api/library?part=owned").json()["games"]["rows"][0][0]
    assert c.get(f"/api/game/{gid}/verify").json() == {"status": "", "match_by": ""}
    assert c.get("/api/game/999999/verify").status_code == 404

    db = sqlite3.connect(tmp / "library.db")
    db.execute("UPDATE games SET verify='sconosciuta', match_by='name'")
    db.commit()
    db.close()
    c = TestClient(create_app(cfg))
    assert c.get(f"/api/game/{gid}/verify").json() == {"status": "sconosciuta", "match_by": "name"}
    rep = c.get("/api/verify/report?console=gba").json()
    n = rep["total"]
    assert n >= 1 and rep["counts"] == {"sconosciuta": n} and gid in {x["id"] for x in rep["unverified"]}
    assert c.get("/api/verify/report?console=snes").json()["total"] == 0
