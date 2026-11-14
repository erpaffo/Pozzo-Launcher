"""Robustezza del download manager: post-download che riparte dopo un riavvio, disco pieno, nuovi tentativi di
risoluzione, tetto alle estrazioni insieme. Nessuna rete: il motore HTTP e' finto."""
import errno
import httpx
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import manager as M  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.store import Store  # noqa: E402


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), **dl}})
    return M.Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _wait(cond, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _saved(tmp, **opts):
    t = T.DownloadTask(source="https://x.test/g.zip", save_path=str(tmp / "out"), name="g.zip", status=T.COMPLETED,
                       size=10, done=10, options=opts)
    Store(tmp / "cache").save([t])
    return t.id


def test_post_download_interrotto_riparte_al_riavvio(tmp):
    rotto = _saved(tmp, steps={"extract": "active"})  # chiuso a meta' estrazione
    finito = _saved(tmp, steps={"extract": "done", "library": "done"}, post_done=True)
    vecchio = _saved(tmp)  # completato senza post-download (versioni vecchie, on_completed assente)
    troppi = _saved(tmp, steps={}, post_tries=M.POST_TRIES)  # ogni volta il launcher e' caduto: basta
    m = _mgr(tmp)
    got = []
    m.on_completed = got.append
    m.start()
    assert _wait(lambda: m.tasks[rotto].options.get("post_done")), m.tasks[rotto].options
    assert [t.id for t in got] == [rotto] and m.tasks[rotto].options["post_tries"] == 1
    assert not m.tasks[vecchio].options.get("post_done") and m.tasks[finito].options["post_done"]
    assert m.tasks[troppi].options["post_done"] and any(s["state"] == "error" for s in m.tasks[troppi].stages)
    m.stop()
    m2 = _mgr(tmp)  # finito: al riavvio dopo non riparte piu'
    m2.on_completed = got.append
    m2.start()
    time.sleep(1.5)
    assert len(got) == 1
    m2.stop()


def test_post_download_non_finito_resta_da_riprendere(tmp, monkeypatch):
    """Finche' on_completed gira il task e' salvato con steps e senza post_done: e' cio' che start() cerca."""
    async def run(task, *a, **k):
        task.name, task.size, task.done = "x.bin", 10, 10
    monkeypatch.setattr(M.HTTP, "run", run)
    m = _mgr(tmp)
    inside, go = threading.Event(), threading.Event()
    m.on_completed = lambda t: (inside.set(), go.wait(20))
    m.start()
    t = m.add("https://x.test/a")
    assert inside.wait(20)
    back = next(x for x in Store(tmp / "cache").load() if x.id == t.id)
    assert back.status == T.COMPLETED and "steps" in back.options and not back.options.get("post_done")
    go.set()
    assert _wait(lambda: t.options.get("post_done"))
    m.stop()


def test_estrazioni_insieme_limitate_dal_semaforo(tmp, monkeypatch):
    async def run(task, *a, **k):
        task.name, task.size, task.done = task.id + ".bin", 10, 10
    monkeypatch.setattr(M.HTTP, "run", run)
    m = _mgr(tmp, post_active=1)
    now, peak, lock = [0], [0], threading.Lock()

    def post(t):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        time.sleep(0.4)
        with lock:
            now[0] -= 1
    m.on_completed = post
    m.start()
    ts = [m.add(f"https://x.test/{i}") for i in range(3)]
    assert _wait(lambda: all(t.options.get("post_done") for t in ts))
    assert peak[0] == 1, peak
    m.stop()


def test_disco_pieno_mette_in_pausa_e_riprende_da_solo(tmp, monkeypatch):
    gap, calls = [0], [0]

    async def run(task, *a, **k):
        calls[0] += 1
        task.name, task.size = "x.bin", 10
        if calls[0] == 1:
            task.options["segs"] = [[0, 9, 4]]
            gap[0] = 5
            raise OSError(errno.ENOSPC, "No space left on device")
        task.done = 10
    monkeypatch.setattr(M.HTTP, "run", run)
    m = _mgr(tmp)
    m._space_gap = lambda t: gap[0]
    m.start()
    t = m.add("https://x.test/a")
    assert _wait(lambda: t.status == T.PAUSED), (t.status, t.error)
    assert t.error.startswith(M.DISK_FULL) and t.phase == M.DISK_FULL and t.options["disk_full"]
    assert t.options["segs"] == [[0, 9, 4]] and m._batch == [0, 0]  # stato per riprendere intatto, nessun fallimento
    assert any(l["level"] == "warn" and M.DISK_FULL in l["msg"] for l in t.log_after(0)[0])
    time.sleep(1.5)
    assert t.status == T.PAUSED and calls[0] == 1  # ancora pieno: resta fermo
    gap[0] = 0
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert "disk_full" not in t.options and not t.error
    m.stop()


def test_ripresa_a_mano_dopo_disco_pieno_non_riparte_da_sola(tmp, monkeypatch):
    async def run(task, *a, **k):
        task.size = 10
        raise OSError(errno.ENOSPC, "pieno")
    monkeypatch.setattr(M.HTTP, "run", run)
    m = _mgr(tmp)
    m.start()
    t = m.add("https://x.test/a")
    assert _wait(lambda: t.status == T.PAUSED)
    with m.lock:
        m.resume(t.id)
        assert "disk_full" not in t.options and t.phase == ""
        m.pause(t.id)  # l'utente lo ferma: non e' piu' una pausa da disco pieno
    time.sleep(1.5)
    assert t.status == T.PAUSED
    m.stop()


def test_risoluzione_fallita_si_ritenta_con_un_tetto(tmp, monkeypatch):
    calls = {}

    async def run(task, *a, **k):
        calls[task.id] = calls.get(task.id, 0) + 1
        task.phase = "Sblocco il link"
        if "debrid" in task.source:  # un risolutore ha detto perche' non ce l'ha fatta
            m._res[task.id] = (object(), ["Real-Debrid: il servizio sta preparando il file"])
        raise ValueError("Il link è una pagina, non un file")
    monkeypatch.setattr(M.HTTP, "run", run)
    monkeypatch.setattr(M, "RESOLVE_WAIT", 0)
    monkeypatch.setattr(M, "RESOLVE_TRIES", 2)
    m = _mgr(tmp)
    idle = []
    m.on_idle = lambda ok, bad: idle.append(bad)
    m.start()
    a = m.add("https://debrid.test/a")
    b = m.add("https://altro.test/b")  # nessuna nota: errore definitivo, niente tentativi
    assert _wait(lambda: calls.get(a.id) == 3 and a.status == T.ERROR and "retry_at" not in a.options), (calls, a.options)
    time.sleep(1.5)
    assert calls == {a.id: 3, b.id: 1} and b.status == T.ERROR and "res_err" not in a.options
    assert "Real-Debrid" in a.error and _wait(lambda: sum(idle) == 2), idle  # fallito una volta sola, alla fine
    assert sum("Nuovo tentativo" in l["msg"] for l in a.log_after(0)[0]) == 2
    m.stop()


def _status(code):
    req = httpx.Request("GET", "https://cdn.test/f.bin?token=x")
    return httpx.HTTPStatusError(f"HTTP {code}", request=req, response=httpx.Response(code, request=req))


def _expiring(monkeypatch, plan):
    """Motore HTTP finto: plan[n] = (byte scaricati, codice con cui fallisce o None per finire) alla n-esima partenza."""
    calls = []

    async def run(task, *a, **k):
        done, code = plan[min(len(calls), len(plan) - 1)]
        calls.append(dict(task.options))  # le opzioni con cui parte: il link vecchio deve essere sparito
        task.name, task.size, task.done = "x.bin", 10, done
        task.options["segs"] = [[0, 9, done]]
        if code is None:
            task.done = 10
            return
        if not task.options.get("direct"):
            task.options["url"] = "https://cdn.test/f.bin?token=x"  # link risolto da debrid/host
        else:
            task.options["url"] = task.source
        raise _status(code)
    monkeypatch.setattr(M.HTTP, "run", run)
    monkeypatch.setattr(M, "RESOLVE_WAIT", 0)
    monkeypatch.setattr(M, "RESOLVE_TRIES", 2)
    return calls


def test_link_scaduto_a_meta_si_risolve_da_solo(tmp, monkeypatch):
    calls = _expiring(monkeypatch, [(4, 403), (4, None)])
    m = _mgr(tmp)
    idle = []
    m.on_idle = lambda ok, bad: idle.append((ok, bad))
    m.start()
    t = m.add("https://debrid.test/a")
    assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    assert len(calls) == 2 and "url" not in calls[1] and calls[1]["segs"] == [[0, 9, 4]]  # link buttato, segmenti tenuti
    msgs = [l["msg"] for l in t.log_after(0)[0]]
    assert any("Link scaduto (HTTP 403)" in x for x in msgs) and any("Nuovo tentativo 1/2" in x for x in msgs)
    assert _wait(lambda: idle == [(1, 0)]), idle  # la scadenza non e' un fallimento
    assert not t.error and "res_err" not in t.options and "exp_done" not in t.options
    m.stop()


def test_link_morto_finisce_in_errore_dopo_i_tentativi(tmp, monkeypatch):
    for code in (401, 410):
        calls = _expiring(monkeypatch, [(4, code)])  # sempre lo stesso: nessun progresso tra un tentativo e l'altro
        m = _mgr(tmp / str(code))
        idle = []
        m.on_idle = lambda ok, bad: idle.append((ok, bad))
        m.start()
        t = m.add("https://debrid.test/a")
        assert _wait(lambda: len(calls) == 3 and t.status == T.ERROR and "retry_at" not in t.options), (len(calls), t.status)
        time.sleep(1.5)
        assert len(calls) == 3 and "scaduto" in t.error and f"HTTP {code}" in t.error  # messaggio chiaro, non si ripete all'infinito
        assert _wait(lambda: idle == [(0, 1)]), idle  # fallito una volta sola, alla fine
        m.stop()


def test_link_scaduto_con_progressi_non_esaurisce_i_tentativi(tmp, monkeypatch):
    calls = _expiring(monkeypatch, [(2, 403), (4, 403), (6, 403), (8, 403), (9, None)])  # ogni link regge un po'
    m = _mgr(tmp)
    m.start()
    t = m.add("https://debrid.test/a")
    assert _wait(lambda: t.status == T.COMPLETED, 40), (len(calls), t.status, t.error)
    assert len(calls) == 5
    m.stop()


def test_link_scritto_dall_utente_che_da_403_non_si_ritenta(tmp, monkeypatch):
    calls = _expiring(monkeypatch, [(4, 403)])
    m = _mgr(tmp)
    m.start()
    a = m.add("https://x.test/a", direct=True)  # il link e' gia' quello finale: risolvere di nuovo non cambia nulla
    assert _wait(lambda: a.status == T.ERROR) and "HTTP 403" in a.error and "retry_at" not in a.options
    time.sleep(1.5)
    assert len(calls) == 1
    m.stop()


def test_403_senza_byte_scaricati_e_un_rifiuto_non_un_link_scaduto(tmp, monkeypatch):
    calls = _expiring(monkeypatch, [(0, 403)])
    m = _mgr(tmp)
    m.start()
    b = m.add("https://debrid.test/b")
    assert _wait(lambda: b.status == T.ERROR) and "retry_at" not in b.options
    time.sleep(1.5)
    assert len(calls) == 1
    m.stop()
