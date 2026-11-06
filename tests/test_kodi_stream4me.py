"""Test per Stream4me e Kodi Bridge (Task 3 Pozzo Launcher).

Verifica:
- Costanti e parsing delle sezioni Stream4me (get_stream4me_sections).
- Endpoint /plugin-api/ricette-web/stream4me/sections (preset, sample e mock).
- Normalizzazione in MediaItem con source='ricette-web'.
- Risoluzione flussi .m3u8 e .mp4 in play_target.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Caricamento dinamico dei moduli di estensione
_EXT_DIR = Path(__file__).resolve().parent.parent / "extensions" / "ricette-web"

_kb_spec = importlib.util.spec_from_file_location("kodi_bridge", _EXT_DIR / "kodi_bridge.py")
kb = importlib.util.module_from_spec(_kb_spec)
_kb_spec.loader.exec_module(kb)

_rw_spec = importlib.util.spec_from_file_location("ricette_web", _EXT_DIR / "backend.py")
rw = importlib.util.module_from_spec(_rw_spec)
_rw_spec.loader.exec_module(rw)


class FakeGS:
    """Simulatore host PluginAPI per test delle rotte backend."""

    def __init__(self, cfg):
        self.cfg, self.routes, self.logs = cfg, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[(path.lstrip("/"), methods[0])] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self.routes[(path.lstrip("/"), "GET")](**kw)

    def post(self, path, body=None, **kw):
        return self.routes[(path.lstrip("/"), "POST")](body=body, **kw)

    def add_player(self, player):
        pass

    def add_scraper(self, scraper):
        pass

    def job(self, *a, **k):
        pass


def make_gs(tmp: Path, monkeypatch, auto_offline: bool = True):
    """Configura FakeGS con cache pulita e bridge attivo (offline per velocità nei test)."""
    monkeypatch.setattr(rw, "load_recipes", lambda ext_dir=None: [])
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: kb)
    if auto_offline:
        monkeypatch.setattr(kb, "install_kodi_addon", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")))
    gs = FakeGS(SimpleNamespace(config_path=tmp / "config.toml", app={}))
    rw.register(gs)
    return gs


def create_sample_addon(dest: Path) -> Path:
    """Crea una struttura valida di addon Stream4me con canali per ciascuna categoria."""
    addon_dir = dest / "plugin.video.stream4me"
    addon_dir.mkdir(parents=True, exist_ok=True)
    channels_dir = addon_dir / "channels"
    channels_dir.mkdir(parents=True, exist_ok=True)

    addon_xml = """<?xml version="1.0" encoding="UTF-8"?>
<addon id="plugin.video.stream4me" name="Stream4me" version="1.0.4">
  <requires><import addon="xbmc.python" version="3.0.0"/></requires>
  <extension point="xbmc.python.pluginsource" library="default.py"/>
</addon>
"""
    (addon_dir / "addon.xml").write_text(addon_xml, encoding="utf-8")

    channels = {
        "cinema_uno.json": {
            "id": "cinema_uno",
            "name": "Cinema Uno",
            "host": "https://cinema.example",
            "categories": ["Film", "Novita"],
            "find_videos": "/search?q=%s",
        },
        "serie_hub.json": {
            "id": "serie_hub",
            "name": "Serie Hub",
            "host": "https://series.example",
            "categories": ["Serie TV", "Show"],
            "find_videos": "/search?q=%s",
        },
        "tv_live.json": {
            "id": "tv_live",
            "name": "TV Live Italia",
            "host": "https://live.example",
            "categories": ["Canali TV", "Live Streaming"],
            "find_videos": "/live/canali",
        },
        "anime_land.json": {
            "id": "anime_land",
            "name": "Anime Land",
            "host": "https://anime.example",
            "categories": ["Anime", "Animazione"],
            "find_videos": "/anime/search?q=%s",
        },
        "misto.json": {
            "id": "misto_box",
            "name": "Misto Box",
            "host": "https://misto.example",
            "categories": ["Film", "Serie TV"],
            "find_videos": "/search?q=%s",
        },
    }

    for filename, data in channels.items():
        (channels_dir / filename).write_text(json.dumps(data), encoding="utf-8")

    return addon_dir


# ---------------------------------------------------------------- Test Parsing Sezioni
def test_stream4me_default_url():
    """La costante STREAM4ME_DEFAULT_URL deve puntare al repo Stream4me."""
    assert hasattr(kb, "STREAM4ME_DEFAULT_URL")
    assert "Stream4me" in kb.STREAM4ME_DEFAULT_URL


def test_get_stream4me_sections_preset_simulato():
    """Senza cartella addon, get_stream4me_sections restituisce le categorie simulate."""
    sections = kb.get_stream4me_sections(None)
    assert isinstance(sections, dict)
    assert set(sections.keys()) == {"film", "serie", "canali", "animazione"}

    for key, items in sections.items():
        assert len(items) > 0
        for item in items:
            assert item["source"] == "ricette-web"
            assert item["source_label"] == "Stream4me"
            assert "id" in item and item["id"]
            assert "title" in item and item["title"]
            assert item.get("kind") in ("film", "episodio")
            assert "url" in item or "stream_url" in item


def test_get_stream4me_sections_da_cartella_canali(tmp_path):
    """Estrae e cataloga correttamente i canali presenti nell'addon."""
    addon_dir = create_sample_addon(tmp_path)
    sections = kb.get_stream4me_sections(addon_dir)

    film_titles = [it["title"] for it in sections["film"]]
    assert "Cinema Uno" in film_titles
    assert "Misto Box" in film_titles

    serie_titles = [it["title"] for it in sections["serie"]]
    assert "Serie Hub" in serie_titles
    assert "Misto Box" in serie_titles  # canale condiviso

    canali_titles = [it["title"] for it in sections["canali"]]
    assert "TV Live Italia" in canali_titles

    anime_titles = [it["title"] for it in sections["animazione"]]
    assert "Anime Land" in anime_titles


