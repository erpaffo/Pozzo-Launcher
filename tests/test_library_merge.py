"""Unione dei duplicati tra store: vista della libreria, le voci salvate restano separate. Nessuna rete."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config, stores  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.library import build  # noqa: E402

SNAP = [
    {"store": "epic", "id": "e1", "title": "The Witcher 3: Wild Hunt™", "installed": False, "playtime": 60},
    {"store": "steam", "id": "s1", "title": "Witcher 3 - Wild Hunt", "installed": False, "playtime": 120},
    {"store": "gog", "id": "g1", "title": "Other Game", "installed": False, "playtime": 5},
]


def _entries(**app):
    with tempfile.TemporaryDirectory() as t:
        cfg = config.Config(cache=Path(t) / "c", output=Path(t) / "o")
        cfg.cache.mkdir()
        cfg.app.update(app)
        cache = Cache(cfg.cache)
        orig = stores.load_snapshots
        stores.load_snapshots = lambda c, pids=None: [dict(s) for s in SNAP]
        try:
            return build._store_entries(cfg, cache)
        finally:
            stores.load_snapshots = orig
            cache.close()


def test_merge_on_groups_variants_and_prefers_store():
    es = {e["store"]: e for e in _entries(merge_stores=True)}
    assert es["epic"]["grp"] == es["steam"]["grp"] != es["gog"]["grp"]
    assert es["steam"]["primary"] == 1 and es["epic"]["primary"] == 0
    assert sum(e["store_playtime"] for e in es.values() if e["grp"] == es["steam"]["grp"]) == 180


def test_custom_order():
    es = {e["store"]: e for e in _entries(merge_stores=True, store_order=["epic", "steam"])}
    assert es["epic"]["primary"] == 1 and es["steam"]["primary"] == 0


def test_off_does_not_merge():
    es = _entries(merge_stores=False)
    assert len({e["grp"] for e in es}) == 3 and all(e["primary"] == 1 for e in es)


def test_default_keeps_merging():
    assert len({e["grp"] for e in _entries()}) == 2


if __name__ == "__main__":
    test_merge_on_groups_variants_and_prefers_store()
    test_custom_order()
    test_off_does_not_merge()
    print("ok")
