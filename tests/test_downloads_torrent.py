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


def test_magnet_con_metadati_rispettano_i_posti(tmp, monkeypatch):
    """20 magnet, 2 posti: chi aspetta i metadati non occupa, ma a metadati arrivati scaricano al massimo in 2."""
    import asyncio
    active, peak = set(), [0]

    async def fake(task, eng, client, on_complete=lambda: None, gate=None, space=None):
        task.options["metadata"] = False
        await asyncio.sleep(0.05)
        if gate:
            await gate()
        task.options["metadata"] = True
        active.add(task.id)
        peak[0] = max(peak[0], len(active))
        await asyncio.sleep(0.3)
        active.discard(task.id)

    monkeypatch.setattr(TOR, "run", fake)
    m = _mgr(tmp, max_active=2)
    m.start()
    ts = [m.add("magnet:?xt=urn:btih:" + f"{i:040x}") for i in range(20)]
    assert _wait(lambda: all(t.status == T.COMPLETED for t in ts), 60), [t.status for t in ts]
    assert peak[0] <= 2, peak
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
    u = m.add(swarm.magnet, force=True)  # l'unico posto e' libero: chi condivide non lo occupa (stesso torrent apposta)
    assert _wait(lambda: u.status == T.RUNNING)
    m.pause(t.id)  # ferma la condivisione, resta completato
    assert _wait(lambda: t.id not in m._torrent.handles and "seeding" not in t.options)
    assert t.status == T.COMPLETED
    m.stop()


def test_condivisione_riparte_dopo_il_riavvio(swarm, tmp):
    m = _mgr(tmp, seed_ratio=50)
    got = []
    m.on_completed = got.append
    m.start()
    t = m.add(str(swarm.torrent), connect=[swarm.peer])
    assert _wait(lambda: t.status == T.COMPLETED and t.options.get("seeding")), (t.status, t.error)
    finished = t.finished
    m.stop()  # chiusura del launcher: non e' una fine della condivisione
    assert t.options.get("seeding") is True and t.status == T.COMPLETED
    m2 = _mgr(tmp, seed_ratio=50)
    m2.on_completed = got.append
    m2.start()
    t2 = m2.tasks[t.id]
    assert _wait(lambda: t2.id in m2._torrent.handles), t2.options
    assert t2.options["seeding"] is True and t2.status == T.COMPLETED and t2.finished == finished
    m2.pause(t2.id)  # fermata a mano: finisce davvero, e solo ora parte il post-download
    assert _wait(lambda: "seeding" not in t2.options and len(got) == 1), (t2.options, got)
    m2.stop()


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
    # nome non risolto durante il download: puo' essere il Wi-Fi caduto, libtorrent lo riprova (niente fail_limit 1)
    assert "riprovo" in logs[0][0]
    assert all(t["fail_limit"] == 0 for t in h.trackers()), h.trackers()
    assert "udp://fake.invalid:1337/ann" not in e.dead_trackers.get(tid, set())
    ses.remove_torrent(h)


def _dns(monkeypatch, table):
    """getaddrinfo finto: host -> "ok" | "nx" (il nome non esiste) | "again" (DNS giu') | "slow" (oltre il timeout)."""
    import socket

    def fake(host, *a, **k):
        r = table[host]
        if r == "slow":
            raise socket.timeout("lento")
        if r in ("nx", "again"):
            raise socket.gaierror(socket.EAI_NONAME if r == "nx" else socket.EAI_AGAIN, r)
        return [(socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("1.2.3.4", 0))]
    monkeypatch.setattr(TOR.socket, "getaddrinfo", fake)
    monkeypatch.setattr(TOR.socket, "gethostbyname", lambda h: fake(h)[0][4][0])  # quello che usava la 0.18


def _magnet(*hosts):
    from urllib.parse import quote
    return "magnet:?xt=urn:btih:" + "0123456789abcdef" * 2 + "01234567" + "".join(
        f"&tr={quote(f'udp://{h}:1337/ann', safe='')}" for h in hosts)


def test_pre_verifica_esclude_solo_i_nomi_che_non_esistono(tmp, monkeypatch):
    import asyncio
    e = TOR.Engine(tmp / "res")
    e.configure({})
    _dns(monkeypatch, {"buono.org": "ok", "lento.org": "slow", "sparito.org": "nx", "giu.org": "again"})
    t = T.DownloadTask(source=_magnet("buono.org", "lento.org", "sparito.org", "giu.org", "valid.example"), save_path=str(tmp))
    p = asyncio.run(TOR._params(t, e, None))
    hosts = {u.split("//")[1].split(":")[0] for u in p.trackers}
    assert hosts == {"buono.org", "lento.org", "giu.org", "valid.example"}, hosts  # lento o DNS giu': restano
    assert t.options["bad_trackers"] == ["udp://sparito.org:1337/ann"]


