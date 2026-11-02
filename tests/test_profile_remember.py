"""«Entra sempre con questo profilo su questo dispositivo»: cookie gs_remember per dispositivo (PC e telefono non si
influenzano), GET /api/profiles dice `remembered`, con un PIN non sbloccato si chiede comunque. Nessuna rete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config, sync  # noqa: E402


def test_ricorda_su_questo_dispositivo(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = config.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    app = create_app(cfg)
    pc, phone = TestClient(app), TestClient(app)
    remembered = lambda c: c.get("/api/profiles").json()["remembered"]  # noqa: E731

    pc.post("/api/profiles", json={"name": "Luca"})
    st = pc.get("/api/profiles").json()
    assert st["ask"] is True and st["remembered"] is False, "con 2 profili si chiede, e nessuno ha ancora ricordato"

    # scelta con la casella spuntata: ricorda il profilo di questo dispositivo, non quello degli altri
    r = pc.post("/api/profiles/active", json={"id": "luca", "remember": True})
    assert r.status_code == 200 and "gs_remember=1" in r.headers["set-cookie"]
    assert remembered(pc) is True and remembered(phone) is False
    # senza il campo la scelta del dispositivo non cambia; con false si torna a chiedere
    assert pc.post("/api/profiles/active", json={"id": "default"}).status_code == 200
    assert remembered(pc) is True
    assert pc.post("/api/profiles/active", json={"id": "default", "remember": False}).status_code == 200
    assert remembered(pc) is False

    # dalle Impostazioni: ricorda il profilo in uso / chiedi di nuovo
    assert pc.post("/api/profiles/remember", json={"remember": True}).json() == {"remembered": True}
    assert remembered(pc) is True and pc.get("/api/profiles").json()["active"] == "default"
    assert pc.post("/api/profiles/remember", json={"remember": False}).json() == {"remembered": False}
    assert remembered(pc) is False

    # profilo con PIN: finche' non e' sbloccato in questa sessione, si chiede comunque
    sync.update_profile(cfg, "luca", pin="1234")
    assert pc.post("/api/profiles/active", json={"id": "luca", "pin": "1234", "remember": True}).status_code == 200
    assert remembered(pc) is True, "sbloccato con il PIN giusto"
    # nuovo avvio dell'app (sessione del server nuova): il PIN non e' sbloccato, quindi si chiede comunque
    again = TestClient(create_app(cfg))
    again.cookies.set("gs_profile", "luca")
    again.cookies.set("gs_remember", "1")
    assert remembered(again) is False, "dopo un riavvio un profilo con PIN chiede di nuovo il PIN"
    assert again.post("/api/profiles/luca/unlock", json={"pin": "1234"}).status_code == 200
    assert remembered(again) is True

    # un profilo eliminato non e' piu' ricordato
    sync.update_profile(cfg, "luca", pin="")
    assert pc.post("/api/profiles/active", json={"id": "default"}).status_code == 200
    pc.cookies.set("gs_profile", "inesistente")
    assert remembered(pc) is False
