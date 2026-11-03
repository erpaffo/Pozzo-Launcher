"""Servizi debrid con risposte finte (httpx.MockTransport): sblocco, ripiego sul link originale, chiave sbagliata, chiavi mai esposte."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.downloads import debrid as D, resolvers  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

HOSTER = "https://1fichier.com/?abc"
CALLS = []


def handler(req: httpx.Request) -> httpx.Response:
    CALLS.append(req)
    url, auth = str(req.url), req.headers.get("authorization", "")
    if "real-debrid" in url:
        if req.url.path.endswith("/hosts/domains"):
            return httpx.Response(200, json=["1fichier.com"])
        if auth != "Bearer RD":
            return httpx.Response(401, json={"error": "bad_token", "error_code": 8})
        if url.endswith("/user"):
            return httpx.Response(200, json={"username": "mario", "type": "premium", "expiration": "2027-01-01T00:00:00.000Z"})
        if "1fichier" not in req.content.decode():
            return httpx.Response(503, json={"error": "hoster_unsupported", "error_code": 16})
        return httpx.Response(200, json={"download": "https://rd.example/d/gioco.bin"})
    if "alldebrid" in url:
        if req.url.path.endswith("/hosts/domains"):
            return httpx.Response(200, json={"status": "success", "data": {"hosts": ["1fichier.com", "example.com"]}})
        if auth != "Bearer AD" or req.url.params.get("agent") != D.AGENT:
            return httpx.Response(401, json={"status": "error", "error": {"code": "AUTH_BAD_APIKEY", "message": "chiave sbagliata"}})
        if req.url.path.endswith("/user"):
            return httpx.Response(200, json={"status": "success", "data": {"user": {"username": "luigi", "isPremium": True, "premiumUntil": 1800000000}}})
        return httpx.Response(200, json={"status": "success", "data": {"link": "https://ad.example/gioco.bin"}})
    if "premiumize" in url:
        if req.url.path.endswith("/services/list"):
            return httpx.Response(200, json={"status": "success", "directdl": ["1fichier.com"]})
        return httpx.Response(200, json={"status": "error", "message": "unsupported host"})
    if "torbox" in url:
        if req.url.path.endswith("/webdl/hosters"):
            return httpx.Response(200, json={"success": True, "data": [
                {"domains": ["1fichier.com", "datanodes.to"], "status": True}]})
        if req.url.path.endswith("/createwebdownload"):
            return httpx.Response(200, json={"success": True, "data": {"webdownload_id": 7}})
        if req.url.path.endswith("/requestdl") and req.url.params.get("token") == "TB" and req.url.params.get("web_id") == "7":
            return httpx.Response(200, json={"success": True, "data": "https://tb.example/gioco.bin"})
        return httpx.Response(200, json={"success": False, "error": "BAD_TOKEN", "detail": "token non valido"})
    if "debrid-link" in url:
        if req.url.path.endswith("/downloader/hosts"):
            return httpx.Response(200, json={"success": True, "value": [
                {"domains": ["1fichier.com"], "status": 1}]})
        if req.url.path.endswith("/downloader/add") and req.headers.get("Authorization") == "Bearer DL":
            return httpx.Response(200, json={"success": True, "value": {"downloadLink": "https://dl.example/gioco.bin"}})
        if req.url.path.endswith("/account/infos") and req.headers.get("Authorization") == "Bearer DL":
            return httpx.Response(200, json={"success": True, "value": {"username": "ciro", "premiumLeft": 3600}})
        return httpx.Response(200, json={"success": False, "error": "badToken"})
    return httpx.Response(404)


@pytest.fixture(autouse=True)
def mock(monkeypatch):
    CALLS.clear()
    D._cache.clear()
    D._hosts_cache.clear()
    monkeypatch.setattr(D, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(resolvers, "_FNS", [])


def test_sblocco_e_cache():
    fn = D.resolver(lambda: {"realdebrid": {"enabled": True, "key": "RD"}})
    assert fn(HOSTER) == ("https://rd.example/d/gioco.bin", "realdebrid")
    n = len(CALLS)
    assert fn(HOSTER) == ("https://rd.example/d/gioco.bin", "realdebrid") and len(CALLS) == n  # dalla cache
    assert fn("magnet:?xt=urn:btih:x") == ""


def test_host_non_supportato_passa_al_servizio_dopo_o_al_link_originale():
    conf = {"realdebrid": {"enabled": True, "key": "RD"}, "alldebrid": {"enabled": True, "key": "AD"},
            "premiumize": {"enabled": True, "key": "PM"}}
    fn = D.resolver(lambda: conf)
    assert fn("https://example.com/f") == ("https://ad.example/gioco.bin", "alldebrid")
    before = len(CALLS)
    conf["alldebrid"]["enabled"] = False  # spento: non si chiama
    D._cache.clear()
    assert fn("https://example.com/f") == ""
    assert not any("alldebrid" in str(r.url) for r in CALLS[before:])
    resolvers.register(fn)
    assert resolvers.resolve("https://example.com/f") == ("https://example.com/f", "")


def test_datanodes_solo_con_i_servizi_che_lo_supportano():
    url = "https://datanodes.to/abc"
    fn = D.resolver(lambda: {"debridlink": {"enabled": True, "key": "DL"}})
    assert fn(url) == ""
    assert not any(req.url.path.endswith("/downloader/add") for req in CALLS)

    fn = D.resolver(lambda: {"debridlink": {"enabled": True, "key": "DL"},
                             "torbox": {"enabled": True, "key": "TB"}})
    assert fn(url) == ("https://tb.example/gioco.bin", "torbox")
    assert not any(req.url.path.endswith("/downloader/add") for req in CALLS)


def test_torbox_crea_e_chiede_il_link():
    fn = D.resolver(lambda: {"torbox": {"enabled": True, "key": "TB"}})
    assert fn(HOSTER) == ("https://tb.example/gioco.bin", "torbox")


def test_chiave_sbagliata():
    fn = D.resolver(lambda: {"realdebrid": {"enabled": True, "key": "NO"}})
    assert fn(HOSTER) == ""
    r = D.account("realdebrid", "NO")
    assert r == {"ok": False, "user": "", "premium": False, "expires": None, "error": "bad_token"}
    assert D.account("alldebrid", "NO")["error"] == "chiave sbagliata"
    assert D.account("torbox", "NO")["error"] == "token non valido"
    assert D.account("realdebrid", "RD") == {"ok": True, "error": "", "user": "mario", "premium": True,
                                             "expires": "2027-01-01T00:00:00.000Z"}
    a = D.account("alldebrid", "AD")
    assert a["ok"] and a["user"] == "luigi" and a["premium"] and a["expires"].startswith("2027-01-15")


def test_il_task_ricorda_chi_ha_sbloccato_e_le_chiavi_non_escono(tmp):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    m = Manager(cfg, save=lambda new: None)
    m.update_settings({"debrid": {"realdebrid": {"enabled": True, "key": "RD"}}})
    resolvers.register(D.resolver(lambda: m._raw()["debrid"]))
    t = T.DownloadTask(source=HOSTER, save_path=str(tmp))
    assert m._resolve(t, HOSTER) == "https://rd.example/d/gioco.bin"
    assert t.view()["options"]["resolved_by"] == "realdebrid"
    body = json.dumps({"tasks": m.list(), "settings": m.settings()})  # come GET /api/downloads
    assert '"RD"' not in body and m.settings()["debrid"]["realdebrid"] == {"enabled": True, "key_set": True}


def test_rotte(tmp):
    from fastapi.testclient import TestClient
    from pozzo import config
    from pozzo.app.server import create_app
    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.app["downloads"] = {"max_active": 1, "dir": str(tmp / "out")}
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/downloads/settings", json={"debrid": {"realdebrid": {"enabled": True, "key": "RD"}}, "seed_ratio": 2})
        assert r.status_code == 200 and r.json()["debrid"]["realdebrid"]["key_set"] and r.json()["seed_ratio"] == 2
        assert '"RD"' not in c.get("/api/downloads").text and '"RD"' in (tmp / config.SETTINGS_FILE).read_text("utf-8")
        assert c.post("/api/downloads/settings", json={"encryption": "x"}).status_code == 400
        assert c.post("/api/downloads/alt-speed", json={"on": True}).json()["alt_active"] is True
        assert c.post("/api/downloads/debrid/realdebrid/test").json()["user"] == "mario"
        assert c.post("/api/downloads/debrid/boh/test").status_code == 404
        c.post("/api/downloads/alt-speed", json={"on": False})
        a, b = (c.post("/api/downloads", json={"source": f"http://127.0.0.1:9/{n}"}).json()["tasks"][0]["id"] for n in "ab")
        assert c.post("/api/downloads/pause-all").json() == {"ok": True}
        assert c.post(f"/api/downloads/{b}/move", json={"to": "top"}).json() == {"ok": True}
        assert [t["id"] for t in c.get("/api/downloads").json()["tasks"]] == [b, a]
        assert c.post(f"/api/downloads/{a}/move", json={"to": "x"}).status_code == 400
        assert c.post(f"/api/downloads/{a}/limit", json={"down": 100, "up": 5}).json() == {"ok": True}
        assert next(t for t in c.get("/api/downloads").json()["tasks"] if t["id"] == a)["options"]["limit"] == {"down": 100, "up": 5}
        assert c.post(f"/api/downloads/{a}/recheck").status_code == 400
        assert c.post(f"/api/downloads/{a}/reannounce").status_code == 400
        assert c.post("/api/downloads/nessuno/recheck").status_code == 404
        assert c.post("/api/downloads/resume-all").json() == {"ok": True}
        r = c.get(f"/api/downloads/{a}/log").json()
        assert r["lines"][0]["msg"].startswith("Aggiunto (http)") and r["n"] == len(r["lines"]) + r["from"] and r["from"] == 0
        # il download puo' scrivere altre righe mentre si legge: si controlla che `after` riparta dalla riga giusta
        r2 = c.get(f"/api/downloads/{a}/log", params={"after": r["n"]}).json()
        full = c.get(f"/api/downloads/{a}/log").json()
        assert r2["from"] == r["n"] and full["lines"][r["n"] - full["from"]:][:len(r2["lines"])] == r2["lines"]
        assert "log_n" in c.get("/api/downloads").json()["tasks"][0] and "logs" not in c.get("/api/downloads").json()["tasks"][0]
        assert c.get("/api/downloads/nessuno/log").status_code == 404 and c.post("/api/downloads/nessuno/log/clear").status_code == 404
        assert c.post(f"/api/downloads/{a}/log/clear").json() == {"ok": True}
        # il download e' ripartito (resume-all) e puo' scrivere righe nuove subito dopo: quelle vecchie pero' non ci sono piu'
        assert not any(ln["msg"].startswith("Aggiunto (http)") for ln in c.get(f"/api/downloads/{a}/log").json()["lines"])
        for tid in (a, b):
            c.post(f"/api/downloads/{tid}/cancel", json={})


def test_debridlink_sblocca_e_verifica():
    fn = D.resolver(lambda: {"debridlink": {"enabled": True, "key": "DL"}})
    assert fn(HOSTER) == ("https://dl.example/gioco.bin", "debridlink")
    assert D.account("debridlink", "DL") == {"ok": True, "error": "", "user": "ciro", "premium": True,
                                             "expires": D.account("debridlink", "DL")["expires"]}
    bad = D.account("debridlink", "NO")
    assert bad["ok"] is False and bad["error"]


def test_registro_del_task_senza_chiavi_ne_query(tmp):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    m = Manager(cfg, save=lambda new: None)
    m.update_settings({"debrid": {"realdebrid": {"enabled": True, "key": "RD"}}})
    resolvers.register(D.resolver(lambda: m._raw()["debrid"]), "Sblocco il link con il servizio debrid")
    resolvers.register(lambda u: resolvers.note("rifiutato con la chiave RD") and "", "Altro passaggio")
    src = HOSTER + "&token=SECRET"
    t = T.DownloadTask(source=src, save_path=str(tmp))
    assert m._resolve(t, src) == "https://rd.example/d/gioco.bin"
    msgs = [l["msg"] for l in t.logs]
    text = "\n".join(msgs)
    assert "SECRET" not in text and "RD" not in text and "rifiutato con la chiave ***" in msgs
    assert "Sblocco il link con il servizio debrid" in msgs
    assert "Link finale: https://rd.example/d/gioco.bin (sbloccato da realdebrid)" in msgs
    assert [l["level"] for l in t.logs if "rifiutato" in l["msg"]] == ["warn"]
