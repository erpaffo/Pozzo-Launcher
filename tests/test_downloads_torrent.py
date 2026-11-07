"""Torrent nella coda: sciame locale (un seeder libtorrent su 127.0.0.1), nessuna rete esterna."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

lt = pytest.importorskip("libtorrent")

from pozzo import net  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import torrent as TOR  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

PIECE = 16384
LOCAL = {"enable_dht": False, "enable_lsd": False, "enable_upnp": False, "enable_natpmp": False}


@pytest.fixture
def swarm(tmp):
    """Set di due file (a allineato ai pezzi: scegliere solo b non tocca a) e un seeder che li condivide."""
    src = tmp / "src" / "set"
    src.mkdir(parents=True)
    data = {"a.bin": os.urandom(PIECE * 8), "b.bin": os.urandom(PIECE * 5 + 100)}
    for n, b in data.items():
        (src / n).write_bytes(b)
    ct = lt.create_torrent(lt.list_files(str(src)), PIECE)
    lt.set_piece_hashes(ct, str(src.parent))
    raw = lt.bencode(ct.generate())
    (tmp / "set.torrent").write_bytes(raw)
    ti = lt.torrent_info(raw)
    seed = lt.session({"listen_interfaces": "127.0.0.1:0", **LOCAL})
    seed.set_peer_class_filter(lt.ip_filter())  # i peer locali di solito ignorano i limiti: qui il limite vale
    p = lt.add_torrent_params()
    p.ti, p.save_path = ti, str(src.parent)
    p.flags |= lt.torrent_flags.seed_mode
    h = seed.add_torrent(p)
    yield SimpleNamespace(data=data, torrent=tmp / "set.torrent", magnet=lt.make_magnet_uri(ti),
                          peer=f"127.0.0.1:{seed.listen_port()}", seed=seed, handle=h)
    seed.remove_torrent(h)


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl,
                                                       "discovery": {"dht": False, "pex": False, "lsd": False, "upnp": False}}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _wait(cond, timeout=150):  # largo: con molti test in parallelo o su runner lenti 60 s non bastavano
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_scarica_tutto_da_file_torrent(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(str(swarm.torrent), connect=[swarm.peer])
    assert t.type == "torrent"
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    for n, b in swarm.data.items():
        assert (tmp / "out" / "set" / n).read_bytes() == b
    v = t.view()
    assert v["name"] == "set" and v["size"] == v["done"] == sum(map(len, swarm.data.values()))
    assert {f["name"].replace("\\", "/"): f["progress"] for f in v["options"]["files"]} == {"set/a.bin": 1.0, "set/b.bin": 1.0}
    assert "priorities" not in v["options"] and v["options"]["metadata"] is True
    assert not m._torrent.handles  # niente seeding dopo la fine
    m.stop()


def test_solo_il_file_scelto(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet, connect=[swarm.peer], wanted="b.bin")
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert (tmp / "out" / "set" / "b.bin").read_bytes() == swarm.data["b.bin"]
    assert not (tmp / "out" / "set" / "a.bin").exists()
    assert t.size == len(swarm.data["b.bin"])
    assert [f["priority"] for f in t.options["files"]] == [0, 4]
    m.stop()


def test_file_non_trovato_e_magnet_rotto(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet, connect=[swarm.peer], wanted="zzz")
    assert _wait(lambda: t.status == T.ERROR) and "zzz" in t.error
    with pytest.raises(ValueError):
        m.add("magnet:?xt=urn:btih:abc")
    with pytest.raises(ValueError):
        m.add(str(tmp / "manca.torrent"))
    m.stop()


def test_ripresa_dopo_riavvio_usa_i_resume_data(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    swarm.seed.apply_settings({"upload_rate_limit": 4096})
    t = m.add(swarm.magnet, connect=[swarm.peer], wanted="b.bin")
    assert _wait(lambda: t.options.get("metadata"))
    assert t.status == T.RUNNING  # seeder lento: a meta'
    m.pause(t.id)
    rf = m._torrent.resume_file(t.id)
    assert _wait(lambda: rf.exists() and not m._torrent.handles)
    m.stop()

    m2 = _mgr(tmp)
    t2 = next(x for x in m2.store.load() if x.id == t.id)
    t2.options.pop("connect")  # senza peer: i metadati possono venire solo dai resume data
    m2.store.save([t2])
    m2.start()
    m2.resume(t.id)
    t2 = m2.tasks[t.id]
    assert _wait(lambda: t2.options.get("metadata") and t2.options.get("files"))
    assert [f["priority"] for f in t2.options["files"]] == [0, 4]  # anche la scelta dei file e' sopravvissuta
    swarm.seed.apply_settings({"upload_rate_limit": 0})
    t2.options["connect"] = [swarm.peer]
    assert _wait(lambda: t2.status == T.COMPLETED), (t2.status, t2.error)
    assert (tmp / "out" / "set" / "b.bin").read_bytes() == swarm.data["b.bin"]
    m2.stop()


def test_set_files_dal_vivo(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet)  # nessun peer: resta in attesa dei metadati
    assert _wait(lambda: t.id in m._torrent.handles)
    m.set_sequential(t.id, True)
    assert _wait(lambda: t.id in m._torrent.handles
                 and m._torrent.handles[t.id].flags() & lt.torrent_flags.sequential_download)
    m.set_sequential(t.id, False)
    assert _wait(lambda: t.id in m._torrent.handles
                 and not m._torrent.handles[t.id].flags() & lt.torrent_flags.sequential_download)
    m.set_files(t.id, {"0": 4})
    with pytest.raises(ValueError):
        m.set_files(t.id, {"0": 3})
    t.options["connect"] = [swarm.peer]
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert (tmp / "out" / "set" / "a.bin").read_bytes() == swarm.data["a.bin"]
    m.stop()


def test_gioco_scelto_da_un_set(swarm, tmp):
    """Un gioco preso da un set: titolo al posto del nome del set, altri file ne' visibili ne' scaricabili."""
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet, name="Gioco B", wanted="b.bin", **{"connect": [swarm.peer]})
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    v = t.view()
    assert v["name"] == "Gioco B"
    assert [f["name"] for f in v["options"]["files"]] == [str(Path("set") / "b.bin")] and v["options"]["files_locked"]
    with pytest.raises(ValueError):
        m.set_files(t.id, {"0": 4})
    m.stop()


def test_nome_dal_file_se_ne_scarichi_uno_solo(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet, wanted="b.bin", **{"connect": [swarm.peer]})
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert t.name == "b"  # non «set»
    m.stop()


def test_pick_files_so():
    names = ["set/a.bin", "set/b.bin", "set/c.bin"]
    assert TOR.pick_files(names, "magnet:?xt=urn:btih:x&so=0,2", "b") == {0, 2}
    assert TOR.pick_files(names, "magnet:?xt=urn:btih:x&so=1-5", "") == {1, 2}
    assert TOR.pick_files(names, "magnet:?xt=urn:btih:x", "B.BIN") == {1}
    assert TOR.pick_files(names, "magnet:?xt=urn:btih:x", "") == set()
    assert TOR.is_torrent("https://x/y.torrent?k=1") and TOR.is_torrent("MAGNET:?xt") and not TOR.is_torrent("https://x/y.zip")


def test_pausa_e_ripresa_rapide(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(str(swarm.torrent))  # nessun peer: resta in corso
    assert _wait(lambda: t.options.get("metadata"))
    m.pause(t.id)
    m.resume(t.id)  # il vecchio job sta ancora salvando/togliendo il torrent: il nuovo deve aspettarlo
    time.sleep(3)
    assert t.status == T.RUNNING and not t.error and t.id in m._torrent.handles
    m.stop()


def test_magnet_senza_metadati_libera_il_posto(swarm, tmp, monkeypatch):
    monkeypatch.setattr(TOR, "META_TIMEOUT", 1)
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet)  # nessun peer: i metadati non arrivano
    assert _wait(lambda: t.status == T.ERROR) and "Riprendi" in t.error
    m.resume(t.id)
    assert t.status in (T.QUEUED, T.RUNNING) and not t.error  # il tick puo' gia' averlo fatto ripartire
    m.stop()


def test_set_files_aggiorna_la_vista_e_riapre_il_completato(tmp):
    m = _mgr(tmp)
    t = T.DownloadTask(source="magnet:?xt=urn:btih:" + "a" * 40, save_path=str(tmp), type="torrent", status=T.COMPLETED,
                       options={"priorities": {"0": 0, "1": 4}, "files": [{"index": 0, "priority": 0}, {"index": 1, "priority": 4}]})
    m.tasks[t.id] = t
    m.set_files(t.id, {"0": 7})
    assert t.status == T.QUEUED and [f["priority"] for f in t.options["files"]] == [7, 4]


def test_tracker_aggiunti_anche_dal_vivo_e_limiti_per_torrent(swarm, tmp):
    m = _mgr(tmp)
    m.update_settings({"trackers": ["udp://uno.example:80/announce"]})
    m.start()
    t = m.add(str(swarm.torrent))  # nessun peer: resta in corso
    assert _wait(lambda: t.id in m._torrent.handles)
    h = m._torrent.handles[t.id]
    urls = lambda: {e["url"] for e in h.trackers()}  # noqa: E731
    assert _wait(lambda: "udp://uno.example:80/announce" in urls())
    m.update_settings({"trackers": ["udp://uno.example:80/announce", "wss://due.example/ws"]})
    assert _wait(lambda: "wss://due.example/ws" in urls())
    assert _wait(lambda: t.options.get("trackers") == 2)
    m.set_limit(t.id, 30, 20)
    assert _wait(lambda: h.download_limit() == 30 * 1024 and h.upload_limit() == 20 * 1024)
    m.recheck(t.id)
    m.reannounce(t.id)
    m.stop()


def test_condivisione_dopo_la_fine_non_occupa_posti(swarm, tmp):
    m = _mgr(tmp, seed_ratio=50, max_active=1)
    m.start()
    t = m.add(str(swarm.torrent), connect=[swarm.peer])
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert t.options["seeding"] is True and t.id in m._torrent.handles and t.finished
    assert "ratio" in t.view()["options"]
    u = m.add(swarm.magnet)  # l'unico posto e' libero: chi condivide non lo occupa
    assert _wait(lambda: u.status == T.RUNNING)
    m.pause(t.id)  # ferma la condivisione, resta completato
    assert _wait(lambda: t.id not in m._torrent.handles and "seeding" not in t.options)
    assert t.status == T.COMPLETED
    m.stop()


def test_cancella_torrent_caricato_con_i_file(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    m.uploads.mkdir(parents=True)
    up = m.uploads / "x-set.torrent"
    up.write_bytes(swarm.torrent.read_bytes())
    t = m.add(str(up), connect=[swarm.peer])
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    m.cancel(t.id, delete_files=True)
    assert _wait(lambda: not (tmp / "out" / "set").exists() and not up.exists(), 5)
    assert (tmp / "out").exists()
    m.stop()


def test_registro_del_torrent(swarm, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet, connect=[swarm.peer], wanted="b.bin")
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    msgs = [l["msg"] for l in t.log_after(0)[0]]
    text = " ".join(msgs)
    assert msgs[0].startswith("Aggiunto (torrent): magnet:?…") and "btih" not in text
    assert any(x.startswith("Torrent aggiunto alla sessione") for x in msgs)
    assert any(x.startswith("Metadati ricevuti: set, 2 file") for x in msgs) and "File scelti: 1 di 2" in msgs
    assert any(x.startswith("Stato: ") for x in msgs)
    assert msgs[-1].startswith("Completato: b")
    with pytest.raises(ValueError):  # gioco scelto da un set: la selezione e' bloccata
        m.set_files(t.id, {"0": 1})
    m.stop()


def test_stato_sessione_su_disco(tmp):
    e = TOR.Engine(tmp / "res")
    e.configure({})
    e._pack.update(LOCAL, listen_interfaces="127.0.0.1:0")
    e.session()
    e.close()
    f = tmp / "res" / "session.dat"
    assert f.read_bytes()
    e2 = TOR.Engine(tmp / "res")
    e2._pack = dict(e._pack)
    assert e2.session() is not None  # round trip
    e2.close()
    f.write_bytes(os.urandom(200))  # rovinato: fallback
    e3 = TOR.Engine(tmp / "res")
    e3._pack = dict(e._pack)
    assert e3.session() is not None
    e3.close()


def test_tracker_paralleli_e_filtro_avvisi(tmp):
    e = TOR.Engine(tmp / "res")
    e.configure({})
    assert e._pack.get("announce_to_all_trackers") is True
    assert e._pack.get("announce_to_all_tiers") is True
    assert e._pack.get("tracker_completion_timeout") == 15

    mag = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&tr=udp%3A%2F%2Ffake.invalid%3A1337%2Fann"
    p = lt.parse_magnet_uri(mag)
    p.save_path = str(tmp)
    p.tracker_tiers = [0] * len(p.trackers)
    ses = e.session()
    h = ses.add_torrent(p)
    e.add_trackers(h)
    assert all(t["tier"] == 0 for t in h.trackers())
    tid = "test-task"
    e.handles[tid] = h
    logs = []
    e.logs[tid] = lambda msg, level="info": logs.append((msg, level))
    assert _wait(lambda: e._pump() or logs, 15)  # l'errore DNS arriva quando arriva: su CI lenta non sono 1,5 s
    for _ in range(10):  # poi si controlla che l'avviso non si ripeta
        e._pump()
        time.sleep(0.1)
    assert len(logs) == 1
    assert "fake.invalid" in logs[0][0] and logs[0][1] == "warn"
    assert not any("unreachable" in m[0].lower() or "non raggiungibile" in m[0].lower() for m in logs)
    assert any(t["url"] == "udp://fake.invalid:1337/ann" and t["fail_limit"] == 1 for t in h.trackers())
    assert "udp://fake.invalid:1337/ann" in e.dead_trackers[tid]
    ses.remove_torrent(h)


def test_pre_verifica_e_blacklist_tracker_unreachable(tmp):
    import asyncio
    e = TOR.Engine(tmp / "res")
    e.configure({})
    mag = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&tr=udp%3A%2F%2Fnonexistent-fake-xyz123.org%3A1337%2Fann&tr=udp%3A%2F%2Fvalid.example%3A1337%2Fann"
    t = T.DownloadTask(source=mag, save_path=str(tmp))
    p = asyncio.run(TOR._params(t, e, None))
    assert "udp://valid.example:1337/ann" in p.trackers
    assert "udp://nonexistent-fake-xyz123.org:1337/ann" not in p.trackers
    assert "udp://nonexistent-fake-xyz123.org:1337/ann" in t.options["dead_trackers"]

    p.save_path = str(tmp)
    ses = e.session()
    h = ses.add_torrent(p)
    e.handles[t.id] = h
    e.logs[t.id] = lambda m, l="info": None
    h.add_tracker({"url": "udp://runtime-dead.invalid:1337/ann", "tier": 0})
    h.force_reannounce()
    assert _wait(lambda: e._pump() or "udp://runtime-dead.invalid:1337/ann" in e.dead_trackers[t.id], 15)
    assert "udp://runtime-dead.invalid:1337/ann" in e.dead_trackers[t.id]
    assert any(tr["url"] == "udp://runtime-dead.invalid:1337/ann" and tr["fail_limit"] == 1 for tr in h.trackers())

    e.trackers = ["udp://runtime-dead.invalid:1337/ann"]
    e.add_trackers(h, t)
    assert len([tr for tr in h.trackers() if "runtime-dead.invalid" in tr["url"]]) == 1
    ses.remove_torrent(h)
