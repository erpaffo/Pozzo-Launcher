"""Click'n'Load: le quattro rotte su un server vero (porta a caso), cifratura come la fa una pagina, limiti, elenco in
attesa e nessun download aggiunto senza conferma. Nessuna rete esterna (link con IP pubblici scritti, niente DNS)."""

import base64
import socket
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.downloads import clicknload as CNL  # noqa: E402
from pozzo.downloads import manager as M  # noqa: E402

KEY = b"1234567890987654"  # la chiave dell'esempio della wiki di JDownloader
JK = "function f(){ return '31323334353637383930393837363534';}"
GOOD = ["https://1.1.1.1/gioco.part1.rar", "http://8.8.8.8/b.zip",
        "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=x"]
BAD = ["file:///etc/passwd", "ftp://8.8.8.8/x", "javascript:alert(1)", "http://192.168.1.1/router", "C:\\Windows\\x.exe"]


def _crypt(text: str, key: bytes = KEY) -> str:
    """Come una pagina Click'n'Load: AES-128-CBC, IV = chiave, riempito con NUL fino al blocco."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    data = text.encode()
    data += b"\0" * (-len(data) % 16)
    e = Cipher(algorithms.AES(key), modes.CBC(key)).encryptor()
    return base64.b64encode(e.update(data) + e.finalize()).decode()


@pytest.fixture
def cnl():
    c = CNL.ClickNLoad(port=0)
    c.apply(True)
    host, port = c.server.server_address[:2]
    c.url = f"http://{host}:{port}"
    yield c
    c.apply(False)


def test_spento_di_default_e_solo_loopback():
    assert M.DEFAULTS["clicknload"] is False and CNL.PORT == 9666 and CNL.HOST == "127.0.0.1"
    c = CNL.ClickNLoad(port=0)
    assert c.server is None  # nessun server finche' l'impostazione non e' attiva
    c.apply(True)
    try:
        assert c.server.server_address[0] == "127.0.0.1"
    finally:
        c.apply(False)
    assert c.server is None


def test_rotte_di_controllo_e_nient_altro(cnl):
    r = httpx.get(cnl.url + "/jdcheck.js")
    assert r.status_code == 200 and r.text.startswith("jdownloader=true;") and "javascript" in r.headers["content-type"]
    for p in ("/flash", "/flash/"):
        assert httpx.get(cnl.url + p).text.strip() == "JDownloader"
    for p in ("/", "/api/downloads", "/static/app.js", "/flash/add", "/crossdomain.xml", "/../etc/passwd"):
        assert httpx.get(cnl.url + p).status_code == 404, p
    assert httpx.post(cnl.url + "/api/downloads", data={"urls": GOOD[0]}).status_code == 404
    assert not cnl.pending()


def test_add_tiene_solo_http_https_magnet(cnl):
    r = httpx.post(cnl.url + "/flash/add", data={"urls": "\r\n".join(BAD + GOOD), "passwords": "pw1\nPw2",
                                                 "source": "https://pagina.example/thread/1"})
    assert r.status_code == 200 and r.text.strip() == "success"
    [p] = cnl.pending()
    assert p["links"] == GOOD and p["passwords"] == ["pw1", "Pw2"]
    assert p["source"] == "https://pagina.example/thread/1" and p["site"] == "pagina.example"
    r = httpx.post(cnl.url + "/flash/add", data={"urls": "\n".join(BAD)})  # niente di buono: niente in attesa
    assert r.status_code == 400 and len(cnl.pending()) == 1


def test_addcrypted2_andata_e_ritorno(cnl):
    r = httpx.post(cnl.url + "/flash/addcrypted2", data={"crypted": _crypt("\r\n".join(GOOD + BAD)), "jk": JK,
                                                         "passwords": "segreta", "source": "https://x.example/p"})
    assert r.status_code == 200 and r.text.strip() == "success", r.text
    [p] = cnl.pending()
    assert p["links"] == GOOD and p["passwords"] == ["segreta"]
    for jk in ('function f(){ return "31323334353637383930393837363534" }', "function f() {return '31323334353637383930393837363534'}"):
        assert CNL.key_from_jk(jk) == KEY  # le forme solite


@pytest.mark.parametrize("jk", [
    "", "31323334353637383930393837363534",  # niente funzione
    "function f(){ return '3132333435363738393039383736353';}",  # 31 cifre
    "function f(){ return '31323334353637383930393837363534' + x;}",
    "function f(){ return eval(atob('MTIz'));}",
    "function f(){ fetch('http://evil'); return '31323334353637383930393837363534';}",
    "function f(){ return '31323334353637383930393837363534';} f(); alert(1)",
])
def test_jk_malformato_rifiutato(cnl, jk):
    r = httpx.post(cnl.url + "/flash/addcrypted2", data={"crypted": _crypt(GOOD[0]), "jk": jk})
    assert r.status_code == 400 and not cnl.pending()


def test_cifrato_rotto_e_corpo_troppo_grande(cnl):
    for crypted in ("non base64 !!", base64.b64encode(b"corto").decode(), _crypt(GOOD[0], b"x" * 16)):
        r = httpx.post(cnl.url + "/flash/addcrypted2", data={"crypted": crypted, "jk": JK})
        assert r.status_code == 400
    r = httpx.post(cnl.url + "/flash/add", data={"urls": "https://1.1.1.1/a\n" * 20_000})
    assert r.status_code == 413
    assert not cnl.pending()
    assert httpx.get(cnl.url + "/flash").status_code == 200  # il server e' ancora vivo


def test_elenco_in_attesa_con_tetto(cnl):
    for i in range(CNL.MAX_PENDING):
        assert httpx.post(cnl.url + "/flash/add", data={"urls": f"https://1.1.1.1/{i}"}).status_code == 200
    assert httpx.post(cnl.url + "/flash/add", data={"urls": "https://1.1.1.1/troppi"}).status_code == 400
    many = "\n".join(f"https://1.1.1.1/f{i}" for i in range(200))
    first = cnl.pending()[0]
    assert cnl.take(first["id"]) == first and cnl.take(first["id"]) is None
    assert httpx.post(cnl.url + "/flash/add", data={"urls": many}).status_code == 200
    assert len(cnl.pending()[-1]["links"]) == 50  # stesso tetto degli appunti


def test_porta_occupata_segnalata_senza_crash():
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    try:
        c = CNL.ClickNLoad(port=busy.getsockname()[1])
        c.apply(True)
        assert c.server is None and c.error == "busy"
        c.apply(False)
        assert c.error == ""
    finally:
        busy.close()


def test_niente_in_coda_senza_conferma(tmp, monkeypatch):
    from fastapi.testclient import TestClient
    from pozzo import config
    from pozzo.app.server import create_app
    monkeypatch.setattr(CNL, "PORT", 0)
    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.app["downloads"] = {"max_active": 0, "dir": str(tmp / "out")}
    app = create_app(cfg)
    with TestClient(app) as c:
        cnl = app.state.clicknload
        s = c.get("/api/downloads").json()["settings"]
        assert s["clicknload"] is False and s["clicknload_error"] == ""
        r = c.post("/api/downloads/settings", json={"clicknload": True})
        assert r.status_code == 200 and r.json()["clicknload"] is True
        url = "http://127.0.0.1:%d" % cnl.server.server_address[1]
        assert httpx.post(url + "/flash/add", data={"urls": "\n".join(GOOD), "source": "https://s.example/"}).text.strip() == "success"
        assert c.get("/api/downloads").json()["tasks"] == []  # arrivati, ma non in coda
        [p] = c.get("/api/downloads/clicknload").json()["pending"]
        assert p["links"] == GOOD
        got = c.post(f"/api/downloads/clicknload/{p['id']}/take", json={}).json()
        assert got["links"] == GOOD and c.get("/api/downloads/clicknload").json()["pending"] == []
        assert c.get("/api/downloads").json()["tasks"] == []  # li aggiunge solo il dialog, confermato dalla persona
        assert c.post(f"/api/downloads/clicknload/{p['id']}/take", json={}).status_code == 404
        c.post("/api/downloads/settings", json={"clicknload": False})
        assert cnl.server is None
        with pytest.raises(httpx.ConnectError):
            httpx.get(url + "/flash")

