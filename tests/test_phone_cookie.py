"""Cookie del telefono abbinato: SameSite=Lax (non Strict).

Safari su iPhone non manda i cookie Strict quando l'app viene riaperta dall'icona nella Home: sembrava non abbinata.
Copre: l'abbinamento imposta Lax; /m/api/hello riemette il cookie (i telefoni col vecchio Strict passano a Lax);
senza cookie /m/api/hello non ne crea uno.

Esegui: python tests/test_phone_cookie.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo.remote import phone as PH  # noqa: E402
from test_phone_downloads import make_client, make_hub  # noqa: E402


def test_abbinamento_lax():
    hub = make_hub()
    api = make_client(hub, [])
    r = api.post("/m/api/pair", json={"code": hub.new_code(), "name": "iPhone"})
    sc = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "samesite=lax" in sc and "httponly" in sc and "secure" in sc, sc
    print("ok  abbinamento: cookie Lax, HttpOnly, Secure")


def test_hello_riemette_lax():
    hub = make_hub()
    token = hub.pair(hub.new_code(), "iPhone")
    api: TestClient = make_client(hub, [])
    r = api.get("/m/api/hello", headers={"Cookie": f"{PH.COOKIE}={token}"})
    assert r.json()["paired"] is True
    assert "samesite=lax" in r.headers.get("set-cookie", "").lower(), r.headers
    api.cookies.clear()  # il TestClient terrebbe il cookie appena ricevuto
    r = api.get("/m/api/hello")
    assert r.json()["paired"] is False and "set-cookie" not in r.headers
    print("ok  hello: abbinato -> cookie riemesso Lax; non abbinato -> nessun cookie")


if __name__ == "__main__":
    test_abbinamento_lax()
    test_hello_riemette_lax()
