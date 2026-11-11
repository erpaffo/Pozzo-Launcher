"""Funzioni «alla qBittorrent»: categorie e tag, cartella degli incompleti, limiti per categoria, IP filter, RSS."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import manager as M, rss as RSS, task as T  # noqa: E402
from pozzo.downloads.engines import torrent as TOR  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

MAGNET = "magnet:?xt=urn:btih:" + "a" * 40
LOCAL = {"enable_dht": False, "enable_lsd": False, "enable_upnp": False, "enable_natpmp": False}


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl}})
    cfg.app["downloads"].setdefault("discovery", {"dht": False, "pex": False, "lsd": False, "upnp": False})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: cfg.app.update(downloads=new))


# ------------------------------------------------------------ categorie e tag
def test_categorie_validate_e_cartella(tmp):
    m = _mgr(tmp)
    cats = [{"name": "Giochi", "folder": str(tmp / "giochi"), "seed_ratio": "2", "seed_minutes": 30, "action": "remove"}, {"name": "Altro"}]
    s = m.update_settings({"categories": cats})
    assert s["categories"][0] == {"name": "Giochi", "folder": str(tmp / "giochi"), "seed_ratio": 2.0, "seed_minutes": 30, "action": "remove"}
    assert (tmp / "giochi").is_dir() and s["categories"][1]["folder"] == ""
    for bad in ("x", [{"name": ""}], [{"name": "A"}, {"name": "a"}], [{"name": "A", "action": "boh"}],
                [{"name": "A", "folder": str(tmp / "out" / "f.txt" / "x")}]):
        if bad != "x" and "f.txt" in str(bad):
            (tmp / "out").mkdir(exist_ok=True)
            (tmp / "out" / "f.txt").write_text("x")
        with pytest.raises(ValueError):
            m.update_settings({"categories": bad})
    t = m.add("https://x.example/a.zip", category="giochi", tags=["a", " b ", "a", ""])
    assert t.category == "giochi" and t.save_path == str(tmp / "giochi") and t.tags == ["a", "b"]
    t2 = m.add("https://x.example/b.zip", str(tmp / "mio"), category="Giochi")
    assert t2.save_path == str(tmp / "mio")  # il percorso esplicito vince
    t3 = m.add("https://x.example/c.zip")
    m.set_category(t3.id, "Giochi", "x,y")
    assert t3.save_path == str(tmp / "giochi") and t3.tags == ["x", "y"] and t3.view()["category"] == "Giochi"
    m.set_category(t3.id, tags=[])  # categoria intatta
    assert t3.category == "Giochi" and t3.tags == []
    with pytest.raises(KeyError):
        m.set_category("nope", "x")


# ------------------------------------------------------------ cartella degli incompleti
def test_incompleti_spostamento_riprendibile(tmp):
    m = _mgr(tmp, incomplete_dir=str(tmp / "inc"))
    t = m.add("https://x.example/a.zip")
    inc, fin = Path(t.save_path), tmp / "out"
    assert inc == tmp / "inc" / t.id and t.options["final_dir"] == str(fin)
    (inc / "sub").mkdir()
    (inc / "a.zip").write_bytes(b"1")
    (inc / "sub" / "b.bin").write_bytes(b"2")
    # crash a meta': un file e' gia' arrivato, uno e' rimasto, c'e' pure una copia provvisoria
    fin.mkdir(exist_ok=True)
    (fin / "a.zip").write_bytes(b"1")
    (inc / "a.zip").unlink()
    m._move_final(t)
    assert (fin / "a.zip").read_bytes() == b"1" and (fin / "sub" / "b.bin").read_bytes() == b"2"
    assert not inc.exists() and t.save_path == str(fin) and "final_dir" not in t.options


def test_incompleti_nel_post_prima_di_on_completed(tmp):
    m = _mgr(tmp, incomplete_dir=str(tmp / "inc"))
    t = m.add("https://x.example/a.zip")
    (Path(t.save_path) / "a.zip").write_bytes(b"1")
    seen = []
    m.on_completed = lambda x: seen.append((x.save_path, (tmp / "out" / "a.zip").exists()))
    t.status = T.COMPLETED
    m._post(t)
    for _ in range(100):
        if t.options.get("post_done"):
            break
        import time
        time.sleep(0.05)
    assert seen == [(str(tmp / "out"), True)] and t.options["post_done"]


def test_senza_incompleti_comportamento_di_prima(tmp):
    t = _mgr(tmp).add("https://x.example/a.zip")
    assert t.save_path == str(tmp / "out") and "final_dir" not in t.options


# ------------------------------------------------------------ limiti di condivisione per categoria
def test_limiti_categoria_prevalgono(tmp):
    pytest.importorskip("libtorrent")
    m = _mgr(tmp, seed_ratio=1.0, seed_minutes=10, seed_action="pause",
             categories=[{"name": "k", "seed_ratio": 3, "seed_minutes": 0, "action": "remove"}, {"name": "v"}])
    t = m.add(MAGNET, category="k")
    m._apply_seed(t)
    assert t.options["seed_limits"] == [3.0, 10] and t.options["seed_action"] == "remove"  # minuti: globali (0 = non impostato)
    m.set_category(t.id, "v")
    assert "seed_limits" not in t.options and t.options["seed_action"] == "pause"  # globali, live nel motore


@pytest.mark.parametrize("action", ["remove", "pause"])
def test_azione_a_limite_raggiunto(tmp, monkeypatch, action):
    pytest.importorskip("libtorrent")
    m = _mgr(tmp, categories=[{"name": "k", "seed_ratio": 1, "action": action}])
    t = m.add(MAGNET, category="k")

    async def fake(task, eng, client, done):  # il motore: ha condiviso fino al limite
        task.options.update(seeding=True, seed_reached=True)
        task.status = T.COMPLETED

    monkeypatch.setattr(TOR, "run", fake)
    m._client = None
    asyncio.run(m._job(t, 0))
    assert not t.options.get("seeding") and "seed_reached" not in t.options
    m._auto_resume()
    if action == "remove":
        assert t.options["autoremove"] and t.id not in m.tasks  # via dalla lista
    else:
        assert t.options["seed_stopped"] and t.id in m.tasks and t.status == T.COMPLETED


# ------------------------------------------------------------ IP filter
def test_parse_ip_filter(tmp):
    f = tmp / "f.dat"
    f.write_text("# commento\n001.002.003.000 - 001.002.003.255 , 000 , Un nome\nAcme: Spam:5.6.7.8-5.6.7.9\n10.0.0.0/8\n::1/128\n\n", "utf-8")
    assert TOR.parse_ip_filter(f) == [("1.2.3.0", "1.2.3.255"), ("5.6.7.8", "5.6.7.9"), ("10.0.0.0", "10.255.255.255"), ("::1", "::1")]
    f.write_text("10.0.0.0/8\nroba\n", "utf-8")
    with pytest.raises(ValueError, match="riga 2"):
        TOR.parse_ip_filter(f)


def test_ip_filter_applicato_alla_sessione(tmp):
    lt = pytest.importorskip("libtorrent")
    f = tmp / "f.p2p"
    f.write_text("Blocco:9.9.9.0-9.9.9.255\n", "utf-8")
    e = TOR.Engine(tmp / "res")
    e.configure({"ip_filter_path": str(f)})
    e._pack.update(LOCAL, listen_interfaces="127.0.0.1:0")
    e.session()
    assert e.ses.get_ip_filter().access("9.9.9.9") == 1 and e.ses.get_ip_filter().access("8.8.8.8") == 0
    f.write_text("rotto\n", "utf-8")  # file cambiato + nuovo percorso: errore -> filtro ignorato, niente eccezioni
    e.configure({"ip_filter_path": str(f) + "?"})
    assert e.ip_error and e.ses.get_ip_filter().access("9.9.9.9") == 0
    e.configure({"ip_filter_path": str(f)})
    assert "riga 1" in e.ip_error and e.ses.get_ip_filter().access("9.9.9.9") == 0
    e.close()


def test_ip_filter_percorso_inesistente_rifiutato(tmp):
    with pytest.raises(ValueError):
        _mgr(tmp).update_settings({"ip_filter_path": str(tmp / "non-c-e")})


# ------------------------------------------------------------ RSS
RSS_XML = b"""<?xml version="1.0"?><rss version="2.0" xmlns:torrent="http://x/t"><channel>
<item><title>Gioco Uno [PC]</title><guid>g1</guid><link>https://x.example/page1</link><enclosure url="https://x.example/uno.zip"/></item>
<item><title>Altra cosa</title><guid>g2</guid><link>https://x.example/page2</link></item>
<item><title>Gioco Due ROM</title><guid>g3</guid><link>https://x.example/page3</link><torrent:magnetURI>%s</torrent:magnetURI></item>
</channel></rss>""" % MAGNET.encode()
ATOM_XML = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom Uno</title><id>urn:1</id>
<link href="https://x.example/atom1.zip"/></entry></feed>"""


