"""Filtri salvati: pulizia dei dati e separazione per profilo (nessun server)."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import profilecfg as PC
from pozzo.app.routes.collart import clean_filters

# pulizia: scarta voci senza nome o senza filtri, limita i campi, tiene solo viste note
items = [
    {"id": "a", "name": "  Platform anni 90  ", "f": {"search": "x" * 200, "sort": "year", "disc": {"decade": "1990", "genre": "Platform", "zz": "1"},
                                                    "view": {"type": "platform", "id": "snes"}}},
    {"name": "   ", "f": {}},
    {"name": "senza f"},
    {"name": "vista strana", "f": {"view": {"type": "evil", "id": "1"}}},
]
out = clean_filters(items, now_ms=5)
assert [x["name"] for x in out] == ["Platform anni 90", "vista strana"]
assert len(out[0]["f"]["search"]) == 80
assert out[0]["f"]["disc"] == {"preset": "", "genre": "Platform", "decade": "1990"}
assert out[0]["f"]["view"] == {"type": "platform", "id": "snes"}
assert "view" not in out[1]["f"] and out[1]["id"].startswith("f5")

# per profilo: ognuno vede i propri
with tempfile.TemporaryDirectory() as d:
    cfg = SimpleNamespace(app={"profile": "default", "profiles": [{"id": "bimbo"}]}, config_path=Path(d) / "config.toml",
                          settings_path=lambda: Path(d) / "settings.json")
    import pozzo.config as C
    C.settings_path = lambda c: Path(d) / "settings.json"
    PC.set(cfg, "saved_filters", [{"id": "1", "name": "mio"}])
    with PC.override("bimbo"):
        assert PC.get(cfg, "saved_filters") is None
        PC.set(cfg, "saved_filters", [{"id": "2", "name": "suo"}])
        assert PC.get(cfg, "saved_filters")[0]["name"] == "suo"
    assert PC.get(cfg, "saved_filters")[0]["name"] == "mio"
print("ok")
