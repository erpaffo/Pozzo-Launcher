import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

_p = Path(__file__).resolve().parent.parent / "extensions" / "ricette-web" / "backend.py"
_spec = importlib.util.spec_from_file_location("ricette_web_backend", _p)
rw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rw)

VALID_TOML = """
name = "Film Classici"
host = "archive.org"
type = "html"
start_url = "https://archive.org/details/movies"

[list]
selector = ".movies"
item = ".card"
title = ".card-title"
link = "a.card-link@href"
cover = "img.card-img@src"

[detail]
title = "h1.title"
"""

HTML_FIXTURE = """
<div class="movies">
  <div class="card">
    <a class="card-link" href="/film/night-of-the-living-dead">
      <span class="card-title">Night of the Living Dead (1968)</span>
    </a>
    <img class="card-img" src="/posters/notld.jpg" />
  </div>
  <div class="card">
    <a class="card-link" href="https://archive.org/film/nosferatu">
      <span class="card-title">Nosferatu (1922)</span>
    </a>
    <img class="card-img" src="https://archive.org/posters/nosferatu.jpg" />
  </div>
</div>
"""

JSON_FIXTURE = """{
  "results": [
    {
      "name": "Carnival of Souls (1962)",
      "url": "/details/carnival_of_souls",
      "thumb": "/thumbs/carnival.jpg"
    },
    {
      "name": "Charade (1963)",
      "url": "https://api.archive.org/details/charade",
      "thumb": "https://api.archive.org/thumbs/charade.jpg"
    }
  ]
}"""

JSON_RECIPE = {
    "name": "Archive JSON",
    "host": "api.archive.org",
    "type": "json",
    "start_url": "https://api.archive.org/list",
    "list": {
        "selector": "results",
        "item": "results",
        "title": "name",
        "link": "url",
        "cover": "thumb",
    },
    "detail": {"title": "name"},
}


def test_parse_recipe_valid():
    r = rw.parse_recipe(VALID_TOML)
    assert r["name"] == "Film Classici"
    assert r["host"] == "archive.org"
    assert r["type"] == "html"
    assert r["id"] == "film-classici"
    assert r["list"]["item"] == ".card"
    assert r["detail"]["title"] == "h1.title"

    # Ricetta d'esempio reale inclusa nel repo
    recipe_file = Path(__file__).resolve().parent.parent / "extensions" / "ricette-web" / "recipe.toml"
    if recipe_file.exists():
        rf = rw.parse_recipe(recipe_file.read_text("utf-8"))
        assert rf["host"] == "archive.org"
        assert rf["type"] == "html"


def test_parse_recipe_unknown_field():
    with pytest.raises(ValueError, match="Campo ignoto"):
        rw.parse_recipe(VALID_TOML + "\ninvalid_key = 'bad'\n")
    with pytest.raises(ValueError, match="Campo ignoto in \\[list\\]"):
        rw.parse_recipe(VALID_TOML.replace('title = ".card-title"', 'title = ".card-title"\nextra = "bad"'))


def test_parse_recipe_code_rejected():
    with pytest.raises(ValueError, match="Campo vietato"):
        rw.parse_recipe(VALID_TOML + '\ncode = "print(1)"\n')
    with pytest.raises(ValueError, match="Campo vietato"):
        rw.parse_recipe(VALID_TOML + '\nscript = "evil()"\n')
    with pytest.raises(ValueError, match="Campo vietato"):
        rw.parse_recipe(VALID_TOML.replace('title = ".card-title"', 'title = ".card-title"\neval = "x"'))


def test_parse_recipe_missing_host():
    toml_no_host = "\n".join(line for line in VALID_TOML.splitlines() if not line.startswith("host ="))
    with pytest.raises(ValueError, match="Campo obbligatorio mancante: 'host'"):
        rw.parse_recipe(toml_no_host)
    with pytest.raises(ValueError, match="Campo obbligatorio mancante: 'host'"):
        rw.parse_recipe(VALID_TOML.replace('host = "archive.org"', 'host = ""'))


def test_apply_recipe_html():
    rec = rw.parse_recipe(VALID_TOML)
    items = rw.apply_recipe(rec, HTML_FIXTURE)
    assert len(items) == 2

    first = items[0]
    assert first["title"] == "Night of the Living Dead (1968)"
    assert first["year"] == 1968
    assert first["kind"] == "film"
    assert first["source"] == "ricette-web"
    assert first["seen"] is False
    assert first["resume_pos"] == 0.0
    assert first["poster"] == "https://archive.org/posters/notld.jpg"
    assert len(first["id"]) == 16

    second = items[1]
    assert second["title"] == "Nosferatu (1922)"
    assert second["year"] == 1922
    assert second["poster"] == "https://archive.org/posters/nosferatu.jpg"


