"""Link di download degli store online: lettura di gioco/aggiornamento/DLC con provider e parti,
risoluzione degli accorciatori pubblicitari e API che apre i link scelti. Nessuna rete.

Esegui: PYTHONUTF8=1 python tests/test_storelinks.py
"""

import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo import storelinks as SL  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.library.build import build  # noqa: E402

URL_NX = "https://example-store.test/gioco-switch-nsp-update-dlc/"
URL_ZP = "https://example-store2.test/gioco-switch-nsp/"
URL_REPACK = "https://example-repack.test/gioco-pc/"

# come la pagina di un repack PC: una riga per fonte, le parti dirette dentro lo spoiler
HTML_REPACK = """<html><body><article><div class="entry">
  <p>Intro con un <a href="https://example-repack.test/">link al sito stesso</a>.</p>
  <ul>
    <li><a href="https://1337x.to/torrent/5019311/gioco/">1337x</a> |
        [<a href="magnet:?xt=urn:btih:abc&amp;dn=Gioco">magnet</a>]
        [<a href="https://paste.example.test/?aaa#bbb">.torrent file only</a>] <br>
        <img src="https://torrent-stats.info/x.png"></li>
    <li><a href="https://paste.example.test/?ccc#ddd">Filehoster: MultiUpload</a> (10+ hosters, interchangeable)
        [Use <a href="https://www.jdownloader.org/jdownloader2">JDownloader2</a>]</li>
    <li><a href="https://paste.example.test/?eee#fff">Filehoster: DataNodes</a> (Speed &amp; Usability)
      <div class="su-spoiler"><div class="su-spoiler-title" role="button">Click to show direct links</div>
        <div class="su-spoiler-content">
          <a href="https://datanodes.to/a/Gioco.part01.rar" rel="nofollow">Gioco.part01.rar</a><br>
          <a href="https://datanodes.to/b/Gioco.part02.rar" rel="nofollow">Gioco.part02.rar</a><br>
        </div></div></li>
    <li><a href="https://fuckingfast.co/w34fqbnw8b#Gioco.part03.rar">Filehoster: FuckingFast (REALLY Fucking Fast 🚀)</a></li>
  </ul>
</div></article></body></html>"""

# come una pagina nxbrew reale: intestazione per file e un paragrafo per provider
HTML_NX = """<html><body><article><div class="entry">
  <p><strong>Download Links</strong></p>
  <p><strong>Base Game NSP (996 MB)</strong></p>
  <p><strong>DataNodes</strong><br><a href="https://ouo.io/aaa">Download</a></p>
  <p><strong>1Fichier</strong><br><a href="https://ouo.io/bbb">Download</a></p>
  <p><strong>Base Game NSP Part 2 (1 GB)</strong></p>
  <p><strong>DataNodes</strong><br><a href="https://datanodes.to/part2">Download</a></p>
  <p><strong>Update 1.0.7 (v458752)</strong></p>
  <p><strong>DataNodes</strong><br><a href="https://ouo.io/ccc">Download</a></p>
  <p><strong>DLC Pack (3 DLCs)</strong></p>
  <p><strong>DataNodes</strong><br><a href="https://ouo.io/ddd">Download</a></p>
  <p>Please report any broken/dead/missing links in the comment section.</p>
</div></article></body></html>"""

# come una pagina ziperto reale: intestazione e provider nella stessa riga
HTML_ZP = """<html><body><div class="entry-content">
  <p><span><strong>Download <span>(Base Game)</span> Links: <span>NSP</span> (168MB)</strong></span><br>
     <strong><a href="https://ouo.io/eee">MegaUp</a> | <a href="https://datanodes.to/base">Datanodes</a></strong></p>
  <p><span><strong>Download (EUR) Links: NSP</strong></span><br>
     <strong><a href="https://ouo.io/fff">MegaUp</a></strong></p>
</div></body></html>"""


