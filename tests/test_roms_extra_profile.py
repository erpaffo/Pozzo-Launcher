"""Cartelle ROM aggiuntive: quelle aggiunte da un profilo sono sue, un altro profilo non le vede nemmeno nell'elenco;
quelle globali (aggiunte prima dei profili) restano di tutti e si tolgono come prima. Nessuna rete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config, profilecfg as PC  # noqa: E402


def test_extra_roms_per_profilo(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    glob, mia, sua = tmp / "globale", tmp / "mia", tmp / "sua"
    for d in (glob, mia, sua):
        d.mkdir()
    cfg.extra_roms = [glob]
    app = create_app(cfg)
    pc, phone = TestClient(app), TestClient(app)
    pc.post("/api/profiles", json={"name": "Luca"})
    assert pc.post("/api/profiles/active", json={"id": "luca"}).status_code == 200
    assert phone.post("/api/profiles/active", json={"id": "default"}).status_code == 200

    add = lambda c, d: c.post("/api/roms/extra", json={"action": "add", "path": str(d)})  # noqa: E731
    paths = lambda r: {(x["path"], x["own"]) for x in r.json()["extra"]}  # noqa: E731

    r = add(pc, mia)
    assert paths(r) == {(str(glob), False), (str(mia.resolve()), True)}, "Luca vede la globale e la propria"
    r = add(phone, sua)
    assert paths(r) == {(str(glob), False), (str(sua.resolve()), True)}, "il Principale non vede la cartella di Luca"
    assert PC.values(cfg, "roms_extra") == {"luca": [str(mia.resolve())], "default": [str(sua.resolve())]}
    assert add(pc, mia).status_code == 400 and add(pc, glob).status_code == 400, "niente doppioni"
    # la globale salvata in forma non canonica (sui runner tmp e' un link o un nome corto): il doppione va riconosciuto
    cfg.extra_roms = [glob / ".." / glob.name]
    assert add(pc, glob).status_code == 400, "doppione con globale non normalizzata"
    cfg.extra_roms = [glob]

    r = pc.post("/api/roms/extra", json={"action": "remove", "path": str(mia.resolve())})
    assert paths(r) == {(str(glob), False)}
    assert not PC.values(cfg, "roms_extra").get("luca"), "tolta dalla lista di Luca"
    r = phone.post("/api/roms/extra", json={"action": "remove", "path": str(glob)})
    assert paths(r) == {(str(sua.resolve()), True)} and not cfg.extra_roms, "la globale si toglie come prima"
