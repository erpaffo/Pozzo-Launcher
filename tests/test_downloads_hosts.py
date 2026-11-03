"""Dalla pagina di un host al link diretto (DataNodes, 1Fichier, KrakenFiles, MegaUp) e rifiuto delle
pagine HTML salvate come file. Nessuna rete: le risposte sono finte.

Esegui: PYTHONUTF8=1 python tests/test_downloads_hosts.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import storelinks as SL  # noqa: E402
from pozzo.downloads import hosts  # noqa: E402
from pozzo.downloads.engines import http as HTTP  # noqa: E402


class Reply:
    def __init__(self, text="", headers=None, data=None):
        self.text, self.headers, self._data = text, headers or {}, data

    def json(self):
        return self._data


class Session:
    """Sostituisce httpx.Client: risponde come la pagina vera, senza rete."""

    def __init__(self, get=None, post=None):
        self._get, self._post = get, post

    def get(self, url, **kw):
        return self._get(url) if self._get else Reply()

    def post(self, url, **kw):
        return self._post(url, kw) if self._post else Reply()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(session, browser=None):
    """Sostituisce il client HTTP e il browser: restituisce le funzioni per rimettere tutto com'era."""
    old_client, old_browser = hosts.httpx.Client, SL.with_browser
    hosts.httpx.Client = lambda *a, **k: session
    SL.with_browser = lambda url: (browser or (lambda u: ""))(url)
    return old_client, old_browser


def _restore(old_client, old_browser):
    hosts.httpx.Client, SL.with_browser = old_client, old_browser


def test_datanodes():
    """DataNodes è «solo browser»: nessuna richiesta HTTP, il link lo dà il download del WebView."""
    assert hosts.is_host_page("https://datanodes.to/abc123xy/") and "datanodes.to" in hosts.BROWSER_ONLY
    calls = []
    old = _patch(Session(), browser=lambda u: calls.append(u) or "https://tunnel5.dlproxy.uk/download/abc?sig=1")
    try:
        assert hosts.resolve("https://datanodes.to/abc123xy/") == "https://tunnel5.dlproxy.uk/download/abc?sig=1"
        assert calls == ["https://datanodes.to/abc123xy/"], calls
    finally:
        _restore(*old)
    print("ok  datanodes: solo browser, link dal download del WebView")


def test_is_file_url():
    page = "https://datanodes.to/abc123xy/Gioco"
    assert hosts.is_file_url("https://s12.datanodes.to/d/abc123xy/Gioco.nsp", page), "CDN diverso"
    assert hosts.is_file_url("https://datanodes.to/abc123xy/Gioco.nsp", page), "estensione di file"
    assert hosts.is_file_url("https://datanodes.to/d/abc123xy/x", page), "percorso /d/"
    assert hosts.is_file_url("https://megaup.net/download/tok123", page), "endpoint del file con token"
    assert not hosts.is_file_url("https://datanodes.to/download", page), "il modulo non è un file"
    assert not hosts.is_file_url("https://datanodes.to/abc123xy/Gioco", page), "la pagina stessa"
    assert not hosts.is_file_url("javascript:void(0)", page)
    print("ok  is_file_url: CDN, estensione e /d/ sì; modulo e pagina stessa no")


def test_fichier():
    """Un POST sulla pagina, il link sta nel pulsante arancione; il limite per IP non si insiste."""
    page = '<div class="ct_warn">wait</div><a class="ok btn-general btn-orange" href="https://a-3.1fichier.com/xyz">Scarica</a>'
    old = _patch(Session(post=lambda url, kw: Reply(text=page)))
    try:
        assert hosts.resolve("https://1fichier.com/?xyz") == "https://a-3.1fichier.com/xyz"
    finally:
        _restore(*old)
    old = _patch(Session(post=lambda url, kw: Reply(text="Vous devez attendre, you must wait 30 minutes")))
    try:
        assert hosts.resolve("https://1fichier.com/?xyz") == "", "limite per IP: niente link inventato"
    finally:
        _restore(*old)
    home = "<html><head><title>1fichier.com: Cloud Storage</title></head><body>Prices Register</body></html>"
    old = _patch(Session(post=lambda url, kw: Reply(text=home)),
                 browser=lambda u: (_ for _ in ()).throw(AssertionError("qui il browser non serve")))
    try:
        assert hosts.resolve("https://1fichier.com/?rimosso") == "", "file rimosso: la home, non un file"
    finally:
        _restore(*old)
    print("ok  1fichier: POST -> pulsante arancione, limite per IP e file rimosso riconosciuti")


def test_krakenfiles():
    """Form #dl-form con token, POST in JSON."""
    page = ('<form id="dl-form" action="/download/abc">'
            '<input type="hidden" id="dl-token" value="tok123"></form>')

    def post(url, kw):
        assert url == "https://krakenfiles.com/download/abc" and kw["data"] == {"token": "tok123"}, kw
        return Reply(data={"status": "ok", "url": "https://s3.krakenfiles.com/file/Gioco.nsp"})

    old = _patch(Session(get=lambda url: Reply(text=page), post=post))
    try:
        assert hosts.resolve("https://krakenfiles.com/view/abc/view.html") == \
            "https://s3.krakenfiles.com/file/Gioco.nsp"
    finally:
        _restore(*old)
    print("ok  krakenfiles: form + token -> JSON con l'url")


