"""Route BIOS, emulatore consigliato e installazione «un clic» (pozzo/app/routes/emulators_extra.py).

Nessuna rete: l'installazione e il controllo dei BIOS sono sostituiti da funzioni finte che registrano le chiamate.
Esegui: python tests/test_emulators_extra.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import bios as BI, config, emuinstall_extra as EX  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.boot import registro  # noqa: E402


def _client(tmp: Path):
    (tmp / "config.toml").write_text(f'[paths]\nroms = "{(tmp / "roms").as_posix()}"\n'
                                     f'cache = "{(tmp / "cache").as_posix()}"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    return TestClient(create_app(cfg)), cfg  # senza "with": niente eventi di avvio


def test_bios_e_recommend(tmp: Path):
    c, cfg = _client(tmp)
    r = c.get("/api/emulators/bios", params={"console": "psx"})
    assert r.status_code == 200 and r.json()["console"] == "psx" and "items" in r.json(), r.text

    r = c.get("/api/emulators/bios", params={"console": "xxx"})
    assert r.status_code == 400 and "sconosciuta" in r.json()["detail"], r.text

    r = c.get("/api/emulators/recommend", params={"console": "gba"})
    assert r.status_code == 200 and {"emulator", "reason", "installed", "supported"} <= set(r.json()), r.text
    r = c.get("/api/emulators/recommend", params={"console": "xxx"})
    assert r.status_code == 400, r.text
    print("ok  BIOS e consigliato: risposte, console sconosciuta -> 400")


def test_bios_errori_di_rete_e_disco(tmp: Path):
    c, _ = _client(tmp)
    saved = BI.check
    try:
        def boom_os(console, folder=None):
            raise OSError("disco non leggibile")

        BI.check = boom_os
        r = c.get("/api/emulators/bios", params={"console": "psx"})
        assert r.status_code == 502 and "disco" in r.json()["detail"], r.text
        assert "Connessione" in r.json()["detail"], "messaggio in italiano"

        def boom_val(console, folder=None):
            raise ValueError("console sconosciuta: finta")

        BI.check = boom_val
        assert c.get("/api/emulators/bios", params={"console": "psx"}).status_code == 400
    finally:
        BI.check = saved
    print("ok  BIOS: OSError -> 502, ValueError -> 400, niente 500")


def test_install_recommended(tmp: Path):
    c, cfg = _client(tmp)
    chiamate = []
    saved = EX.install_recommended

    def finta(console_id, progress=None, cfg=None):
        chiamate.append(console_id)
        if progress:
            progress("Scarico l'emulatore", 0.5)
        return {"ok": True, "emulator": "finto", "core_installed": [], "message": "fatto"}

    try:
        EX.install_recommended = finta
        r = c.post("/api/emulators/install-recommended", json={"console": "gba"})
        assert r.status_code == 200 and r.json()["ok"] is True and chiamate == ["gba"], r.text
        snap = c.get("/api/emulators/install-recommended", params={"console": "gba"}).json()
        assert snap["ready"] is True and snap["steps"][0]["state"] == "done", snap

        r = c.post("/api/emulators/install-recommended", json={"console": "xxx"})
        assert r.status_code == 400 and "sconosciuta" in r.json()["detail"], r.text

        # installazione in corso: niente seconda installazione sulla stessa console
        registro("install-gba").start("installa", "in corso")
        r = c.post("/api/emulators/install-recommended", json={"console": "gba"})
        assert r.status_code == 409, r.text
        registro("install-gba").done("installa")

        def rete(console_id, progress=None, cfg=None):
            raise OSError("rete assente")

        EX.install_recommended = rete
        r = c.post("/api/emulators/install-recommended", json={"console": "psx"})
        assert r.status_code == 502 and "rete assente" in r.json()["detail"], r.text
        snap = c.get("/api/emulators/install-recommended", params={"console": "psx"}).json()
        assert snap["ready"] is True and snap["steps"][0]["state"] == "error", "errore registrato, non blocca"

        def esito_no(console_id, progress=None, cfg=None):
            return {"ok": False, "emulator": "finto", "core_installed": [], "message": "release senza file per Windows."}

        EX.install_recommended = esito_no
        r = c.post("/api/emulators/install-recommended", json={"console": "switch"})
        assert r.status_code == 502 and r.json()["detail"] == "release senza file per Windows.", r.text
    finally:
        EX.install_recommended = saved
    print("ok  install-recommended: successo, 400, 409 in corso, 502 con messaggio, registro coerente")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        tmp = Path(t)
        test_bios_e_recommend(tmp)
        test_bios_errori_di_rete_e_disco(tmp)
        test_install_recommended(tmp)
    print("TUTTI I TEST OK")


if __name__ == "__main__":
    main()
