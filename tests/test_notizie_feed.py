import importlib.util
from pathlib import Path

import pytest

_p = Path(__file__).resolve().parent.parent / "extensions" / "notizie" / "backend.py"
_spec = importlib.util.spec_from_file_location("notizie_backend", _p)
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

SRC = {"id": "x", "casa": "Sega", "nome": "X"}
RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>Sonic Frontiers update 1.2 &amp; fixes</title><link>http://a/1</link><guid>g1</guid>
<pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
<media:content url="http://a/i.jpg" medium="image"/><category>Sonic</category></item></channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New DLC announced</title><id>t:1</id>
<link rel="alternate" href="http://b/2"/><updated>2026-11-02T08:30:00Z</updated>
<summary>Text &lt;img src="http://b/p.png"&gt; more</summary></entry></feed>"""


def test_parse_rss_atom_and_garbage():
    r = nb.parse_feed(RSS, SRC)[0]
    assert (r["kind"], r["summary"], r["image"], r["published"], r["tags"]) == ("patch", "Hello world", "http://a/i.jpg", "2026-11-03T10:00:00Z", ["Sonic"])
    a = nb.parse_feed(ATOM, SRC)[0]
    assert (a["link"], a["kind"], a["published"], a["image"]) == ("http://b/2", "dlc", "2026-11-02T08:30:00Z", "http://b/p.png")
    assert nb.parse_feed(b"<html>no", SRC, log=lambda *_: None) == []
    items = nb.parse_feed(RSS, SRC) + nb.parse_feed(ATOM, SRC)
    assert len(nb.select(items, q="dlc", before="2026-11-03")) == 1
    assert nb.classify({"title": "Zelda trailer"}) == "annuncio" and nb.classify({"title": "Ciao"}) == "notizia"


def test_validate_settings():
    v = nb.validate_settings({"disabled_sources": ["gematsu", "zzz"], "custom_sources": [{"nome": "Mio", "url": "https://e.org/rss"}]})
    assert v["disabled_sources"] == ["gematsu"] and v["custom_sources"][0]["casa"] == "Personali"
    with pytest.raises(ValueError):
        nb.validate_settings({"custom_sources": [{"nome": "x", "url": "file:///etc/passwd"}]})
