"""Gestore download: segmenti, ripresa, coda con priorita', persistenza, nomi sicuri. Server HTTP locale, nessuna rete."""

import asyncio
import os
import re
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import http as H  # noqa: E402
from pozzo.downloads import manager as M  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

DATA = os.urandom(5 * 1024 * 1024 + 123)
SERVED = {"bytes": 0}
REQS: list[str] = []  # intestazioni Range viste dal server
HITS: dict[str, int] = {}  # richieste per percorso (link monouso)
FLAKY = {"cut": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body, name = DATA, "gioco.bin"
        REQS.append(self.headers.get("Range", ""))
        HITS[self.path] = HITS.get(self.path, 0) + 1
        if (self.path.startswith("/once") and HITS[self.path] > 1) or self.path.startswith("/gone"):  # come 1fichier: il link vale una volta sola
            self.send_response(410)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/evil"):
            name = "..%2F..%2Fevil.bin"
        start, end = 0, len(body) - 1
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if m and not self.path.startswith("/norange"):
            start = int(m.group(1))
            end = int(m.group(2) or end)
        part = body[start:end + 1]
        self.send_response(206 if m and not self.path.startswith("/norange") else 200)
        self.send_header("Content-Length", str(len(part)))
        # /rotag: come datanodes, ogni richiesta arriva da un server diverso con un etag diverso
        self.send_header("ETag", f'"r{HITS[self.path]}"' if self.path.startswith("/rotag") else '"v1"')
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        if m and not self.path.startswith("/norange"):
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
        self.end_headers()
        if self.path.startswith("/norange-flaky") and FLAKY["cut"]:
            FLAKY["cut"] = False
            part = part[:len(part) // 2]  # connessione chiusa a meta'
        try:
            for i in range(0, len(part), 64 * 1024):
                self.wfile.write(part[i:i + 64 * 1024])
                SERVED["bytes"] += min(64 * 1024, len(part) - i)
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _lan_ok(monkeypatch):
    monkeypatch.setattr(H.hosts, "assert_public", lambda u: None)  # i server di prova stanno su 127.0.0.1

@pytest.fixture(scope="module")
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def _task(url, dest):
    return T.DownloadTask(source=url, save_path=str(dest))


async def test_segmenti_e_contenuto(server, tmp):
    t = _task(server + "/a", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 4, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == DATA
    assert len(list(tmp.iterdir())) == 1  # niente .part rimasto
    assert t.done == t.size == len(DATA)


async def test_ripresa_non_riscarica_il_gia_fatto(server, tmp):
    t = _task(server + "/a", tmp)
    b = H.Bucket()
    b.rate = 1024 * 1024
    async with httpx.AsyncClient() as c:
        job = asyncio.ensure_future(H.run(t, c, b, 2, lambda u: u))
        while t.done < 1024 * 1024:
            await asyncio.sleep(0.05)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        fatto = t.done
        assert 0 < fatto < len(DATA)
        REQS.clear()
        await H.run(t, c, H.Bucket(), 2, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == DATA
    # il gia' scaricato non si rivede: dopo la ripresa nessuna richiesta riparte da zero con un intervallo
    assert not [r for r in REQS if re.fullmatch(r"bytes=0-\d+", r)]


async def test_ripresa_con_etag_diverso_riusa_link_e_part(server, tmp):
    calls = []

    def resolve(u):
        calls.append(u)
        return server + "/rotag"
    t = _task("https://datanodes.example/pagina", tmp)
    b = H.Bucket()
    b.rate = 1024 * 1024
    async with httpx.AsyncClient() as c:
        job = asyncio.ensure_future(H.run(t, c, b, 2, resolve))
        while t.done < 1024 * 1024:
            await asyncio.sleep(0.05)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        REQS.clear()
        await H.run(t, c, H.Bucket(), 2, resolve)
    assert len(calls) == 1, "alla ripresa il link risolto si riusa: niente passaggi rifatti"
    assert (tmp / "gioco.bin").read_bytes() == DATA
    assert not [r for r in REQS if re.fullmatch(r"bytes=0-\d+", r)], "etag diverso ma stessa dimensione: si riprende"
    assert "url" not in t.options


async def test_link_risolto_scaduto_si_risolve_di_nuovo(server, tmp):
    calls = []
    t = _task("https://host.example/pagina", tmp)
    t.options.update(url=server + "/gone", url_at=time.time())
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 2, lambda u: calls.append(u) or server + "/a")
    assert calls == ["https://host.example/pagina"]
    assert (tmp / "gioco.bin").read_bytes() == DATA


async def test_senza_range(server, tmp):
    t = _task(server + "/norange", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 4, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == DATA


async def test_nome_non_esce_dalla_cartella(server, tmp):
    dest = tmp / "d"
    t = _task(server + "/evil", dest)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 2, lambda u: u)
    assert [p.parent for p in dest.iterdir()] == [dest] and not (tmp / "evil.bin").exists()


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl}})
    return Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _wait(cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_coda_priorita_e_limite(server, tmp):
    m = _mgr(tmp, max_active=1)
    release, orig = threading.Event(), m._resolve
    m._resolve = lambda t, u: orig(t, u) if u.endswith("/a") else (release.wait(30), orig(t, u))[1]
    m.start()
    with m.lock:  # risolvono tutti e tre (non occupano posti), il link di «a» arriva per primo
        a = m.add(server + "/a", name="a.bin", limit={"down": 256, "up": 0})  # lento: la coda resta visibile
        b = m.add(server + "/b", name="b.bin")
        c = m.add(server + "/c", name="c.bin", priority=5, limit={"down": 256, "up": 0})
    assert _wait(lambda: a.done > 0)
    release.set()
    # link risolti, ma il solo posto e' di «a»: aspettano al gate senza scaricare
    assert _wait(lambda: b.id in m._gates and c.id in m._gates)
    assert m._dl_ids == {a.id} and b.done == c.done == 0 and b.phase == "In attesa di un posto libero"
    m.pause(a.id)
    assert _wait(lambda: c.done > 0)  # vince la priorita'
    assert b.id in m._gates and b.done == 0
    m.stop()


def test_risoluzione_lenta_non_blocca_chi_ha_gia_il_link(server, tmp):
    m = _mgr(tmp, max_active=1)
    release, orig = threading.Event(), m._resolve
    m._resolve = lambda t, u: (release.wait(30), orig(t, u))[1] if "/slow" in u else orig(t, u)
    m.start()
    with m.lock:
        slow = m.add(server + "/slow", name="s.bin", priority=2)  # prima in coda, ma bloccato a risolvere
        fast = m.add(server + "/fast", name="f.bin")
    assert _wait(lambda: fast.status == T.COMPLETED)
    assert slow.status == T.RUNNING and slow.done == 0
    release.set()
    assert _wait(lambda: slow.status == T.COMPLETED)
    m.stop()


def test_tetto_ai_risolutori_in_parallelo(server, tmp):
    m = _mgr(tmp, max_active=1)
    release, orig = threading.Event(), m._resolve
    m._resolve = lambda t, u: (release.wait(30), orig(t, u))[1]
    m.start()
    with m.lock:
        ts = [m.add(server + f"/r{i}", name=f"r{i}.bin") for i in range(M.RESOLVERS_MAX + 1)]
    assert _wait(lambda: sum(t.status == T.RUNNING for t in ts) == M.RESOLVERS_MAX)
    time.sleep(1.5)
    assert sum(t.status == T.RUNNING for t in ts) == M.RESOLVERS_MAX  # il quarto aspetta in coda
    release.set()
    assert _wait(lambda: all(t.status == T.COMPLETED for t in ts), 30)
    m.stop()


def test_annullato_al_gate_non_perde_il_posto(server, tmp):
    m = _mgr(tmp, max_active=1)
    release, orig = threading.Event(), m._resolve
    m._resolve = lambda t, u: (release.wait(30), orig(t, u))[1] if u.endswith("/b") else orig(t, u)
    m.start()
    with m.lock:
        a = m.add(server + "/a", name="a.bin", limit={"down": 256, "up": 0})
        b = m.add(server + "/b", name="b.bin")
    assert _wait(lambda: a.done > 0)
    release.set()
    assert _wait(lambda: b.id in m._gates)
    m.cancel(b.id)
    assert _wait(lambda: b.id not in m._jobs and not m._gates)
    assert m._dl_ids == {a.id}
    m.cancel(a.id)
    c = m.add(server + "/c", name="c.bin")
    assert _wait(lambda: c.status == T.COMPLETED)  # il posto di «a» torna libero, quello di «b» non era mai stato preso
    assert not m._dl_ids
    m.stop()


async def test_magnet_senza_metadati_non_occupa_un_posto(tmp):
    m = _mgr(tmp, max_active=1)

    async def job(t, segments):
        pass
    m._job = job
    mag = _task("magnet:?xt=urn:btih:abc", tmp)
    mag.type, mag.status, mag.options["metadata"] = "torrent", T.RUNNING, False
    b = _task("http://x/b", tmp)
    m.tasks, m._jobs = {mag.id: mag, b.id: b}, {mag.id: None}
    m._tick()
    assert b.status == T.RUNNING and b.id in m._jobs  # il magnet aspetta i metadati: il posto e' libero
    m._jobs.pop(b.id)
    b.status, mag.options["metadata"] = T.QUEUED, True
    m._tick()
    assert b.status == T.QUEUED  # con i metadati il magnet scarica e occupa il posto


def test_salvataggio_del_tick_limitato(tmp):
    m = _mgr(tmp, max_active=0)
    saved = []
    m.store.save = lambda ts: saved.extend(t.id for t in ts)
    t = _task("http://x/a", tmp)
    t.status = T.RUNNING
    m.tasks = {t.id: t}
    m._tick()
    assert saved == [t.id]
    t.done = 100
    m._tick()
    assert saved == [t.id]  # solo avanzamento: aspetta
    t.phase = "Cerco il file"
    m._tick()
    assert saved == [t.id] * 2  # la fase cambia: subito
    t.done = 200
    m._tick()
    m._saved[t.id] = (m._saved[t.id][0] - M.SAVE_EVERY, m._saved[t.id][1])  # passano 10 s
    m._tick()
    assert saved == [t.id] * 3  # l'avanzamento rimasto da salvare arriva su disco anche senza altri cambi
    m._tick()
    assert saved == [t.id] * 3


def test_porta_fissa_scelta_una_volta(tmp):
    saved = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    m = Manager(cfg, client_factory=net.make_client, save=saved.append)
    m.start()
    port = m.settings()["port"]
    assert 49152 <= port <= 65000 and saved[-1]["port"] == port
    m.stop()
    m2 = Manager(cfg, client_factory=net.make_client, save=saved.append)
    m2.start()
    assert m2.settings()["port"] == port and len(saved) == 1  # stessa porta, niente da salvare
    m2.stop()


def test_porta_automatica_occupata_si_cambia_quella_a_mano_no(tmp, monkeypatch):
    saved = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "port": 50001,
                                                                   "port_auto": True}})
    monkeypatch.setattr(M, "_port_ok", lambda p: p != 50001)  # riservata da Windows dopo il riavvio
    m = Manager(cfg, client_factory=net.make_client, save=saved.append)
    m.start()
    assert m.settings()["port"] != 50001 and saved[-1]["port_auto"] is True
    m.stop()
    m.update_settings({"port": 50001})  # a mano
    assert cfg.app["downloads"]["port_auto"] is False
    m2 = Manager(cfg, client_factory=net.make_client, save=saved.append)
    m2.start()
    assert m2.settings()["port"] == 50001  # occupata, ma scelta dall'utente: resta
    m2.stop()


