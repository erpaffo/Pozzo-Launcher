"""Siti di mod per i titoli famosi: tabella curata, corrispondenza per titolo e console, rotta. Nessuna rete."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config, modsites  # noqa: E402
from pozzo import platforms as P  # noqa: E402


def test_dati_validi():
    t = modsites._table()
    for sid, site in t["sites"].items():
        assert site["search"].startswith("https://") and "{q}" in site["search"], sid
    for g in t["games"]:
        assert g["aliases"] and g["sites"], g["name"]
        assert all(p in P.PLATFORMS for p in g["platforms"]), f"console sconosciuta in {g['name']}"
        for s in g["sites"]:
            sid, url = (s, "x") if isinstance(s, str) else (s["site"], s["url"])
            assert sid in t["sites"] and url.startswith(("x", "https://")), g["name"]


def test_corrispondenza():
    smash = modsites.sites_for("Super Smash Bros. Ultimate (USA)", platform="switch")
    assert [s["site"] for s in smash] == ["gamebanana"]
    assert "Super+Smash+Bros.+Ultimate" in smash[0]["url"]
    assert modsites.sites_for("Super Smash Bros. Ultimate", platform="wii") == [], "stessa console o niente"
    assert modsites.sites_for("The Elder Scrolls V: Skyrim Special Edition", platform="windows")[0]["site"] == "nexusmods"
    assert modsites.sites_for("Pokémon FireRed Version (USA)", platform="gba")[0]["site"] == "romhacking"
    assert modsites.sites_for("Un gioco qualunque", platform="switch") == []
    assert modsites.sites_for("Doomsday Hunters", platform="windows") == [], "l'alias deve finire a parola intera"
    assert modsites.sites_for("", "Super Mario 64", platform="n64")[0]["site"] == "romhacking", "vale anche il nome del DAT"
    valheim = modsites.sites_for("Valheim", platform="windows")
    assert valheim[1]["url"] == "https://thunderstore.io/c/valheim/", "indirizzo fisso al posto della ricerca"


def test_rotta(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    db = sqlite3.connect(tmp / "library.db")
    db.execute("UPDATE games SET title='Super Smash Bros. Ultimate', platform='switch' WHERE id=(SELECT MIN(id) FROM games)")
    db.commit()
    gid = db.execute("SELECT MIN(id) FROM games").fetchone()[0]
    other = db.execute("SELECT MAX(id) FROM games").fetchone()[0]
    db.close()
    c = TestClient(create_app(cfg))
    assert [s["name"] for s in c.get(f"/api/game/{gid}/mod-sites").json()["sites"]] == ["GameBanana"]
    assert c.get(f"/api/game/{other}/mod-sites").json() == {"sites": []}
    assert c.get("/api/game/999999/mod-sites").status_code == 404
