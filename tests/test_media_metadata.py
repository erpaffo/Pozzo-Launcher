"""Test del servizio metadati automatici AniList & TMDB/Wikipedia e della rotta enrich.

Esegui: python -m pytest tests/test_media_metadata.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_modules():
    spec_meta = importlib.util.spec_from_file_location("metadata", ROOT / "extensions" / "media-locale" / "metadata.py")
    meta = importlib.util.module_from_spec(spec_meta)
    sys.modules["metadata"] = meta
    spec_meta.loader.exec_module(meta)

    spec_be = importlib.util.spec_from_file_location("media_locale_backend", ROOT / "extensions" / "media-locale" / "backend.py")
    be = importlib.util.module_from_spec(spec_be)
    spec_be.loader.exec_module(be)
    return be, meta


ML, META = load_modules()


class FakeGS:
    def __init__(self, cfg, pid="media-locale"):
        self.cfg, self.id, self.routes, self.settings, self.logs = cfg, pid, {}, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[path.lstrip("/")] = fn
            return fn
        return deco

    def add_library_kind(self, kind):
        pass

    def add_player(self, player):
        pass

    def job(self, *a, **k):
        pass

    def save_settings(self, values):
        self.settings.update(values)


def test_clean_html():
    raw = "<b>One Piece</b><br>Trama dell'anime.<br />Altra riga."
    cleaned = META._clean_html(raw)
    assert "<b>" not in cleaned and "<br>" not in cleaned
    assert "One Piece Trama dell'anime. Altra riga." in cleaned


def test_fetch_anime_metadata_success():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": {
            "Media": {
                "id": 21,
                "coverImage": {
                    "extraLarge": "https://s4.anilist.co/poster.jpg",
                    "large": "https://s4.anilist.co/poster_large.jpg",
                },
                "bannerImage": "https://s4.anilist.co/backdrop.jpg",
                "description": "Gold Roger was the Pirate King.<br>Monkey D. Luffy sets sail.",
                "genres": ["Action", "Adventure"],
                "format": "TV",
                "averageScore": 88,
            }
        }
    }

    with patch("httpx.post", return_value=fake_response):
        res = META.fetch_anime_metadata("One Piece", episode=1050)
        assert res["poster"] == "https://s4.anilist.co/poster.jpg"
        assert res["backdrop"] == "https://s4.anilist.co/backdrop.jpg"
        assert "Gold Roger was the Pirate King." in res["overview"]
        assert "<br>" not in res["overview"]
        assert res["genres"] == ["Action", "Adventure"]
        assert res["averageScore"] == 88


def test_fetch_anime_metadata_fallback_on_error():
    with patch("httpx.post", side_effect=Exception("Network timeout")):
        assert META.fetch_anime_metadata("One Piece") == {}

    assert META.fetch_anime_metadata("") == {}


def test_fetch_tmdb_metadata_tmdb_api():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {
                "poster_path": "/inception_poster.jpg",
                "backdrop_path": "/inception_bg.jpg",
                "overview": "Dom Cobb è un ladro esperto nel rubare segreti.",
                "release_date": "2010-07-16",
            }
        ]
    }

    with patch.dict("os.environ", {"TMDB_API_KEY": "fake_key"}), patch("httpx.get", return_value=fake_response):
        res = META.fetch_tmdb_metadata("Inception", kind="film", year=2010)
        assert res["poster"] == "https://image.tmdb.org/t/p/w500/inception_poster.jpg"
        assert res["backdrop"] == "https://image.tmdb.org/t/p/w1280/inception_bg.jpg"
        assert "Dom Cobb" in res["overview"]
        assert res["year"] == 2010


def test_fetch_tmdb_metadata_wikipedia_fallback():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "extract": "Inception è un film del 2010 diretto da Christopher Nolan.",
        "thumbnail": {"source": "https://upload.wikimedia.org/poster.jpg"},
        "originalimage": {"source": "https://upload.wikimedia.org/backdrop.jpg"},
    }

    with patch.dict("os.environ", {"TMDB_API_KEY": ""}, clear=True), patch("httpx.get", return_value=fake_response):
        res = META.fetch_tmdb_metadata("Inception", kind="film")
        assert res["poster"] == "https://upload.wikimedia.org/poster.jpg"
        assert res["backdrop"] == "https://upload.wikimedia.org/backdrop.jpg"
        assert "Christopher Nolan" in res["overview"]
        assert res["year"] == 2010


def test_fetch_tmdb_metadata_fallback_on_error():
    with patch("httpx.get", side_effect=Exception("Network error")):
        assert META.fetch_tmdb_metadata("Inception") == {}
    assert META.fetch_tmdb_metadata("") == {}


def test_enrich_item_anime():
    fake_anime_meta = {
        "poster": "https://s4.anilist.co/op_poster.jpg",
        "backdrop": "https://s4.anilist.co/op_banner.jpg",
        "overview": "Avventure di Cappello di Paglia.",
        "genres": ["Azione", "Avventura"],
        "year": 1999,
    }

    item = {
        "id": "item1",
        "kind": "episodio",
        "title": "Episodio 1050",
        "series": "One Piece",
        "season": 1,
        "episode": 1050,
        "path": "Anime/One Piece/One Piece - 1050.mkv",
        "poster": "",
        "overview": "",
    }

    with patch.object(META, "fetch_anime_metadata", return_value=fake_anime_meta):
        enriched = META.enrich_item(item)
        assert enriched["poster"] == "https://s4.anilist.co/op_poster.jpg"
        assert enriched["backdrop"] == "https://s4.anilist.co/op_banner.jpg"
        assert enriched["overview"] == "Avventure di Cappello di Paglia."
        assert enriched["genres"] == "Azione, Avventura"


def test_enrich_item_gia_completo_non_tocca():
    item = {
        "id": "item2",
        "kind": "film",
        "title": "Film Completo",
        "poster": "locandina.jpg",
        "overview": "Trama già presente.",
    }
    with patch.object(META, "fetch_tmdb_metadata") as mock_tmdb:
        enriched = META.enrich_item(item)
        assert enriched == item
        mock_tmdb.assert_not_called()


def test_rotta_enrich_database(tmp):
    cfg = SimpleNamespace(config_path=tmp / "config.toml", app={})
    gs = FakeGS(cfg)
    ML.register(gs)

    # Inserisci un item privo di locandina e trama
    db = ML.connect(ML.db_path(cfg))
    db.execute(
        "INSERT INTO roots(path, added) VALUES('/media', 0);"
    )
    db.execute(
        "INSERT INTO items(id, kind, title, series, path, root, poster, overview) "
        "VALUES('op1', 'episodio', 'Episodio 1050', 'One Piece', '/media/Anime/One Piece/1050.mkv', '/media', '', '');"
    )
    db.commit()
    db.close()

    fake_meta = {
        "poster": "https://s4.anilist.co/one_piece.jpg",
        "backdrop": "https://s4.anilist.co/banner.jpg",
        "overview": "Trama anime One Piece.",
        "genres": "Azione, Avventura",
    }

    with patch.object(META, "fetch_anime_metadata", return_value=fake_meta):
        res = gs.routes["enrich"](body={"id": "op1"})
        assert res["ok"] is True
        assert res["enriched"] == 1

    detail = gs.routes["detail"](id="op1")
    assert detail["poster"] == "https://s4.anilist.co/one_piece.jpg"
    assert detail["backdrop"] == "https://s4.anilist.co/banner.jpg"
    assert detail["overview"] == "Trama anime One Piece."
    assert detail["genres"] == "Azione, Avventura"