def test_get_stream4me_sections_fallback_sezioni_vuote(tmp_path):
    """Se l'addon ha solo canali film, le altre sezioni non restano vuote (preset fallback)."""
    addon_dir = tmp_path / "solo_film"
    addon_dir.mkdir(parents=True, exist_ok=True)
    ch_dir = addon_dir / "channels"
    ch_dir.mkdir(parents=True, exist_ok=True)

    (addon_dir / "addon.xml").write_text(
        '<addon id="plugin.video.stream4me" name="Stream4me" version="1.0"><requires/></addon>',
        encoding="utf-8"
    )
    (ch_dir / "film_only.json").write_text(
        json.dumps({"id": "only_film", "name": "Solo Film", "host": "https://f.example", "categories": ["Film"]}),
        encoding="utf-8"
    )

    sections = kb.get_stream4me_sections(addon_dir)
    assert any(it["title"] == "Solo Film" for it in sections["film"])
    assert len(sections["serie"]) > 0
    assert len(sections["canali"]) > 0
    assert len(sections["animazione"]) > 0


# ---------------------------------------------------------------- Test Endpoint Sections
def test_endpoint_stream4me_sections_default(tmp_path, monkeypatch):
    """L'endpoint /stream4me/sections restituisce le sezioni con preset e popola il DB."""
    gs = make_gs(tmp_path, monkeypatch)
    res = gs.get("stream4me/sections")

    assert "sections" in res
    section_ids = [s["id"] for s in res["sections"]]
    assert "stream4me-film" in section_ids
    assert "stream4me-serie" in section_ids
    assert "stream4me-live" in section_ids
    assert "stream4me-animazione" in section_ids

    # Tutti gli item devono essere normalizzati con source='ricette-web'
    all_items = [it for sec in res["sections"] for it in sec["items"]]
    assert len(all_items) > 0
    assert all(it["source"] == "ricette-web" for it in all_items)
    assert all(it.get("source_label") == "Stream4me" for it in all_items)

    # Verifica che siano stati salvati nel database locale
    db_path = tmp_path / "ricette-web-cache" / "ricette.db"
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM items WHERE recipe_id='stream4me'").fetchone()[0]
        unique_ids = {it["id"] for it in all_items}
        assert count == len(unique_ids)
    finally:
        conn.close()


def test_endpoint_stream4me_sections_con_addon_esistente(tmp_path, monkeypatch):
    """L'endpoint usa l'addon presente in addons_root se già installato."""
    gs = make_gs(tmp_path, monkeypatch)
    addons_root = tmp_path / "ricette-web-cache" / "kodi-addons"
    create_sample_addon(addons_root)

    res = gs.get("stream4me/sections")
    sections_by_id = {s["id"]: s for s in res["sections"]}

    film_titles = [it["title"] for it in sections_by_id["stream4me-film"]["items"]]
    assert "Cinema Uno" in film_titles

    live_titles = [it["title"] for it in sections_by_id["stream4me-live"]["items"]]
    assert "TV Live Italia" in live_titles


def test_endpoint_stream4me_sections_auto_install_mock(tmp_path, monkeypatch):
    """GET /stream4me/sections NON scarica da GitHub; POST /stream4me/install installa esplicitamente."""
    gs = make_gs(tmp_path, monkeypatch, auto_offline=False)
    install_calls = []

    def mock_install(url, root):
        install_calls.append(url)
        return {"id": "plugin.video.s4me", "path": str(create_sample_addon(root))}

    monkeypatch.setattr(kb, "install_kodi_addon", mock_install)

    res = gs.get("stream4me/sections")
    assert install_calls == []
    assert len(res["sections"]) >= 3

    inst = gs.post("stream4me/install", {})
    assert inst["ok"] is True
    assert install_calls == [kb.STREAM4ME_DEFAULT_URL]


def test_endpoint_stream4me_sections_install_fallita_fallback(tmp_path, monkeypatch):
    """Se non installato o offline, /stream4me/sections fa fallback immediato senza errore 500."""
    gs = make_gs(tmp_path, monkeypatch, auto_offline=False)

    def failing_install(*a, **k):
        raise ConnectionError("Rete non disponibile")

    monkeypatch.setattr(kb, "install_kodi_addon", failing_install)

    res = gs.get("stream4me/sections")
    assert "sections" in res
    assert len(res["sections"]) >= 3


def test_endpoint_stream4me_sections_senza_kodi_bridge(tmp_path, monkeypatch):
    """Funziona regolarmente anche se kodi_bridge non è disponibile."""
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: None)
    gs = FakeGS(SimpleNamespace(config_path=tmp_path / "config.toml", app={}))
    rw.register(gs)

    res = gs.get("stream4me/sections")
    assert "sections" in res
    assert len(res["sections"]) == 4


