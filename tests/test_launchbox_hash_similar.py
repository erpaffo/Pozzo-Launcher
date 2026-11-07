"""LaunchBox: titolo canonico del DAT (trovato per hash) prima del fuzzy; /api/similar/{id}. Nessuna rete."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config  # noqa: E402
from pozzo.bulk.launchbox import SCHEMA, INDEXES, LaunchBoxDB  # noqa: E402
from pozzo.matching import normalize  # noqa: E402


def _lb(tmp):
    lb = LaunchBoxDB(tmp)
    db = sqlite3.connect(lb.db_path)
    db.executescript(SCHEMA)
    db.execute("INSERT INTO games(id,pid,name,norm,rating_count) VALUES(1,'gba','Super Foo Adventure',?,5)",
               (normalize("Super Foo Adventure"),))
    db.executescript(INDEXES)
    db.commit()
    db.close()
    lb.meta_path.write_text("{}")
    return lb


def test_hash_title_prima_del_fuzzy(tmp_path):
    lb = _lb(tmp_path)
    assert lb.find("gba", ["zzz"], fuzzy=0) is None
    r = lb.find("gba", ["zzz"], fuzzy=0, hash_title="Super Foo Adventure (USA) (Rev 1)")
    assert r and r["id"] == 1, "il titolo del DAT perde tag regione/revisione"
    assert lb.find("gba", ["Super Foo Adventure"], fuzzy=0)["id"] == 1, "fallback per nome invariato"


def test_similar_per_gioco(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    c = TestClient(create_app(cfg))
    gid = c.get("/api/library?part=owned").json()["games"]["rows"][0][0]
    r = c.get(f"/api/similar/{gid}")
    assert r.status_code == 200
    assert all(i["reasons"] and "owned" in i and i["id"] != gid for i in r.json()["items"])
    assert c.get("/api/similar/999999").status_code == 404
