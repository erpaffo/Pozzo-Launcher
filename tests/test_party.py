"""Endpoint /api/party: invito, anteprima, unione. Launcher, api_play e Discord finti: non parte nulla."""
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pozzo import netplay as NP
from pozzo.app.routes import party
from pozzo.library import launcher as L

G = {"id": 7, "title": "Super Game", "key": "snes/super-game"}


@pytest.fixture
def env(monkeypatch):
    plan = {"emulator": "retroarch", "core": "snes9x"}
    monkeypatch.setattr(L, "plan", lambda cfg, p, prof=None: plan)
    monkeypatch.setattr(party.C, "save_settings", lambda cfg, **kw: None)
    played, parties = [], []
    ctx = SimpleNamespace(
        cfg=SimpleNamespace(app={}), lib=SimpleNamespace(by_key={G["key"]: G}), user=SimpleNamespace(profile=lambda k: None),
        launcher=SimpleNamespace(next_args=[]), discord=SimpleNamespace(set_party=parties.append),
        api_play=played.append)
    app = FastAPI()
    app.include_router(party.build_router(ctx))
    return SimpleNamespace(c=TestClient(app), ctx=ctx, plan=plan, played=played, parties=parties)


def test_invite_ok(env):
    r = env.c.post("/api/party/invite", json={"key": G["key"], "nick": "Ale", "host": "192.168.1.5"})
    assert r.status_code == 200, r.text
    d = r.json()
    t = NP.decode(d["code"])
    assert t["k"] == G["key"] and t["h"] == "192.168.1.5" and t["n"] == "Ale" and t["c"] == "snes9x"
    assert env.ctx.launcher.next_args == NP.args("host", port=NP.PORT, nick="Ale")
    assert env.played == [7] and env.parties[0]["size"] == [1, 2]
    assert env.c.get("/api/party").json()["active"]["code"] == d["code"]


def test_avvio_fallito_non_lascia_argomenti(env):
    from fastapi import HTTPException

    def busy(gid):
        raise HTTPException(409, "E' gia' in esecuzione")
    env.ctx.api_play = busy
    c = TestClient(FastAPI(routes=party.build_router(env.ctx).routes))
    assert c.post("/api/party/invite", json={"key": G["key"]}).status_code == 409
    assert env.ctx.launcher.next_args == []


def test_invite_errors(env):
    assert env.c.post("/api/party/invite", json={"key": "x/y"}).status_code == 404
    assert env.c.post("/api/party/invite", json={"key": G["key"], "host": "non-un-ip"}).status_code == 400
    env.plan["emulator"] = "dolphin"
    r = env.c.post("/api/party/invite", json={"key": G["key"]})
    assert r.status_code == 409 and r.json()["detail"] == {"error": "no-netplay", "emulator": "dolphin", "suggest": "stream"}
    assert env.played == []


def _code(**kw):
    import time
    return NP.encode({"v": 1, "k": G["key"], "c": "snes9x", "h": "10.0.0.2", "p": 55435, "n": "Bob",
                      "x": int(time.time()) + 600, **kw})


def test_preview_and_join(env):
    p = env.c.post("/api/party/preview", json={"code": _code()}).json()
    assert p == {"title": "Super Game", "nick": "Bob", "host": "10.0.0.2", "port": 55435, "have": True}
    assert env.played == []
    r = env.c.post("/api/party/join", json={"code": _code()})
    assert r.status_code == 200 and env.played == [7]
    a = env.ctx.launcher.next_args
    assert a[:2] == ["--connect", "10.0.0.2"] and "--port" in a


def test_join_errors(env):
    assert env.c.post("/api/party/join", json={"code": "POZZO-boh"}).status_code == 400
    assert env.c.post("/api/party/preview", json={"code": "xx"}).status_code == 400
    r = env.c.post("/api/party/join", json={"code": _code(c="altro")})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "core-mismatch"
    assert env.c.post("/api/party/join", json={"code": _code(k="n/a")}).status_code == 404
    assert env.c.post("/api/party/preview", json={"code": _code(k="n/a")}).json()["have"] is False
    assert env.played == []


class _Proc:
    def __init__(self):
        self.stopped = False


def _eden(env, monkeypatch, alive=True):
    env.plan.update(emulator="eden", exe="C:/Eden/eden.exe", core="")
    calls = {"start": [], "prefill": [], "stop": []}
    monkeypatch.setattr(party.EDR, "start", lambda cmd: calls["start"].append(cmd) or _Proc())
    monkeypatch.setattr(party.EDR, "alive", lambda p, wait=0.7: alive)
    monkeypatch.setattr(party.EDR, "prefill", lambda exe, nick, host, port: calls["prefill"].append((nick, host, port)) or "ini")
    monkeypatch.setattr(party.EDR, "stop", lambda p: calls["stop"].append(p))
    return calls


