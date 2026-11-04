"""Coda dei download consapevole della partita (modalita' mentre giochi) e pianificazione del singolo task. Nessuna rete."""

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import manager as M  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

MON = datetime(2026, 3, 2, 23, 0)  # lunedi' 2 marzo 2026


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _task(url, tmp, **kw):
    return T.DownloadTask(source=url, save_path=str(tmp / "out"), **kw)


def _reload(m):
    """Un «riavvio»: la stessa cartella di cache, letta da un manager nuovo."""
    return Manager(m.cfg, client_factory=net.make_client, save=lambda new: None).store.load()


def test_game_mode_off_non_cambia_nulla(tmp):
    state = {"on": False}
    m = _mgr(tmp, max_active=0, limit_down=1000)
    m.playing = lambda: state["on"]
    t = _task("magnet:?xt=urn:btih:abc", tmp, type="torrent")
    t.status = T.RUNNING
    m.tasks = {t.id: t}
    m._tick()
    assert m.settings()["game_active"] is False and m._limits(m._raw()) == (1000, 0)
    state["on"] = True
    m._tick()
    assert t.status == T.RUNNING  # modalita' predefinita: la partita non tocca i download
    assert m._limits(m._raw()) == (1000, 0)
    assert m.settings()["game_active"] is True and m._game["paused"] == []


def test_game_mode_limit_sostituisce_il_limite(tmp):
    state = {"on": False}
    m = _mgr(tmp, max_active=0, limit_down=1000, game_mode="limit", game_limit_kbps=100)
    m.playing = lambda: state["on"]
    a = _task("http://x/a", tmp)
    a.status = T.RUNNING
    m.tasks, m._jobs, m._dl_ids = {a.id: a}, {a.id: None}, {a.id}
    m._tick()
    assert m._buckets[a.id].rate == 1000 * 1024  # nessun gioco: vale il limite globale
    state["on"] = True
    m._tick()
    assert m._limits(m._raw()) == (100, 0)  # solo il download cambia, l'upload resta quello globale
    assert m._buckets[a.id].rate == 100 * 1024
    state["on"] = False
    m._tick()
    assert m._limits(m._raw()) == (1000, 0) and m._buckets[a.id].rate == 1000 * 1024


def test_game_mode_pause_riprende_solo_cio_da_lui_messo_in_pausa(tmp):
    state = {"on": False}
    m = _mgr(tmp, max_active=0, game_mode="pause")
    m.playing = lambda: state["on"]
    tor, web, mine = _task("magnet:?xt=urn:btih:abc", tmp, type="torrent"), _task("http://x/web", tmp), _task("http://x/mine", tmp)
    tor.status = web.status = T.RUNNING
    mine.status = T.PAUSED  # fermato a mano: non e' roba della partita
    m.tasks = {t.id: t for t in (tor, web, mine)}
    state["on"] = True
    m._tick()
    assert tor.status == T.PAUSED  # i torrent si fermano…
    assert web.status == T.RUNNING  # …gli HTTP no, se l'opzione e' spenta
    assert mine.status == T.PAUSED and m._game["paused"] == [tor.id]
    state["on"] = False
    m._tick()
    assert tor.status == T.QUEUED  # torna in coda da solo
    assert web.status == T.RUNNING and mine.status == T.PAUSED  # chi era in pausa a mano resta fermo
    assert m._game["paused"] == []
    # con «metti in pausa anche i download HTTP» si ferma anche quello
    m2 = _mgr(tmp / "due", max_active=0, game_mode="pause", game_pause_http=True)
    m2.playing = lambda: state["on"]
    h = _task("http://x/h", tmp)
    h.status = T.RUNNING
    m2.tasks = {h.id: h}
    state["on"] = True
    m2._tick()
    assert h.status == T.PAUSED and m2._game["paused"] == [h.id]
    state["on"] = False
    m2._tick()
    assert h.status == T.QUEUED


