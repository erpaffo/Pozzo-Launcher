"""_asset_version(): nel build congelato l'hash dei file static si calcola una volta sola; da sorgenti a ogni pagina."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config as C  # noqa: E402
from pozzo.app import server as S  # noqa: E402


def main():
    n = []
    real = S._hash_assets
    S._hash_assets = lambda: (n.append(1), f"v{len(n)}")[1]
    frozen = C.FROZEN
    try:
        C.FROZEN = False
        S._ASSET_V.clear()
        assert S._asset_version() == "v1" and S._asset_version() == "v2", "da sorgenti: sempre fresco"
        n.clear()
        C.FROZEN = True
        assert S._asset_version() == "v1" and S._asset_version() == "v1" and len(n) == 1, "congelato: una volta sola"
    finally:
        S._hash_assets, C.FROZEN = real, frozen
        S._ASSET_V.clear()
    assert S._asset_version().count(".") >= 1  # hash reale
    print("ok  hash dei file static in cache nel build congelato")


if __name__ == "__main__":
    main()
