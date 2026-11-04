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
    assert big.status == T.QUEUED and big.phase.startswith("Spazio insufficiente: servono 10.0 GB")
    assert small.status == T.RUNNING
