import importlib.util
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

_p = Path(__file__).resolve().parent.parent / "extensions" / "ricette-web" / "backend.py"
_spec = importlib.util.spec_from_file_location("ricette_web_backend_pp", _p)
rw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rw)

RECIPE = {"id": "stream-test", "name": "T", "host": "stream.example", "type": "html", "start_url": "https://stream.example/",
          "list": {"selector": "x", "item": "y", "title": "z", "link": "a@href"}, "detail": {"stream": "script"}}
VIX = "https://vixcloud.co/hls/77.m3u8"
HTML = '<h1>F</h1><script>player.setup({ file: "%s" });</script>' % VIX


class FakeGS:
    def __init__(self, app):
        self.cfg, self.routes, self.logs = SimpleNamespace(config_path=None, app=app), {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[(path.lstrip("/"), methods[0])] = fn
            return fn
        return deco

    def add_player(self, p):
        pass

    def job(self, *a, **k):
        pass


class Req:
    def __init__(self, pid):
        self.cookies = {"gs_profile": pid}


def make(tmp, monkeypatch, app=None):
    monkeypatch.setattr(rw, "load_recipes", lambda ext_dir=None: [RECIPE])
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: None)
    monkeypatch.setattr(rw.threading, "Thread", Rec)
    Rec.started.clear()
    gs = FakeGS(app if app is not None else {})
    gs.cfg.config_path = tmp / "config.toml"
    rw.register(gs)
    return gs, tmp / "ricette-web-cache" / "ricette.db"


class Rec(threading.Thread):
    started: list = []

    def start(self):
        Rec.started.append(self)
        super().start()


def seed(db, item_id="i1", pos=0.0, seen=0, table="items"):
    c = sqlite3.connect(db)
    if table == "items":
        c.execute("INSERT OR REPLACE INTO items (id, recipe_id, kind, title, url, stream_url, source, resume_pos, seen, updated)"
                  " VALUES (?, 'stream-test', 'film', 'Film', 'https://stream.example/d', '', 'ricette-web', ?, ?, 0)", (item_id, pos, seen))
    else:
        c.execute("INSERT OR REPLACE INTO episodes (id, parent_id, recipe_id, title, season, episode, source, resume_pos, seen, updated)"
                  " VALUES (?, 'p', 'stream-test', 'E1', 1, 1, 'ricette-web', ?, ?, 0)", (item_id, pos, seen))
    c.commit()
    c.close()


def join_all():
    for t in list(Rec.started):
        t.join(5)


def test_prefetch_riempie_la_cache_e_play_target_non_risolve_di_nuovo(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch)
    seed(db)
    calls, gate = [], threading.Event()

    def fetch(*a, **k):
        calls.append(1)
        gate.wait(5)
        return HTML.encode(), {}

    monkeypatch.setattr(rw, "fetch_url", fetch)
    assert gs.routes[("prefetch", "POST")](body={"id": "i1"}) == {"ok": True, "warming": True}  # risponde con il fetch ancora bloccato
    assert gs.routes[("prefetch", "POST")](body={"id": "i1"}) == {"ok": True, "warming": False}  # gia' in corso
    gate.set()
    join_all()
    assert len(calls) == 1
    out = gs.routes[("play_target", "GET")](id="i1")
    assert out["url"].startswith("/plugin-api/ricette-web/hls.m3u8") and len(calls) == 1
    assert gs.routes[("prefetch", "POST")](body={"id": "i1"}) == {"ok": True, "warming": False}  # cache fresca
    assert sqlite3.connect(db).execute("SELECT stream_url FROM items").fetchone()[0] == ""  # token mai nel db


