"""Mod Thunderstore dei giochi PC della libreria: layout BepInEx, dipendenze, attiva/disattiva, rimozione, rotte.
Nessuna rete: il download e' finto."""

import io
import json
import sqlite3
import sys
import tempfile
import time
import types
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import gamemods as GM  # noqa: E402
from pozzo import mods as M  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402

TS = "https://thunderstore.io/package/download/"


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, value in files.items():
            z.writestr(name, value)
    return buf.getvalue()


def _pkg(full: str, deps=(), url=""):
    owner, name = full.split("-", 1)
    return {"full_name": full, "name": name, "owner": owner, "versions": [{
        "version_number": "1.0.0", "download_url": url or f"{TS}{owner}/{name}/1.0.0/",
        "dependencies": [f"{d}-1.0.0" for d in deps]}]}


PACK = "BepInEx-BepInExPack"
RAW = [_pkg(PACK), _pkg("A-Lib", [PACK]), _pkg("B-Mod", ["A-Lib", PACK]), _pkg("C-Mod", ["A-Lib"]),
       _pkg("LavaGang-MelonLoader"), _pkg("M-Melon", ["LavaGang-MelonLoader"]),
       _pkg("X-Evil", [PACK], "https://evil.example/x.zip"), _pkg("Z-Slip", [PACK])]
PAYLOADS = {
    PACK: _zip({"manifest.json": "{}", "icon.png": "x", "BepInExPack/winhttp.dll": "loader",
                "BepInExPack/doorstop_config.ini": "new", "BepInExPack/BepInEx/core/BepInEx.dll": "core"}),
    "A-Lib": _zip({"manifest.json": "{}", "Lib.dll": "lib", "config/lib.cfg": "cfg"}),
    "B-Mod": _zip({"plugins/B.dll": "b"}),
    "C-Mod": _zip({"C.dll": "c"}),
    "Z-Slip": _zip({"../escape.dll": "no"}),
}
GOT: list = []


def _fake_download(url, dest, provider, max_bytes=M.MOD_MAX_DOWNLOAD):
    owner, name = url[len(TS):].split("/")[:2]
    GOT.append(f"{owner}-{name}")
    Path(dest).write_bytes(PAYLOADS[f"{owner}-{name}"])


def _env(tmp: Path):
    game_dir = tmp / "Valheim"
    game_dir.mkdir()
    (game_dir / "doorstop_config.ini").write_text("orig", encoding="utf-8")
    cfg = types.SimpleNamespace(config_path=tmp / "config.toml")
    user = UserData(tmp / "userdata.db")
    game = {"key": "windows/steam:892970", "title": "Valheim", "platform": "windows", "install_dir": str(game_dir)}
    return cfg, user, game, game_dir


def _raises(fn, exc, key=None):
    try:
        fn()
    except exc as e:
        assert key is None or getattr(e, "key", None) == key, e
        return
    raise AssertionError(f"atteso {exc.__name__}")


def test_layout_e_dipendenze():
    index = {x["id"]: x for x in M.parse_thunderstore(RAW)}
    assert index["B-Mod"]["deps"] == ["A-Lib", PACK]
    assert GM.plan(index, "B-Mod") == [PACK, "A-Lib", "B-Mod"]
    assert GM.installable(index, "C-Mod") and not GM.installable(index, "M-Melon"), "MelonLoader: solo link"
    cyc = {"A-X": {"deps": ["B-Y"]}, "B-Y": {"deps": ["A-X", PACK]}, PACK: {}}
    assert GM.plan(cyc, "A-X") == [PACK, "B-Y", "A-X"], "ciclo gestito"
    assert GM.layout(PACK, "BepInExPack/winhttp.dll") == "winhttp.dll"
    assert GM.layout("denikson-BepInExPack_Valheim", "BepInExPack_Valheim/BepInEx/core/x.dll") == "BepInEx/core/x.dll"
    assert GM.layout("A-Lib", "Lib.dll") == "BepInEx/plugins/A-Lib/Lib.dll"
    assert GM.layout("A-Lib", "config/a.cfg") == "BepInEx/config/a.cfg"
    assert GM.layout("A-Lib", "BepInEx/patchers/p.dll") == "BepInEx/patchers/A-Lib/p.dll"
    print("ok  dipendenze in ordine (cicli fermati), loader non BepInEx esclusi, layout come r2modman")


