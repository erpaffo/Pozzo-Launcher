"""Budget di tempo e RAM per l'avvio dell'app e per la costruzione della libreria.

Esegui: PYTHONUTF8=1 python tests/perf/test_perf_budget.py   (oppure pytest tests/perf)

Ogni misura gira in un processo figlio (`--startup` / `--build`): le import di FastAPI e i residui di
una misura non sporcano la successiva. Nessuna rete: i DAT libretro stanno gia' in cache e le socket
(non di loopback) e i trasporti httpx sollevano `Offline`, che e' una BaseException perche' i
sorgenti ingoiano `Exception`: una richiesta fatta per sbaglio fa fallire il test invece di sparire.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Misure ripetute qui (Windows 11, Python 3.13, disco OneDrive, 201 rom da 1 KB su 3 console, DAT
# libretro gia' in cache, nessuna rete): avvio 4,1 s e 32 MB di picco Python, libreria 2,5 s e 19 MB.
# Picco da tracemalloc, import dei moduli compresi nella misura (nella libreria e' compreso l'import
# di pozzo.library.build). Le soglie sono circa il triplo del tempo e il doppio della RAM, per non
# fallire su una macchina o un runner piu' lento; l'RSS si stampa soltanto.
BUDGET = {
    "startup_seconds": 12.0,
    "startup_peak_mb": 70.0,
    "build_seconds": 8.0,
    "build_peak_mb": 40.0,
    "timeout_seconds": 180,  # oltre: il figlio viene ucciso e il test fallisce
}
GAMES = 201  # divisibile per il numero di console della fixture

SYSTEMS = {"nes": ("Nintendo - Nintendo Entertainment System", "nes"),
           "snes": ("Nintendo - Super Nintendo Entertainment System", "sfc"),
           "gba": ("Nintendo - Game Boy Advance", "gba")}


class Offline(BaseException):
    """Rete nei test di performance: BaseException perche' i sorgenti ingoiano Exception."""


_connect = socket.socket.connect
LOOPBACK = ("127.0.0.1", "::1", "localhost")


def _blocked(*a, **k):
    raise Offline("rete usata nel test di performance")


def _no_network(self, address, *a, **k):
    # su Windows asyncio crea il proprio event loop con una socketpair via 127.0.0.1: quella passa
    if isinstance(address, tuple) and address[0] in LOOPBACK:
        return _connect(self, address, *a, **k)
    raise Offline(f"rete usata nel test di performance: {address}")


def _offline() -> None:
    """Blocca la rete. Due punti: le socket sincrone (urllib) e i trasporti httpx (asincroni, su
    Windows non passano da socket.socket.connect)."""
    import httpx
    socket.socket.connect = _no_network
    httpx.AsyncHTTPTransport.handle_async_request = _blocked
    httpx.HTTPTransport.handle_request = _blocked


def _rss_mb():
    import psutil
    return psutil.Process().memory_info().rss / 2**20


def _library() -> Path:
    """Cartella di lavoro: rom finte + cache con i DAT libretro (senza, il primo giro andrebbe in rete)."""
    from pozzo.sources.libretro import MAIN_DIRS, META_DIRS

    base = Path(tempfile.mkdtemp(prefix="pozzo-perf-"))
    (base / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n',
                                      encoding="utf-8")
    dat = 'clrmamepro (\n\tname "perf"\n)\n\ngame (\n\tname "{pid}"\n\trom ( name "{pid}.{ext}" size 1024 crc DEADBEEF )\n)\n'
    for pid, (system, ext) in SYSTEMS.items():
        for rel in (*MAIN_DIRS, *(f"metadat/{d}" for d in META_DIRS)):
            f = base / "cache" / "libretro" / rel / f"{system}.dat"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(dat.format(pid=pid, ext=ext), encoding="utf-8")
        console = base / "roms" / pid
        console.mkdir(parents=True)
        for i in range(GAMES // len(SYSTEMS)):
            (console / f"Gioco {pid} {i}.{ext}").write_bytes(b"0" * 1024)
    return base


def _measure(kind: str, base: Path) -> dict:
    """Lavoro del processo figlio: una sola operazione, con tempo, picco tracemalloc e RSS."""
    from pozzo import config

    _offline()
    cfg = config.load(base / "config.toml")
    tracemalloc.start()
    rss = _rss_mb()
    t0 = time.perf_counter()
    if kind == "startup":
        from pozzo.app.server import create_app
        create_app(cfg)
    else:
        from pozzo.library.build import build
        build(cfg, log=lambda m: None)
    secs = time.perf_counter() - t0
    peak = tracemalloc.get_traced_memory()[1] / 2**20
    tracemalloc.stop()
    return {"secs": round(secs, 2), "peak_mb": round(peak, 1), "rss_mb": round(_rss_mb() - rss, 1)}


CASES = {"startup": ("startup_seconds", "startup_peak_mb"), "build": ("build_seconds", "build_peak_mb")}


def _check(kind: str) -> None:
    base = _library()
    try:
        out = subprocess.run([sys.executable, str(Path(__file__).resolve()), f"--{kind}", str(base)],
                             capture_output=True, text=True, encoding="utf-8",
                             env={**os.environ, "PYTHONUTF8": "1"}, timeout=BUDGET["timeout_seconds"])
    except subprocess.TimeoutExpired:
        raise AssertionError(f"{kind}: oltre {BUDGET['timeout_seconds']} s, processo fermo")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    assert out.returncode == 0, f"{kind} fallito:\n{out.stdout[-1000:]}\n{out.stderr[-2000:]}"
    m = json.loads(out.stdout.strip().splitlines()[-1])
    secs_key, peak_key = CASES[kind]
    assert m["secs"] <= BUDGET[secs_key], f"{kind}: {m['secs']} s oltre il budget di {BUDGET[secs_key]} s"
    assert m["peak_mb"] <= BUDGET[peak_key], \
        f"{kind}: {m['peak_mb']} MB di picco oltre il budget di {BUDGET[peak_key]} MB"
    print(f"ok  {kind}: {m['secs']} s (max {BUDGET[secs_key]}), picco {m['peak_mb']} MB "
          f"(max {BUDGET[peak_key]}), RSS {m['rss_mb']} MB")


def test_startup() -> None:
    _check("startup")


def test_build() -> None:
    _check("build")


if __name__ == "__main__":
    if len(sys.argv) > 2:  # processo figlio
        print(json.dumps(_measure(sys.argv[1].lstrip("-"), Path(sys.argv[2]))))
    else:
        for kind in CASES:
            _check(kind)
        print("ok  avvio e costruzione della libreria dentro il budget di tempo e RAM")