def test_megaup():
    page = '<a id="btn-download" class="btn" href="/download/abc123">Download</a>'
    old = _patch(Session(get=lambda url: Reply(text=page)))
    try:
        assert hosts.resolve("https://megaup.net/abc123/") == "https://megaup.net/download/abc123"
    finally:
        _restore(*old)
    print("ok  megaup: pulsante di download -> link assoluto")


def test_browser_fallback():
    """Captcha o pagina senza link: la pagina si apre nel browser nascosto (una volta sola)."""
    calls = []
    old = _patch(Session(), browser=lambda url: calls.append(url) or "https://cdn.example.test/Gioco.nsp")
    try:
        assert hosts.resolve("https://megaup.net/abc123/") == "https://cdn.example.test/Gioco.nsp"
        assert calls == ["https://megaup.net/abc123/"], calls
    finally:
        _restore(*old)
    old = _patch(Session(), browser=lambda url: url)  # il browser torna sulla stessa pagina
    try:
        assert hosts.resolve("https://krakenfiles.com/view/abc/view.html") == "", "la pagina dell'host non è il file"
    finally:
        _restore(*old)
    old = _patch(Session(), browser=lambda url: "https://megaup.net/download")  # il browser finisce sul modulo
    try:
        assert hosts.resolve("https://megaup.net/abc123/") == "", "il modulo non e' un file"
    finally:
        _restore(*old)
    assert hosts.resolve("https://example.test/gioco.nsp") == "", "host sconosciuto: link invariato"
    print("ok  ripiego sul browser, pagina dell'host scartata, host sconosciuto invariato")


def test_guardia_html():
    """Una pagina HTML non diventa mai un file: errore chiaro invece di un .nsp da 40 KB."""
    class Stream:
        def __init__(self, headers):
            self.headers = headers
            self.status_code = 200
            self.url = "https://x/Gioco.nsp"

        def raise_for_status(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class Client:
        def __init__(self, headers):
            self.headers = headers

        def stream(self, *a, **k):
            return Stream(self.headers)

    def meta(headers):
        r = Stream(headers)
        return HTTP._meta(r, "https://x/y")

    try:
        meta({"content-type": "text/html; charset=utf-8"})
        raise AssertionError("una pagina HTML deve essere rifiutata")
    except ValueError as e:
        assert "pagina" in str(e), e
    name, total, ranged, tag = meta({"content-type": "application/octet-stream", "content-length": "10"})
    assert name == "Gioco.nsp" and total == 10 and not ranged, (name, total, ranged)
    print("ok  guardia: text/html rifiutato, un file vero passa")


def test_fasi():
    """Ogni risolutore annuncia il suo passaggio prima di partire: è quello che si vede nella coda."""
    from pozzo.downloads import resolvers

    saved = list(resolvers._FNS)
    try:
        resolvers._FNS.clear()
        resolvers.register(lambda u: "https://datanodes.to/abc/Gioco.nsp" if "ouo" in u else "",
                          lambda u: "Salto la pubblicità (ouo.io)" if "ouo" in u else "")
        resolvers.register(lambda u: u, lambda u: "Cerco il file su datanodes.to" if "datanodes.to" in u else "")
        seen = []
        resolvers.resolve("https://ouo.io/x", on_phase=seen.append)
        assert seen == ["Salto la pubblicità (ouo.io)", "Cerco il file su datanodes.to"], seen
        seen.clear()
        resolvers.resolve("https://datanodes.to/abc/Gioco", on_phase=seen.append)
        assert seen == ["Cerco il file su datanodes.to"], seen
        seen.clear()
        resolvers.resolve("https://altro.test/x", on_phase=seen.append)
        assert seen == [], seen
        resolvers.resolve("https://ouo.io/x")  # senza callback: nessun errore
    finally:
        resolvers._FNS[:] = saved
    print("ok  passaggi: l'etichetta arriva prima di ogni risolutore, vuota = non mostrata")


def test_cattura_download_solo_su_windows():
    """L'URL del file si legge dall'evento di download di WebView2: altrove la cattura non c'è e nessuno aspetta."""
    from pozzo.app import browserdl

    old_plat, old_on = browserdl.sys.platform, browserdl._HOOKED["on"]
    try:
        browserdl._HOOKED["on"] = False
        for plat in ("linux", "darwin"):
            browserdl.sys.platform = plat
            assert browserdl.install() is False and not browserdl.available(), plat
    finally:
        browserdl.sys.platform, browserdl._HOOKED["on"] = old_plat, old_on
    op = type("DownloadOperation", (), {"Uri": "https://tunnel5.dlproxy.uk/download/abc?sig=1"})()
    assert browserdl._record(type("Args", (), {"DownloadOperation": op})()) == op.Uri
    assert browserdl._record(object()) == "", "senza l'attributo non si rompe niente"
    print("ok  cattura del download: solo Windows, URL letto senza WebView2 nei test")


if __name__ == "__main__":
    test_datanodes()
    test_is_file_url()
    test_fichier()
    test_krakenfiles()
    test_megaup()
    test_browser_fallback()
    test_fasi()
    test_cattura_download_solo_su_windows()
    test_guardia_html()
    print("TUTTI I TEST OK")
