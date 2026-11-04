"""Route impostazioni webhook: validazione e salvataggio. Nessuna rete.

Esegui: python -m pytest tests/test_webhooks_routes.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402


def test_webhooks_validation_and_save(tmp_path: Path):
    (tmp_path / "roms").mkdir()
    (tmp_path / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n',
                                          encoding="utf-8")
    cfg = config.load(tmp_path / "config.toml")
    api = TestClient(create_app(cfg))
    try:
        bad = {"url": "ftp://esempio.test/hook", "events": ["gioco_avviato"]}
        assert api.post("/api/webhooks", json={"webhooks": [bad]}).status_code == 400
        unknown = {"url": "https://esempio.test/hook", "events": ["cosa_strana"]}
        assert api.post("/api/webhooks", json={"webhooks": [unknown]}).status_code == 400
        assert not (tmp_path / "settings.json").exists() or "webhooks" not in json.loads(
            (tmp_path / "settings.json").read_text(encoding="utf-8")).get("app", {})

        good = {"url": " https://ha.esempio.test/api/webhook/pozzo ", "events": ["prezzo_sceso", "gioco_avviato"],
                "secret": "  s3gr3to  "}
        r = api.post("/api/webhooks", json={"webhooks": [good]})
        assert r.status_code == 200, r.text
        url = "https://ha.esempio.test/api/webhook/pozzo"
        public = [{"url": url, "events": ["gioco_avviato", "prezzo_sceso"], "enabled": True, "has_secret": True}]
        assert r.json()["webhooks"] == public, "il segreto non torna mai al browser"
        assert cfg.app["webhooks"] == [{"url": url, "events": ["gioco_avviato", "prezzo_sceso"], "enabled": True,
                                        "secret": "s3gr3to"}]
        assert api.get("/api/webhooks").json() == {"webhooks": public}
        assert "s3gr3to" not in api.get("/api/webhooks").text

        # campo vuoto: il segreto resta (anche cambiando indirizzo, grazie a «orig»)
        url2 = "https://ha.esempio.test/api/webhook/nuovo"
        api.post("/api/webhooks", json={"webhooks": [{"url": url2, "orig": url, "events": ["gioco_avviato"], "secret": ""}]})
        assert cfg.app["webhooks"][0]["secret"] == "s3gr3to"
        # valore nuovo: sostituisce; clear_secret: lo toglie
        api.post("/api/webhooks", json={"webhooks": [{"url": url2, "orig": url2, "events": ["gioco_avviato"], "secret": "n"}]})
        assert cfg.app["webhooks"][0]["secret"] == "n"
        r = api.post("/api/webhooks", json={"webhooks": [{"url": url2, "orig": url2, "events": [], "clear_secret": True}]})
        assert "secret" not in cfg.app["webhooks"][0] and r.json()["webhooks"][0]["has_secret"] is False
    finally:
        api.close()
