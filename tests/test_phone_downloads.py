"""Telefono abbinato che accoda link sul PC (POST /m/api/downloads).

Copre: senza abbinamento 401; con un link javascript: 400; con un link https la chiamata arriva alla stessa
funzione di POST /api/downloads, con solo i link (niente cartella o priorita' scelte dal telefono).

Esegui: python tests/test_phone_downloads.py  (oppure pytest tests/test_phone_downloads.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Body, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo.remote import phone as PH  # noqa: E402


def make_hub() -> PH.PhoneHub:
    tmp = Path(tempfile.mkdtemp())
    (tmp / "roms").mkdir(exist_ok=True)
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    return PH.PhoneHub(config.load(tmp / "config.toml"), config.save_settings)


def make_client(hub: PH.PhoneHub, calls: list) -> TestClient:
    app = FastAPI()

    def fake_add(body: dict = Body(...)):  # finta coda del PC (come routes/downloads.py): registra cosa riceve
        calls.append(body)
        return {"ok": True, "tasks": []}
    app.state.downloads_add = fake_add

    PH.register(app, hub, Path(tempfile.mkdtemp()))
    return TestClient(PH.PhoneGate(app, hub), base_url="https://testserver")


def test_non_abbinato_401():
    hub, calls = make_hub(), []
    r = make_client(hub, calls).post("/m/api/downloads", json={"links": ["https://example.com/a"]})
    assert r.status_code == 401, r.status_code
    assert not calls, "senza abbinamento il link non deve arrivare alla coda"
    print("ok  senza abbinamento: 401")


def test_abbinato_link_non_valido_400_e_https_inoltrato():
    hub, calls = make_hub(), []
    token = hub.pair(hub.new_code(), "Telefono di prova")
    api = make_client(hub, calls)
    cookie = {"Cookie": f"{PH.COOKIE}={token}"}

    r = api.post("/m/api/downloads", json={"links": ["javascript:alert(1)"]}, headers=cookie)
    assert r.status_code == 400, r.status_code
    assert not calls, "un link javascript: non deve arrivare alla coda"

    r = api.post("/m/api/downloads", json={"links": ["  https://example.com/gioco.zip  ", "magnet:?xt=urn:btih:abc"],
                                          "save_path": "C:/Windows", "priority": 2}, headers=cookie)
    assert r.status_code == 200, r.text
    assert calls == [{"links": ["https://example.com/gioco.zip", "magnet:?xt=urn:btih:abc"]}], calls
    print("ok  abbinato: javascript: 400, https e magnet inoltrati puliti alla coda")


def test_app_vera_rotta_trovata():
    """Con l'app vera (create_app) la rotta POST /api/downloads si trova per percorso e riceve solo i link."""
    from pozzo.app.server import create_app
    from pozzo.downloads.manager import Manager

    tmp = Path(tempfile.mkdtemp())
    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    seen = []

    class _T:
        def __init__(self, u):
            self.u = u

        def view(self):
            return {"source": self.u}

    def fake_add(self, u, save_path="", **kw):
        seen.append((u, save_path, kw.get("priority")))
        return _T(u)

    orig, Manager.add = Manager.add, fake_add
    try:
        app = create_app(config.load(tmp / "config.toml"))
        hub = app.state.phone_hub
        token = hub.pair(hub.new_code(), "Telefono di prova")
        api = TestClient(PH.PhoneGate(app, hub), base_url="https://testserver")
        r = api.post("/m/api/downloads", json={"links": ["https://example.com/a.zip"], "save_path": "C:/Windows"},
                     headers={"Cookie": f"{PH.COOKIE}={token}"})
    finally:
        Manager.add = orig
    assert r.status_code == 200, r.text
    assert len(r.json()["tasks"]) == 1, r.json()  # m.js conta i download aggiunti da qui
    assert seen == [("https://example.com/a.zip", "", 0)], seen
    print("ok  app vera: rotta trovata, solo i link")


if __name__ == "__main__":
    test_app_vera_rotta_trovata()
    test_non_abbinato_401()
    test_abbinato_link_non_valido_400_e_https_inoltrato()