def test_invite_eden_avvia_stanza_e_entra_da_ospite(env, monkeypatch):
    calls = _eden(env, monkeypatch)
    r = env.c.post("/api/party/invite", json={"key": G["key"], "nick": "Alessandro", "host": "192.168.1.5"})
    assert r.status_code == 200, r.text
    d = r.json()
    t = NP.decode(d["code"])
    assert t["e"] == "eden" and t["p"] == NP.EDEN_PORT and t["w"] and t["c"] == ""
    cmd = calls["start"][0]
    assert "--room" in cmd and "--password" in cmd and cmd[cmd.index("--password") + 1] == t["w"]
    assert calls["prefill"] == [("Alessandro", "127.0.0.1", NP.EDEN_PORT)]
    assert env.ctx.launcher.next_args == ["-m", f"Alessandro:{t['w']}@127.0.0.1:{NP.EDEN_PORT}"]
    assert d["steps"] and env.played == [7]
    assert env.c.post("/api/party/close").json() == {"ok": True}
    assert calls["stop"]  # la stanza viene fermata
    assert env.c.get("/api/party").json()["active"] is None


def test_invite_eden_stanza_che_non_parte(env, monkeypatch):
    _eden(env, monkeypatch, alive=False)
    r = env.c.post("/api/party/invite", json={"key": G["key"], "host": "192.168.1.5"})
    assert r.status_code == 409 and "eden-room" in r.json()["detail"] and env.played == []


def test_join_eden(env, monkeypatch):
    calls = _eden(env, monkeypatch)
    r = env.c.post("/api/party/join", json={"code": _code(e="eden", w="pw-1", p=24872, c="")})
    assert r.status_code == 200 and r.json()["prefilled"] is True and env.played == [7]
    assert calls["prefill"][0][1:] == ("10.0.0.2", 24872) and calls["start"] == []
    assert env.ctx.launcher.next_args[0] == "-m" and env.ctx.launcher.next_args[1].endswith("@10.0.0.2:24872")
    env.plan["emulator"] = "retroarch"
    r = env.c.post("/api/party/join", json={"code": _code(e="eden", w="pw-1", p=24872, c="")})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "emulator-mismatch"


def test_preview_accetta_messaggio_intero(env):
    msg = NP.invite_message(_code(), G["title"], "retroarch")
    p = env.c.post("/api/party/preview", json={"code": msg}).json()
    assert p["host"] == "10.0.0.2" and p["have"] is True


def test_get_party_kinds_lan(env, monkeypatch):
    monkeypatch.setattr(party, "lan_ips", lambda: ["192.168.1.5"])
    d = env.c.get("/api/party").json()
    assert d["kinds"]["192.168.1.5"]["kind"] == "lan" and d["register_protocol"] is True


def test_invite_risposta_ha_link_e_messaggio(env):
    d = env.c.post("/api/party/invite", json={"key": G["key"], "host": "192.168.1.5"}).json()
    assert d["link"].startswith("pozzo://join/") and d["code"] in d["message"]


def test_public_ip(env, monkeypatch):
    monkeypatch.setattr(party.NA, "public_ip", lambda: "8.8.8.8")
    d = env.c.post("/api/party/public-ip").json()
    assert d == {"ip": "8.8.8.8", "kind": "public", "tip": party.NA.address_kind("8.8.8.8")["tip"], "error": ""}
    monkeypatch.setattr(party.NA, "public_ip", lambda: "")
    r = env.c.post("/api/party/public-ip")
    assert r.status_code == 200 and r.json()["ip"] == "" and r.json()["error"].startswith("Non riesco")


def _invite_code():
    return NP.encode({"v": 1, "k": G["key"], "c": "snes9x", "h": "10.0.0.2", "p": 55435, "n": "Bob"})


def test_incoming_codice_valido_e_get(env):
    code = _invite_code()
    r = env.c.post("/api/party/incoming", json={"code": code})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert env.c.get("/api/party").json()["incoming"] == {"code": code}
    assert env.played == [] and env.ctx.launcher.next_args == []  # nessun avvio del gioco


def test_incoming_codice_falso_400(env):
    r = env.c.post("/api/party/incoming", json={"code": "POZZO-non-valido"})
    assert r.status_code == 400 and r.json()["detail"]
    assert env.c.get("/api/party").json()["incoming"] is None


