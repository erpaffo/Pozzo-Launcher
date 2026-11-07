"""Gioca nel browser: mappa console -> core, la ROM si serve solo se e' di un gioco in libreria, salvataggi nel
database dell'utente e cancello del telefono. Nessuna rete: il download di EmulatorJS/Ruffle non viene toccato."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_phone_extras import close, client, make_cfg, paired_gate, teardown_function  # noqa: E402,F401

from pozzo import platforms as P, webplay as W  # noqa: E402


def game(gid, platform, files, **kw):
    return {"id": gid, "key": f"k{gid}", "platform": platform, "title": f"Gioco {gid}", "files": [str(f) for f in files],
            "store": None, **kw}


def test_mappa_core():
    assert set(W.CORES) <= set(P.PLATFORMS)
    assert W.CORES["nes"] == ("nes", "fceumm") and W.CORES["snes"][1] == "snes9x"
    assert W.CORES["gb"] == W.CORES["gbc"] == ("gb", "gambatte") and W.CORES["gba"][1] == "mgba"
    assert W.CORES["megadrive"][1] == "genesis_plus_gx" and W.CORES["psx"][1] == "pcsx_rearmed"
    assert W.plan(game(1, "nes", ["a.nes"])) == {"kind": "ejs", "system": "nes", "core": "fceumm"}
    assert W.plan(game(1, "ps2", ["a.iso"])) is None  # console pesante: fuori
    assert W.plan(game(1, "windows", ["a.exe"], store="steam")) is None
    assert W.plan(game(1, "windows", ["x.swf"]))["kind"] == "ruffle"
    assert W.plan(game(1, "nes", [])) is None


def test_rom_solo_della_libreria(tmp_path):
    cfg = make_cfg(tmp_path)
    rom = tmp_path / "roms" / "mario.nes"
    rom.write_bytes(b"NES\x1a" + bytes(range(200)))
    secret = tmp_path / "segreto.txt"
    secret.write_text("no")
    api = client(cfg)
    lib = api.app.state.lib
    for g in (game(901, "nes", [rom]), game(902, "ps2", [rom]), game(903, "nes", [tmp_path / "manca.nes"]),
              game(904, "windows", [rom], store="steam")):
        lib.by_id[g["id"]] = g
    r = api.get("/api/play/901/rom/mario.nes")
    assert r.status_code == 200 and r.content == rom.read_bytes()
    part = api.get("/api/play/901/rom/mario.nes", headers={"Range": "bytes=0-3"})
    assert part.status_code == 206 and part.content == b"NES\x1a"
    assert api.get("/api/play/902/rom/x.iso").status_code == 403  # console non giocabile nel browser
    assert api.get("/api/play/904/rom/x").status_code == 403  # gioco di store
    assert api.get("/api/play/903/rom/x.nes").status_code == 404  # file sparito
    assert api.get("/api/play/999/rom/x.nes").status_code == 404  # non in libreria
    # il nome nell'indirizzo non sceglie il file: nessun percorso della richiesta arriva al disco
    for name in ("..%2F..%2Fsegreto.txt", "%2E%2E%2Fsegreto.txt", str(secret).replace("\\", "%5C").replace(":", "%3A")):
        r = api.get(f"/api/play/901/rom/{name}")
        assert r.content != b"no" and r.status_code in (200, 404)
    assert api.get("/play-assets/../../segreto.txt").status_code in (404,)
    assert api.get("/play-assets/ejs/..%2F..%2Fsegreto.txt").status_code == 404
    assert api.get("/play-assets/altro/x.js").status_code == 404
    page = api.get("/play/901")
    assert page.status_code == 200 and "Gioco 901" in page.text and '"core": "fceumm"' in page.text
    assert api.get("/play/902").status_code == 403
    assert "nes" in api.get("/api/webplay/platforms").json()["platforms"]


def test_salvataggi(tmp_path):
    cfg = make_cfg(tmp_path)
    rom = tmp_path / "roms" / "z.gba"
    rom.write_bytes(b"x")
    api = client(cfg)
    api.app.state.lib.by_id[910] = game(910, "gba", [rom])
    assert api.get("/api/play/910/save?kind=sram").status_code == 404
    blob = bytes(range(256)) * 8
    assert api.post("/api/play/910/save?kind=sram", content=blob).json()["size"] == len(blob)
    assert api.post("/api/play/910/save?kind=state", content=b"stato").status_code == 200
    assert api.get("/api/play/910/save?kind=sram").content == blob
    assert api.get("/api/play/910/save?kind=state").content == b"stato"
    assert api.post("/api/play/910/save?kind=altro", content=b"x").status_code == 400
    assert api.post("/api/play/910/save?kind=sram", content=b"").status_code == 400
    assert api.post("/api/play/999/save?kind=sram", content=b"x").status_code == 404
    # sta nel database dell'utente (quello che copia il backup)
    import sqlite3
    db = sqlite3.connect(Path(cfg.cache) / "userdata.db")
    assert db.execute("SELECT count(*) FROM web_saves WHERE key='k910'").fetchone()[0] == 2
    db.close()


def test_cancello_telefono(tmp_path):
    cfg = make_cfg(tmp_path)
    rom = tmp_path / "roms" / "a.nes"
    rom.write_bytes(b"NES\x1a")
    app, gate = paired_gate(cfg)
    try:
        app.state.lib.by_id[920] = game(920, "nes", [rom])
        ok = [("GET", "/play/920"), ("GET", "/api/play/920/rom/a.nes"), ("GET", "/api/play/920/status"),
              ("GET", "/api/play/920/save"), ("POST", "/api/play/920/save"), ("GET", "/play-assets/ejs/nope.js")]
        for m, u in ok:
            assert gate.request(m, u, content=b"s" if m == "POST" else None).status_code not in (401, 403), (m, u)
        assert gate.get("/api/play/920/rom/a.nes").content == b"NES\x1a"
        # il resto dell'app resta chiuso dal telefono
        for m, u in [("GET", "/api/webplay/platforms"), ("DELETE", "/api/play/920/save"), ("GET", "/play-assets/x/y.js"),
                     ("GET", "/play/920/altro"), ("GET", "/api/play/920/rom"), ("GET", "/static/play.html"),
                     ("GET", "/play-assets/ejs/../../x")]:
            assert gate.request(m, u).status_code in (403, 404, 405), (m, u)
        assert gate.request("GET", "/api/webplay/platforms").status_code == 403
        # senza abbinamento: niente
        gate.cookies.clear()
        assert gate.get("/play/920").status_code == 401
        assert gate.get("/api/play/920/rom/a.nes").status_code == 401
        assert gate.post("/api/play/920/save", content=b"x").status_code == 401
    finally:
        close(app, gate)