def test_pre_verifica_senza_rete_non_esclude_nessuno(tmp, monkeypatch):
    """Offline (macOS risponde «il nome non esiste» per tutti): nessun nome risolto = nessuna prova, restano tutti."""
    import asyncio
    e = TOR.Engine(tmp / "res")
    e.configure({})
    _dns(monkeypatch, {"a.org": "nx", "b.org": "nx"})
    t = T.DownloadTask(source=_magnet("a.org", "b.org"), save_path=str(tmp))
    p = asyncio.run(TOR._params(t, e, None))
    assert len(p.trackers) == 2 and not t.options.get("bad_trackers")


def test_errori_permanenti_dei_tracker():
    def alert(cat, code):
        err = SimpleNamespace(category=lambda: SimpleNamespace(name=lambda: cat), value=lambda: code)
        return SimpleNamespace(error=err)
    assert TOR._permanent(alert("http", 404)) and TOR._permanent(alert("http", 410))
    assert TOR._permanent(alert("libtorrent", 24))  # protocollo non supportato
    for cat, code in (("http", 503), ("http", 429), ("libtorrent", 36), ("asio.netdb", 1), ("asio.netdb", 2), ("system", 61)):
        assert not TOR._permanent(alert(cat, code)), (cat, code)  # timeout, nome non risolto, rifiutato: si riprova


def test_vecchio_elenco_dei_tracker_morti_buttato_una_volta(swarm, tmp):
    """Task della 0.18: options["dead_trackers"] (con dentro anche tracker solo lenti) si butta, i tracker tornano."""
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet + "&tr=udp%3A%2F%2Flento.example%3A1337%2Fann", connect=[swarm.peer],
              dead_trackers=["udp://lento.example:1337/ann"])
    assert _wait(lambda: t.id in m._torrent.handles)
    h = m._torrent.handles[t.id]
    assert _wait(lambda: "udp://lento.example:1337/ann" in {e["url"] for e in h.trackers()})
    assert "dead_trackers" not in t.options
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    m.stop()


# ------------------------------------------------------------ disco pieno
def test_errore_disco_pieno_di_libtorrent():
    import errno
    for cat in (lt.generic_category(), lt.system_category()):
        assert TOR.disk_full(lt.error_code(errno.ENOSPC, cat))  # file_error_alert / torrent_status.errc su macOS e Linux
    assert not TOR.disk_full(lt.error_code(errno.EACCES, lt.system_category()))  # altri errori di scrittura: restano errori
    assert not TOR.disk_full(lt.error_code(errno.ENOSPC, lt.libtorrent_category()))  # stesso numero, altra categoria


def _poco_spazio(monkeypatch, free):
    """Disco finto: free[0] byte liberi, riletti subito (niente attese di cache)."""
    import shutil
    from pozzo.downloads import extract as X
    X._FREE.clear()
    monkeypatch.setattr(X, "FREE_TTL", 0.2)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=free[0]))


@pytest.mark.parametrize("how", ["magnet", "torrent"])
def test_senza_spazio_dopo_i_metadati_si_ferma_e_riprende_da_solo(swarm, tmp, monkeypatch, how):
    """Un magnet ha dimensione ignota al controllo di coda: lo spazio si controlla coi metadati (il .torrent subito)."""
    free = [50_000]  # meno dei ~213 KB del set
    _poco_spazio(monkeypatch, free)
    m = _mgr(tmp)
    m.start()
    t = m.add(swarm.magnet if how == "magnet" else str(swarm.torrent), connect=[swarm.peer])
    assert _wait(lambda: t.status == T.PAUSED, 60), (t.status, t.error)
    assert t.error.startswith("Disco pieno") and t.phase == "Disco pieno" and t.options["disk_full"]
    assert t.size == sum(map(len, swarm.data.values())) and m._batch == [0, 0]  # nessun fallimento
    assert _wait(lambda: not m._torrent.handles) and m._torrent.resume_file(t.id).exists()  # metadati su disco per riprendere
    time.sleep(1.5)
    assert t.status == T.PAUSED  # ancora pieno: resta fermo
    free[0] = 10**9
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    for n, b in swarm.data.items():
        assert (tmp / "out" / "set" / n).read_bytes() == b
    assert "disk_full" not in t.options
    m.stop()


def test_disco_pieno_durante_il_torrent_mette_in_pausa(tmp, monkeypatch):
    """libtorrent ferma il torrent con un errore ENOSPC (torrent_status.errc): pausa «Disco pieno», non errore."""
    import errno
    calls = []

    async def run(task, *a, **k):
        calls.append(1)
        task.size = 10
        raise OSError(errno.ENOSPC, "No space left on device")  # come lo alza TOR.run da s.errc
    monkeypatch.setattr("pozzo.downloads.manager.TOR.run", run)
    m = _mgr(tmp)
    m.start()
    t = m.add("magnet:?xt=urn:btih:" + "c" * 40)
    assert _wait(lambda: t.status == T.PAUSED, 30), (t.status, t.error)
    assert t.error.startswith("Disco pieno") and t.options["disk_full"] and m._batch == [0, 0]
    m.cancel(t.id)  # senza, il ciclo lo riprenderebbe (size 10 sta nel disco) mentre la cartella di prova sparisce
    m.stop()