def test_rss_parse():
    it = RSS.parse(RSS_XML)
    assert [i["id"] for i in it] == ["g1", "g2", "g3"]
    assert it[0]["links"] == ["https://x.example/uno.zip", "https://x.example/page1"] and it[2]["links"][0] == MAGNET
    assert RSS.parse(ATOM_XML) == [{"id": "urn:1", "title": "Atom Uno", "links": ["https://x.example/atom1.zip"]}]
    with pytest.raises(ValueError):
        RSS.parse(b"<!DOCTYPE x [<!ENTITY a 'b'>]><rss/>")
    with pytest.raises(ValueError):
        RSS.parse(b"non xml")


def test_rss_match_primo_filtro_e_regex_rotta():
    it = RSS.parse(RSS_XML)
    got = RSS.match(it, {"g3"}, [{"regex": "(rotta", "category": "z"}, {"regex": "gioco", "category": "g"}, {"regex": "uno", "category": "u"}])
    assert [(i["id"], c) for i, c in got] == [("g1", "g")]


def test_rss_check_senza_doppioni_e_categoria(tmp):
    m = _mgr(tmp, categories=[{"name": "giochi", "folder": str(tmp / "g")}])
    feed = {"url": "https://feed.example/rss", "interval_min": 30, "filters": [{"regex": "^Gioco Uno", "category": "giochi"}]}
    m._rss_fetch = lambda u: RSS_XML
    assert m.rss_check(feed) == 1
    (t,) = m.tasks.values()
    assert t.source == "https://x.example/uno.zip" and t.category == "giochi" and t.save_path == str(tmp / "g")
    assert m.rss_check(feed) == 0 and len(m.tasks) == 1  # stesso feed, item gia' visto
    m2 = _mgr(tmp, categories=m._raw()["categories"])  # visti persistiti nel db: nuovo Manager, nessun doppione
    m2._rss_fetch = lambda u: RSS_XML
    assert m2.rss_check(feed) == 0 and not m2.tasks
    assert feed["url"] not in m._rss_run and feed["url"] in m._rss_at
    m._rss_fetch = lambda u: (_ for _ in ()).throw(OSError("giu'"))  # feed irraggiungibile: nessuna eccezione
    assert m.rss_check(feed) == 0


