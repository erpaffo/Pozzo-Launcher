"""Doppioni nella coda: stesso link, stessa magnet (o magnet + .torrent dello stesso torrent) non si aggiungono due volte,
a meno di «aggiungi comunque». Nessuna rete."""
import base64
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import torrent as TOR  # noqa: E402
from pozzo.downloads.manager import Duplicate, Manager, source_key  # noqa: E402

HASH = "a" * 40
MAGNET = f"magnet:?xt=urn:btih:{HASH}&dn=Gioco"


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def test_stesso_link_non_si_aggiunge_due_volte(tmp):
    m = _mgr(tmp)
    a = m.add("https://x.example/a.zip?t=1")
    for same in ("https://x.example/a.zip?t=1", " https://X.EXAMPLE/a.zip?t=1#frammento "):
        with pytest.raises(Duplicate):
            m.add(same)
    m.add("https://x.example/a.zip?t=2")  # un altro token e' un altro link
    m.add("https://x.example/b.zip")
    assert len(m.tasks) == 3
    with pytest.raises(Duplicate):  # anche la prova del lotto (dry_run) lo segnala
        m.add(a.source, dry_run=True)
    assert m.add(a.source, force=True).id != a.id and len(m.tasks) == 4  # «aggiungi comunque»
    assert "force" not in m.tasks[a.id].options


def test_quali_stati_contano(tmp):
    m = _mgr(tmp)
    t = m.add("https://x.example/a.zip")
    for st in (T.QUEUED, T.RUNNING, T.PAUSED, T.COMPLETED):  # completato: il file c'e' gia'
        t.status = st
        with pytest.raises(Duplicate):
            m.add("https://x.example/a.zip")
    t.status = T.ERROR  # in errore si riprova aggiungendo di nuovo
    assert m.add("https://x.example/a.zip").source == t.source
    m.cancel(t.id)  # annullato: non c'e' piu'
    assert len(m.tasks) == 1


def test_magnet_per_info_hash_anche_base32(tmp):
    m = _mgr(tmp)
    m.add(MAGNET)
    b32 = base64.b32encode(bytes.fromhex(HASH)).decode()
    for same in (f"magnet:?xt=urn:btih:{HASH.upper()}", f"magnet:?xt=urn:btih:{b32}&tr=udp://t.example:1"):
        with pytest.raises(Duplicate):
            m.add(same)
    m.add("magnet:?xt=urn:btih:" + "b" * 40)
    assert len(m.tasks) == 2


def _torrent(tmp) -> tuple[bytes, str]:
    """Un .torrent di prova (solo i metadati) e la sua magnet."""
    lt = pytest.importorskip("libtorrent")
    src = tmp / "src" / "set"
    src.mkdir(parents=True)
    (src / "a.bin").write_bytes(os.urandom(40000))
    ct = lt.create_torrent(lt.list_files(str(src)), 16384)
    lt.set_piece_hashes(ct, str(src.parent))
    raw = lt.bencode(ct.generate())
    return raw, lt.make_magnet_uri(lt.torrent_info(raw))


def test_magnet_e_file_torrent_dello_stesso_torrent(tmp):
    raw, magnet = _torrent(tmp)
    f = tmp / "set.torrent"
    f.write_bytes(raw)
    assert source_key(str(f)) == source_key(magnet) != str(f)
    m = _mgr(tmp)
    m.add(str(f))
    with pytest.raises(Duplicate):
        m.add(magnet)
    m2 = _mgr(tmp / "due")
    m2.add(magnet)
    with pytest.raises(Duplicate):
        m2.add(str(f))


def test_rss_salta_il_doppione_senza_provare_gli_altri_link(tmp):
    m = _mgr(tmp)
    m.add("https://x.example/uno.zip")
    feed = {"url": "https://feed.example/rss", "interval_min": 30, "filters": [{"regex": "Uno", "category": ""}]}
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><item><title>Gioco Uno</title><guid>g1</guid>
    <link>https://x.example/page1</link><enclosure url="https://x.example/uno.zip"/></item></channel></rss>"""
    m._rss_fetch = lambda u: xml
    assert m.rss_check(feed) == 0 and len(m.tasks) == 1  # l'enclosure e' gia' in lista: la pagina non si accoda al suo posto


def test_aggiunta_dalla_rotta_salta_i_doppioni_e_dice_quanti(tmp):
    from fastapi.testclient import TestClient
    from pozzo import config
    from pozzo.app.server import create_app
    (tmp / "roms").mkdir()
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.app["downloads"] = {"max_active": 0, "dir": str(tmp / "out")}
    with TestClient(create_app(cfg)) as c:
        u = [f"http://127.0.0.1:9/{n}" for n in "abc"]
        assert c.post("/api/downloads", json={"links": u[:1]}).json()["skipped"] == []
        r = c.post("/api/downloads", json={"links": [u[0], u[1], u[2], u[1]]}).json()  # a gia' in lista, b due volte nel lotto
        assert len(r["tasks"]) == 2 and r["skipped"] == [u[0], u[1]]
        r = c.post("/api/downloads", json={"links": [u[0]]})  # singolo: 200 con tasks vuoto, la UI chiede
        assert r.status_code == 200 and r.json() == {"ok": True, "tasks": [], "skipped": [u[0]]}
        r = c.post("/api/downloads", json={"links": [u[0]], "force": True}).json()
        assert len(r["tasks"]) == 1 and r["skipped"] == []
        assert len(c.get("/api/downloads").json()["tasks"]) == 4
        bad = c.post("/api/downloads", json={"links": [u[0], "ftp://x/y"]})  # un link sbagliato resta tutto o niente
        assert bad.status_code == 400
        # .torrent caricato dopo la sua magnet: stesso torrent, la copia caricata non resta in cartella
        raw, magnet = _torrent(tmp)
        assert len(c.post("/api/downloads", json={"links": [magnet]}).json()["tasks"]) == 1
        up = lambda **form: c.post("/api/downloads/torrent-file", files={"file": ("set.torrent", raw)}, data=form).json()
        uploads = Path(cfg.cache) / "torrents" / "uploads"
        assert up()["skipped"] == ["set.torrent"] and not list(uploads.glob("*"))
        r = up(force="1")
        assert len(r["tasks"]) == 1 and r["skipped"] == []
