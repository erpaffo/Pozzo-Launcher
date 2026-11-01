"""Impostazioni e account per profilo (pozzo/profilecfg.py): migrazione dai globali, isolamento tra profili,
PIN (solo hash) e limite dei tentativi. Nessuna rete: cartelle temporanee."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config, profilecfg as PC, sync  # noqa: E402
from pozzo.cache import Cache  # noqa: E402


def _cfg(tmp: Path):
    cfg = config.Config(cache=tmp / "cache", output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    cfg.cache.mkdir(parents=True)
    return cfg


def test_migrazione_dai_globali():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        tmp = Path(t)
        cfg = _cfg(tmp)
        config.save_settings(cfg, app={"spotify": {"client_id": "x", "refresh_token": "r"},
                                       "discord": {"enabled": True, "client_id": "1"}})
        c = Cache(cfg.cache)
        c.kv_set("auth:epic", {"refresh_token": "e"})
        c.kv_set("auth:gog", {"refresh_token": "g"})
        c.close()

        PC.migrate(cfg)
        assert PC.get(cfg, "spotify") == {"client_id": "x", "refresh_token": "r"}
        assert PC.get(cfg, "discord") == {"enabled": True, "client_id": "1"}
        assert PC.get(cfg, "epic") == {"refresh_token": "e"} and PC.get(cfg, "gog") == {"refresh_token": "g"}
        assert PC.path(cfg, "default").exists()

        # i globali restano; un secondo avvio non ricopia (il file del profilo e' la fonte)
        config.save_settings(cfg, app={"spotify": {"client_id": "nuovo"}})
        PC.migrate(cfg)
        assert PC.get(cfg, "spotify") == {"client_id": "x", "refresh_token": "r"}
        assert config.read_settings(cfg)["app"]["spotify"]["client_id"] == "nuovo"
        print("ok  migrazione: il principale copia account e impostazioni globali, una volta sola")


def test_account_isolato_tra_profili():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        tmp = Path(t)
        cfg = _cfg(tmp)
        config.save_settings(cfg, app={"spotify": {"client_id": "principale"}})
        PC.migrate(cfg)
        sync.add_profile(cfg, "Luca")

        cfg.app["profile"] = "luca"  # come fa il cambio profilo del server
        assert PC.get(cfg, "spotify") is None, "un profilo nuovo non eredita gli account del principale"
        PC.set(cfg, "spotify", {"client_id": "luca"})
        cfg.app["profile"] = "default"
        assert PC.get(cfg, "spotify")["client_id"] == "principale", "il principale non vede l'account di Luca"
        cfg.app["profile"] = "luca"
        assert PC.get(cfg, "spotify")["client_id"] == "luca"
        PC.set(cfg, "spotify", None)
        assert PC.get(cfg, "spotify") is None
        cfg.app["profile"] = "default"
        assert PC.get(cfg, "spotify")["client_id"] == "principale"
        print("ok  account isolati: ogni profilo ha i suoi, il principale non cambia")


def test_pin_solo_hash():
    h = PC.hash_pin("4321")
    assert PC.check_pin(h, "4321") and not PC.check_pin(h, "4322") and not PC.check_pin(h, "")
    assert PC.hash_pin("4321") != h, "il sale cambia a ogni PIN"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = _cfg(Path(t))
        sync.add_profile(cfg, "Luca")
        for bad in ("12", "12345678901", "12a4", "1 23"):
            try:
                sync.update_profile(cfg, "luca", pin=bad)
                raise AssertionError(f"PIN non valido accettato: {bad!r}")
            except ValueError:
                pass
        sync.update_profile(cfg, "luca", pin="4321")
        assert "'4321'" not in str(cfg.app["profiles"]) and cfg.app["profiles"][-1]["pin_hash"]
        sync.update_profile(cfg, "luca", pin="")
        assert "pin_hash" not in cfg.app["profiles"][-1] and not sync.profiles(cfg)[1]["locked"]
    print("ok  PIN: hash con sale, confronto sicuro, solo 4-8 cifre, toglibile")


def test_limite_tentativi():
    now = [0.0]
    lim = PC.PinLimiter(clock=lambda: now[0])
    for _ in range(4):
        lim.fail("luca")
        assert lim.wait("luca") == 0
    lim.fail("luca")  # quinto errore: 30 secondi di attesa
    assert lim.wait("luca") == 30
    now[0] = 29
    assert lim.wait("luca") == 1
    now[0] = 31
    assert lim.wait("luca") == 0
    lim.fail("luca")
    lim.ok("luca")
    assert lim.wait("luca") == 0
    for _ in range(5):
        lim.fail("altro")
    assert lim.wait("luca") == 0, "un profilo bloccato non blocca gli altri"
    print("ok  limite tentativi: 5 errori, 30 secondi, reset dopo un PIN giusto")


def test_sblocco_dal_server():
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = _cfg(Path(t))
        c = TestClient(create_app(cfg))
        c.post("/api/profiles", json={"name": "Luca"})
        assert c.patch("/api/profiles/luca", json={"pin": "4321"}).status_code == 200
        for _ in range(5):
            assert c.post("/api/profiles/luca/unlock", json={"pin": "0000"}).status_code == 403
        r = c.post("/api/profiles/luca/unlock", json={"pin": "4321"})
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0, r.text
        assert c.patch("/api/profiles/luca", json={"pin": ""}).status_code == 403, "PIN cambiato senza sblocco"
    print("ok  sblocco dal server: PIN errato 403, dopo 5 errori 429 con Retry-After")


if __name__ == "__main__":
    test_migrazione_dai_globali()
    test_account_isolato_tra_profili()
    test_pin_solo_hash()
    test_limite_tentativi()
    test_sblocco_dal_server()
    print("TUTTI I TEST OK")