def test_persistenza_e_ripresa(server, tmp):
    m = _mgr(tmp, limit_down=2048)
    m.start()
    t = m.add(server + "/a", name="x.bin")
    assert _wait(lambda: t.done > 0)
    m.stop()
    m2 = _mgr(tmp)
    m2.start()
    assert m2.tasks[t.id].status in (T.QUEUED, T.RUNNING, T.COMPLETED)
    assert _wait(lambda: m2.tasks[t.id].status == T.COMPLETED)
    assert (tmp / "out" / "x.bin").read_bytes() == DATA


def test_rifiuta_sorgenti_non_supportate(tmp):
    m = _mgr(tmp)
    for bad in ("magnet:?xt=urn:btih:abc", "ftp://x/y", "file:///etc/passwd", "casa"):
        with pytest.raises(ValueError):
            m.add(bad)


async def test_senza_range_dopo_un_errore_riparte_da_capo(server, tmp):
    FLAKY["cut"] = True
    t = _task(server + "/norange-flaky", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 4, lambda u: u)
    assert not FLAKY["cut"] and (tmp / "gioco.bin").read_bytes() == DATA


async def test_non_sovrascrive_un_file_esistente(server, tmp):
    (tmp / "gioco.bin").write_bytes(b"mio")
    t = _task(server + "/a", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 2, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == b"mio"
    assert t.name == "gioco (1).bin" and (tmp / t.name).read_bytes() == DATA


def test_pausa_e_ripresa_rapide_non_perdono_il_job(server, tmp):
    m = _mgr(tmp, limit_down=256)
    m.start()
    t = m.add(server + "/a", name="r.bin")
    assert _wait(lambda: t.done > 0)
    m.pause(t.id)
    m.resume(t.id)
    assert _wait(lambda: t.status == T.RUNNING and t.id in m._jobs)
    time.sleep(1)  # il vecchio job e' finito: non deve aver tolto il nuovo
    assert t.id in m._jobs
    m.pause(t.id)
    time.sleep(0.5)
    d = t.done
    time.sleep(1.5)
    assert t.done == d, "in pausa ma scarica ancora"
    m.stop()


def test_annulla_e_cancella_mentre_scarica(server, tmp):
    m = _mgr(tmp, limit_down=256)
    m.start()
    t = m.add(server + "/a", name="c.bin")
    assert _wait(lambda: t.done > 0)
    part = Path(t.options["part"])
    m.cancel(t.id, delete_files=True)  # su Windows il .part e' ancora aperto dal job
    assert _wait(lambda: not part.exists(), 5)
    m.stop()


def test_eventi_solo_per_i_task_cambiati(tmp):
    sent = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "max_active": 0}})
    m = Manager(cfg, events=SimpleNamespace(emit=lambda n, d: sent.append([v["id"] for v in d["tasks"]])))
    a, b = _task("http://x/a", tmp), _task("http://x/b", tmp)
    m.tasks = {a.id: a, b.id: b}
    m._tick()
    assert sorted(sent.pop()) == sorted([a.id, b.id])
    m._tick()
    assert not sent  # niente di nuovo, niente evento
    m.pause(a.id)  # in coda, mai partito: la UI deve saperlo lo stesso
    m._tick()
    assert sent == [[a.id]]


