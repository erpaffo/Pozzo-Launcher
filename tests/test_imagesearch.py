"""Ricerca immagini sul web per «Completa i mancanti»: parsing delle pagine (finte), sicurezza dello scarico,
rotte preview/apply con provider finto. Nessuna rete reale.

Esegui: python tests/test_imagesearch.py
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo import imagesearch as IS  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.library.build import build  # noqa: E402


def png(w=300, h=400, fmt="PNG") -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(b, fmt)
    return b.getvalue()


def test_parsing():
    page = 'x <script>... vqd="4-1234567890123" ...</script>'
    assert IS.parse_ddg_vqd(page) == "4-1234567890123" and IS.parse_ddg_vqd("niente") is None
    js = json.dumps({"results": [{"image": "https://a.example/1.jpg"}, {"nope": 1}, {"image": "https://b.example/2.png"}]})
    assert IS.parse_ddg_results(js) == ["https://a.example/1.jpg", "https://b.example/2.png"]
    assert IS.parse_ddg_results("<html>") == []
    bing = ('<a class="iusc" m="{&quot;murl&quot;:&quot;https://c.example/x.jpg&quot;,&quot;t&quot;:&quot;a&quot;}" x="1">'
            '<a m="{rotto"><a m="{&quot;murl&quot;:&quot;https://d.example/y.png&quot;}">')
    assert IS.parse_bing(bing) == ["https://c.example/x.jpg", "https://d.example/y.png"]
    print("ok  parsing DuckDuckGo e Bing")


def test_search_fallback():
    old = IS.PROVIDERS

    def bad(q):
        raise IS.SearchError("blocked")
    try:
        IS.PROVIDERS = [("a", bad), ("b", lambda q: ["ftp://x/1.jpg", "https://ok.example/1.jpg", "https://ok.example/2.jpg"])]
        assert IS.search("q", 1) == ["https://ok.example/1.jpg"], "riserva + solo http(s)"
        IS.PROVIDERS = [("a", bad), ("b", bad)]
        try:
            IS.search("q")
            raise AssertionError("doveva fallire")
        except IS.SearchError as e:
            assert str(e) == "blocked"
        IS.PROVIDERS = [("a", lambda q: []), ("b", lambda q: [])]
        assert IS.search("q") == []
    finally:
        IS.PROVIDERS = old
    print("ok  motore di riserva ed errori")


def test_sicurezza():
    for bad in ("file:///etc/passwd", "ftp://x.example/a.png", "http://127.0.0.1/a.png", "http://192.168.1.5/a.png",
                "http://localhost/a.png", "http://[::1]/a.png"):
        try:
            IS.fetch_image(bad)
            raise AssertionError(f"accettato {bad}")
        except ValueError:
            pass
    for data in (b"<html>no</html>", png(50, 50), png(300, 400)[:200], b"GIF89a" + b"\0" * 30):
        try:
            IS.validate_image(data)
            raise AssertionError("immagine non valida accettata")
        except ValueError:
            pass
    f = IS.validate_image(png(300, 400))
    assert (f.ext, f.w, f.h) == ("png", 300, 400)
    assert IS.validate_image(png(200, 200, "WEBP")).ext == "webp"
    print("ok  URL privati/file:, non-immagini, troppo piccole")


def test_limite_e_redirect():
    import httpx
    old, orig = httpx.Client, IS.assert_public
    big = b"\x89PNG" + b"0" * (IS.MAX_BYTES + 10)
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if req.url.path == "/r":
            return httpx.Response(302, headers={"location": "http://10.0.0.1/p.png"})
        if req.url.path == "/big":
            return httpx.Response(200, content=big)
        return httpx.Response(200, content=png())

    class C(old):
        def __init__(self, *a, **k):
            k.pop("transport", None)
            super().__init__(*a, transport=httpx.MockTransport(handler), **k)
    # host finti non si risolvono: si controllano davvero solo gli indirizzi privati
    IS.assert_public = lambda u: orig(u) if "10.0.0.1" in u else None
    httpx.Client = C
    try:
        for u, why in (("http://ok.example/big", "troppo grande"), ("http://ok.example/r", None)):
            try:
                IS.fetch_image(u)
                raise AssertionError("doveva fallire")
            except ValueError as e:
                assert why is None or str(e) == why, e
        assert not any("10.0.0.1" in s for s in seen), "il redirect verso la LAN non va seguito"
        assert IS.fetch_image("http://ok.example/ok").w == 300
    finally:
        httpx.Client = old
        IS.assert_public = orig
    print("ok  limite di dimensione e redirect verso la rete locale")


def test_rotte(tmp: Path):
    (tmp / "roms" / "n64").mkdir(parents=True)
    (tmp / "roms" / "n64" / "Snow Game (USA).z64").write_bytes(b"N64" * 2000)
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    build(cfg, log=lambda *a: None)
    queries, pics = [], {"https://img.example/ok.png": png(), "https://img.example/b.png": png(320, 240)}

    def search(q, n=1):
        queries.append(q)
        return ["https://img.example/bad.png", "https://img.example/ok.png", "https://img.example/b.png"]

    def fetch(u):
        if u not in pics:
            raise ValueError("no")
        return IS.validate_image(pics[u])
    IS.search, IS.fetch_image = search, fetch
    with TestClient(create_app(cfg)) as cl:
        gid = cl.get("/api/library?part=owned").json()["games"]["rows"][0][0]  # unico gioco della libreria
        kinds = {k["kind"]: k for k in cl.get(f"/api/game/{gid}/media").json()["kinds"]}
        assert kinds["cover"]["url"] is None
        r = cl.post(f"/api/game/{gid}/media/fill/preview", json={"kinds": ["cover", "screenshot"]}).json()
        a, b = r["items"]
        assert a["kind"] == "cover" and a["candidate_url"] == "https://img.example/ok.png", "primo risultato VALIDO (salta la non-immagine)"
        assert (a["w"], a["h"]) == (300, 400) and a["size"] > 0 and a["domain"] == "img.example"
        assert "Snow Game" in queries[0] and "cover art" in queries[0], queries
        assert "screenshot" in queries[1]
        assert cl.get(a["thumb"]).headers["content-type"] == "image/png"
        assert not [k for k in cl.get(f"/api/game/{gid}/media").json()["kinds"] if k["custom"]], "l'anteprima non salva"
        # «Cambia»: scarta l'indirizzo gia' proposto
        c = cl.post(f"/api/game/{gid}/media/fill/preview", json={"kinds": ["cover"], "skip": [a["candidate_url"]]}).json()["items"][0]
        assert c["candidate_url"] == "https://img.example/b.png", c
        # apply: indirizzo non proveniente dall'anteprima -> rifiutato
        ap = cl.post(f"/api/game/{gid}/media/fill/apply", json={"items": [{"kind": "cover", "candidate_url": "https://evil.example/x.png"}]}).json()
        assert not ap["results"][0]["ok"]
        ap = cl.post(f"/api/game/{gid}/media/fill/apply", json={"items": [
            {"kind": "cover", "candidate_url": a["candidate_url"]}, {"kind": "../etc", "candidate_url": "x"}]}).json()
        assert ap["results"][0]["ok"] and not ap["results"][1]["ok"]
        assert [k for k in ap["kinds"] if k["kind"] == "cover"][0]["custom"]
        again = cl.post(f"/api/game/{gid}/media/fill/apply", json={"items": [{"kind": "cover", "candidate_url": a["candidate_url"]}]}).json()
        assert not again["results"][0]["ok"], "token gia' consumato"
        # mai sovrascrivere: il tipo ora c'e', l'anteprima non lo propone piu' e apply lo rifiuta
        assert all(i["kind"] != "cover" for i in cl.post(f"/api/game/{gid}/media/fill/preview", json={}).json()["items"])
        ap = cl.post(f"/api/game/{gid}/media/fill/apply", json={"items": [{"kind": "cover", "candidate_url": c["candidate_url"]}]}).json()
        assert not ap["results"][0]["ok"]

        def blocked(q, n=1):
            raise IS.SearchError("blocked")
        IS.search = blocked
        e = cl.post(f"/api/game/{gid}/media/fill/preview", json={"kinds": ["fanart"]}).json()["items"][0]
        assert e["error"] and "candidate_url" not in e
    print("ok  rotte preview/apply: nessun salvataggio senza conferma, nessuna sovrascrittura")


if __name__ == "__main__":
    test_parsing()
    test_search_fallback()
    test_sicurezza()
    test_limite_e_redirect()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_rotte(Path(t))
