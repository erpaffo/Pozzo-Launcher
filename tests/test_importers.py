"""Importatori di libreria: file di esempio minuscoli, nessuna rete."""

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import importers as IMP  # noqa: E402
from pozzo.importers.formats import PARSERS  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402


@pytest.fixture
def env(tmp_path):
    user = UserData(tmp_path / "u.db")
    lib = SimpleNamespace(games=[{"key": "windows/steam:1", "title": "Half-Life", "store": "steam"},
                                 {"key": "snes/zelda.sfc", "title": "Zelda", "store": None}])
    return user, lib


def test_playnite(env, tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([{"Name": "Half Life", "Playtime": 3600, "Favorite": True, "Categories": [{"Name": "FPS"}]},
                             {"Name": "Sconosciuto"}]))
    user, lib = env
    r = IMP.apply(user, lib, PARSERS["playnite"](f))
    assert (r["matched"], r["skipped"], r["favorites"], r["playtime"], r["collections"]) == (1, 1, 1, 1, 1)
    g = user.games()["windows/steam:1"]
    assert g["favorite"] == 1 and g["playtime"] == 3600
    IMP.apply(user, lib, PARSERS["playnite"](f))  # secondo giro: non raddoppia
    assert user.games()["windows/steam:1"]["playtime"] == 3600


def test_launchbox_xml_e_playlist(tmp_path):
    d = tmp_path / "Data"
    (d / "Platforms").mkdir(parents=True)
    (d / "Playlists").mkdir()
    (d / "Platforms" / "SNES.xml").write_text("<LaunchBox><Game><Title>Zelda</Title><Favorite>true</Favorite>"
                                              "<PlayTime>120</PlayTime></Game></LaunchBox>")
    (d / "Playlists" / "a.xml").write_text("<LaunchBox><Playlist><Name>Classici</Name></Playlist>"
                                           "<PlaylistGame><GameTitle>Zelda</GameTitle></PlaylistGame></LaunchBox>")
    (r,) = PARSERS["launchbox"](tmp_path)
    assert r["favorite"] and r["playtime"] == 120 and r["collections"] == ["Classici"]


def test_launchbox_rifiuta_entita(tmp_path):
    f = tmp_path / "x.xml"
    f.write_text('<!DOCTYPE a [<!ENTITY e "boom">]><LaunchBox/>')
    with pytest.raises(IMP.ImportError_):
        PARSERS["launchbox"](f)


def test_lutris(tmp_path):
    f = tmp_path / "pga.db"
    db = sqlite3.connect(f)
    db.executescript("CREATE TABLE games(id INT, name TEXT, playtime REAL, lastplayed INT);"
                     "CREATE TABLE categories(id INT, name TEXT);CREATE TABLE games_categories(game_id INT, category_id INT);"
                     "INSERT INTO games VALUES(1,'Doom',2.0,100);INSERT INTO categories VALUES(1,'favorite'),(2,'Retro');"
                     "INSERT INTO games_categories VALUES(1,1),(1,2);")
    db.commit()
    db.close()
    (r,) = PARSERS["lutris"](f)
    assert r["playtime"] == 7200 and r["favorite"] and r["collections"] == ["Retro"]


def test_heroic(tmp_path):
    (tmp_path / "store_cache").mkdir()
    (tmp_path / "store_cache" / "legendary_library.json").write_text(json.dumps({"library": [{"app_name": "a1", "title": "Fortnite"}]}))
    (tmp_path / "timetracking.json").write_text(json.dumps({"a1": {"totalPlayed": 10, "lastPlayed": "2024-01-01T00:00:00Z"}}))
    (tmp_path / "favourites.json").write_text(json.dumps({"favourites": [{"appName": "a1"}]}))
    (r,) = PARSERS["heroic"](tmp_path)
    assert r["playtime"] == 600 and r["favorite"] and r["last_played"] > 0


def test_pegasus(tmp_path):
    f = tmp_path / "metadata.pegasus.txt"
    f.write_text("collection: SNES\nextension: sfc\n\ngame: Zelda\nfile: z.sfc\n\ngame: Mario\ncollections: SNES, Top\n")
    a, b = PARSERS["pegasus"](f)
    assert a["collections"] == ["SNES"] and b["collections"] == ["SNES", "Top"]


def test_limiti_e_percorsi(tmp_path, monkeypatch):
    big = tmp_path / "b.json"
    big.write_text("[]")
    monkeypatch.setattr(IMP, "MAX_BYTES", 1)
    with pytest.raises(IMP.ImportError_):
        PARSERS["playnite"](big)
    with pytest.raises(IMP.ImportError_):
        PARSERS["playnite"](tmp_path / ".." / "b.json")
    with pytest.raises(IMP.ImportError_):
        PARSERS["pegasus"](big)  # estensione sbagliata
