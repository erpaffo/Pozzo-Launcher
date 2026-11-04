"""Riprendi a giocare (/api/home/resume): 3 giochi piu' recenti, non nascosti, con tempo, HLTB e ultimo salvataggio.
Nessuna rete."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo.app.server import create_app  # noqa: E402
from pozzo.library import saves  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402

NOW = 1_800_000_000.0


@pytest.fixture
def client(tmp: Path, monkeypatch):
    import sqlite3

    rom = tmp / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    db = sqlite3.connect(tmp / "library.db")
    db.execute("UPDATE games SET hltb=? WHERE key=?", ('{"main": 10.0, "extra": 15.0}', "gba/AAA"))
    db.commit()
    db.close()
    ud = UserData(tmp / "userdata.db")  # stesso file che il server apre per il profilo predefinito
    ud.db.executemany("INSERT INTO user_games(key, last_played, playtime, hidden) VALUES(?, ?, ?, ?)", [
        ("gba/CCC", NOW - 50, 0, 0),        # il piu' recente, senza HLTB
        ("gba/AAA", NOW - 100, 600, 0),     # 600 s giocati su 10 ore di HLTB
        ("psp/DDD", NOW - 200, 900, 1),     # nascosto: escluso
        ("steam/42", NOW - 300, 0, 0),      # store PC, senza tempo
        ("gba/BBB", NOW - 400, 0, 0),       # quarto: escluso dal limite di 3
    ])
    ud.db.commit()
    ud.close()

    def fake_backups(cfg, key):  # niente cartelle di salvataggio vere: solo AAA ha una copia, steam da' errore
        if key == "steam/42":
            raise OSError("cartella mancante")
        if key == "gba/AAA":
            return [{"name": "nuovo", "time": NOW - 10}, {"name": "vecchio", "time": NOW - 900}]
        return []

    monkeypatch.setattr(saves, "list_backups", fake_backups)
    with TestClient(create_app(tmp_cfg(tmp, rom)), base_url=BASE) as c:
        yield c


def test_riprendi_tre_piu_recenti(client):
    items = client.get("/api/home/resume").json()["items"]
    assert [i["key"] for i in items] == ["gba/CCC", "gba/AAA", "steam/42"]
    cccc, aaa, steam = items
    assert set(cccc) == {"id", "key", "title", "platform", "cover", "played_secs", "hltb_main_secs",
                         "remaining_secs", "last_played", "save"}
    assert cccc["cover"] == f"/img/{cccc['id']}/cover"
    assert cccc["hltb_main_secs"] is None and cccc["remaining_secs"] is None and cccc["save"] is None
    assert aaa["played_secs"] == 600 and aaa["hltb_main_secs"] == 36000 and aaa["remaining_secs"] == 35400
    assert aaa["last_played"] == NOW - 100
    assert aaa["save"] == {"time": NOW - 10, "name": "nuovo"}
    assert steam["save"] is None and steam["played_secs"] == 0

