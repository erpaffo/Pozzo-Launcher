"""extensions/index.json: lo sha256 di ogni file deve corrispondere a quello su disco (riusa tools/extensions.py).

Non rigenera l'indice: se fallisce, va rigenerato con `python tools/extensions.py index` dopo aver verificato le modifiche.

Esegui: python tests/test_index_consistent.py   (o pytest tests/test_index_consistent.py)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extensions"


def _extensions_module():
    spec = importlib.util.spec_from_file_location("pozzo_tools_extensions", ROOT / "tools" / "extensions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def problems() -> list[str]:
    mod = _extensions_module()
    index = json.loads((EXT / "index.json").read_text(encoding="utf-8"))
    out = []
    for e in index["extensions"]:
        d = (EXT / e["base"]).resolve()
        for name, expected in e["files"].items():
            f = d / name
            if not f.is_file():
                out.append(f"{e['id']}: {name} nell'indice ma non su disco")
            elif mod.sha(f) != expected:
                out.append(f"{e['id']}: sha256 di {name} diverso da index.json")
    return out


def test_index_sha256_matches_files():
    bad = problems()
    assert not bad, "index.json non allineato:\n" + "\n".join(bad)


if __name__ == "__main__":
    test_index_sha256_matches_files()
    print("ok")