def test_passaggi_visibili_nella_coda(tmp):
    """Prima del download la riga dice il passaggio in corso (ouo, pagina dell'host, preparazione)."""
    sent = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "max_active": 0}})
    m = Manager(cfg, events=SimpleNamespace(emit=lambda n, d: sent.append(d["tasks"][0])), save=lambda new: None)
    t = _task("http://x/ouo", tmp)
    m.tasks[t.id] = t
    m._phase(t, "Salto la pubblicità (ouo.io)")
    assert t.phase == "Salto la pubblicità (ouo.io)" and sent[-1]["phase"] == t.phase and sent[-1]["id"] == t.id
    n = len(sent)
    m._phase(t, "Salto la pubblicità (ouo.io)")
    assert len(sent) == n  # stesso passaggio: nessun evento inutile
    m._phase(t, "Cerco il file su datanodes.to")
    assert sent[-1]["phase"] == "Cerco il file su datanodes.to"
    m.tasks.pop(t.id)  # task cancellato mentre la risoluzione e' in corso: nessun evento
    m._phase(t, "Preparo il download")
    assert len(sent) == n + 1


def test_fase_sparisce_quando_il_download_parte(server, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(server + "/a", name="f.bin")
    assert _wait(lambda: t.done > 0)
    assert t.phase == "", t.phase  # a download partito la riga mostra avanzamento e velocità
    m.stop()


def test_vista_e_salvataggio_mentre_il_ciclo_cambia_options(tmp):
    """Le rotte leggono (list/view/salvataggio) mentre il ciclo aggiunge e toglie chiavi: niente «changed size»."""
    m = _mgr(tmp)
    t = _task("http://x/a", tmp)
    m.tasks[t.id] = t
    stop, old = threading.Event(), sys.getswitchinterval()

    def churn():
        while not stop.is_set():
            t.options.update({f"k{j}": j for j in range(200)})
            t.options["files"] = [{"index": 0, "priority": 4}]
            for j in range(200):
                t.options.pop(f"k{j}")

    sys.setswitchinterval(1e-6)
    th = threading.Thread(target=churn)
    th.start()
    try:
        for i in range(3000):
            m.list()
            if i % 300 == 0:
                m.store.save([t])
    finally:
        stop.set()
        th.join()
        sys.setswitchinterval(old)


def test_torrent_caricati_tolti_con_il_task_e_orfani_all_avvio(tmp):
    m = _mgr(tmp)
    m.uploads.mkdir(parents=True)
    used, orphan = m.uploads / "a-set.torrent", m.uploads / "b-vecchio.torrent"
    used.write_bytes(b"x")
    orphan.write_bytes(b"x")
    t = T.DownloadTask(source=str(used), save_path=str(tmp), type="torrent", status=T.PAUSED)
    m.store.save([t])
    m.start()
    assert used.exists() and not orphan.exists()
    m.cancel(t.id)
    assert _wait(lambda: not used.exists(), 5)
    m.stop()


def test_cancella_file_toglie_le_cartelle_rimaste_vuote(tmp):
    m = _mgr(tmp)
    root = tmp / "out"
    for n in ("set/sub/a.bin", "set/b.bin", "altro/mio.txt"):
        (root / n).parent.mkdir(parents=True, exist_ok=True)
        (root / n).write_bytes(b"x")
    t = T.DownloadTask(source="magnet:?xt=urn:btih:" + "a" * 40, save_path=str(root), type="torrent", status=T.COMPLETED,
                       options={"files": [{"name": "set/sub/a.bin"}, {"name": "set/b.bin"}, {"name": "altro/manca.bin"}]})
    m.tasks[t.id] = t
    m.cancel(t.id, delete_files=True)
    assert not (root / "set").exists() and (root / "altro" / "mio.txt").exists() and root.exists()


def test_fascia_lenta_giorni_e_mezzanotte():
    s = {"alt_enabled": False, "alt_schedule": {"enabled": True, "from": "22:00", "to": "07:00", "days": [0]}}  # lunedi
    mon, tue = datetime(2026, 11, 2), datetime(2026, 11, 3)
    assert mon.weekday() == 0
    assert M.alt_active(s, mon.replace(hour=23))
    assert M.alt_active(s, tue.replace(hour=6, minute=59))  # notte di lunedi, gia' martedi
    assert not M.alt_active(s, tue.replace(hour=7))
    assert not M.alt_active(s, mon.replace(hour=3))  # notte di domenica: domenica non e' scelta
    assert not M.alt_active(s, tue.replace(hour=23))
    s["alt_schedule"].update({"from": "09:00", "to": "17:30", "days": [1]})
    assert M.alt_active(s, tue.replace(hour=17, minute=29)) and not M.alt_active(s, tue.replace(hour=17, minute=30))
    assert not M.alt_active(s, mon.replace(hour=10))
    s["alt_schedule"]["enabled"] = False
    assert not M.alt_active(s, tue.replace(hour=10))
    assert M.alt_active({**s, "alt_enabled": True})


def test_limiti_lenti_e_quote_per_priorita(tmp):
    m = _mgr(tmp, limit_down=1000, alt_limit_down=100, alt_limit_up=7, max_active=0)
    a, b = _task("http://x/a", tmp), _task("http://x/b", tmp)
    a.priority, b.priority, a.status, b.status = 2, 0, T.RUNNING, T.RUNNING
    m.tasks, m._jobs, m._dl_ids = {a.id: a, b.id: b}, {a.id: None, b.id: None}, {a.id, b.id}
    m._tick()
    assert m._buckets[a.id].rate == 800 * 1024 and m._buckets[b.id].rate == 200 * 1024  # peso 2**priorita'
    m.set_limit(b.id, 50, 0)
    assert b.options["limit"] == {"down": 50, "up": 0}
    m._tick()
    assert m._buckets[b.id].rate == 50 * 1024  # vale il piu' basso tra quota e limite proprio
    m.set_alt(True)
    assert m.settings()["alt_active"] and m._limits(m._raw()) == (100, 7)
    m._tick()
    assert m._buckets[a.id].rate == 80 * 1024
    if m._torrent:
        assert m._torrent._pack["download_rate_limit"] == 100 * 1024 and m._torrent._pack["upload_rate_limit"] == 7 * 1024
    m.set_alt(False)
    m.update_settings({"limit_down": 0})
    m._tick()
    assert m._buckets[a.id].rate == 0 and m._buckets[b.id].rate == 50 * 1024


def test_limite_del_task_rallenta_il_download(server, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(server + "/a", name="l.bin")
    m.set_limit(t.id, 256, 0)
    assert _wait(lambda: t.done > 0)
    d0, t0 = t.done, time.time()
    time.sleep(2)
    rate = (t.done - d0) / (time.time() - t0)
    assert rate < 400 * 1024, rate
    m.stop()


def test_sposta_in_cima_e_in_fondo(tmp):
    m = _mgr(tmp)
    a, b, c = (m.add(f"http://x/{n}") for n in "abc")
    b.priority = 1
    m.move(c.id, "top")
    assert [v["id"] for v in m.list()] == [c.id, b.id, a.id] and c.priority == 1
    m.move(b.id, "bottom")
    assert [v["id"] for v in m.list()] == [c.id, a.id, b.id] and b.priority == 0
    with pytest.raises(ValueError):
        m.move(a.id, "meta")


def test_pausa_e_ripresa_di_tutti(tmp):
    m = _mgr(tmp)
    a, b = m.add("http://x/a"), m.add("http://x/b", priority=9)
    assert b.priority == 2
    m.pause_all()
    assert a.status == b.status == T.PAUSED
    m.resume_all()
    assert a.status == b.status == T.QUEUED
    with pytest.raises(ValueError):
        m.recheck(a.id)  # solo torrent


def test_impostazioni_controllate(tmp):
    saved = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "discovery": False}})
    m = Manager(cfg, save=saved.append)
    assert m.settings()["discovery"] == {"dht": False, "pex": False, "lsd": False, "upnp": False}  # vecchio interruttore unico
    s = m.update_settings({"max_active": 99, "segments": 0, "port": 70000, "seed_ratio": 1000, "seed_minutes": -3,
                           "max_active_torrent": "4", "trackers": ["udp://a:1/ann", "udp://a:1/ann", "ftp://no", " wss://w/x ", 5],
                           "discovery": {"dht": True}, "encryption": "require",
                           "alt_schedule": {"enabled": True, "from": "7:05", "days": [3, 1, 1]}})
    assert (s["max_active"], s["segments"], s["port"], s["seed_ratio"], s["seed_minutes"], s["max_active_torrent"]) == (10, 1, 65535, 100.0, 0, 4)
    assert s["trackers"] == ["udp://a:1/ann", "wss://w/x"]
    assert s["discovery"] == {"dht": True, "pex": False, "lsd": False, "upnp": False}
    assert s["alt_schedule"] == {"enabled": True, "from": "07:05", "to": "07:00", "days": [1, 3]}
    assert saved[-1]["encryption"] == "require" and cfg.app["downloads"] is saved[-1]
    for bad in ({"encryption": "forse"}, {"alt_schedule": {"to": "25:00"}}, {"alt_schedule": {"days": [7]}},
                {"limit_down": "tanto"}, {"seed_ratio": "nan"}, {"alt_enabled": "si"}, {"debrid": {"boh": {}}}, {"trackers": 3}):
        with pytest.raises(ValueError):
            m.update_settings(bad)
    m.update_settings({"debrid": {"realdebrid": {"enabled": True, "key": "SEGRETA"}}})
    s = m.settings()
    assert s["debrid"]["realdebrid"] == {"enabled": True, "key_set": True} and "SEGRETA" not in repr(s)
    assert s["debrid"]["torbox"] == {"enabled": False, "key_set": False}
    assert m._raw()["debrid"]["realdebrid"]["key"] == "SEGRETA"
    m.update_settings({"debrid": {"realdebrid": {"key": ""}}})
    assert m.settings()["debrid"]["realdebrid"] == {"enabled": True, "key_set": False}


