"""Pagina del telefono: tutto quello che carica deve passare dal cancello del telefono (PhoneGate).

Bug: /static/i18n.js e /api/i18n davano 403 al telefono, t() mancava e la pagina si rompeva tutta (libreria vuota,
giochi che non partono, pulsanti del controller fermi, «Can't find variable: t» su iPhone).
Copre: ogni src/href di /m/ risponde 200 a un telefono abbinato; le traduzioni rispondono anche prima dell'abbinamento.

Esegui: python tests/test_phone_page_assets.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.remote import phone as PH  # noqa: E402


def main():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    app = create_app(config.load(tmp / "config.toml"))
    hub = app.state.phone_hub
    api = TestClient(PH.PhoneGate(app, hub), base_url="https://testserver")

    for p in ("/api/i18n", "/api/i18n/it", "/m/static/i18n.js"):  # schermata di abbinamento: nessun cookie
        assert api.get(p).status_code == 200, p
    print("ok  traduzioni raggiungibili prima dell'abbinamento")

    token = hub.pair(hub.new_code(), "iPhone")
    h = {"Cookie": f"{PH.COOKIE}={token}"}
    html = api.get("/m/", headers=h).text
    paths = re.findall(r'(?:src|href)="(/[^"]+)"', html)
    assert any(p.endswith("i18n.js") for p in paths), paths
    bad = [(p, r.status_code) for p in paths if (r := api.get(p, headers=h)).status_code != 200]
    assert not bad, bad
    print(f"ok  {len(paths)} file della pagina del telefono raggiungibili da un telefono abbinato")


if __name__ == "__main__":
    main()
