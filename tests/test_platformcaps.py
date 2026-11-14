"""Funzioni mancanti fuori da Windows: liste per piattaforma, chiavi i18n, rotta."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config, platformcaps  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402

from unittest import mock  # noqa: E402

assert platformcaps.missing("win32") == []
with mock.patch.object(platformcaps.shutil, "which", return_value=None):  # nessun programma esterno installato
    dar, lin = platformcaps.missing("darwin"), platformcaps.missing("linux")
with mock.patch.object(platformcaps.shutil, "which", return_value="/usr/bin/x"):  # installati: voci sparite
    pieno = platformcaps.missing("linux")
assert "p.missing.xdotool" not in pieno and "p.missing.notifysend" not in pieno and "p.missing.dolphin" in pieno
for l in (dar, lin):
    assert "p.missing.vigem" in l and "p.missing.xenia" in l
assert "p.missing.powerplan" in dar and "p.missing.xdotool" not in dar
assert "p.missing.xdotool" in lin and "p.missing.dolphin" in lin and "p.missing.powerplan" not in lin
loc = Path(__file__).resolve().parent.parent / "pozzo" / "data" / "locales"
for lang in ("it", "en"):
    cat = json.loads((loc / f"{lang}.json").read_text(encoding="utf-8"))
    assert all(k in cat for k in dar + lin + ["p.missing.title", "p.missing.intro", "p.missing.notice"]), lang

tmp = Path(tempfile.mkdtemp())
cfg = config.Config(cache=tmp, output=tmp / "out", roms=tmp / "roms")
cfg.config_path = tmp / "config.toml"
r = TestClient(create_app(cfg)).get("/api/platform/missing").json()
assert r["platform"] == sys.platform and r["missing"] == platformcaps.missing(), r
print("ok")
