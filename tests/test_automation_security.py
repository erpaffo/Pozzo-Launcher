"""Sicurezza degli script utente (shell=True): nessun percorso diverso dalla UI puo' impostare comandi senza conferma.

Percorsi che scrivono before/after: POST /api/game/{id}/profile, POST /api/app/launch, POST /api/app/scripts (UI desktop,
con conferma). Tutti gli altri (import di altri launcher, /api/v1, telefono, sincronizzazione, estensioni, ripristino
copie) o non li toccano o avvisano: qui si prova ognuno.

Esegui: PYTHONUTF8=1 python tests/test_automation_security.py
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import backup, config, importers as IMP, sync  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.importers.formats import PARSERS  # noqa: E402
from pozzo.library import automation as A  # noqa: E402
from pozzo.library.build import SCHEMA  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def cfg(tmp_path):
    db = sqlite3.connect(tmp_path / "library.db")
    db.executescript(SCHEMA)
    db.execute("INSERT INTO games(key, platform, title, sort_title, year, genres, files, media, found, grp, is_primary, origin, "
               "store, installed) VALUES('steam/42','windows','Half-Life 2','half-life 2',2004,'[]','[]','{}',1,'windows/s:hl2',1,'{}','steam',1)")
    db.execute("INSERT INTO meta VALUES('built_at', '1')")
    db.commit()
    db.close()
    c = config.Config(cache=tmp_path, output=tmp_path / "out")
    c.config_path = tmp_path / "config.toml"
    return c


def _gid(c):
    return c.get("/api/library").json() and next(iter(c.get("/api/v1/games").json()["items"]))["id"]


def test_profile_route_needs_confirmation(cfg):
    with TestClient(create_app(cfg), base_url=BASE) as c:
        gid = _gid(c)
        # senza conferma: 428, con l'elenco dei comandi, e niente viene salvato
        r = c.post(f"/api/game/{gid}/profile", json={"before": "calc.exe"})
        assert r.status_code == 428 and r.json()["code"] == "scripts_confirm", r.text
        assert r.json()["scripts"] == [{"field": "before", "cmd": "calc.exe"}] and r.json()["detail"]
        assert c.get(f"/api/game/{gid}/profile").json()["profile"] == {}
        # anche il campo annidato delle automazioni (before_cmd/after_cmd)
        r = c.post(f"/api/game/{gid}/profile", json={"auto": {"after_cmd": "evil.bat"}})
        assert r.status_code == 428 and r.json()["scripts"][0]["field"] == "auto.after_cmd", r.text
        # con conferma si salva
        r = c.post(f"/api/game/{gid}/profile", json={"before": "calc.exe", "confirm_scripts": True})
        assert r.status_code == 200 and r.json()["profile"]["before"] == "calc.exe", r.text
        assert "confirm_scripts" not in r.json()["profile"]
        # la UI rimanda lo stesso comando a ogni salvataggio: invariato = nessuna nuova conferma
        assert c.post(f"/api/game/{gid}/profile", json={"before": "calc.exe", "companion": ""}).status_code == 200
        # cambiarlo o aggiungerne uno richiede di nuovo la conferma; toglierlo no
        assert c.post(f"/api/game/{gid}/profile", json={"before": "calc.exe & evil"}).status_code == 428
        assert c.post(f"/api/game/{gid}/profile", json={"before": "calc.exe", "after": "x"}).status_code == 428
        assert c.post(f"/api/game/{gid}/profile", json={}).status_code == 200
        assert c.get(f"/api/game/{gid}/profile").json()["profile"] == {}
        # solo "true" vero vale come conferma (non stringhe o numeri)
        assert c.post(f"/api/game/{gid}/profile", json={"before": "x", "confirm_scripts": "true"}).status_code == 428
        assert c.post(f"/api/game/{gid}/profile", json={"before": "x", "confirm_scripts": 1}).status_code == 428


def test_global_routes_need_confirmation(cfg):
    with TestClient(create_app(cfg), base_url=BASE) as c:
        for url, body, key in (("/api/app/launch", {"before": "a.bat"}, "launch"),
                               ("/api/app/scripts", {"game_started": "b.bat"}, "scripts")):
            r = c.post(url, json=body)
            assert r.status_code == 428 and r.json()["code"] == "scripts_confirm", (url, r.text)
            assert not cfg.app.get(key), cfg.app
            assert c.post(url, json={**body, "confirm_scripts": True}).status_code == 200
            assert list(cfg.app[key].values()) == list(body.values())
            assert c.post(url, json=body).status_code == 200  # invariato
        # le opzioni senza comandi non chiedono nulla
        assert c.post("/api/app/launch", json={"before": "a.bat", "close_launcher": True}).status_code == 200
        assert c.post("/api/app/launch", json={"splash": False}).status_code == 200
        assert "before" not in cfg.app["launch"]


def test_check_confirm_unit():
    A.check_confirm({"before": "a"}, {"before": "a"}, False)
    A.check_confirm({"before": "a"}, {}, False)
    with pytest.raises(A.ScriptsNeedConfirm) as e:
        A.check_confirm({"before": "a"}, {"before": "b", "after": "c"}, False)
    assert e.value.changed == {"before": "b", "after": "c"}
    A.check_confirm({}, {"before": "b"}, True)
    assert A.commands({"before": " x ", "auto": {"after_cmd": "y", "before_cmd": ""}, "preset": "p"}) == \
        {"before": "x", "auto.after_cmd": "y"}


def test_phone_and_v1_cannot_reach_script_fields(cfg):
    from pozzo.remote import phone
    surfaces = [p for sets in (phone.ALLOWED, phone.PC_ALLOWED, phone.GUEST_ALLOWED, phone.LIB_ALLOWED) for _, p in sets]
    for url in ("/api/game/1/profile", "/api/app/launch", "/api/app/scripts"):
        assert not any(re.fullmatch(p, url) for p in surfaces), url
    with TestClient(create_app(cfg), base_url=BASE) as c:
        paths = c.get("/openapi.json").json()["paths"]
        assert not [p for p in paths if p.startswith("/api/v1/") and re.search(r"profile|launch|script|auto", p)]
        # il browser di un altro sito (Origin diverso) non puo' scrivere: CSRF
        cfg2 = c.app.state.cfg
        assert cfg2 is cfg


def test_import_never_brings_scripts(tmp_path):
    pn = tmp_path / "p.json"
    pn.write_text(json.dumps([
        {"Name": "A", "PreScript": "del /s c:\\", "GameActions": [{"Type": "Script", "Script": "evil"}]},
        {"Name": "B", "GameActions": [{"Type": 0, "Path": "x.exe"}]}]), encoding="utf-8")
    peg = tmp_path / "metadata.pegasus.txt"
    peg.write_text("game: C\nlaunch: calc.exe\n\ngame: D\n", encoding="utf-8")
    recs = PARSERS["playnite"](pn)
    assert [r["scripts"] for r in recs] == [True, False]
    assert [r["scripts"] for r in PARSERS["pegasus"](peg)] == [True, False]
    # l'import non scrive mai profili di avvio e dice quanti script ha ignorato
    user = UserData(tmp_path / "u.db")
    calls = []
    user.set_profile = lambda *a, **k: calls.append(a)
    lib = SimpleNamespace(games=[{"key": "k/a", "title": "A", "store": None}])
    out = IMP.apply(user, lib, recs)
    assert out["scripts_ignored"] == 1 and out["matched"] == 1 and not calls, out
    assert not any(user.profile(k) for k in ("k/a", "k/b"))
    for r in recs:  # il record non porta mai il testo dei comandi
        assert "evil" not in json.dumps(r) and "del /s" not in json.dumps(r)
    from pozzo.app.routes import libimport  # il messaggio per l'utente esiste in ogni lingua
    from pozzo import i18n as I
    assert I.tr("s.libimport.scriptsIgnored", "en", n=2).startswith("2 games")
    del libimport


def test_sync_and_extensions_cannot_write_scripts(cfg):
    assert not {"launch", "scripts"} & set(sync.APP_KEYS) and not {"launch", "scripts", "auto"} & set(sync.SETTINGS_SECTIONS)
    config.save_settings(cfg, app={"launch": {"before": "mine.bat"}})
    c = {"settings_t": 0}
    evil = {"t": 9e9, "data": {"sections": {}, "app": {"launch": {"before": "evil"}, "scripts": {"game_started": "evil"},
                                                      "theme": "x"}}}
    assert sync.merge_settings(cfg, c, evil)
    app = config.read_settings(cfg)["app"]
    assert app["launch"] == {"before": "mine.bat"} and "scripts" not in app and app["theme"] == "x", app
    # una estensione salva solo nella sua sezione "plugins"
    from pozzo.app.extensions import PluginAPI
    api = PluginAPI(None, cfg, "demo", None, print)
    api.save_settings({"launch": {"before": "evil"}})
    s = config.read_settings(cfg)
    assert s["plugins"]["demo"] == {"launch": {"before": "evil"}} and s["app"]["launch"] == {"before": "mine.bat"}


def test_backup_restore_warns_about_commands(cfg, tmp_path):
    Path(cfg.cache).mkdir(exist_ok=True)
    user = UserData(Path(cfg.cache) / "userdata.db")
    config.save_settings(cfg, app={"launch": {"before": "a.bat"}, "scripts": {"game_started": "b.bat"}})
    user.set_profile(["k/1", "k/2"], {"after": "c.bat"})
    user.set_profile(["k/3"], {"auto": {"before_cmd": "d.bat"}})
    user.set_profile(["k/4"], {"preset": "quality"})
    b = backup.create(cfg)
    r = backup.restore(cfg, b.name, user=user)
    assert r["runs_commands"] == 2 + 3, r  # 2 comandi globali + 3 profili con comandi
    user.set_profile(["k/1", "k/2", "k/3"], None)
    config.save_settings(cfg, app={"launch": {"before": None}, "scripts": {"game_started": None}})
    b2 = backup.create(cfg)
    assert backup.restore(cfg, b2.name, user=user)["runs_commands"] == 0
    user.db.close()
    from pozzo import i18n as I
    assert "3" in I.tr("s.backups.scriptsWarning", "en", n=3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