def test_parse_nxbrew():
    d = SL.parse_page(HTML_NX, URL_NX)
    links = d["links"]
    assert [x["kind"] for x in links] == ["game", "game", "game", "update", "dlc"], links
    assert [x["provider"] for x in links] == ["DataNodes", "1Fichier", "DataNodes", "DataNodes", "DataNodes"], links
    assert links[2]["part"] == 2 and links[0]["part"] == 0, links
    assert links[0]["short"] and links[0]["host"] == "ouo.io", links[0]
    assert not links[2]["short"] and links[2]["host"] == "datanodes.to", links[2]
    assert all(x["label"] for x in links)
    print("ok  nxbrew: gioco (anche a parti), aggiornamento e DLC con provider e accorciatori riconosciuti")


def test_parse_ziperto():
    d = SL.parse_page(HTML_ZP, URL_ZP)
    links = d["links"]
    assert [(x["kind"], x["provider"]) for x in links] == [
        ("game", "MegaUp"), ("game", "Datanodes"), ("game", "MegaUp")], links
    assert "———" not in links[0]["label"] and links[0]["label"].startswith("Download"), links[0]["label"]
    assert links[0]["url"] == "https://ouo.io/eee" and links[1]["url"] == "https://datanodes.to/base"
    print("ok  ziperto: provider nella stessa riga, versioni in altre lingue come righe distinte")


def test_parse_repack():
    """Pagina di un repack PC: magnet, pagina del torrent, paste dei filehoster e parti dirette."""
    d = SL.parse_page(HTML_REPACK, URL_REPACK)
    links = d["links"]
    assert [x["role"] for x in links] == ["page", "magnet", "paste", "paste", "direct", "direct", "direct"], links
    page = next(x for x in links if x["role"] == "page")
    assert page["provider"] == "1337x" and page["host"] == "1337x.to", page
    mag = next(x for x in links if x["role"] == "magnet")
    assert mag["url"].startswith("magnet:?xt=urn:btih:abc") and "&dn=Gioco" in mag["url"], mag
    pastes = [x for x in links if x["role"] == "paste"]
    assert [x["provider"] for x in pastes] == ["MultiUpload", "DataNodes"], pastes
    # con il magnet il «.torrent file only» sarebbe un doppione
    assert not any("torrent file only" in x["provider"].lower() for x in links), links
    parts = [x for x in links if x["role"] == "direct"]
    assert [x["part"] for x in parts] == [1, 2, 3] and parts[0]["series"] == "Gioco", parts
    assert {x["file"] for x in parts} == {"Gioco.part01.rar", "Gioco.part02.rar", "Gioco.part03.rar"}, parts
    # «Filehoster: FuckingFast» è un file (il nome sta nel frammento), non un paste da leggere
    assert parts[2]["host"] == "fuckingfast.co" and parts[2]["file"] == "Gioco.part03.rar", parts[2]
    assert all("example-repack" not in x["url"] and "jdownloader" not in x["url"] for x in links), links
    print("ok  repack PC: magnet, pagina, paste e parti dirette (con serie) riconosciuti")


def test_repack_rumore():
    """Crediti, sito dello sviluppatore, forum e immagini non sono download: restano fuori."""
    d = SL.parse_page(HTML_REPACK_RUMORE, URL_REPACK)
    urls = [x["url"] for x in d["links"]]
    assert urls == ["magnet:?xt=urn:btih:dd&dn=Gioco", "https://datanodes.to/gioco/Gioco.rar"], urls
    assert [x["role"] for x in d["links"]] == ["magnet", "direct"], d["links"]
    print("ok  repack PC: i link che non scaricano nulla (sito, forum, screenshot) vengono scartati")


def test_repack_aggiornamento():
    """Un aggiornamento elencato nella pagina si legge come tipo «update», con le sue fonti."""
    d = SL.parse_page(HTML_REPACK_UPDATE, URL_REPACK)
    kinds = [(x["kind"], x["role"], x["host"]) for x in d["links"]]
    assert kinds == [("game", "direct", "datanodes.to"), ("update", "magnet", ""),
                     ("update", "direct", "fuckingfast.co")], kinds
    print("ok  repack PC: l'aggiornamento è una riga sua (magnet e file), separato dal gioco")


