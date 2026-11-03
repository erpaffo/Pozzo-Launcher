"""Immagini scelte a mano: vista per tipo, file dal PC, ritorno all'originale, copertina visibile nella griglia
anche per i giochi senza copertina dalle fonti (es. Hearthstone da Battle.net)."""
import io
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo.app.server import create_app  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def client(tmp: Path):
    rom = tmp / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    db = sqlite3.connect(tmp / "library.db")  # gioco di uno store senza nessuna immagine dalle fonti
    db.execute("INSERT INTO games(key, platform, title, sort_title, genres, files, media, found, grp, is_primary, origin, "
               "store, installed) VALUES('windows/battlenet:hs_beta', 'windows', 'Hearthstone', 'hearthstone', '[]', '[]', "
               "'{}', 1, 'windows/s:hs', 1, '{}', 'battlenet', 1)")
    db.commit()
    db.close()
    with TestClient(create_app(tmp_cfg(tmp, rom)), base_url=BASE) as c:
        yield c


def _hs(c):
    lib = c.get("/api/library").json()
    cols = lib["games"]["cols"]
    row = next(r for r in lib["games"]["rows"] if r[cols.index("title")] == "Hearthstone")
    return row[cols.index("id")], bool(row[cols.index("cover")])


def test_copertina_dal_pc_visibile_e_ripristinabile(client):
    gid, has = _hs(client)
    assert not has
    kinds = {k["kind"]: k for k in client.get(f"/api/game/{gid}/media").json()["kinds"]}
    assert not kinds["cover"]["source"] and not kinds["cover"]["custom"] and kinds["cover"]["url"] is None

    r = client.post(f"/api/game/{gid}/media/cover/file", files={"file": ("c.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 200, r.text
    assert next(k for k in r.json()["kinds"] if k["kind"] == "cover")["custom"]
    assert _hs(client)[1], "la griglia deve chiedere la copertina scelta a mano"
    assert client.get(f"/img/{gid}/cover").content[:4] == b"\x89PNG"

    r = client.delete(f"/api/game/{gid}/media/cover")
    assert r.status_code == 200 and not next(k for k in r.json()["kinds"] if k["kind"] == "cover")["custom"]
    assert not _hs(client)[1]


def test_file_non_immagine_e_tipo_sconosciuto_rifiutati(client):
    gid, _ = _hs(client)
    r = client.post(f"/api/game/{gid}/media/cover/file", files={"file": ("x.png", io.BytesIO(b"<html>no</html>"), "image/png")})
    assert r.status_code == 400
    r = client.post(f"/api/game/{gid}/media/boh/file", files={"file": ("c.png", io.BytesIO(PNG), "image/png")})
    assert r.status_code == 400
    assert client.delete(f"/api/game/{gid}/media/boh").status_code == 400
