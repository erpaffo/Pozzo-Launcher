"""Profili sullo stesso PC: una sola libreria, ognuno vede i suoi giochi (pozzo/ownership.py), account e impostazioni
per profilo, profilo per dispositivo (cookie gs_profile), backup con i file dei profili. Nessuna rete."""

import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import backup, config, ownership as OW, profilecfg as PC, stores, sync  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.library import build  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402


def _cfg(tmp: Path):
    cfg = config.Config(cache=tmp / "cache", output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    cfg.cache.mkdir(parents=True)
    cfg.roms = tmp / "roms"
    cfg.roms.mkdir()
    return cfg


def _as(cfg, pid):
    cfg.app["profile"] = pid


def test_rom_folders_shared_and_own(tmp):
    cfg = _cfg(tmp)
    sync.add_profile(cfg, "Luca")
    sync.add_profile(cfg, "Anna")
    (tmp / "luca").mkdir(), (tmp / "both").mkdir()
    _as(cfg, "luca")
    PC.set(cfg, "roms_extra", [str(tmp / "luca"), str(tmp / "both")])
    _as(cfg, "anna")
    PC.set(cfg, "roms_extra", [str(tmp / "both")])
    _as(cfg, "default")

    roots = OW.profile_roots(cfg)
    assert roots == {tmp / "luca": ["luca"], tmp / "both": ["luca", "anna"]}
    assert set(config.rom_roots(cfg)) == {cfg.roms, tmp / "luca", tmp / "both"}, "la scansione vede l'unione"
    files = {"k/shared": [str(cfg.roms / "a.gba")], "k/luca": [str(tmp / "luca" / "b.gba")],
             "k/both": [str(tmp / "both" / "c.gba")],  # stessa ROM in due cartelle proprie: un record, due proprietari
             "k/mix": [str(tmp / "luca" / "d.gba"), str(cfg.roms / "d.gba")]}  # anche in quella globale: di tutti
    own = OW.file_owners(cfg, files)
    assert own == {"k/luca": ["luca"], "k/both": ["anna", "luca"]}
    g = lambda k: {"key": k, "owners": own.get(k)}  # noqa: E731
    assert OW.visible(g("k/shared"), "anna") and OW.visible(g("k/mix"), "anna")
    assert OW.visible(g("k/luca"), "luca") and not OW.visible(g("k/luca"), "anna") and not OW.visible(g("k/luca"), "default")
    assert OW.visible(g("k/both"), "luca") and OW.visible(g("k/both"), "anna") and not OW.visible(g("k/both"), "default")
    # se una cartella propria e' gia' globale resta globale
    config.save_settings(cfg, paths={"extra_roms": [str(tmp / "luca")]})
    assert tmp / "luca" not in OW.profile_roots(cfg)

    # library.db: la tabella game_owners diventa g["owners"] solo sui giochi non condivisi
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE game_owners(key TEXT, owner TEXT)")
    db.executemany("INSERT INTO game_owners VALUES(?,?)", [("k/both", "luca"), ("k/both", "anna")])
    games = [{"key": "k/both"}, {"key": "k/shared"}]
    assert OW.apply(db, games) and games[0]["owners"] == ["luca", "anna"] and "owners" not in games[1]
    assert OW.apply(sqlite3.connect(":memory:"), [{"key": "x"}]) is False, "library.db vecchia: tutto condiviso"
    # versioni di un gioco: ognuno ne vede solo alcune, ma il gruppo non resta mai vuoto
    grp = [{"key": "a", "owners": ["luca"]}, {"key": "b"}]
    assert [x["key"] for x in OW.members(grp, "anna")] == ["b"] and len(OW.members(grp, "luca")) == 2
    assert OW.members([{"key": "a", "owners": ["luca"]}], "anna")


def test_store_lists_per_account(tmp):
    """Due profili con lo stesso gioco Steam: una voce sola; i soli posseduti sono del proprio profilo."""
    cfg = _cfg(tmp)
    c = Cache(cfg.cache)
    g = lambda i, inst=False: {"store": "steam", "id": i, "title": f"Gioco {i}", "installed": inst}  # noqa: E731
    c.kv_set("store:steam", [g("1", True), g("2")])            # Principale: 1 installato, 2 posseduto
    c.kv_set("store:steam:luca", [g("2"), g("3"), g("1", True)])  # Luca: 2 e 3 posseduti
    c.kv_set("store:battlenet", [{"store": "battlenet", "id": "w", "title": "WoW", "installed": False}])
    c.kv_set("store:manual", [{"store": "manual", "id": "5", "title": "Mio", "installed": True, "owner": "luca"},
                              {"store": "manual", "id": "6", "title": "Di tutti", "installed": True, "owner": ""}])
    snaps = {(s["store"], s["id"]): s["owners"] for s in stores.load_snapshots(c)}
    assert snaps == {("steam", "1"): [], ("steam", "2"): ["default", "luca"], ("steam", "3"): ["luca"],
                     ("battlenet", "w"): [], ("manual", "5"): ["luca"], ("manual", "6"): []}, snaps
    assert len(stores.load_snapshots(c)) == 6, "una sola voce per gioco, qualunque numero di profili"
    entries = {e["key"]: e["owners"] for e in build._store_entries(cfg, c)}
    assert entries["windows/steam:2"] == ["default", "luca"] and entries["windows/steam:1"] == []
    assert stores.snap_key("steam", "luca") == "store:steam:luca" and stores.snap_key("steam") == "store:steam"
    assert stores.snap_key("xbox", "luca") == "store:xbox", "store del sistema: una lista sola"
    c.close()


def test_manual_games_per_profile(tmp):
    shared = tmp / "userdata.db"
    # database di prima: manual_games senza la colonna profile, con una riga
    db = sqlite3.connect(shared)
    db.execute("CREATE TABLE manual_games(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, exe TEXT, args TEXT, "
               "cwd TEXT, added REAL, kind TEXT DEFAULT 'game', meta TEXT)")
    db.execute("INSERT INTO manual_games(title, exe, args, cwd, added) VALUES('Vecchio','C:/v.exe','[]','',1)")
    db.commit()
    db.close()
    main = UserData(shared, profile="default")
    luca = UserData(tmp / "luca.db", shared=shared, profile="luca")
    assert [m["profile"] for m in main.manual_games()] == [None], "la riga di prima resta, condivisa"
    luca.add_manual("Solo mio", "C:/mio.exe", [])
    main.add_manual("Del principale", "C:/pri.exe", [])
    by = {m["title"]: m["profile"] for m in luca.manual_games()}
    assert by == {"Vecchio": None, "Solo mio": "luca", "Del principale": "default"}, "la tabella e' una sola per i profili"
    n = len(main.manual_games())
    luca.add_manual("Stesso gioco", "C:/PRI.exe", [])  # stesso exe del principale: un solo record, ora di tutti
    assert len(main.manual_games()) == n
    assert {m["title"]: m["profile"] for m in main.manual_games()}["Del principale"] is None
    main.close(), luca.close()


def test_settings_isolated_between_profiles(tmp):
    cfg = _cfg(tmp)
    config.save_settings(cfg, app={"theme": "oled", "github_token": "gh-principale",
                                   "wishlist": {"itad_key": "k1", "country": "IT"}},
                         stores={"steam": {"api_key": "steam-principale", "steamid": "111", "path": "C:/Steam"}})
    PC.migrate(cfg)
    sync.add_profile(cfg, "Luca")
    assert PC.get(cfg, "github_token") == "gh-principale" and PC.get(cfg, "steam")["steamid"] == "111"
    with PC.override("luca"):
        assert PC.active(cfg) == "luca"
        assert PC.get(cfg, "github_token") is None and PC.get(cfg, "steam") is None and PC.get(cfg, "wishlist") is None
        assert PC.get(cfg, "theme") == "oled", "il tema (non segreto) parte da quello globale"
        PC.set(cfg, "steam", {"api_key": "steam-luca", "steamid": "222"})
        PC.set(cfg, "theme", "chiaro")
        from pozzo import ports, wishlist
        PC.set(cfg, "wishlist", {"itad_key": "k2"})
        PC.set(cfg, "github_token", "gh-luca")
        assert ports._token(cfg) == "gh-luca" and wishlist.settings(cfg)["itad_key"] == "k2"
        st = stores.Steam(cfg, None, None, print).settings
        assert st["api_key"] == "steam-luca" and st["path"] == "C:/Steam", "chiave del profilo, percorso della macchina"
    assert PC.get(cfg, "theme") == "oled" and PC.get(cfg, "steam")["api_key"] == "steam-principale"
    assert ports._token(cfg) == "gh-principale" and wishlist.settings(cfg)["itad_key"] == "k1"
    assert stores.Steam(cfg, None, None, print).settings["api_key"] == "steam-principale"
    assert PC.values(cfg, "steam") == {"default": {"api_key": "steam-principale", "steamid": "111"},
                                       "luca": {"api_key": "steam-luca", "steamid": "222"}}
    # file di un profilo creato prima delle chiavi nuove: una sola copia dal globale, poi il profilo e' la fonte
    p = PC.path(cfg, "default")
    p.write_text(json.dumps({"spotify": {"client_id": "x"}}), encoding="utf-8")
    PC.migrate(cfg)
    assert json.loads(p.read_text(encoding="utf-8"))["github_token"] == "gh-principale"
    PC.set(cfg, "github_token", None)
    PC.migrate(cfg)
    assert PC.get(cfg, "github_token") is None, "un valore tolto non rispunta dal globale"


def test_backup_includes_profile_json(tmp):
    cfg = _cfg(tmp)
    PC.set(cfg, "github_token", "t0")
    sync.add_profile(cfg, "Luca")
    with PC.override("luca"):
        PC.set(cfg, "steam", {"api_key": "segreta"})
    UserData(sync.profile_path(cfg, "default")).close()
    out = backup.create(cfg)
    with zipfile.ZipFile(out) as z:
        assert {"profiles/default.json", "profiles/luca.json", "userdata.db"} <= set(z.namelist())
    PC.path(cfg, "luca").write_text("{}", encoding="utf-8")  # perdita dei dati
    res = backup.restore(cfg, out.name)
    assert "profiles/luca.json" in res["restored"]
    with PC.override("luca"):
        assert PC.get(cfg, "steam") == {"api_key": "segreta"}


def test_device_profile_cookie_and_library(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    db = sqlite3.connect(tmp / "library.db")  # Psp: gioco del solo Luca, come lo scriverebbe la ricostruzione
    db.execute("INSERT INTO game_owners VALUES('psp/DDD', 'luca')")
    db.commit()
    db.close()
    app = create_app(cfg)
    pc, phone = TestClient(app), TestClient(app)
    ids = lambda c: {r[1] for r in c.get("/api/library?part=owned").json()["games"]["rows"]}  # noqa: E731
    pc.post("/api/profiles", json={"name": "Luca"})
    sync.update_profile(cfg, "luca", pin="1234")
    assert phone.get("/api/profiles").json()["ask"] is True, "con 2 profili «Chi gioca?» e' acceso di default"

    # PIN: serve, errato, limite dei tentativi, profilo inesistente
    r = pc.post("/api/profiles/active", json={"id": "luca"})
    assert r.status_code == 403 and r.json()["error"] == "pin" and "gs_profile" not in pc.cookies
    for _ in range(4):
        assert pc.post("/api/profiles/active", json={"id": "luca", "pin": "0000"}).status_code == 403
    r = pc.post("/api/profiles/active", json={"id": "luca", "pin": "0000"})
    assert r.status_code == 403
    r = pc.post("/api/profiles/active", json={"id": "luca", "pin": "1234"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert pc.post("/api/profiles/active", json={"id": "nessuno"}).status_code == 404
    sync.update_profile(cfg, "luca", pin="")  # senza PIN si passa

    r = pc.post("/api/profiles/active", json={"id": "luca"})
    assert r.status_code == 200 and r.json() == {"active": "luca"}
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    r = phone.post("/api/profiles/active", json={"id": "default"})
    assert r.status_code == 200
    assert pc.get("/api/profiles").json()["active"] == "luca" and phone.get("/api/profiles").json()["active"] == "default"
    # ognuno vede i suoi giochi e i suoi dati
    assert "Kingdom Hearts - Birth by Sleep" in {r[1] for r in pc.get("/api/library?part=owned").json()["games"]["rows"]}
    assert "Kingdom Hearts - Birth by Sleep" not in {r[1] for r in phone.get("/api/library?part=owned").json()["games"]["rows"]}
    gid = next(r[0] for r in pc.get("/api/library?part=owned").json()["games"]["rows"] if r[1].startswith("Pokemon - Versione Rubino"))
    pc.post(f"/api/game/{gid}/flag", json={"field": "favorite", "value": True})
    fav = lambda c: sum(r[1] for r in c.get("/api/library?part=owned").json()["groups"]["rows"])  # noqa: E731
    assert fav(pc) == 1 and fav(phone) == 0, "preferiti separati per dispositivo"
    # impostazioni del profilo del dispositivo
    assert pc.post("/api/profile/settings", json={"theme": "oled"}).json()["theme"] == "oled"
    assert phone.get("/api/profile/settings").json()["theme"] == "default", "il tema e' del profilo del dispositivo"
    assert pc.post("/api/profile/settings", json={"steam": {"api_key": "x"}}).status_code == 400, "mai segreti"
    assert pc.post("/api/profiles/ask", json={"ask": False}).json() == {"ask": False}
    assert phone.get("/api/profiles").json()["ask"] is False
    keys = set(pc.get("/api/profile/settings").json())
    assert {"theme", "experience", "ask_profile"} <= keys
    ps = pc.get("/api/profiles").json()
    assert set(ps["profiles"][0]) == {"id", "name", "avatar", "color", "locked"}
    # cartella ROM propria dal profilo attivo del dispositivo
    d = tmp / "mie"
    d.mkdir()
    assert pc.post("/api/profile/roms", json={"action": "add", "path": str(d)}).json()["roms_extra"] == [str(d.resolve())]
    assert PC.values(cfg, "roms_extra") == {"luca": [str(d.resolve())]}
