"""Permessi dichiarati delle estensioni: etichette in italiano e copia nell'indice."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # il runner lancia lo script diretto, senza pytest

from pozzo.app.extensions import describe_permissions  # noqa: E402


def test_describe_permissions_labels_and_unknown():
    out = describe_permissions(["rete:api.rawg.io", "libreria:lettura", "avvio", "boh:x"])
    assert [x["id"] for x in out] == ["rete:api.rawg.io", "libreria:lettura", "avvio", "boh:x"]
    assert out[0]["label"] == "Accesso a internet: api.rawg.io"
    assert out[1]["label"] == "Legge la libreria"
    assert out[2]["label"] == "Avvia giochi o programmi"
    assert out[3]["label"].startswith("Permesso non riconosciuto")
    assert describe_permissions(None) == []
    assert describe_permissions(["rete:*"])[0]["label"] == "Accesso a internet: qualsiasi sito, scelto dall'utente"

    # l'indice copia "permissions" dal plugin.toml (tools/extensions.py)
    spec = importlib.util.spec_from_file_location("pozzo_tools_ext_perm", ROOT / "tools" / "extensions.py")
    T = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(T)
    d = Path(__import__("tempfile").mkdtemp())
    (d / "plugin.toml").write_text('[plugin]\nname = "x"\npermissions = ["notifiche"]\n', encoding="utf-8")
    assert T.entry(d, "./")["permissions"] == ["notifiche"]
