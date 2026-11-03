"""Risolutore MultiUp: dalla pagina con l'elenco dei mirror a un solo link per il resto della catena.
Nessuna rete: `multiup._get` e' finto. REAL e' la struttura vera di /en/mirror/<id> (verificata sul sito, ridotta).

Esegui: PYTHONUTF8=1 python tests/test_downloads_multiup.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo.downloads import multiup, resolvers  # noqa: E402

PAGE = "https://multiup.io/en/download/abc123/Gioco.nsp"
_REAL_GET = multiup._get


class Reply:
    def __init__(self, text="", url=PAGE, headers=None):
        self.text, self.url, self.headers = text, url, headers or {}


# struttura reale di https://multiup.io/en/mirror/<id> (ridotta): UseNet interno, social con href esterni, 4 host
REAL = """<html><head><title>Mirror list Gioco [x][v0].rar - Mirror Upload - MultiUp.io</title></head><body>
<a target="_blank" href="https://www.facebook.com/sharer.php?u=https://multiup.io/x" rel="nofollow">fb</a>
<a href="/download-fast/c4eb/Gioco.rar" nameHost="UseNet" link="/download-fast/c4eb/Gioco.rar" validity="valid" id="0" class="host btn">Download (355)</a>
<a href="https://gofile.io/d/FI6cxpKR" target="_blank" nameHost="gofile.io" link="https://gofile.io/d/FI6cxpKR" validity="valid" id="2" class="host btn">Download</a>
<a href="https://mixdrop.ag/f/pjj8gw73f3lo81" nameHost="mixdrop.ag" link="https://mixdrop.ag/f/pjj8gw73f3lo81" validity="invalid" id="3" class="host btn">Download</a>
<a href="https://datanodes.to/abc12345/Gioco.rar" nameHost="datanodes.to" link="https://datanodes.to/abc12345/Gioco.rar" validity="unknown" id="4" class="host btn">Download</a>
<a href="https://megaup.net/a673/Gioco.rar" nameHost="megaup.net" link="https://megaup.net/a673/Gioco.rar" validity="valid" id="5" class="host btn">Download</a>
<a href="https://megaup.net/a673/Gioco.rar" nameHost="megaup.net" link="https://megaup.net/a673/Gioco.rar" validity="valid" id="6" class="host btn">Download</a>
</body></html>"""
REAL_URL = "https://multiup.io/en/mirror/c4ebca5bad6275fa349b6afef5cc4cc7"


def _btn(host, link, validity="valid"):
    return f'<button type="submit" class="host" namehost="{host}" link="{link}" validity="{validity}">{host}</button>'


def _page(*buttons):
    return "<html><body><a href='/en/'>home</a>" + "".join(buttons) + "</body></html>"


try:
    import pytest

    @pytest.fixture(autouse=True)
    def _ripristina():
        yield
        multiup._get = _REAL_GET
except ImportError:  # eseguito a mano
    pass


def _with(pages):
    """pages: url -> Reply (o testo). Restituisce le URL chieste, in ordine."""
    asked = []

    def fake(url, **kw):
        asked.append((url, kw))
        r = pages.get(url, Reply("", url))
        return Reply(r, url) if isinstance(r, str) else r

    multiup._get = fake
    return asked


def test_preferisce_1fichier():
    _with({PAGE: _page(_btn("1fichier.com", "https://1fichier.com/?dead", "invalid"),
                       _btn("datanodes.to", "https://datanodes.to/abc12345/Gioco.nsp"),
                       _btn("krakenfiles.com", "https://krakenfiles.com/view/k1/file.html"),
                       _btn("1fichier.com", "https://1fichier.com/?ok"))})
    # il primo 1fichier e' morto, quindi vale il secondo; datanodes resta ultimo
    assert multiup.resolve(PAGE) == "https://1fichier.com/?ok"
    print("ok  1fichier vivo prima di tutto, morti saltati")


def test_solo_datanodes():
    _with({PAGE: _page(_btn("datanodes.to", "https://datanodes.to/abc12345/Gioco.nsp"))})
    assert multiup.resolve(PAGE) == "https://datanodes.to/abc12345/Gioco.nsp"
    print("ok  solo datanodes: lo si prende lo stesso")


def test_datanodes_prima_di_un_host_sconosciuto():
    """datanodes lo sa fare il browser (finestra nascosta + URL del download): prima di un host qualunque."""
    _with({PAGE: _page(_btn("datanodes.to", "https://datanodes.to/abc12345/x"), _btn("zippyshare.example", "https://z.example/f"))})
    assert multiup.resolve(PAGE) == "https://datanodes.to/abc12345/x"
    print("ok  datanodes prima di un host sconosciuto (che non sapremmo scaricare)")


def test_niente_mirror_o_captcha():
    _with({PAGE: "<html><body><div class='g-recaptcha'></div></body></html>"})
    assert multiup.find(PAGE) == ("", "la pagina chiede un captcha")
    _with({PAGE: _page()})
    assert multiup.find(PAGE) == ("", "nessun mirror nella pagina")
    _with({PAGE: _page(_btn("1fichier.com", "https://1fichier.com/?x", "invalid"))})
    assert multiup.find(PAGE) == ("", "tutti i mirror sono offline")
    _with({PAGE: "<html><head><title>Fichier non trouvé - Upload mirroir - MultiUp.io</title></head></html>"})
    assert multiup.find(PAGE) == ("", "il file non esiste più su MultiUp")  # pagina vera di un file rimosso
    print("ok  captcha / vuota / tutti morti -> \"\" con il motivo")


def test_redirect_un_salto():
    red = "https://multiup.io/redirect/xyz"
    asked = _with({PAGE: _page(f'<a namehost="krakenfiles.com" href="{red}">k</a>'),
                   red: Reply("", red, {"location": "https://krakenfiles.com/view/k1/file.html"})})
    assert multiup.resolve(PAGE) == "https://krakenfiles.com/view/k1/file.html"
    assert (red, {"follow_redirects": False, "timeout": 8}) in asked
    print("ok  /redirect/ risolto con un solo salto, senza seguirlo")


def test_pagina_corta_e_mirror():
    short = "https://multiup.io/abc123"
    _with({short: _page(_btn("megaup.net", "https://megaup.net/xyz/f"))})
    assert multiup.resolve(short) == "https://megaup.net/xyz/f"
    # /download/ senza elenco: si prova la variante /mirror/
    _with({PAGE: "<html></html>",
           PAGE.replace("/download/", "/mirror/"): _page(_btn("1fichier.com", "https://1fichier.com/?m"))})
    assert multiup.resolve(PAGE) == "https://1fichier.com/?m"
    print("ok  /<id> e variante /mirror/")


def test_non_multiup():
    asked = _with({})
    for u in ("https://1fichier.com/?abc", "https://example.com/multiup.io/x", "https://multiup.io/", "https://multiup.io"):
        assert multiup.resolve(u) == "" and not multiup.is_page(u), u
    assert asked == []
    print("ok  altri link intatti, nessuna rete")


def test_catena():
    saved = resolvers._FNS[:]
    try:
        _with({PAGE: _page(_btn("1fichier.com", "https://1fichier.com/?ok"))})
        seen, fasi = [], []
        resolvers._FNS[:] = []
        resolvers.register(multiup.resolve, lambda u: "Cerco i mirror su MultiUp" if multiup.is_page(u) else "")
        resolvers.register(lambda u: (seen.append(u), "https://s1.1fichier.com/file.nsp")[1] if "1fichier" in u else "", "dopo")
        assert resolvers.resolve(PAGE, fasi.append) == ("https://s1.1fichier.com/file.nsp", "")
        assert seen == ["https://1fichier.com/?ok"] and fasi == ["Cerco i mirror su MultiUp", "dopo"], (seen, fasi)
    finally:
        resolvers._FNS[:] = saved
    print("ok  catena: il risolutore dopo riceve il mirror")


def test_mirrors_struttura_reale():
    asked = _with({REAL_URL: Reply(REAL, REAL_URL)})
    # da /download/<id>/<nome> si va dritti all'elenco /en/mirror/<id>
    r = multiup.mirrors("https://multiup.io/download/c4ebca5bad6275fa349b6afef5cc4cc7/Gioco.rar")
    assert asked[0][0] == REAL_URL
    assert (r["page"], r["name"], r["reason"]) == (REAL_URL, "Gioco [x][v0].rar", "")
    # UseNet e social scartati, duplicato tolto, vivi prima; tra i vivi viene prima chi sappiamo scaricare
    # (datanodes lo fa il browser), poi gli altri (gofile, megaup: servono un account o il loro popup), morto in fondo
    assert [(m["name"], m["live"]) for m in r["mirrors"]] == [("datanodes", True), ("gofile", True), ("megaup", True), ("mixdrop", False)]
    assert r["mirrors"][0] == {"host": "datanodes.to", "name": "datanodes", "url": "https://datanodes.to/abc12345/Gioco.rar", "live": True}
    assert multiup.mirrors("https://multiup.io/c4ebca5bad6275fa349b6afef5cc4cc7")["mirrors"] == r["mirrors"]
    print("ok  mirrors(): struttura reale, ordine, morti, duplicati")


def test_mirrors_motivi():
    _with({PAGE: _page(_btn("1fichier.com", "https://1fichier.com/?x", "invalid"))})
    r = multiup.mirrors(PAGE)
    assert r["reason"] == "tutti i mirror sono offline" and len(r["mirrors"]) == 1 and not r["mirrors"][0]["live"]
    assert multiup.mirrors("https://example.com/a")["reason"] and multiup.mirrors("https://example.com/a")["mirrors"] == []

    def boom(url, **kw):
        raise multiup.httpx.ConnectError("no")
    multiup._get = boom
    assert multiup.mirrors(PAGE)["reason"] == "MultiUp non risponde"
    print("ok  mirrors(): motivi")


def test_redirect_con_transport_finto():
    red, dead = "https://multiup.io/redirect/ok1", "https://multiup.io/redirect/ko2"

    def handler(req):
        if req.url.path == "/en/mirror/c4ebca5bad6275fa349b6afef5cc4cc7":
            return multiup.httpx.Response(200, text=_page(f'<a namehost="krakenfiles.com" href="{red}">k</a>',
                                                         f'<a namehost="1fichier.com" href="{dead}">f</a>'))
        if req.url.path.endswith("ok1"):  # il salto non va seguito: solo il Location
            return multiup.httpx.Response(302, headers={"location": "https://krakenfiles.com/view/k1/file.html"})
        return multiup.httpx.Response(500)

    real = multiup.httpx.Client
    multiup.httpx.Client = lambda **kw: real(transport=multiup.httpx.MockTransport(handler), **kw)
    try:
        r = multiup.mirrors(REAL_URL)
    finally:
        multiup.httpx.Client = real
    assert [(m["host"], m["url"], m.get("redirect")) for m in r["mirrors"]] == [
        ("krakenfiles.com", "https://krakenfiles.com/view/k1/file.html", None), ("multiup.io", dead, True)]
    print("ok  redirect: un salto, se fallisce resta il link con redirect=true")


def test_rotta_mirrors(tmp_path):
    from fastapi.testclient import TestClient
    from pozzo import config, storelinks as SL
    from pozzo.app.server import create_app
    (tmp_path / "roms").mkdir()
    (tmp_path / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp_path / "config.toml")
    cfg.app["downloads"] = {"max_active": 1, "dir": str(tmp_path / "out")}
    old = SL.resolve
    SL.resolve = lambda cache, url: REAL_URL if url == "https://ouo.io/abc" else url  # niente browser: accorciatore finto
    try:
        _with({REAL_URL: Reply(REAL, REAL_URL)})
        with TestClient(create_app(cfg)) as c:
            j = c.post("/api/links/mirrors", json={"url": "https://ouo.io/abc"}).json()
            assert j["ok"] and j["page"] == REAL_URL and j["name"] and j["reason"] == ""
            assert [m["host"] for m in j["mirrors"]][:2] == ["datanodes.to", "gofile.io"]
            assert c.post("/api/links/mirrors", json={"url": "ftp://x"}).status_code == 400
            assert c.post("/api/links/mirrors", json={}).status_code == 400
            j = c.post("/api/links/mirrors", json={"url": "https://example.com/x"}).json()
            assert not j["ok"] and j["mirrors"] == [] and j["reason"]
            _with({REAL_URL: "<html><head><title>Fichier non trouvé - MultiUp.io</title></head></html>"})
            j = c.post("/api/links/mirrors", json={"url": REAL_URL}).json()
            assert not j["ok"] and j["reason"] == "il file non esiste più su MultiUp"
            SL.resolve = lambda cache, url: url  # accorciatore non saltato
            assert c.post("/api/links/mirrors", json={"url": "https://ouo.io/abc"}).json()["reason"]
    finally:
        SL.resolve = old
    print("ok  rotta /api/links/mirrors")


if __name__ == "__main__":
    test_preferisce_1fichier()
    test_solo_datanodes()
    test_datanodes_prima_di_un_host_sconosciuto()
    test_niente_mirror_o_captcha()
    test_redirect_un_salto()
    test_pagina_corta_e_mirror()
    test_non_multiup()
    test_catena()
    print("TUTTI I TEST OK")


def test_motivo_nelle_note():
    from pozzo.downloads import resolvers
    _with({PAGE: "<html><head><title>Fichier non trouvé - MultiUp.io</title></head></html>"})
    phases = []
    resolvers.register  # le note esistono solo dentro resolve(): si passa da li'
    old = list(resolvers._FNS)
    try:
        resolvers._FNS[:] = [(multiup.resolve, "")]
        url, _by = resolvers.resolve(PAGE, on_phase=phases.append)
    finally:
        resolvers._FNS[:] = old
    assert url == PAGE and any("MultiUp: il file non esiste più su MultiUp" in p for p in phases), phases
