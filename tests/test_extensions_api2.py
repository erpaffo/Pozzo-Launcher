"""Estensioni API 2: api = 2 si carica, api = 1 continua a funzionare, api troppo alta resta spenta.

Copre anche le registrazioni dichiarative (kind di libreria, player, scraper), il permesso «media:lettura» e la
lettura da /api/extensions.

Esegui: python -m pytest tests/test_extensions_api2.py
"""

from __future__ import annotations

import shutil
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo.app import extensions as X  # noqa: E402

# un'estensione api = 1 come quelle gia' pubblicate: fonte di metadati + rotta
VECCHIA = ("def register(gs):\n"
           "    gs.add_source(type('Vecchia', (), {'name': 'vecchia'}))\n"
           "    @gs.route('ciao')\n"
           "    def ciao():\n"
           "        return {'ok': 1}\n")

# un'estensione api = 2 dei media: sezione, player e ricetta
NUOVA = ("def register(gs):\n"
         "    gs.add_library_kind({'id': 'film', 'label': 'Film', 'icon': 'x'})\n"
         "    gs.add_player({'id': 'integrato', 'label': 'Lettore', 'mode': 'integrato'})\n"
         "    gs.add_scraper({'id': 'internet-archive', 'url': 'https://archive.org/details/x'})\n"
         "    @gs.route('ciao')\n"
         "    def ciao():\n"
         "        return {'ok': 2}\n")


def make(tmp_path: Path, plugins: dict[str, tuple[str, str]]):
    """plugins: {id: (valore di api nel manifest, sorgente backend)}."""
    for pid, (api, src) in plugins.items():
        d = tmp_path / "plugins" / pid
        d.mkdir(parents=True)
        (d / "plugin.toml").write_text(f'[plugin]\nname = "{pid}"\napi = {api}\n', encoding="utf-8")
        (d / "backend.py").write_text(src, encoding="utf-8")
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={})
    app, log = FastAPI(), []
    errors = X.load_backends(app, cfg, X.Events(), log.append)
    return app, cfg, errors, log


@pytest.fixture(autouse=True)
def _clean():
    yield
    X.stop_jobs()
    for reg in (X.LIBRARY_KINDS, X.PLAYERS, X.SCRAPERS):
        reg.clear()
    for d in (X.LOAD_MS, X.FIRST_USE_MS, X.EAGER_NEEDED):
        d.clear()


def plug(cfg, pid, errors=None):
    return next(p for p in X.list_plugins(cfg, errors) if p["id"] == pid)


def test_api1_e_api2_convivono(tmp_path):
    app, cfg, errors, _ = make(tmp_path, {"vecchia": ("1", VECCHIA), "nuova": ("2", NUOVA)})
    assert errors == {}
    c = TestClient(app)
    assert c.get("/plugin-api/vecchia/ciao").json() == {"ok": 1}  # le api = 1 non cambiano
    assert c.get("/plugin-api/nuova/ciao").json() == {"ok": 2}
    assert plug(cfg, "vecchia")["api"] == 1 and plug(cfg, "nuova")["api"] == 2
    assert plug(cfg, "vecchia")["enabled"] and plug(cfg, "nuova")["enabled"]

    reg = X.media_registry()
    assert reg["api"] == 2
    assert reg["library_kinds"] == [{"id": "film", "label": "Film", "icon": "x", "extension": "nuova"}]
    assert reg["players"] == [{"id": "integrato", "label": "Lettore", "mode": "integrato", "extension": "nuova"}]
    assert reg["scrapers"][0]["url"] == "https://archive.org/details/x"
    assert reg["scrapers"][0]["extension"] == "nuova"


def test_api_troppo_alta_o_rotta_resta_spenta(tmp_path):
    app, cfg, errors, _ = make(tmp_path, {"futura": ("3", NUOVA), "boh": ('"due"', NUOVA)})
    assert errors == {}
    assert plug(cfg, "futura")["api"] == 3 and plug(cfg, "futura")["enabled"] is False
    assert plug(cfg, "boh")["enabled"] is False  # manifest sbagliato: spenta, l'app parte lo stesso
    assert X.LIBRARY_KINDS == []  # nessuna registrazione da un'estensione che non si carica
    assert TestClient(app).get("/plugin-api/futura/ciao").status_code == 404


def test_estensione_pubblicata_api1_continua_a_caricare():
    """Le estensioni gia' nel repository (es. Notizie) restano api = 1 e compatibili."""
    reali = [d for d in (ROOT / "extensions").iterdir() if (d / "plugin.toml").exists() and d.name != "index.json"]
    assert reali
    for d in reali:
        api = tomllib.loads((d / "plugin.toml").read_text(encoding="utf-8"))["plugin"].get("api", 1)
        assert int(api) <= X.API_VERSION, d.name


def test_estensione_api1_installata_risulta_abilitata(tmp_path):
    """Copia reale di un'estensione api = 1 nella cartella plugin: viene elencata e abilitata come prima."""
    src = ROOT / "extensions" / "notizie"
    dest = tmp_path / "plugins" / "notizie"
    dest.mkdir(parents=True)
    for name in ("plugin.toml", "backend.py"):
        shutil.copy2(src / name, dest / name)
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={})
    p = plug(cfg, "notizie")
    assert p["api"] == 1 and p["enabled"] is True and p["backend"] and p["permissions"]


def test_registrazioni_doppie_e_non_valide(tmp_path):
    app = FastAPI()
    gs = X.PluginAPI(app, SimpleNamespace(config_path=tmp_path / "c.toml", app={}), "media", X.Events(), print)
    gs.add_library_kind({"id": "film", "label": "Film"})
    gs.add_library_kind({"id": "film", "label": "Film e serie"})  # stessa estensione: sostituisce
    assert [x["label"] for x in X.LIBRARY_KINDS] == ["Film e serie"]
    with pytest.raises(ValueError):
        gs.add_library_kind({"id": "Film!", "label": "Male"})
    with pytest.raises(ValueError):
        gs.add_library_kind({"id": "film"})
    with pytest.raises(ValueError):
        gs.add_player({"id": "x", "label": "x", "mode": "boh"})
    with pytest.raises(ValueError):
        gs.add_scraper({"id": "x", "url": "file:///c:/ricetta.toml"})
    # due estensioni diverse possono registrare lo stesso id
    altri = X.PluginAPI(app, SimpleNamespace(config_path=tmp_path / "c.toml", app={}), "altro", X.Events(), print)
    altri.add_library_kind({"id": "film", "label": "Film (server)"})
    assert [x["extension"] for x in X.LIBRARY_KINDS] == ["media", "altro"]


def test_permesso_media_lettura():
    assert X.describe_permissions(["media:lettura"]) == [
        {"id": "media:lettura", "label": "Legge le cartelle di film e musica scelte dall'utente"}]


def test_lazy_che_registra_kind_viene_segnalato(tmp_path):
    src = "def register(gs):\n    gs.add_library_kind({'id': 'film', 'label': 'Film'})\n"
    app, cfg, errors, log = make(tmp_path, {"pigro": ('1\nload = "lazy"', src)})
    assert X.EAGER_NEEDED == {}  # non importato all'avvio
    assert TestClient(app).get("/plugin-api/pigro/non-esiste").status_code == 404  # primo uso: importa
    assert X.EAGER_NEEDED == {"pigro": {"gs.add_library_kind"}}
    assert any("gs.add_library_kind" in m and "eager" in m for m in log)