def test_prefetch_id_sconosciuto_ed_errori(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch)
    assert gs.routes[("prefetch", "POST")](body={"id": "nope"}) == {"ok": False, "warming": False}
    assert gs.routes[("prefetch", "POST")](body={}) == {"ok": False, "warming": False}
    seed(db)

    def boom(*a, **k):
        raise OSError("rete")

    monkeypatch.setattr(rw, "fetch_url", boom)
    assert gs.routes[("prefetch", "POST")](body={"id": "i1"})["ok"] is True
    join_all()
    assert gs.routes[("prefetch", "POST")](body={"id": "i1"})["warming"] is True  # fallito: puo' ripartire


def test_progress_per_profilo_stesso_episodio(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch, {"profile": "a", "profiles": [{"id": "a"}, {"id": "b"}]})
    seed(db, "e1", table="episodes")
    sp = gs.routes[("set_progress", "POST")]
    sp(body={"id": "e1", "pos": 30}, request=Req("a"))
    sp(body={"id": "e1", "pos": 5, "seen": True}, request=Req("b"))
    pt = gs.routes[("play_target", "GET")]
    seed(db, "e1", table="episodes")  # le colonne non contano piu'
    c = sqlite3.connect(db)
    c.execute("UPDATE episodes SET url='https://stream.example/d', stream_url='https://x/v.mp4'")
    c.commit()
    assert pt(id="e1", request=Req("a"))["resume_pos"] == 30.0
    assert pt(id="e1", request=Req("b"))["resume_pos"] == 0.0
    assert pt(id="e1", request=Req("zzz"))["resume_pos"] == 30.0  # cookie non valido: profilo attivo "a"


def test_cookie_non_valido_usa_profilo_attivo(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch, {"profile": "a", "profiles": [{"id": "a"}]})
    seed(db, "e1", table="episodes")
    out = gs.routes[("set_progress", "POST")](body={"id": "e1", "pos": 9}, request=Req("zzz"))
    assert out["item"]["resume_pos"] == 9.0
    assert sqlite3.connect(db).execute("SELECT profile FROM progress").fetchall() == [("a",)]


def test_migrazione_al_profilo_attivo_idempotente(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch, {"profile": "a", "profiles": [{"id": "a"}]})
    seed(db, "i1", pos=12.0)
    seed(db, "e1", seen=1, table="episodes")
    rw._db_init(db, "a")
    rw._db_init(db, "a")
    rows = sorted(sqlite3.connect(db).execute("SELECT profile, item_id, pos, seen FROM progress").fetchall())
    assert rows == [("a", "e1", 0.0, 1), ("a", "i1", 12.0, 0)]
    # un altro profilo non eredita il legacy ormai assegnato
    assert rw.load_progress(sqlite3.connect(db), "b") == {}


def test_detail_non_perde_il_visto_rileggendo_le_stagioni(tmp_path, monkeypatch):
    gs, db = make(tmp_path, monkeypatch)
    c = sqlite3.connect(db)
    c.execute("INSERT INTO items (id, recipe_id, kind, title, url, source, updated) VALUES ('s4me:sc:7', 's4me:sc', 'serie', 'Serie', 'https://sc.example/titles/7', 'stream4me', 0)")
    c.commit()
    c.close()
    ep = {"id": "ep1", "title": "Episodio 1", "season": 1, "episode": 1, "stream_url": "", "url": "https://sc.example/w/1"}
    bridge = SimpleNamespace(scrape_channel_episodes=lambda *a, **k: [dict(ep)])
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: bridge)
    monkeypatch.setattr(rw.httpx, "get", lambda *a, **k: SimpleNamespace(status_code=200, text="<html/>"))
    d1 = gs.routes[("detail", "GET")](id="s4me:sc:7")
    assert d1["episodes"][0]["seen"] is False
    gs.routes[("set_progress", "POST")](body={"id": "ep1", "pos": 0, "seen": True})
    c = sqlite3.connect(db)
    c.execute("DELETE FROM meta")
    c.commit()
    c.close()
    d2 = gs.routes[("detail", "GET")](id="s4me:sc:7")
    assert d2["episodes"][0]["seen"] is True
