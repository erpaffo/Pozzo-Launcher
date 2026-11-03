"""Endpoint /api/party: invito, anteprima, unione. Launcher, api_play e Discord finti: non parte nulla."""
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