async def test_task_pianificato_non_parte_prima_dellorario(tmp):
    m = _mgr(tmp, max_active=3)

    async def fake_job(t, segments):  # l'avvio non deve toccare la rete
        return None

    m._job = fake_job
    t = m.add("http://x/a", start_at="23:00")
    assert t.status == T.QUEUED and t.options == {"start_at": "23:00"}
    # la pianificazione e' su disco: un riavvio la ritrova
    assert [x.options.get("start_at") for x in _reload(m) if x.id == t.id] == ["23:00"]
    m.now = lambda: datetime(2026, 3, 2, 22, 59)
    m._tick()
    assert t.status == T.QUEUED  # manca un minuto
    m.now = lambda: MON
    m._tick()
    assert t.status == T.RUNNING and "start_at" not in t.options
    assert "start_at" not in [x for x in _reload(m) if x.id == t.id][0].options  # partito: niente piu' attesa
    await asyncio.sleep(0)  # il job finto finisce senza lasciare task appesi


def test_pianificazione_invalida_rifiutata(tmp):
    m = _mgr(tmp, max_active=0)
    t = _task("http://x/a", tmp)
    m.tasks = {t.id: t}
    with pytest.raises(ValueError):
        m.set_schedule(t.id, "25:00")
    with pytest.raises(ValueError):
        m.set_schedule(t.id, "12:00", [9])
    with pytest.raises(ValueError):
        m.add("http://x/b", start_at="domani")
    assert "start_at" not in t.options  # niente mezze pianificazioni
    m.set_schedule(t.id, "12:00", [1, 1, 2])
    assert t.options == {"start_at": "12:00", "days": [1, 2]}
    t.status = T.PAUSED
    m.set_schedule(t.id, "12:00")  # una pianificazione riporta in coda un download fermo
    assert t.status == T.QUEUED and t.options == {"start_at": "12:00"}
    m.set_schedule(t.id, "")
    assert "start_at" not in t.options and "days" not in t.options


def test_due_rispetta_orario_giorni_e_data():
    assert M._due({}, MON) and M._due({"start_at": ""}, MON)
    assert M._due({"start_at": "23:00"}, MON) and not M._due({"start_at": "23:01"}, MON)
    assert M._due({"start_at": "23:00", "days": [0]}, MON)  # lunedi'
    assert not M._due({"start_at": "23:00", "days": [1]}, MON)
    assert not M._due({"start_at": "2026-03-02 23:30"}, MON)  # data e ora una volta sola
    assert M._due({"start_at": "2026-03-02 22:00"}, MON)


def test_rotte_pianificazione_e_modalita_partita(tmp):
    """Le rotte nuove: «Avvia alle» e le tre chiavi di «Mentre giochi» (niente rete: il task non parte)."""
    from fastapi.testclient import TestClient
    from pozzo import config
    from pozzo.app.server import create_app

    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.app["downloads"] = {"max_active": 1, "dir": str(tmp / "out")}
    with TestClient(create_app(cfg)) as c:
        r = c.post("/api/downloads", json={"source": "http://127.0.0.1:9/x", "start_at": "2099-01-01 03:00"})
        task = r.json()["tasks"][0]
        assert task["status"] == T.QUEUED and task["options"]["start_at"] == "2099-01-01 03:00"
        time.sleep(1.1)  # il ciclo gira: un task pianificato per il 2099 non parte
        assert next(t for t in c.get("/api/downloads").json()["tasks"] if t["id"] == task["id"])["status"] == T.QUEUED
        assert c.post(f"/api/downloads/{task['id']}/schedule", json={"start_at": "24:00"}).status_code == 400
        assert c.post("/api/downloads/nessuno/schedule", json={"start_at": "23:00"}).status_code == 404
        assert c.post(f"/api/downloads/{task['id']}/schedule", json={"start_at": ""}).json() == {"ok": True}
        assert "start_at" not in next(t for t in c.get("/api/downloads").json()["tasks"] if t["id"] == task["id"])["options"]
        s = c.get("/api/downloads").json()["settings"]
        assert s["game_mode"] == "off" and s["game_active"] is False
        assert c.post("/api/downloads/settings", json={"game_mode": "boh"}).status_code == 400
        r = c.post("/api/downloads/settings", json={"game_mode": "pause", "game_pause_http": True, "game_limit_kbps": 500})
        assert r.json()["game_mode"] == "pause" and r.json()["game_pause_http"] is True and r.json()["game_limit_kbps"] == 500
        c.post(f"/api/downloads/{task['id']}/cancel", json={})
