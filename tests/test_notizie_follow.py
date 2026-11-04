import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import httpx

_p = Path(__file__).resolve().parent.parent / "extensions" / "notizie" / "backend.py"
_spec = importlib.util.spec_from_file_location("notizie_follow", _p)
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc).timestamp()
STEAM = {"appnews": {"appid": 1245620, "newsitems": [
    {"gid": "1", "title": "Elden Ring patch 1.12 released", "url": "https://s/1", "contents": "<b>Fix</b> bugs",
     "date": 1793793600, "feedname": "steam_community_announcements"},
    {"gid": "2", "title": "Old news", "url": "https://s/2", "contents": "", "date": 1700000000, "feedname": "x"},
]}}


def feed_item(title, casa="Sega", days_ago=1, kind=None):
    it = {"id": title, "source": "x", "casa": casa, "title": title, "link": "", "summary": "", "image": "",
          "published": nb.iso(NOW - days_ago * 86400), "tags": []}
    it["kind"] = kind or nb.classify(it)
    return it


def test_parse_steam_news_sample():
    items = nb.parse_steam_news(STEAM)
    assert [i["title"] for i in items] == ["Elden Ring patch 1.12 released", "Old news"]
    first = items[0]
    assert (first["kind"], first["link"], first["summary"], first["casa"]) == ("patch", "https://s/1", "Fix bugs", "Steam")
    assert first["published"] == nb.iso(1793793600)
    assert nb.parse_steam_news({}) == [] and nb.parse_steam_news({"appnews": {"newsitems": [{"title": ""}]}}) == []


def test_unread_and_match():
    items = nb.parse_steam_news(STEAM)
    assert [i["unread"] for i in nb.mark_unread(items, nb.iso(1750000000))] == [True, False]  # la seconda e' del 2023
    assert [i["unread"] for i in nb.mark_unread(items, nb.iso(1793793599))] == [True, False]  # confronto stretto
    assert [i["unread"] for i in nb.mark_unread(items, nb.iso(1793793600))] == [False, False]
    feed = [feed_item("The Witcher 3: Wild Hunt next-gen update"), feed_item("Witcher 2 sale"), feed_item("Zelda trailer")]
    assert [i["title"] for i in nb.match_items(feed, "The Witcher 3")] == ["The Witcher 3: Wild Hunt next-gen update"]
    assert nb.match_items(feed, "Ys") == []  # titoli troppo corti non agganciano nulla


def test_digest_selection():
    feed = [
        feed_item("Game A patch 1.1", casa="Sega", days_ago=1),
        feed_item("Game B trailer", casa="Sega", days_ago=2),
        feed_item("Game C release", casa="Sega", days_ago=3),
        feed_item("Game D announced", casa="Sega", days_ago=4),
        feed_item("Game E chat", casa="Sega", days_ago=1),  # notizia generica, ultima per peso
        feed_item("Vecchia patch", casa="Nintendo", days_ago=10),  # fuori dalla settimana
        feed_item("Zelda patch", casa="Nintendo", days_ago=1),
    ]
    d = nb.digest(feed, ["Game B"], NOW)
    assert d["week_start"] == "2026-10-28" and d["week_end"] == "2026-11-04"
    assert d["counts"]["totale"] == 6 and d["counts"]["per_tipo"]["patch"] == 2
    assert all(i["title"] != "Vecchia patch" for i in d["top"])
    # peso del tipo + recenza: annuncio/uscita davanti, patch poi, notizia generica ultima
    assert [i["title"] for i in d["top"]] == ["Game B trailer", "Game C release", "Game D announced",
                                              "Game A patch 1.1", "Zelda patch", "Game E chat"]
    assert len(d["per_casa"]["Sega"]) == 3 and len(d["per_casa"]["Nintendo"]) == 1
    assert [i["title"] for i in d["mine"]] == ["Game B trailer"]
    assert d["counts"]["mine"] == 1


def test_digest_top_is_capped_at_ten():
    feed = [feed_item(f"Gioco {n} news", casa=f"Casa{n}", days_ago=1) for n in range(15)]
    d = nb.digest(feed, [], NOW)
    assert len(d["top"]) == 10 and d["mine"] == []


class FakeResp:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data
        self.content = b""

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def get(self, url, headers=None):
        self.calls += 1
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


def test_steam_news_cache_and_backoff(tmp_path):
    ok = FakeClient(FakeResp(200, STEAM))
    items = nb.steam_news(tmp_path, 1245620, ok, NOW)
    assert len(items) == 2 and ok.calls == 1
    # dentro l'ora: niente rete, dalla cache
    again = FakeClient(FakeResp(200, STEAM))
    assert len(nb.steam_news(tmp_path, 1245620, again, NOW + 600)) == 2 and again.calls == 0

    # dopo l'ora ma con errore: backoff, si ripiega sull'ultimo dato noto
    bad = FakeClient(FakeResp(503))
    later = NOW + 7200
    assert len(nb.steam_news(tmp_path, 1245620, bad, later)) == 2 and bad.calls == 1
    assert len(nb.steam_news(tmp_path, 1245620, bad, later + 60)) == 2 and bad.calls == 1  # ancora in backoff

    timeout = FakeClient(httpx.ConnectTimeout("boom"))
    assert nb.steam_news(tmp_path, 999, timeout, NOW) == [] and timeout.calls == 1