# pagina con i link che non scaricano nulla: crediti, forum, sito dello sviluppatore, screenshot
HTML_REPACK_RUMORE = """<html><body><article><div class="entry">
  <ul>
    <li><a href="magnet:?xt=urn:btih:dd&amp;dn=Gioco">magnet</a></li>
    <li><a href="https://datanodes.to/gioco/Gioco.rar">Filehoster: DataNodes</a></li>
    <li><a href="https://www.pixelperfectdude.com/">Pixel Perfect Dude</a></li>
    <li><a href="https://cs.rin.ru/forum/viewtopic.php?p=1">Discussion (and possible) future updates on CS.RIN.RU thread</a></li>
    <li><a href="https://en.riotpixels.com/games/gioco/screenshots/">en.riotpixels.com</a></li>
  </ul>
</div></article></body></html>"""

# pagina con l'aggiornamento accanto al gioco
HTML_REPACK_UPDATE = """<html><body><article><div class="entry">
  <ul>
    <li><a href="https://datanodes.to/gioco/Gioco.rar">Filehoster: DataNodes</a></li>
    <li><strong>Update v1.0.4 (206 MB)</strong> [<a href="magnet:?xt=urn:btih:ee&amp;dn=Gioco+Update">magnet</a>]
        <a href="https://fuckingfast.co/abc#Gioco_Update_v1.0.4.rar">Filehoster: FuckingFast</a></li>
  </ul>
</div></article></body></html>"""