# ---------------------------------------------------------------- Test Risoluzione Flussi (play_target)
def test_stream4me_play_target_flusso_diretto(tmp_path, monkeypatch):
    """Item con stream_url già definito restituisce il flusso senza richieste esterne."""
    gs = make_gs(tmp_path, monkeypatch)
    gs.get("stream4me/sections")  # popola DB

    # Inseriamo o usiamo item con flusso diretto .m3u8
    conn = sqlite3.connect(tmp_path / "ricette-web-cache" / "ricette.db")
    conn.execute(
        "INSERT OR REPLACE INTO items (id, recipe_id, kind, title, url, stream_url, source) VALUES "
        "('stream4me:canali:live-tv', 'stream4me', 'film', 'Live TV', 'https://live.example', 'https://cdn.example/live/master.m3u8', 'ricette-web')"
    )
    conn.commit()
    conn.close()

    target = gs.get("play_target", id="stream4me:canali:live-tv")
    assert target["url"] == "https://cdn.example/live/master.m3u8"
    assert target["resume_pos"] == 0.0
    assert target["external"] is False  # .m3u8 va a hls.js nel player integrato

    # Item con .mp4 riproducibile direttamente
    conn = sqlite3.connect(tmp_path / "ricette-web-cache" / "ricette.db")
    conn.execute(
        "INSERT OR REPLACE INTO items (id, recipe_id, kind, title, url, stream_url, source) VALUES "
        "('stream4me:film:diretto', 'stream4me', 'film', 'Film Diretto', 'https://film.example', 'https://cdn.example/film.mp4', 'ricette-web')"
    )
    conn.commit()
    conn.close()

    target_mp4 = gs.get("play_target", id="stream4me:film:diretto")
    assert target_mp4["url"] == "https://cdn.example/film.mp4"
    assert target_mp4["external"] is False


