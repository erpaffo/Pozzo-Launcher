"""Il payload della libreria elenca ogni console nota, anche senza giochi né store (serve per aggiungerle uno store)."""
import re
from pathlib import Path


def test_library_payload_lists_every_platform():
    src = (Path(__file__).resolve().parents[1] / "pozzo" / "app" / "routes" / "library.py").read_text(encoding="utf-8")
    assert re.search(r"for p in P\.PLATFORMS:\s*\n\s*plats\[p\] \+= 0", src)


def test_catalogs_endpoint_exists():
    src = (Path(__file__).resolve().parents[1] / "pozzo" / "app" / "routes" / "stores.py").read_text(encoding="utf-8")
    assert '@router.get("/api/catalogs")' in src
