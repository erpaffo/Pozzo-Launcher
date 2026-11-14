"""Previsione dello spazio della coda e gate di avvio in _tick: un task troppo grande resta in coda, uno piccolo parte. Nessuna rete."""

import asyncio
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import extract as X  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

GB = 2**30


def setup_function():
    X._FREE.clear()  # spazio libero in cache per disco: ogni test parte senza


def _task(tmp, name, size, done=0, status=T.QUEUED):
    return T.DownloadTask(source=f"http://x/{name}", save_path=str(tmp / "out"), name=name, size=size, done=done, status=status)


def test_previsione_per_disco(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=100))
    tasks = [_task(tmp_path, "a.zip", 10, done=4, status=T.RUNNING),  # 6 da scaricare, poi 10 da estrarre
             _task(tmp_path, "b.bin", 0),  # dimensione ignota: conta zero
             _task(tmp_path, "c.zip", 5, status=T.COMPLETED)]  # finito: non conta
    (d,) = X.queue_forecast(tasks)["drives"]
    assert d == {"drive": X.drive_of(tmp_path), "free_now": 100, "after_queue": 94, "after_extract": 84, "ok": True, "unknown": 1}


def test_task_troppo_grande_resta_in_coda(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=10 * GB))
    cfg = SimpleNamespace(cache=tmp_path / "cache", app={"downloads": {"dir": str(tmp_path / "out")}})
    m = Manager(cfg, client_factory=net.make_client, save=lambda new: None)

    async def job(t, segments):  # niente download vero: basta che il task parta
        return

    m._job = job
    big, small = _task(tmp_path, "grosso.bin", 20 * GB), _task(tmp_path, "piccolo.bin", 2 * GB)
    big.created = 0  # prima in coda: deve essere saltato senza fermare quello piccolo
    m.tasks = {big.id: big, small.id: small}

    async def tick():
        m._tick()
        await asyncio.sleep(0)  # lascia partire i job creati dal tick

    asyncio.run(tick())
    _refreshed(m)  # lo spazio si legge in un thread: al primo giro non c'e' ancora, chi aspetta resta in coda
    asyncio.run(tick())
    # 10 GB se il piccolo parte al secondo giro, 12 se il thread dello spazio finisce gia' durante il primo e il piccolo
    # (2 GB) e' gia' in corso: tutti e due giusti, dipende solo dai tempi
    assert big.status == T.QUEUED and big.phase in ("Spazio insufficiente: servono 10.0 GB", "Spazio insufficiente: servono 12.0 GB"), big.phase
    assert small.status == T.RUNNING


def _refreshed(m):
    import time
    end = time.time() + 5
    while getattr(m, "_space_busy", False) and time.time() < end:
        time.sleep(0.01)


def test_spazio_letto_fuori_dal_lock_e_dal_ciclo_una_volta_per_disco(tmp_path, monkeypatch):
    """Disco di rete spento: disk_usage puo' bloccare per il timeout SMB. Non sul thread del ciclo, non col lock
    preso, e una volta sola per disco ogni ~10 s anche con tanti task in coda."""
    import threading
    calls = []
    cfg = SimpleNamespace(cache=tmp_path / "cache", app={"downloads": {"dir": str(tmp_path / "out")}})
    m = Manager(cfg, client_factory=net.make_client, save=lambda new: None)

    def usage(p):
        calls.append((threading.current_thread() is threading.main_thread(), m.lock._is_owned()))  # lock preso da chi legge
        return SimpleNamespace(free=GB)  # non basta per nessuno: restano tutti in coda e si ricontrollano a ogni giro
    monkeypatch.setattr(shutil, "disk_usage", usage)
    m.tasks = {t.id: t for t in (_task(tmp_path, f"t{i}.bin", 2 * GB) for i in range(5))}
    for _ in range(3):
        m._tick()
        _refreshed(m)
    assert calls and not any(main or locked for main, locked in calls), calls
    assert len(calls) == 1, calls
    assert all(t.status == T.QUEUED and t.phase.startswith("Spazio insufficiente") for t in m.tasks.values())