def test_rss_tick_rispetta_intervallo(tmp):
    m = _mgr(tmp)
    calls = []
    m.rss_check = lambda f: (calls.append(f["url"]), m._rss_run.discard(f["url"]), m._rss_at.__setitem__(f["url"], __import__("time").monotonic()))
    s = {"rss": [{"url": "https://feed.example/rss", "interval_min": 5, "filters": []}]}
    m._rss_tick(s)
    for _ in range(50):
        if calls:
            break
        __import__("time").sleep(0.02)
    m._rss_tick(s)
    __import__("time").sleep(0.1)
    assert calls == ["https://feed.example/rss"]


def test_rss_config_validata(tmp):
    m = _mgr(tmp)
    s = m.update_settings({"rss": [{"url": "https://f.example/r", "interval_min": 1, "filters": [{"regex": "a", "category": "c"}, {"regex": " "}]}]})
    assert s["rss"] == [{"url": "https://f.example/r", "interval_min": 5, "filters": [{"regex": "a", "category": "c"}]}]
    for bad in ([{"url": "ftp://x"}], [{"url": "https://x.example", "filters": [{"regex": "(x"}]}], "no"):
        with pytest.raises(ValueError):
            m.update_settings({"rss": bad})


def test_rss_fetch_blocca_reti_locali():
    with pytest.raises(ValueError):
        RSS.fetch("http://127.0.0.1:1/feed")