def test_stream4me_play_target_risoluzione_web(tmp_path, monkeypatch):
    """play_target per un item con URL pagina web estrae il flusso con extract_stream_urls."""
    gs = make_gs(tmp_path, monkeypatch)
    gs.get("stream4me/sections")

    html_content = """
    <html><body>
      <video src="https://cdn.example/streaming/video.mp4" title="Video"></video>
    </body></html>
    """

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_content
    monkeypatch.setattr(rw.httpx, "get", lambda *a, **k: mock_resp)

    # nuove-uscite ha stream_url='' e url='https://stream4me.example/film/nuove-uscite'
    target = gs.get("play_target", id="stream4me:film:nuove-uscite")
    assert target["url"] == "https://cdn.example/streaming/video.mp4"
    assert target["external"] is False  # .mp4 è riproducibile internamente

    # Verifica persistenza nel DB: seconda chiamata non riscarica
    monkeypatch.setattr(rw.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Non deve scaricare")))
    cached_target = gs.get("play_target", id="stream4me:film:nuove-uscite")
    assert cached_target["url"] == "https://cdn.example/streaming/video.mp4"


def test_stream4me_play_target_risoluzione_plugin_url(tmp_path, monkeypatch):
    """play_target per handle plugin:// risolve tramite run_kodi_addon_directory."""
    gs = make_gs(tmp_path, monkeypatch)
    addons_root = tmp_path / "ricette-web-cache" / "kodi-addons"
    create_sample_addon(addons_root)

    # Inseriamo un item con plugin://
    conn = sqlite3.connect(tmp_path / "ricette-web-cache" / "ricette.db")
    conn.execute(
        "INSERT INTO items (id, recipe_id, kind, title, url, stream_url, source) VALUES "
        "('stream4me:plugin:item', 'stream4me', 'film', 'Plugin Item', 'plugin://plugin.video.stream4me/play?id=1', '', 'ricette-web')"
    )
    conn.commit()
    conn.close()

    resolved_item = {"stream_url": "https://cdn.example/resolved/master.m3u8"}
    monkeypatch.setattr(kb, "run_kodi_addon_directory", lambda *a, **k: [resolved_item])

    target = gs.get("play_target", id="stream4me:plugin:item")
    assert target["url"] == "https://cdn.example/resolved/master.m3u8"
    assert target["external"] is False


# ---------------------------------------------------------------- Test Provider Browser, Scraper & Pin
def test_find_stream4me_dir_s4me(tmp_path):
    """find_stream4me_dir trova plugin.video.s4me oltre a plugin.video.stream4me."""
    addons_root = tmp_path / "kodi-addons"
    s4me = addons_root / "plugin.video.s4me"
    (s4me / "channels").mkdir(parents=True)
    (s4me / "channels.json").write_text('{"direct": {"cb01": "https://cb01.example"}}', encoding="utf-8")

    assert kb.find_stream4me_dir(addons_root) == s4me
    assert kb.find_stream4me_dir(tmp_path / "inesistente") is None


def test_list_stream4me_providers_e_menus(tmp_path):
    """list_stream4me_providers estrae canali attivi, host da channels.json e menu da .py."""
    kb._clear_stream4me_caches()
    s4me = tmp_path / "plugin.video.s4me"
    ch_dir = s4me / "channels"
    ch_dir.mkdir(parents=True)
    (s4me / "channels.json").write_text(
        json.dumps({"direct": {"animesaturn": "https://www.animesaturn.cx", "spento": "https://spento.example"}}),
        encoding="utf-8",
    )
    (ch_dir / "animesaturn.json").write_text(
        json.dumps({"id": "animesaturn", "name": "AnimeSaturn", "active": True, "categories": ["anime"]}),
        encoding="utf-8",
    )
    (ch_dir / "animesaturn.py").write_text(
        """
def mainlist(item):
    return [('Ultimi Episodi', ['/ ultimiepisodi', 'peliculas']), ('In Corso', ['/incorso', 'peliculas'])]
""",
        encoding="utf-8",
    )
    (ch_dir / "spento.json").write_text(
        json.dumps({"id": "spento", "name": "Spento", "active": False, "categories": ["movie"]}),
        encoding="utf-8",
    )

    provs = kb.list_stream4me_providers(s4me, only_active=True)
    assert len(provs) == 1
    p = provs[0]
    assert p["id"] == "animesaturn"
    assert p["name"] == "AnimeSaturn"
    assert p["host"] == "https://www.animesaturn.cx"
    assert "anime" in p["categories"]
    assert any(m["label"] == "In Corso" and m["path"] == "/incorso" for m in p["menus"])

    all_provs = kb.list_stream4me_providers(s4me, only_active=False)
    assert len(all_provs) == 2


def test_scrape_channel_items_patron_e_bs4():
    """scrape_channel_items estrae card sia tramite patron regex sia con BeautifulSoup fallback."""
    html_cards = """
    <html><body>
      <nav><a href="/">Home</a><a href="/login">Login</a><a href="/page/2">2</a></nav>
      <div class="movies-list">
        <article class="post">
          <a href="/film/dune-parte-due-2024/">
            <img data-src="/img/dune2.jpg" alt="Dune Parte Due (2024)" />
            <h2 class="entry-title">Dune - Parte Due (2024)</h2>
          </a>
        </article>
        <article class="post">
          <a href="/serie-tv/the-last-of-us/">
            <img src="https://img.example/tlou.jpg" />
            <h3 class="title">The Last of Us - Serie TV (2023)</h3>
          </a>
        </article>
      </div>
    </body></html>
    """
    items = kb.scrape_channel_items(html_cards, "https://cb01.example", channel_id="cb01", channel_name="CB01")
    assert len(items) == 2
    dune = next(i for i in items if "Dune" in i["title"])
    assert dune["kind"] == "film"
    assert dune["year"] == 2024
    assert dune["poster"] == "https://cb01.example/img/dune2.jpg"
    assert dune["url"] == "https://cb01.example/film/dune-parte-due-2024/"
    assert dune["source"] == "stream4me"

    tlou = next(i for i in items if "Last of Us" in i["title"])
    assert tlou["kind"] == "episodio"
    assert tlou["year"] == 2023


def test_scrape_channel_episodes_e_detail_integration(tmp_path, monkeypatch):
    """scrape_channel_episodes estrae gli episodi e media_detail li popola nel DB."""
    detail_html = """
    <html><body>
      <div class="episodes">
        <a href="https://serie.example/ep/1x01">1x01 - L'inizio</a>
        <a href="https://serie.example/ep/1x02">1x02 - Il viaggio</a>
      </div>
      <iframe src="https://player.example/embed/serie1"></iframe>
    </body></html>
    """
    eps = kb.scrape_channel_episodes(detail_html, "https://serie.example/show/1", series_title="Show", channel_id="euro")
    assert len(eps) == 2
    assert eps[0]["season"] == 1 and eps[0]["episode"] == 1
    assert eps[1]["season"] == 1 and eps[1]["episode"] == 2

    gs = make_gs(tmp_path, monkeypatch)
    gs.post("stream4me/pin", {
        "item": {
            "id": "s4me:euro:show1",
            "title": "Show Test",
            "kind": "episodio",
            "url": "https://serie.example/show/1",
            "poster": "https://serie.example/p.jpg",
        }
    })

    mock_resp = MagicMock(status_code=200, text=detail_html)
    monkeypatch.setattr(rw.httpx, "get", lambda *a, **k: mock_resp)

    det = gs.get("detail", id="s4me:euro:show1")
    assert det["title"] == "Show Test"
    assert "episodes" in det and len(det["episodes"]) == 2
    assert det["episodes"][0]["episode"] == 1


def test_routes_stream4me_providers_browse_and_pin(tmp_path, monkeypatch):
    """Verifica le rotte /stream4me/providers, /stream4me/browse, /stream4me/pin, /stream4me/pinned, /stream4me/unpin."""
    kb._clear_stream4me_caches()
    gs = make_gs(tmp_path, monkeypatch)
    addons_root = tmp_path / "ricette-web-cache" / "kodi-addons"
    create_sample_addon(addons_root)

    prov_res = gs.get("stream4me/providers")
    assert prov_res["installed"] is True
    assert len(prov_res["providers"]) >= 4

    sample_html = """
    <div class="list">
      <article><a href="/watch/matrix-1999"><img src="/m.jpg"/><h2>Matrix (1999)</h2></a></article>
      <article><a href="/watch/inception-2010"><img src="/i.jpg"/><h2>Inception (2010)</h2></a></article>
    </div>
    """
    monkeypatch.setattr(kb.httpx, "get", lambda *a, **k: MagicMock(status_code=200, text=sample_html, raise_for_status=lambda: None))

    b_res = gs.get("stream4me/browse", channel="cinema_uno")
    assert b_res["provider"]["id"] == "cinema_uno"
    assert len(b_res["items"]) == 2

    # Pin di un item alla Home
    first_item = b_res["items"][0]
    pin_res = gs.post("stream4me/pin", {"item": first_item})
    assert pin_res["ok"] is True
    assert pin_res["item"]["pinned"] is True

    pinned_list = gs.get("stream4me/pinned")["items"]
    assert len(pinned_list) == 1
    assert pinned_list[0]["id"] == first_item["id"]

    unpin_res = gs.post("stream4me/unpin", {"id": first_item["id"]})
    assert unpin_res["ok"] is True
    assert gs.get("stream4me/pinned")["items"] == []


def test_scrape_channel_items_anime_classification():
    """scrape_channel_items su un canale anime (animesaturn/animeworld) imposta kind='episodio', series=<title> e genre='Anime'."""
    anime_html = """
    <div class="anime-list">
      <div class="anime-card">
        <a href="/play/frieren-oltre-la-fine-del-viaggio">
          <img src="/img/frieren.jpg" />
          <h3>Frieren - Oltre la fine del viaggio</h3>
        </a>
      </div>
      <div class="anime-card">
        <a href="/play/solo-leveling-2024">
          <img src="/img/solo.jpg" />
          <h3>Solo Leveling (2024)</h3>
        </a>
      </div>
    </div>
    """
    items = kb.scrape_channel_items(
        anime_html,
        "https://www.animesaturn.cx",
        channel_id="animesaturn",
        channel_name="AnimeSaturn",
        channel_categories=["anime"],
    )
    assert len(items) == 2
    for it in items:
        assert it["kind"] == "episodio"
        assert it["series"] == it["title"]
        assert it["season"] == 1
        assert it["episode"] == 1
        assert it["genre"] == "Anime"
        assert "anime" in it["overview"].lower()


def test_pin_library_integration_and_priority_in_media_list(tmp_path, monkeypatch):
    """POST /stream4me/pin salva film, serie o anime nella libreria e GET /list li restituisce per primi."""
    gs = make_gs(tmp_path, monkeypatch)

    # Popoliamo il DB con alcuni item non pinnati per verificare la priorità in media_list
    gs.get("stream4me/sections")

    # Pin di un anime
    anime_item = {
        "id": "s4me:animeworld:frieren",
        "title": "Frieren",
        "url": "https://animeworld.example/play/frieren",
        "channel_id": "animeworld",
        "channel_name": "AnimeWorld",
        "genre": "Anime",
    }
    res_anime = gs.post("stream4me/pin", {"item": anime_item})
    assert res_anime["ok"] is True
    assert res_anime["item"]["kind"] == "episodio"
    assert res_anime["item"]["series"] == "Frieren"
    assert "anime" in res_anime["item"]["overview"].lower()

    # Pin di una serie TV
    serie_item = {
        "id": "s4me:eurostreaming:tlou",
        "title": "The Last of Us",
        "kind": "episodio",
        "series": "The Last of Us",
        "url": "https://euro.example/serie/tlou",
    }
    res_serie = gs.post("stream4me/pin", {"item": serie_item})
    assert res_serie["ok"] is True
    assert res_serie["item"]["kind"] == "episodio"
    assert res_serie["item"]["series"] == "The Last of Us"

    # Pin di un film
    film_item = {
        "id": "s4me:cb01:oppenheimer",
        "title": "Oppenheimer",
        "kind": "film",
        "url": "https://cb01.example/film/oppenheimer",
    }
    res_film = gs.post("stream4me/pin", {"item": film_item})
    assert res_film["ok"] is True
    assert res_film["item"]["kind"] == "film"

    # Verifica che GET /list restituisca gli elementi pinnati per primi anche con limit ridotto
    listed = gs.get("list", limit=3)
    assert len(listed) == 3
    listed_ids = {it["id"] for it in listed}
    assert listed_ids == {"s4me:animeworld:frieren", "s4me:eurostreaming:tlou", "s4me:cb01:oppenheimer"}

    frieren_out = next(it for it in listed if it["id"] == "s4me:animeworld:frieren")
    assert frieren_out["kind"] == "episodio"
    assert frieren_out["series"] == "Frieren"
    assert frieren_out["season"] == 1
    assert frieren_out["episode"] == 1
    assert "anime" in frieren_out["overview"].lower()


def test_stream4me_providers_add_enable_and_remove(tmp_path, monkeypatch):
    """Verifica l'aggiunta di provider personalizzati, l'abilitazione di canali inattivi e la rimozione di provider."""
    kb._clear_stream4me_caches()
    gs = make_gs(tmp_path, monkeypatch)
    addons_root = tmp_path / "ricette-web-cache" / "kodi-addons"
    addon_dir = create_sample_addon(addons_root)
    (addon_dir / "channels" / "inattivo.json").write_text(
        json.dumps({"id": "inattivo_ch", "name": "Canale Inattivo", "host": "https://inattivo.example", "active": False, "categories": ["movie"]}),
        encoding="utf-8",
    )

    res = gs.get("stream4me/providers")
    active_ids = {p["id"] for p in res["providers"]}
    inactive_ids = {p["id"] for p in res["available_inactive"]}
    assert "cinema_uno" in active_ids
    assert "inattivo_ch" not in active_ids
    assert "inattivo_ch" in inactive_ids

    # Abilita un provider built-in inattivo
    en_res = gs.post("stream4me/providers", {"enable": "inattivo_ch"})
    assert en_res["ok"] is True
    assert "inattivo_ch" in {p["id"] for p in en_res["providers"]}
    assert "inattivo_ch" not in {p["id"] for p in en_res["available_inactive"]}

    # Aggiunge un provider personalizzato tramite URL
    add_res = gs.post("stream4me/providers", {
        "name": "Mio Anime Custom",
        "host": "https://mioanime.example",
        "categories": ["anime"],
    })
    assert add_res["ok"] is True
    assert add_res["provider"]["id"] == "mio-anime-custom"
    assert add_res["provider"]["search_url"] == "https://mioanime.example/?s={query}"
    assert "mio-anime-custom" in {p["id"] for p in add_res["providers"]}

    # Rimuove un provider built-in (tasto destro -> Rimuovi)
    rem_res = gs.post("stream4me/providers/remove", {"id": "cinema_uno"})
    assert rem_res["ok"] is True
    assert rem_res["removed"] == "cinema_uno"
    assert "cinema_uno" not in {p["id"] for p in rem_res["providers"]}
    assert "cinema_uno" in {p["id"] for p in rem_res["available_inactive"]}

    # Rimuove il provider personalizzato
    rem_custom = gs.post("stream4me/providers/remove", {"id": "mio-anime-custom"})
    assert rem_custom["ok"] is True
    assert "mio-anime-custom" not in {p["id"] for p in rem_custom["providers"]}


def test_animeworld_scrape_items_real_title_and_filter_noise():
    """AnimeWorld HTML: estrae il vero titolo con (ITA) invece del badge 'DUB' e filtra link social/navigazione."""
    aw_html = """
    <html><body>
      <div class="header">
        <div class="item"><a href="/random">Anime casuale</a></div>
        <div class="item"><a href="https://t.me/animeworld">Telegram</a></div>
        <div class="item"><a href="https://instagram.com/animeworld">Instagram</a></div>
        <div class="item"><a href="/sfondi">Sfondi scaricabili</a></div>
        <div class="item"><a href="/changelog">Aggiornamenti al sito</a></div>
      </div>
      <div class="film-list">
        <div class="item">
          <div class="inner">
            <a href="/play/fullmetal-alchemist-brotherhood-ita.abc12" class="poster" data-jtitle="Hagane no Renkinjutsushi">
              <img src="https://img.animeworld.ac/locandine/fmab.jpg" alt="Fullmetal Alchemist: Brotherhood (ITA)" />
              <div class="status"><div class="dub">DUB</div></div>
            </a>
            <a href="/play/fullmetal-alchemist-brotherhood-ita.abc12" class="name" title="Fullmetal Alchemist: Brotherhood (ITA)">Fullmetal Alchemist: Brotherhood (ITA)</a>
          </div>
        </div>
        <div class="item">
          <div class="inner">
            <a href="/play/steins-gate.xyz99" class="poster">
              <img src="https://img.animeworld.ac/locandine/sg.jpg" alt="Steins;Gate" />
              <div class="status"><div class="epa">24</div></div>
            </a>
            <a href="/play/steins-gate.xyz99" class="name">Steins;Gate</a>
          </div>
        </div>
      </div>
    </body></html>
    """
    aw_py = '''
def peliculas(item):
    patron = '<div class="inner">\\s*<a href="(?P<url>[^"]+)" class[^>]+>\\s*'
    patron += '<img src="(?P<thumb>[^"]+)" alt?="(?P<title>[^"]+)"[^>]+>.*?'
    patron += '(?:<div class="(?P<lang>[^"]+)">[^<]+</div>\\s*)?'
    patron += '</a>'
'''
    # Test sia con py_source multi-linea (+= via AST) sia con BS4 fallback
    items_ast = kb.scrape_channel_items(
        aw_html, "https://www.animeworld.ac", channel_id="animeworld", channel_name="AnimeWorld", py_source=aw_py, channel_categories=["anime"]
    )
    titles_ast = [it["title"] for it in items_ast]
    assert "Fullmetal Alchemist: Brotherhood (ITA)" in titles_ast
    assert "Steins;Gate" in titles_ast
    assert "DUB" not in titles_ast
    assert not any(noise in titles_ast for noise in ("Anime casuale", "Telegram", "Instagram", "Sfondi scaricabili", "Aggiornamenti al sito"))

    items_bs4 = kb.scrape_channel_items(
        aw_html, "https://www.animeworld.ac", channel_id="animeworld", channel_name="AnimeWorld", py_source="", channel_categories=["anime"]
    )
    titles_bs4 = [it["title"] for it in items_bs4]
    assert "Fullmetal Alchemist: Brotherhood (ITA)" in titles_bs4
    assert "Steins;Gate" in titles_bs4
    assert "DUB" not in titles_bs4
    assert len(items_bs4) == 2


def test_animeworld_episodes_deduplication_across_servers():
    """AnimeWorld dettaglio con multipli blocchi .server: estrae solo 1 istanza di Episodio 1, Episodio 2 (nessun triplicato)."""
    aw_detail_html = """
    <html><body>
      <div class="widget servers">
        <div class="server active" data-name="9">
          <ul class="episodes range active">
            <li class="episode"><a data-episode-id="101" data-id="srv1-ep1" data-episode-num="1" data-num="1" href="/play/fmab/srv1-ep1" class="active">1</a></li>
            <li class="episode"><a data-episode-id="102" data-id="srv1-ep2" data-episode-num="2" data-num="2" href="/play/fmab/srv1-ep2">2</a></li>
          </ul>
        </div>
        <div class="server" data-name="4">
          <ul class="episodes range active">
            <li class="episode"><a data-episode-id="101" data-id="srv2-ep1" data-episode-num="1" data-num="1" href="/play/fmab/srv2-ep1">1</a></li>
            <li class="episode"><a data-episode-id="102" data-id="srv2-ep2" data-episode-num="2" data-num="2" href="/play/fmab/srv2-ep2">2</a></li>
          </ul>
        </div>
        <div class="server" data-name="6">
          <ul class="episodes range active">
            <li class="episode"><a data-episode-id="101" data-id="srv3-ep1" data-episode-num="1" data-num="1" href="/play/fmab/srv3-ep1">1</a></li>
            <li class="episode"><a data-episode-id="102" data-id="srv3-ep2" data-episode-num="2" data-num="2" href="/play/fmab/srv3-ep2">2</a></li>
          </ul>
        </div>
      </div>
    </body></html>
    """
    eps = kb.scrape_channel_episodes(
        aw_detail_html, "https://www.animeworld.ac/play/fmab", series_title="FMAB", channel_id="animeworld"
    )
    assert len(eps) == 2
    assert eps[0]["episode"] == 1
    assert eps[0]["title"] == "Episodio 1"
    assert eps[0]["url"] == "https://www.animeworld.ac/play/fmab/srv1-ep1"
    assert eps[1]["episode"] == 2
    assert eps[1]["title"] == "Episodio 2"
    assert eps[1]["url"] == "https://www.animeworld.ac/play/fmab/srv1-ep2"


def test_ad_blocking_in_extract_stream_urls():
    """_is_ad e extract_stream_urls bloccano banner/iframe pubblicitari (es. a-ads.com) mantenendo i flussi video reali."""
    assert kb._is_ad("https://ad.a-ads.com/2445450/?size=300x250") is True
    assert kb._is_ad("https://syndication.exoclick.com/ads-iframe.html") is True
    assert kb._is_ad("https://sweetpixel.org/DDL/ANIME/FMAB/FMAB_Ep_01_ITA.mp4") is False

    html_with_ads = """
    <html><body>
      <iframe src="https://ad.a-ads.com/2445450/?size=300x250"></iframe>
      <iframe src="https://a-ads.com/campaigns/123"></iframe>
      <iframe src="https://vixcloud.co/embed/363398?token=abc"></iframe>
    </body></html>
    """
    streams = kb.extract_stream_urls(html_with_ads, base_url="https://www.animeworld.ac/play/fmab")
    urls = [s["url"] for s in streams]
    assert "https://ad.a-ads.com/2445450/?size=300x250" not in urls
    assert "https://a-ads.com/campaigns/123" not in urls
    assert urls == ["https://vixcloud.co/embed/363398?token=abc"]


def test_resolve_channel_stream_animeworld_and_animeunity():
    """resolve_channel_stream risolve sia AnimeWorld /api/episode/info sia AnimeUnity /embed-url -> vixcloud -> .mp4 diretto."""
    def fake_fetcher(url: str) -> str:
        if "animeworld.ac/api/episode/info?id=vodn-Y" in url:
            return json.dumps({
                "Target": "https://www.animeworld.ac/api/episode/serverPlayerAnimeWorld?id=vodn-Y",
                "grabber": "https://sweetpixel.org/DDL/ANIME/FullMetalAlchemistBrotherhoodITA/FullMetalAlchemistBrotherhood_Ep_01_ITA.mp4",
                "name": "AnimeWorld Server",
            })
        if "animeunity.co/embed-url/12345" in url:
            return "https://vixcloud.co/embed/363398?token=xyz&expires=1770000000&canPlayFHD=1"
        if "vixcloud.co/embed/363398" in url:
            return """
            <html><script>
              window.video = { id: 363398, filename: 'Ep_01.mp4' };
              window.downloadUrl = 'https://au-d1-04.scws-content.net/download/363398/1080p.mp4?token=dl123';
              window.masterPlaylist = { url: 'https://vixcloud.co/playlist/363398?b=1' };
            </script></html>
            """
        return ""

    aw_stream = kb.resolve_channel_stream(
        "https://www.animeworld.ac/play/fullmetal-alchemist-brotherhood-ita.abc12/vodn-Y",
        fetcher=fake_fetcher,
    )
    assert aw_stream == "https://sweetpixel.org/DDL/ANIME/FullMetalAlchemistBrotherhoodITA/FullMetalAlchemistBrotherhood_Ep_01_ITA.mp4"
    assert kb.is_direct_stream(aw_stream) is True

    au_stream = kb.resolve_channel_stream(
        "https://www.animeunity.so/embed-url/12345",
        fetcher=fake_fetcher,
    )
    assert au_stream == "https://au-d1-04.scws-content.net/download/363398/1080p.mp4?token=dl123"
    assert kb.is_direct_stream(au_stream) is True


def test_animeunity_domain_normalization_and_items_json():
    """Normalizza animeunity.so -> animeunity.co e parsa gli attributi Vue items-json / records."""
    assert kb._normalize_provider_host("https://www.animeunity.so") == "https://www.animeunity.co"
    assert kb._normalize_provider_host("https://animeunity.tv/anime/1-test") == "https://animeunity.co/anime/1-test"

    payload = {
        "data": [
            {
                "id": 999,
                "number": "1",
                "anime": {
                    "id": 343,
                    "title": "Fullmetal Alchemist: Brotherhood",
                    "title_eng": "Fullmetal Alchemist: Brotherhood",
                    "slug": "fullmetal-alchemist-brotherhood",
                    "imageurl": "https://img.animeunity.so/anime/fmab.jpg",
                    "date": "2009",
                    "plot": "Due fratelli alchimisti...",
                    "dub": 0,
                },
            },
            {
                "id": 1000,
                "number": "1",
                "anime": {
                    "id": 500,
                    "title_eng": "Death Note",
                    "slug": "death-note-ita",
                    "imageurl": "https://img.animeunity.co/anime/dn.jpg",
                    "date": "2006",
                    "plot": "Un quaderno...",
                    "dub": 1,
                },
            },
        ]
    }
    import html as html_mod
    escaped = html_mod.escape(json.dumps(payload), quote=True)
    au_html = f'<html><body><layout-items items-json="{escaped}"></layout-items></body></html>'

    items = kb.scrape_channel_items(
        au_html, "https://www.animeunity.so/", channel_id="animeunity", channel_name="AnimeUnity", channel_categories=["anime"]
    )
    assert len(items) == 2
    assert items[0]["title"] == "Fullmetal Alchemist: Brotherhood"
    assert items[0]["url"] == "https://www.animeunity.co/anime/343-fullmetal-alchemist-brotherhood"
    assert items[0]["poster"] == "https://img.animeunity.co/anime/fmab.jpg"
    assert items[0]["year"] == 2009
    assert items[1]["title"] == "Death Note (ITA)"
    assert items[1]["url"] == "https://www.animeunity.co/anime/500-death-note-ita"


def test_animeworld_and_animesaturn_search_targets():
    """Verifica che i target di ricerca per AnimeWorld e AnimeSaturn usino le query corrette (/filter?keyword= e /filter?key=)."""
    kb._clear_stream4me_caches()
    aw_prov = {"id": "animeworld", "name": "AnimeWorld", "host": "https://www.animeworld.ac"}
    as_prov = {"id": "animesaturn", "name": "AnimeSaturn", "host": "https://www.animesaturn.net"}

    aw_target = kb._build_search_target(aw_prov, "frieren")
    assert aw_target == "https://www.animeworld.ac/filter?keyword=frieren"

    as_target = kb._build_search_target(as_prov, "frieren")
    assert as_target == "https://www.animesaturn.net/filter?key=frieren"

    # Verifica scraping pagina di ricerca con filtro e sidebar rumorosa
    aw_search_html = """
    <html><body>
      <div class="film-list">
        <div class="item">
          <a class="poster" href="/play/sousou-no-frieren.kbcPv"><img src="/frieren.jpg" alt="Poster"/></a>
          <a class="name" href="/play/sousou-no-frieren.kbcPv">Frieren: Beyond Journey's End</a>
        </div>
        <div class="item">
          <a class="poster" href="/play/frieren-ita.v26Gn"><img src="/frieren_ita.jpg" alt="Poster"/></a>
          <a class="name" href="/play/frieren-ita.v26Gn">Frieren: Beyond Journey's End (ITA)</a>
        </div>
      </div>
      <div id="sidebar">
        <div class="widget-body">
          <div class="item">
            <a class="name" href="/play/one-piece.xyz">One Piece</a>
          </div>
        </div>
      </div>
    </body></html>
    """
    items = kb.scrape_channel_items(
        aw_search_html,
        "https://www.animeworld.ac/filter?keyword=frieren",
        channel_id="animeworld",
        channel_name="AnimeWorld",
        channel_categories=["anime"],
    )
    assert len(items) == 2
    assert items[0]["title"] == "Frieren: Beyond Journey's End"
    assert items[1]["title"] == "Frieren: Beyond Journey's End (ITA)"
    assert not any("One Piece" in it["title"] for it in items)







def test_vix_hls_url_compone_token():
    html = """window.masterPlaylist = { params: {'token': 'abc', 'expires': '99', 'asn': ''}, url: 'https://vixcloud.cc/playlist/1', }
    window.canPlayFHD = true"""
    assert kb._vix_hls_url(html, "https://vixcloud.cc/embed/1?lang=it") == "https://vixcloud.cc/playlist/1?token=abc&expires=99&asn=&h=1&lang=it"


def test_streamingcommunity_titles_paginati_con_poster_cdn():
    import html as h
    page = {"props": {"cdn_url": "https://cdn.sc.test", "titles": {"data": [
        {"id": 7, "slug": "x", "name": "Uno", "type": "movie",
         "images": [{"filename": "c.webp", "type": "cover"}, {"filename": "p.webp", "type": "poster"}]}]}}}
    doc = '<div data-page="%s"></div>' % h.escape(json.dumps(page), quote=True)
    [it] = kb.scrape_channel_items(doc, "https://sc.test", "streamingcommunity", "SC")
    assert it["poster"] == "https://cdn.sc.test/images/p.webp" and it["kind"] == "film"


def test_list_nasconde_provider_rimossi_schede_canale_e_duplicati(tmp_path, monkeypatch):
    kb._clear_stream4me_caches()
    gs = make_gs(tmp_path, monkeypatch)
    create_sample_addon(tmp_path / "ricette-web-cache" / "kodi-addons")
    conn = sqlite3.connect(tmp_path / "ricette-web-cache" / "ricette.db")
    rows = [
        ("a", "s4me:cinema_uno", "Dup", ""), ("b", "s4me:cinema_uno", "Dup", "http://p/x.jpg"),
        ("c", "s4me:rimosso", "Vecchio", ""), ("d", "stream4me", "Scheda canale", ""),
    ]
    for rid, rec, title, poster in rows:
        conn.execute("INSERT INTO items (id, recipe_id, kind, title, poster, source) VALUES (?, ?, 'film', ?, ?, 'stream4me')", (rid, rec, title, poster))
    conn.commit(); conn.close()

    out = gs.get("list")
    assert [(i["title"], i.get("poster")) for i in out] == [("Dup", "http://p/x.jpg")]

    res = gs.post("stream4me/cleanup", {})
    assert res["ok"] and res["removed"] == 2
