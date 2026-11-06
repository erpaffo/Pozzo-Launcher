"""Epic: un gioco in aggiornamento (manifest in Pending/ come "incompleto") resta installato."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo.stores import epic  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "Pending").mkdir()
    done = root / "old.manifest"
    done.write_text("x")

    def item(folder, name, cid, incomplete, manifest):
        d = {"CatalogItemId": cid, "CatalogNamespace": "fn", "DisplayName": name,
             "bIsIncompleteInstall": incomplete, "CompleteManifestPath": str(manifest)}
        (folder / f"{cid}.item").write_text(json.dumps(d), encoding="utf-8")

    item(root / "Pending", "Aggiornamento", "a", True, done)               # aggiornamento: installato
    item(root / "Pending", "Prima installazione", "b", True, root / "no")  # mai completato: escluso
    item(root, "Normale", "c", False, done)
    epic.MANIFESTS = root
    got = epic.Epic.installed(None)
    assert set(got) == {"a", "c"}, set(got)
print("OK test_epic_manifests")

# giochi free-to-play giocati dall'account ma assenti dalla libreria (Fortnite, Rocket League)
import asyncio  # noqa: E402


class R:
    status_code = 200

    def __init__(self, d):
        self.d = d

    def json(self):
        return self.d


async def fake(client, method, url, **kw):
    if "playtime" in url:
        return R([{"artifactId": "Fortnite", "totalTime": 7200}, {"artifactId": "Sugar", "totalTime": 60},
                  {"artifactId": "Owned", "totalTime": 5}, {"artifactId": "Ignoto", "totalTime": 1}])
    return R([{"appName": "Fortnite", "namespace": "fn", "catalogItemId": "f1"},
              {"appName": "Sugar", "namespace": "rl", "catalogItemId": "r1"},
              {"appName": "Owned", "namespace": "x", "catalogItemId": "o1"}])


epic.request = fake
epic.PC.get = lambda cfg, k, d=None: {"account_id": "acc"}
p = epic.Epic(None, None, None, print)
extra, times = asyncio.run(p._played({}, {"o1"}))
assert [e["appName"] for e in extra] == ["Fortnite", "Sugar"], extra
assert times["Fortnite"] == 7200
print("OK played")