def test_apply_recipe_json():
    items = rw.apply_recipe(JSON_RECIPE, JSON_FIXTURE)
    assert len(items) == 2

    c = items[0]
    assert c["title"] == "Carnival of Souls (1962)"
    assert c["year"] == 1962
    assert c["poster"] == "https://api.archive.org/thumbs/carnival.jpg"
    assert c["source"] == "ricette-web"
    assert c["kind"] == "film"
    assert len(c["id"]) == 16

    d = items[1]
    assert d["title"] == "Charade (1963)"
    assert d["year"] == 1963
    assert d["poster"] == "https://api.archive.org/thumbs/charade.jpg"


# ---------------------------------------------------------------- flussi e player esterno
DETAIL_RECIPE = {
    "id": "stream-test",
    "name": "Stream Test",
    "host": "stream.example",
    "type": "html",
    "start_url": "https://stream.example/list",
    "list": {"selector": ".c", "item": ".c", "title": ".t", "link": "a@href"},
    "detail": {"title": "h1", "stream_url": 'regex:file:\\s*"(https://[^"]+\\.m3u8)"'},
}

DETAIL_HTML = """
<h1>Film</h1>
<script>player.setup({ file: "https://cdn.stream.example/hls/master.m3u8" });</script>
"""


def test_is_direct_stream():
    assert rw.is_direct_stream("https://cdn.example/film.mp4") is True
    assert rw.is_direct_stream("https://cdn.example/film.MP4?token=abc#t=10") is True  # query e fragment ignorati
    assert rw.is_direct_stream("https://cdn.example/audio.mp3") is True
    assert rw.is_direct_stream("https://cdn.example/hls/master.m3u8") is False
    assert rw.is_direct_stream("https://stream.example/watch/123") is False
    assert rw.is_direct_stream("") is False


def test_apply_detail_stream_url_regex(monkeypatch):
    """Il prefisso «regex:» pesca il flusso nascosto negli script JS della pagina."""
    monkeypatch.setattr(rw, "extract_streams", lambda text, base_url="": [])
    out = rw.apply_detail(DETAIL_RECIPE, DETAIL_HTML, "https://stream.example/detail/1")
    assert out["stream_url"] == "https://cdn.stream.example/hls/master.m3u8"


def test_apply_detail_flusso_automatico(monkeypatch):
    """Senza selettore che trova il flusso, si estrae da <video><source> con la regex locale."""
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: None)
    recipe = {**DETAIL_RECIPE, "detail": {"title": "h1"}}
    html = '<h1>Film</h1><video controls><source src="/media/film.mp4" type="video/mp4"></video>'
    out = rw.apply_detail(recipe, html, "https://stream.example/detail/1")
    assert out["stream_url"] == "https://stream.example/media/film.mp4"


# ---------------------------------------------------------------- rotte (host finto)
class FakeGS:
    """Sostituto di PluginAPI: raccoglie rotte e job invece di toccare FastAPI."""

    def __init__(self, cfg):
        self.cfg, self.routes, self.logs = cfg, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[(path.lstrip("/"), methods[0])] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self.routes[(path, "GET")](**kw)

    def post(self, path, body=None, **kw):
        return self.routes[(path, "POST")](body=body, **kw)

    def add_player(self, player):
        pass

    def job(self, *a, **k):
        pass


def make_gs(tmp: Path, monkeypatch, recipe: dict | None = None):
    monkeypatch.setattr(rw, "load_recipes", lambda ext_dir=None: [recipe or DETAIL_RECIPE])
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: None)
    gs = FakeGS(SimpleNamespace(config_path=tmp / "config.toml", app={}))
    rw.register(gs)
    return gs


def db(tmp: Path) -> Path:
    return tmp / "ricette-web-cache" / "ricette.db"


def seed_item(tmp: Path, item_id: str = "i1", url: str = "https://stream.example/detail/1",
              stream_url: str = "") -> None:
    conn = sqlite3.connect(db(tmp))
    conn.execute("INSERT OR REPLACE INTO items (id, recipe_id, kind, title, url, stream_url, source, resume_pos, seen, updated)"
                 " VALUES (?, 'stream-test', 'film', 'Film', ?, ?, 'ricette-web', 12.0, 0, 0)", (item_id, url, stream_url))
    conn.commit()
    conn.close()