def test_installa_disattiva_rimuovi():
    old = (GM.download, GM._running)
    GM.download, GM._running = _fake_download, lambda folder: False
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        cfg, user, game, root = _env(tmp)
        index = {x["id"]: x for x in M.parse_thunderstore(RAW)}
        try:
            pv = GM.preview(cfg, user, game, index, "C-Mod")
            assert [x["id"] for x in pv["install"]] == [PACK, "A-Lib", "C-Mod"]
            assert pv["overwrite"] == ["doorstop_config.ini"]

            GM.install(cfg, user, game, index, "B-Mod")
            assert (root / "winhttp.dll").read_text() == "loader" and (root / "doorstop_config.ini").read_text() == "new"
            assert (root / "BepInEx/core/BepInEx.dll").is_file() and (root / "BepInEx/config/lib.cfg").is_file()
            assert (root / "BepInEx/plugins/A-Lib/Lib.dll").is_file() and (root / "BepInEx/plugins/B-Mod/B.dll").is_file()
            st = user.game_mods(game["key"])
            assert st[PACK]["auto"] and st["A-Lib"]["auto"] and not st["B-Mod"]["auto"]
            assert (tmp / "mods").is_dir(), "archivi e backup nei dati dell'app"

            GOT.clear()
            GM.install(cfg, user, game, index, "C-Mod")
            assert GOT == ["C-Mod"], "dipendenze gia' presenti: niente reinstallazione"

            _raises(lambda: GM.remove(cfg, user, game, "A-Lib"), GM.ModError, "s.mods.requiredBy")
            _raises(lambda: GM.set_enabled(cfg, user, game, "A-Lib", False), GM.ModError, "s.mods.requiredBy")

            GM.set_enabled(cfg, user, game, "B-Mod", False)
            assert not (root / "BepInEx/plugins/B-Mod/B.dll").exists() and (root / "BepInEx/plugins/A-Lib/Lib.dll").is_file()
            GM.set_enabled(cfg, user, game, "C-Mod", False)  # nessuna mod attiva richiede piu' le dipendenze
            assert not (root / "BepInEx/plugins/A-Lib/Lib.dll").exists() and not (root / "winhttp.dll").exists()
            assert (root / "doorstop_config.ini").read_text() == "orig"
            GM.set_enabled(cfg, user, game, "C-Mod", True)  # riattiva anche le dipendenze
            assert (root / "BepInEx/plugins/C-Mod/C.dll").is_file() and (root / "winhttp.dll").is_file()
            assert (root / "doorstop_config.ini").read_text() == "new"

            GM.remove(cfg, user, game, "B-Mod")
            assert "A-Lib" in user.game_mods(game["key"]), "dipendenza condivisa: resta finche' serve"
            GM.remove(cfg, user, game, "C-Mod")
            assert user.game_mods(game["key"]) == {}
            assert (root / "doorstop_config.ini").read_text() == "orig" and not (root / "winhttp.dll").exists()
            assert not (root / "BepInEx/plugins/C-Mod/C.dll").exists()

            _raises(lambda: GM.install(cfg, user, game, index, "X-Evil"), ValueError)
            _raises(lambda: GM.install(cfg, user, game, index, "Z-Slip"), ValueError)
            assert not (tmp / "escape.dll").exists() and "Z-Slip" not in user.game_mods(game["key"])
            _raises(lambda: GM.plan(index, "M-Melon"), GM.ModError, "s.mods.unsupportedLoader")
            _raises(lambda: GM.install(cfg, user, {**game, "install_dir": ""}, index, "C-Mod"), GM.ModError,
                    "s.mods.gameNotInstalled")
            GM._running = lambda folder: True
            _raises(lambda: GM.install(cfg, user, game, index, "C-Mod"), GM.ModError, "s.mods.gameRunning")
        finally:
            GM.download, GM._running = old
            user.close()
    print("ok  BepInEx nella radice, plugin per pacchetto, dipendenze condivise, blocchi, ripristino originali, rifiuti")


def test_rotte():
    from fastapi.testclient import TestClient

    from pozzo import config
    from pozzo.app.server import create_app
    from pozzo.cache import Cache
    from test_frontend import make_library
    old = (GM.download, GM._running)
    GM.download, GM._running = _fake_download, lambda folder: False
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        rom, game_dir = tmp / "g.gba", tmp / "Valheim"
        rom.write_bytes(b"x")
        game_dir.mkdir()
        cfg = config.Config(cache=tmp, output=tmp / "out")
        cfg.config_path = tmp / "config.toml"
        make_library(tmp, rom)
        db = sqlite3.connect(tmp / "library.db")
        gid = db.execute("SELECT MIN(id) FROM games").fetchone()[0]
        other = db.execute("SELECT MAX(id) FROM games").fetchone()[0]
        db.execute("UPDATE games SET title='Valheim', platform='windows', install_dir=?, files=? WHERE id=?",
                   (str(game_dir), json.dumps([str(game_dir)]), gid))
        db.commit()
        db.close()
        c = Cache(tmp)
        c.kv_set("mods:ts:valheim", M.parse_thunderstore(RAW))
        c.close()
        try:
            client = TestClient(create_app(cfg))
            no = client.get(f"/api/game/{other}/mods").json()
            assert no["supported"] is False and no["items"] == [] and "sites" in no
            got = client.get(f"/api/game/{gid}/mods", params={"q": "mod"}).json()
            assert got["supported"] and got["community"] == "valheim" and got["game_installed"]
            assert {x["id"] for x in got["items"]} >= {"B-Mod", "C-Mod"}
            assert "M-Melon" not in {x["id"] for x in got["items"]}, "filtro q"
            every = client.get(f"/api/game/{gid}/mods").json()["items"]
            assert not next(x for x in every if x["id"] == "M-Melon")["installable"]
            job = client.post(f"/api/game/{gid}/mods/install", json={"id": "C-Mod"}).json()
            assert job["status"] in ("running", "done") and job["id"] == 1
            for _ in range(100):
                job = client.get(f"/api/game/{gid}/mods/job").json()
                if job["status"] != "running":
                    break
                time.sleep(0.05)
            assert job["status"] == "done", job
            inst = client.get(f"/api/game/{gid}/mods").json()["installed"]
            assert inst["A-Lib"]["required_by"] == ["Mod"] and (game_dir / "BepInEx/plugins/C-Mod/C.dll").is_file()
            assert client.delete(f"/api/game/{gid}/mods/A-Lib").status_code == 409
            assert client.post(f"/api/game/{gid}/mods/install", json={"id": "M-Melon"}).status_code == 409
            assert client.post(f"/api/game/{gid}/mods/install", json={"id": "nope"}).status_code == 404
            assert client.delete(f"/api/game/{gid}/mods/C-Mod").json() == {}
            assert client.get("/api/game/999999/mods").status_code == 404
        finally:
            GM.download, GM._running = old
    print("ok  rotte: non supportato -> link, elenco, installazione in background, blocchi, rimozione")


if __name__ == "__main__":
    test_layout_e_dipendenze()
    test_installa_disattiva_rimuovi()
    test_rotte()
