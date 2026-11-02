"""Cache disco delle risposte delle fonti: riuso, cache negativa, scadenza, invalidazione, budget, profili condivisi.
Nessuna rete: risposte finte (httpx.MockTransport).

Esegui: python -m pytest tests/test_cache_sources.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo import net  # noqa: E402
from pozzo.cachepolicy import DAY, ttls  # noqa: E402
from pozzo.policy import Ledger, Policy  # noqa: E402


class Fake:
    """Sito finto: conta le richieste vere e risponde col corpo scelto dal test."""

    def __init__(self):
        self.calls, self.status, self.body = 0, 200, {"results": [{"name": "Sonic"}]}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(self.status, json=self.body)


@pytest.fixture
def env(tmp_path):
    fake, now = Fake(), [1_000_000.0]
    cache = net.HttpCache(tmp_path / "cache.db")
    cache.clock = lambda: now[0]
    net.HTTP_CACHE = cache
    yield fake, cache, now, tmp_path
    net.HTTP_CACHE = None
    cache.close()


def get(fake, source="rawg", limiter=None, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as c:
            return await net.request(c, "GET", f"https://api.test/{source}", limiter=limiter, cache_source=source,
                                     ok404=False, params={"search": "sonic", "key": "SEGRETO"}, **kw)
    return asyncio.run(go())


def test_second_identical_request_skips_network(env):
    fake, cache, _, _ = env
    assert get(fake).json()["results"][0]["name"] == "Sonic"
    r = get(fake)
    assert fake.calls == 1 and r.headers["x-pozzo-cache"] == "hit" and cache.hits == 1
    assert r.json()["results"][0]["name"] == "Sonic"


def test_negative_cache_404_and_empty_results_expire_sooner(env):
    fake, cache, now, _ = env
    pos, neg = ttls("rawg")
    assert neg < pos
    fake.status = 404
    assert get(fake).status_code == 404
    get(fake)
    assert fake.calls == 1  # il "non trovato" non si richiede subito
    now[0] += neg + 1
    get(fake)
    assert fake.calls == 2  # scaduto il TTL negativo si riprova
    fake.status, fake.body = 200, {"count": 0, "results": []}
    now[0] += neg + 1
    get(fake)
    get(fake)
    assert fake.calls == 3
    now[0] += neg + 1
    get(fake)
    assert fake.calls == 4  # anche "nessun risultato" scade col TTL negativo


def test_positive_entry_expires_after_ttl(env):
    fake, _, now, _ = env
    pos, neg = ttls("rawg")
    get(fake)
    now[0] += pos - DAY
    get(fake)
    assert fake.calls == 1
    now[0] += 2 * DAY
    get(fake)
    assert fake.calls == 2


def test_invalidate_by_source_key_and_all(env):
    fake, cache, _, _ = env
    get(fake, "rawg")
    get(fake, "wikipedia")
    st = cache.stats()
    assert st["rawg"]["rows"] == 1 and st["wikipedia"]["rows"] == 1 and st["rawg"]["bytes"] > 0
    assert cache.invalidate("rawg") == 1
    assert set(cache.stats()) == {"wikipedia"}
    get(fake, "rawg")
    assert fake.calls == 3  # rawg rifatta, wikipedia no
    key = net.HttpCache.key("GET", "https://api.test/rawg", {"search": "sonic"})
    assert cache.invalidate(key=key) == 1  # la chiave non contiene la credenziale
    assert cache.invalidate() == 1 and cache.stats() == {}  # tutto


def test_purge_expired_and_stats_count_expired(env):
    fake, cache, now, _ = env
    get(fake)
    assert cache.stats()["rawg"]["expired"] == 0
    now[0] += ttls("rawg")[0] + 1
    assert cache.stats()["rawg"]["expired"] == 1
    assert cache.purge_expired() == 1 and cache.stats() == {}


def test_cached_answer_does_not_spend_budget(env):
    fake, cache, _, tmp = env
    ledger = Ledger(tmp / "cache.db")
    pol = Policy("rawg", rate=0, daily=100)
    limiter = net.RateLimiter(0, 1).guard(pol, ledger)
    get(fake, limiter=limiter)
    get(fake, limiter=limiter)
    get(fake, limiter=limiter)
    assert fake.calls == 1 and ledger.used("rawg")[0] == 1
    ledger.close()


def test_two_profiles_share_one_copy(env, tmp_path):
    fake, cache, _, _ = env
    get(fake)  # profilo A
    other = net.HttpCache(tmp_path / "cache.db")  # profilo B: stessa cartella di cache
    other.clock = cache.clock
    net.HTTP_CACHE = other
    r = get(fake)
    assert fake.calls == 1 and r.headers["x-pozzo-cache"] == "hit"
    get(fake, source="rawg")
    assert other.db.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0] == 1
    other.close()
    net.HTTP_CACHE = cache


def test_secret_params_not_stored_and_old_db_migrated(tmp_path):
    import sqlite3
    db = sqlite3.connect(tmp_path / "old.db")
    db.execute("CREATE TABLE http_cache(key TEXT PRIMARY KEY, status INT, body BLOB, ctype TEXT, ts REAL)")
    db.execute("INSERT INTO http_cache VALUES('k', 200, x'7b7d', 'application/json', 1.0)")
    db.commit()
    db.close()
    c = net.HttpCache(tmp_path / "old.db")
    assert c.stats()["altro"]["rows"] == 1 and c.purge_expired() == 1  # riga senza scadenza e vecchissima
    c.close()
    assert net.HttpCache.key("GET", "u", {"key": "A"}) == net.HttpCache.key("GET", "u", {"key": "B"})


def test_hltb_ttls_come_from_policy():
    from pozzo import hltb
    assert (hltb.FOUND_TTL, hltb.MISS_TTL) == ttls("hltb") and hltb.MISS_TTL < hltb.FOUND_TTL


def test_kv_stats_and_delete(tmp_path):
    import time
    from pozzo.cache import Cache
    c = Cache(tmp_path)
    c.kv_set("hltb:pc:sonic", {"main": 1})
    c.kv_set("altro", 1)
    assert c.kv_stats("hltb:", 3600)["rows"] == 1 and c.kv_stats("hltb:", 3600)["expired"] == 0
    assert c.kv_delete("hltb:", older_than=3600) == 0
    time.sleep(0.01)
    assert c.kv_delete("hltb:") == 1 and c.kv_get("altro") == 1
    c.close()


def test_routes_stats_and_clear(tmp_path):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pozzo.app.routes import cache_sources
    from pozzo.cache import Cache
    c = net.HttpCache(tmp_path / "cache.db")
    c.put("k", httpx.Response(200, json={"a": 1}), "rawg", DAY, DAY)
    c.close()
    k = Cache(tmp_path)
    k.kv_set("hltb:pc:sonic", {"main": 1})
    k.close()
    app = FastAPI()
    app.include_router(cache_sources.build_router(SimpleNamespace(cfg=SimpleNamespace(cache=tmp_path))))
    cl = TestClient(app)
    st = cl.get("/api/cache/sources").json()["sources"]
    assert st["rawg"]["rows"] == 1 and st["hltb"]["rows"] == 1
    assert cl.post("/api/cache/sources/clear", json={"source": "rawg"}).json() == {"removed": 1}
    assert "rawg" not in cl.get("/api/cache/sources").json()["sources"]
    assert cl.post("/api/cache/sources/clear", json={}).json() == {"removed": 1}  # tutte: resta solo hltb
    assert cl.post("/api/cache/sources/clear", json={"source": 5}).status_code == 400


def test_launchbox_stats_and_clear(tmp_path):
    import json
    import time
    from pozzo.bulk.launchbox import LaunchBoxDB
    lb = LaunchBoxDB(tmp_path)
    assert lb.cache_stats()["bytes"] == 0 and lb.clear() == 0
    lb.db_path.write_bytes(b"x" * 100)
    lb.meta_path.write_text(json.dumps({"checked": time.time() - 2 * 86400, "indexed": 5, "games": 7}))
    st = lb.cache_stats()
    assert st["bytes"] == 100 and st["rows"] == 7 and st["expired"] == 0 and 4.9 < st["days_left"] < 5.1
    lb.meta_path.write_text(json.dumps({"checked": time.time() - 8 * 86400}))
    assert lb.cache_stats()["expired"] == 1
    assert lb.clear() == 2 and not lb.ready()  # db + meta: al prossimo uso si riscarica