def test_play_target_risolve_pigramente(tmp, monkeypatch):
    gs = make_gs(tmp, monkeypatch)
    seed_item(tmp)
    monkeypatch.setattr(rw, "fetch_url", lambda *a, **k: (DETAIL_HTML.encode(), {}))

    out = gs.get("play_target", id="i1")
    assert out == {"url": "https://cdn.stream.example/hls/master.m3u8", "resume_pos": 12.0, "external": False}

    # il flusso è stato salvato nel DB: la seconda chiamata non riscarica la pagina
    calls = []

    def no_fetch(*a, **k):
        calls.append(a)
        return b"", {}

    monkeypatch.setattr(rw, "fetch_url", no_fetch)
    assert gs.get("play_target", id="i1")["url"] == "https://cdn.stream.example/hls/master.m3u8"
    assert calls == []

    # un .mp4 salvato in tabella resta nel player integrato
    seed_item(tmp, "i2", stream_url="https://cdn.example/film.mp4")
    assert gs.get("play_target", id="i2")["external"] is False


def test_rotta_external_player_o_browser(tmp, monkeypatch):
    gs = make_gs(tmp, monkeypatch)
    seed_item(tmp, "i1", stream_url="https://cdn.stream.example/hls/master.m3u8")

    launched = []
    monkeypatch.setattr(rw.shutil, "which", lambda name: "/usr/bin/mpv" if name == "mpv" else None)
    monkeypatch.setattr(rw.subprocess, "Popen", lambda args, **kw: launched.append(args))
    out = gs.post("external", {"id": "i1"})
    assert out["ok"] is True and out["player"] == "/usr/bin/mpv"
    assert launched == [["/usr/bin/mpv", "https://cdn.stream.example/hls/master.m3u8"]]

    monkeypatch.setattr(rw.shutil, "which", lambda name: None)
    opened = []
    monkeypatch.setattr(rw.webbrowser, "open", lambda url: opened.append(url))
    out = gs.post("external", {"id": "i1"})
    assert out["player"] == "" and opened == ["https://cdn.stream.example/hls/master.m3u8"]

    seed_item(tmp, "i2", url="file:///etc/passwd", stream_url="")
    with pytest.raises(HTTPException) as err:  # solo http(s): niente percorsi locali dal corpo JSON
        gs.post("external", {"id": "i2"})
    assert err.value.status_code == 400


class FakeBridge:
    """kodi_bridge.py finto: installa una cartella addon e restituisce un canale."""

    def __init__(self):
        self.sources = []

    def parse_addon_xml(self, xml_text: str) -> dict:
        return rw._mini_addon_xml(xml_text)

    def install_kodi_addon(self, source, addons_root: Path) -> dict:
        self.sources.append(source)
        d = addons_root / "plugin.video.test"
        d.mkdir(parents=True, exist_ok=True)
        (d / "addon.xml").write_text(
            '<addon id="plugin.video.test" name="Test" version="1.0"><summary>Prova</summary></addon>', "utf-8")
        return {"id": "plugin.video.test", "name": "Test", "version": "1.0", "summary": "Prova",
                "channels": [{"id": "c1", "name": "Canale Uno", "summary": "desc",
                              "poster": "https://stream.example/p.png"}]}


def test_rotte_kodi_addons(tmp, monkeypatch):
    gs = make_gs(tmp, monkeypatch)
    assert gs.get("kodi_addons") == {"addons": []}
    with pytest.raises(HTTPException) as err:  # senza kodi_bridge.py non si installa nulla
        gs.post("kodi_addons", {"url": "https://github.com/Stream4me/addon"})
    assert err.value.status_code == 503

    bridge = FakeBridge()
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: bridge)
    out = gs.post("kodi_addons", {"url": "https://github.com/Stream4me/addon"})
    assert out["ok"] is True and out["addon"]["id"] == "plugin.video.test" and out["items"] == 1
    assert bridge.sources == ["https://github.com/Stream4me/addon"]

    assert [(a["id"], a["name"]) for a in gs.get("kodi_addons")["addons"]] == [("plugin.video.test", "Test")]
    conn = sqlite3.connect(db(tmp))
    try:
        assert conn.execute("SELECT title, source FROM items WHERE recipe_id='kodi:plugin.video.test'").fetchall() \
            == [("Canale Uno", "kodi")]
    finally:
        conn.close()

    assert gs.post("kodi_addons", {"remove": "plugin.video.test"})["removed"] == "plugin.video.test"
    assert gs.get("kodi_addons")["addons"] == []
    with pytest.raises(HTTPException) as err:  # nessun percorso arbitrario dal corpo JSON
        gs.post("kodi_addons", {"remove": "../../etc"})
    assert err.value.status_code == 400