def test_evento_porta_le_impostazioni_quando_cambia_la_modalita_lenta(tmp):
    sent = []
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "max_active": 0}})
    m = Manager(cfg, events=SimpleNamespace(emit=lambda n, d: sent.append(d)), save=lambda new: None)
    m._tick()
    assert sent.pop()["settings"]["alt_active"] is False
    m._tick()
    assert not sent
    cfg.app["downloads"]["alt_enabled"] = True  # come se fosse scattato l'orario
    m._tick()
    assert sent.pop() == {"tasks": [], "settings": m.settings()} and m.settings()["alt_active"]


async def test_link_monouso_si_scarica_con_una_sola_richiesta(server, tmp):
    HITS.clear()
    t = _task(server + "/once", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 1, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == DATA
    assert HITS["/once"] == 1


async def test_host_monouso_non_si_spezza_in_piu_flussi(server, tmp, monkeypatch):
    HITS.clear()
    monkeypatch.setattr(H, "ONE_TIME", ("127.0.0.1",))
    t = _task(server + "/once", tmp)
    async with httpx.AsyncClient() as c:
        await H.run(t, c, H.Bucket(), 4, lambda u: u)
    assert (tmp / "gioco.bin").read_bytes() == DATA
    assert HITS["/once"] == 1


def _msgs(t):
    return [l["msg"] for l in t.log_after(0)[0]]


def test_registro_http_senza_segreti(server, tmp):
    m = _mgr(tmp)
    m.start()
    t = m.add(server + "/a?token=SECRET", name="log.bin")
    assert _wait(lambda: t.status == T.COMPLETED)
    msgs = _msgs(t)
    text = "\n".join(msgs)
    assert "SECRET" not in text and "token=" not in text
    assert msgs[0].startswith("Aggiunto (http)") and "Avviato" in msgs
    assert any(x.startswith("Controllo: gioco.bin") and "Range sì" in x and "HTTP 206" in x for x in msgs)
    assert any(x.startswith("Nuovo download: ") and "segment" in x for x in msgs)
    assert any(x.startswith("Avanzamento ") for x in msgs) and msgs[-1].startswith("Completato: log.bin")
    assert any(x.startswith("Link diretto") for x in msgs)
    assert all(l["level"] in ("info", "warn", "error") and l["t"] > 0 for l in t.logs)
    v = t.view()
    assert v["log_n"] == len(msgs) and "logs" not in v and "logs" not in m.list()[0]
    m.set_priority(t.id, 2)
    m.set_limit(t.id, 100, 0)
    assert t.log_n == len(msgs) + 2 and _msgs(t)[-1].startswith("Limite di velocità: giù 100, su nessuno")
    m.stop()


def test_registro_limite_incrementale_e_svuota():
    t = T.DownloadTask(source="http://x/y", save_path=".")
    for i in range(700):
        t.log(f"riga {i}")
    assert len(t.logs) == T.LOG_MAX == 500 and t.log_n == 700 and t.logs[0]["msg"] == "riga 200"
    lines, n = t.log_after(698)
    assert [l["msg"] for l in lines] == ["riga 698", "riga 699"] and n == 700
    assert t.log_after(700) == ([], 700) and len(t.log_after(0)[0]) == 500  # indici scartati: parte dalla prima rimasta
    t.log("nuova")
    assert t.log_after(700)[0][0]["msg"] == "nuova"
    t.log_clear()
    assert t.log_after(0) == ([], 701) and t.log_n == 701
    t.log("dopo")
    assert t.log_after(701)[0][0]["msg"] == "dopo"


def test_registro_redige_link_e_credenziali():
    t = T.DownloadTask(source="http://x/y", save_path=".")
    t.log("GET https://u:pw@host.example/p/f.bin?token=A&x=1#frag fallito, Bearer abc123, apikey=ZZZ, "
          "magnet:?xt=urn:btih:1&tr=http://t/announce?passkey=P")
    m = t.logs[0]["msg"]
    assert "https://host.example/p/f.bin?…" in m or "https://***host.example/p/f.bin?…" in m
    for s in ("token=A", "pw", "abc123", "ZZZ", "passkey", "btih"):
        assert s not in m


def test_registro_persiste_ridotto_al_riavvio(server, tmp):
    m = _mgr(tmp, limit_down=2048)
    m.start()
    t = m.add(server + "/a", name="p.bin")
    assert _wait(lambda: t.done > 0)
    for i in range(300):
        t.log(f"riga {i}")
    n = t.log_n
    m.stop()
    m2 = _mgr(tmp)
    m2.start()
    t2 = m2.tasks[t.id]
    assert t2.log_n > n and len(t2.logs) == T.LOG_SAVED + 1  # salvate le ultime 200, piu' la riga del riavvio
    msgs = _msgs(t2)
    assert "riga 120" in msgs and "riga 50" not in msgs and "era stato chiuso" in msgs[-1]
    m2.stop()


def test_a_download_finito_parte_il_dopo_download_una_volta(server, tmp):
    m = _mgr(tmp)
    got = []
    m.on_completed = got.append
    m.start()
    t = m.add(server + "/a", name="x.bin")
    assert _wait(lambda: t.status == T.COMPLETED)
    assert _wait(lambda: len(got) == 1) and got[0] is t
    m.pause(t.id)  # un task gia' completato non riparte
    m.stop()
    assert len(got) == 1