def test_incoming_link_pozzo(env):
    code = _invite_code()
    r = env.c.post("/api/party/incoming", json={"url": f"pozzo://join/{code}"})
    assert r.status_code == 200
    assert env.c.get("/api/party").json()["incoming"] == {"code": code}
    assert env.played == []


def test_incoming_link_non_valido_400(env):
    r = env.c.post("/api/party/incoming", json={"url": "https://example.com/x"})
    assert r.status_code == 400 and r.json()["detail"] == "Link non valido"


def test_incoming_emette_evento(env):
    emitted = []
    env.ctx.events = SimpleNamespace(emit=lambda name, data: emitted.append((name, data)))
    code = _invite_code()
    r = env.c.post("/api/party/incoming", json={"code": code})
    assert r.status_code == 200
    assert emitted == [("party_invite", {"code": code})]


def test_incoming_evento_che_fallisce_non_rompe_la_rotta(env):
    def boom(name, data):
        raise RuntimeError("sse down")
    env.ctx.events = SimpleNamespace(emit=boom)
    r = env.c.post("/api/party/incoming", json={"code": _invite_code()})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_pending_join_da_variabile_ambiente(env, monkeypatch):
    code = _invite_code()
    monkeypatch.setenv("POZZO_PENDING_JOIN", f"pozzo://join/{code}")
    c = TestClient(FastAPI(routes=party.build_router(env.ctx).routes))
    assert c.get("/api/party").json()["incoming"] == {"code": code}
    assert "POZZO_PENDING_JOIN" not in os.environ


def test_settings_register_protocol(env):
    r = env.c.post("/api/party/settings", json={"register_protocol": False})
    assert r.status_code == 200 and r.json() == {"register_protocol": False}
    assert env.c.get("/api/party").json()["register_protocol"] is False


def test_settings_register_protocol_non_bool_400(env):
    r = env.c.post("/api/party/settings", json={"register_protocol": "abc"})
    assert r.status_code == 400 and r.json()["detail"] == "register_protocol deve essere true o false"


def test_stesso_gioco_altro_dump(env):
    # chiave diversa (nome file/dimensione diversi) ma stessa console e stesso titolo: lo trova
    assert env.c.post("/api/party/preview", json={"code": _code(k="snes/altrodump", t="super game")}).json()["have"] is True
    assert env.c.post("/api/party/preview", json={"code": _code(k="nes/altrodump", t="Super Game")}).json()["have"] is False


def test_invito_internet_con_upnp(env, monkeypatch):
    aperte = []
    monkeypatch.setattr(party.UP, "open_port", lambda port, proto: aperte.append((port, proto)) or
                        {"external_ip": "5.95.223.48", "control": "c", "service": "s", "port": port, "proto": proto})
    closed = []
    monkeypatch.setattr(party.UP, "close_port", closed.append)
    r = env.c.post("/api/party/invite", json={"key": G["key"], "where": "internet"})
    assert r.status_code == 200, r.text
    assert NP.decode(r.json()["code"])["h"] == "5.95.223.48" and r.json()["upnp"] is True
    assert aperte == [(NP.PORT, "TCP")]  # RetroArch: TCP
    env.c.post("/api/party/close")
    assert closed and closed[-1]["port"] == NP.PORT


def test_invito_internet_cgnat_e_senza_upnp(env, monkeypatch):
    monkeypatch.setattr(party.UP, "open_port", lambda port, proto: {"external_ip": "100.72.1.9", "port": port})
    monkeypatch.setattr(party.UP, "close_port", lambda m: None)
    r = env.c.post("/api/party/invite", json={"key": G["key"], "where": "internet"})
    assert r.status_code == 409 and r.json()["detail"] == {"error": "cgnat", "ip": "100.72.1.9"}
    monkeypatch.setattr(party.UP, "open_port", lambda port, proto: None)  # niente UPnP: IP pubblico da fuori
    monkeypatch.setattr(party.NA, "public_ip", lambda: "5.95.223.48")
    r = env.c.post("/api/party/invite", json={"key": G["key"], "where": "internet"})
    assert r.status_code == 200 and r.json()["upnp"] is False and NP.decode(r.json()["code"])["h"] == "5.95.223.48"


def test_upnp_riconosce_servizio_v2():
    from pozzo import upnp
    xml = ('<service><serviceType>urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1</serviceType>'
           '<controlURL>/ctl/CmnIfCfg</controlURL></service><service><serviceType>'
           'urn:schemas-upnp-org:service:WANIPConnection:2</serviceType><controlURL>/ctl/IPConn</controlURL></service>')
    m = upnp.SERVICE.search(xml)
    assert m.groups() == ("urn:schemas-upnp-org:service:WANIPConnection:2", "/ctl/IPConn")