def _privatebin(text: str, key: bytes) -> str:
    """Un messaggio cifrato come lo serve PrivateBin v1 (AES-GCM con la chiave del frammento)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iv = bytes(range(12))
    ct = AESGCM(key).encrypt(iv, text.encode(), b"")
    return json.dumps({"v": 1, "iv": base64.b64encode(iv).decode(),
                       "ct": base64.b64encode(ct).decode(), "adata": ""})


def test_paste():
    """Un paste cifrato (PrivateBin) e uno in chiaro: in entrambi i casi si leggono solo i link ai file."""
    real_get = SL._paste_get
    key = bytes(range(32))
    frag = base64.urlsafe_b64encode(key).decode().rstrip("=")
    body = ('<a href="https://multiup.io/abc">1</a>'
            '<a href="https://fuckingfast.co/x#Gioco.part01.rar">2</a>'
            '<a href="https://paste.example.test/?self#k">3</a>')
    pages = {
        f"https://paste.example.test/?cifrato#{frag}":
            f'<html><body><div id="cipherdata">{_privatebin(body, key)}</div></body></html>',
        f"https://paste.example.test/?chiaro#{frag}": f"<html><body>{body}</body></html>",
    }

    def fake_get(url, timeout=20.0):
        class R:
            text = pages[url]

            def raise_for_status(self):
                pass

        return R()

    SL._paste_get = fake_get
    try:
        enc = SL.paste(f"https://paste.example.test/?cifrato#{frag}")
        plain = SL.paste(f"https://paste.example.test/?chiaro#{frag}")
    finally:
        SL._paste_get = real_get
    for got in (enc, plain):
        urls = [x["url"] for x in got["links"]]
        assert urls == ["https://multiup.io/abc", "https://fuckingfast.co/x#Gioco.part01.rar"], urls
        assert got["links"][1]["file"] == "Gioco.part01.rar" and got["links"][1]["part"] == 1, got["links"][1]
    print("ok  paste: cifrato PrivateBin e in chiaro, i link propri del paste restano fuori")


def test_risoluzione(tmp_path):
    """Un accorciatore viene risolto una volta e resta in cache; senza un browser a disposizione resta com'e'."""
    cfg = config.load(_make_cfg(tmp_path))
    c = Cache(cfg.cache)
    try:
        seen = []

        def fake_browser(url):
            seen.append(url)
            return "https://datanodes.to/vera" if url.endswith("aaa") else None

        SL.set_resolver(fake_browser)
        real_get = SL.httpx.get
        SL.httpx.get = lambda *a, **k: (_ for _ in ()).throw(SL.httpx.HTTPError("bloccato"))
        try:
            assert SL.resolve(c, "https://ouo.io/aaa") == "https://datanodes.to/vera"
            assert SL.resolve(c, "https://ouo.io/aaa") == "https://datanodes.to/vera" and len(seen) == 1, "risultato in cache"
            assert SL.resolve(c, "https://ouo.io/bbb") == "https://ouo.io/bbb", "senza link vero resta l'accorciatore"
            assert SL.resolve(c, "https://datanodes.to/x") == "https://datanodes.to/x", "i link diretti non si toccano"
        finally:
            SL.httpx.get = real_get
    finally:
        SL.set_resolver(None)
        c.close()
    print("ok  accorciatori: link vero tramite il browser, risultato in cache, fallback al link originale")


def test_api(tmp_path):
    """La scheda del gioco riceve tutti i link; «Scarica» li mette in coda per il manager."""
    cfg = config.load(_make_cfg(tmp_path))
    cfg.app["downloads"] = {"max_active": 0}  # nessun download parte durante il test
    page = "https://example-store.test/elenco"
    cfg.catalogs = {"switch": [page]}
    c = Cache(cfg.cache)
    c.kv_set(f"catalog:type_b:{page}", {"url": page, "index_url": page, "pid": "switch", "time": time.time(),
                                        "entries": [{"name": "Gioco Uno Switch NSP", "size": None,
                                                     "url": URL_NX, "magnet": None, "group": "G"}]})
    c.close()
    build(cfg, log=lambda m: None)
    real_fetch = SL.fetch
    SL.fetch = lambda url, timeout=20.0: SL.parse_page(HTML_NX, url)
    try:
        app = create_app(cfg)
        with TestClient(app) as cl:
            gid = cl.get("/api/library").json()["games"]["rows"][0][0]
            d = cl.get(f"/api/game/{gid}/links").json()
            assert len(d["links"]) == 5 and d["kind_order"][:3] == ["game", "update", "dlc"], d
            assert {x["kind"] for x in d["links"]} == {"game", "update", "dlc"}, d
            urls = [next(x["url"] for x in d["links"] if x["kind"] == k) for k in ("game", "update", "dlc")]
            r = cl.post(f"/api/game/{gid}/download", json={"links": urls})
            assert r.status_code == 200, r.text
            tasks = r.json()["tasks"]
            assert [t["source"] for t in tasks] == urls and all(t["status"] == "queued" for t in tasks), tasks
            assert all(t["category"] == "switch" for t in tasks), tasks
            q = cl.get("/api/downloads").json()
            assert len(q["tasks"]) == 3, q
            real_paste = SL.paste
            SL.paste = lambda url, timeout=20.0: {"url": url, "site": "paste.example.test", "magnet": "",
                                                  "links": [{"url": "https://multiup.io/abc", "host": "multiup.io",
                                                             "file": "Gioco.part01.rar", "part": 1}]}
            try:
                p = cl.get(f"/api/game/{gid}/paste", params={"url": "https://paste.example.test/?x#y"})
                assert p.status_code == 200 and p.json()["links"][0]["url"] == "https://multiup.io/abc", p.text
                assert cl.get("/api/game/1/paste", params={"url": "ftp://nope"}).status_code == 400
            finally:
                SL.paste = real_paste
    finally:
        SL.fetch = real_fetch
    print("ok  API: elenco completo nella scheda, «Scarica» mette i link in coda, paste letto al clic")


def _make_cfg(tmp: Path) -> Path:
    (tmp / "roms").mkdir(exist_ok=True)
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n',
                                     encoding="utf-8")
    return tmp / "config.toml"


if __name__ == "__main__":
    test_parse_nxbrew()
    test_parse_ziperto()
    test_parse_repack()
    test_repack_rumore()
    test_repack_aggiornamento()
    test_paste()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_risoluzione(Path(t))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_api(Path(t))
    print("TUTTI I TEST OK")
