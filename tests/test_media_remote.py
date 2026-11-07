"""Telecomando del lettore Media: rotte in memoria e cancello del telefono."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pozzo.app.routes import media_remote as MR
from pozzo.remote import phone


@pytest.fixture
def c():
    app = FastAPI()
    app.include_router(MR.build_router(SimpleNamespace()))
    return TestClient(app)


def cmd(c, name, arg=None):
    return c.post("/api/media/remote/command", json={"cmd": name, "arg": arg})


def test_validazione(c):
    assert cmd(c, "rm -rf").status_code == 400
    assert cmd(c, "jump").status_code == 400          # manca l'argomento numerico
    assert cmd(c, "jump", "10").status_code == 400
    assert cmd(c, "jump", True).status_code == 400
    assert cmd(c, "pause", 5).status_code == 200      # arg ignorato
    assert cmd(c, "jump", 99999).status_code == 200
    r = c.get("/api/media/remote/poll?since=0").json()
    assert [x["cmd"] for x in r["cmds"]] == ["pause", "jump"]
    assert r["cmds"][0]["arg"] is None and r["cmds"][1]["arg"] == 3600  # limitato


def test_numerazione_e_coda(c):
    for _ in range(25):
        cmd(c, "toggle")
    r = c.get("/api/media/remote/poll?since=0").json()
    assert len(r["cmds"]) == 20 and r["cmds"][0]["n"] == 6 and r["last"] == 25
    assert len(c.get("/api/media/remote/poll?since=23").json()["cmds"]) == 2


def test_scarto_vecchi(c, monkeypatch):
    monkeypatch.setattr(MR, "POLL_WAIT", 0)
    cmd(c, "pause")
    t = MR._now()
    monkeypatch.setattr(MR, "_now", lambda: t + 11)
    assert c.get("/api/media/remote/poll?since=0").json()["cmds"] == []


def test_longpoll_ritorna_al_comando(c, monkeypatch):
    monkeypatch.setattr(MR, "POLL_WAIT", 5.0)

    async def run():
        import httpx
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=c.app), base_url="http://t") as h:
            poll = asyncio.ensure_future(h.get("/api/media/remote/poll?since=0"))
            await asyncio.sleep(0.4)
            assert not poll.done()
            await h.post("/api/media/remote/command", json={"cmd": "next"})
            return await asyncio.wait_for(poll, 3)
    r = asyncio.run(run()).json()
    assert [x["cmd"] for x in r["cmds"]] == ["next"]


def test_longpoll_scade_vuoto(c, monkeypatch):
    monkeypatch.setattr(MR, "POLL_WAIT", 0.3)
    assert c.get("/api/media/remote/poll?since=0").json() == {"cmds": [], "last": 0}


def test_stato(c, monkeypatch):
    assert c.get("/api/media/remote/state").json() == {"active": False}
    s = {"active": True, "title": "Film", "paused": False}
    assert c.post("/api/media/remote/state", json=s).status_code == 200
    assert c.get("/api/media/remote/state").json() == s
    assert c.post("/api/media/remote/state", json={"active": True, "x": "a" * 5000}).status_code == 413
    t = MR._now()
    monkeypatch.setattr(MR, "_now", lambda: t + 9)
    assert c.get("/api/media/remote/state").json() == {"active": False}  # scaduto


def _allowed(rules, method, path):
    return any(m == method and r.match(path) for m, r in rules)


def test_cancello_telefono():
    assert _allowed(phone._ALLOWED, "POST", "/api/media/remote/command")
    assert _allowed(phone._ALLOWED, "GET", "/api/media/remote/state")
    for m, p in (("GET", "/api/media/remote/poll"), ("POST", "/api/media/remote/state"), ("GET", "/api/media/remote/command")):
        assert not _allowed(phone._ALLOWED, m, p)
    for rules in (phone._GUEST_ALLOWED, phone._PC_ALLOWED):
        assert not _allowed(rules, "POST", "/api/media/remote/command")
        assert not _allowed(rules, "GET", "/api/media/remote/state")
