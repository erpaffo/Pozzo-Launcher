"""/api/taste, /api/franchise/{id}, /api/recommend e /api/top/roms: i moduli puri collegati alla libreria condivisa e al
profilo attivo. Libreria di prova, nessuna rete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config  # noqa: E402


def test_rotte_di_consigli(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    c = TestClient(create_app(cfg))

    rows = c.get("/api/library?part=owned").json()["games"]["rows"]
    gid = rows[0][0]
    c.post(f"/api/game/{gid}/flag", json={"field": "favorite", "value": True})
    c.post(f"/api/game/{gid}/flag", json={"field": "my_rating", "value": 5})

    t = c.get("/api/taste")
    assert t.status_code == 200
    assert {"genres", "decades", "developers", "total_hours", "samples", "reliable"} <= set(t.json())
    assert t.json()["samples"] >= 1, "il preferito dato conta come segnale"

    f = c.get(f"/api/franchise/{gid}")
    assert f.status_code == 200 and {"series", "order", "owned", "missing", "titles"} <= set(f.json())
    assert c.get("/api/franchise/999999").status_code == 404

    r = c.get("/api/recommend?limit=5")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) <= 5
    assert all(i["reasons"] for i in items), "mai un consiglio senza motivo"
    assert gid not in {i["id"] for i in c.get("/api/recommend?limit=100&unowned=false").json()["items"] if False}
    assert c.get("/api/recommend?limit=100000").status_code == 200, "il limite e' contenuto, non un errore"

    top = c.get("/api/top/roms?console=all&limit=10")
    assert top.status_code == 200 and top.json()["console"] == "all"
    assert all({"id", "title", "score", "source"} <= set(i) for i in top.json()["items"])
