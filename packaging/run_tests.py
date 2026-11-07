"""Esegue i test (tests/test_*.py e tests/catalog) uno per uno, con un limite di tempo per ognuno.

Serve alla CI: un test bloccato (per esempio una chiamata di rete che non risponde) faceva restare il
job appeso per sempre, senza dire dove. Qui ogni script e' un processo a se': se supera il limite gli si
chiede un dump dei thread (SIGABRT + faulthandler) e poi viene terminato, cosi' il log dice dove si e'
fermato. Uso: python packaging/run_tests.py [--shard K/N] [-j N] [nome_test.py ...]
(--shard: solo la K-esima di N parti, per dividere la suite su piu' job della CI)
(-j N: N script in parallelo sulla stessa macchina, 0 = un processo per core; l'output di ogni script
esce tutto insieme alla fine. Default 1 = in sequenza, con output in diretta)
"""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# directory con dipendenze extra (playwright...): saltate se mancano, senza far fallire la CI
OPTIONAL = {"e2e": "playwright"}
NEEDS_PYTEST = re.compile(r"^\s*(import pytest|from pytest)|@pytest\.|^(async )?def test_\w+\(\s*\w", re.M)


def discover() -> list[str]:
    tests = sorted(p.relative_to(ROOT / "tests").as_posix() for p in (ROOT / "tests").glob("test_*.py"))
    tests += sorted(p.relative_to(ROOT / "tests").as_posix() for p in (ROOT / "tests" / "catalog").glob("test_*.py"))
    for sub, mod in OPTIONAL.items():
        found = sorted(p.relative_to(ROOT / "tests").as_posix() for p in (ROOT / "tests" / sub).glob("test_*.py"))
        if found and importlib.util.find_spec(mod):
            tests += found
        elif found:
            print(f"-- tests/{sub}: saltati ({mod} non installato)", flush=True)
    return tests


def limit() -> float:
    try:
        return float(os.environ.get("POZZO_TEST_TIMEOUT", "180"))
    except ValueError:
        return 180.0


def run(name: str, timeout: float, capture: bool = False) -> bool:
    path = ROOT / "tests" / name
    if not path.is_file():
        print(f"!! {name}: file mancante", flush=True)
        return False
    out: list[str] = [f"\n=== {name}"]  # in parallelo si stampa tutto insieme, per non mescolare i log
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "POZZO_NO_SAMPLE": "1"}
    start = time.time()
    text = path.read_text(encoding="utf-8", errors="replace")
    cmd = [sys.executable, "-X", "faulthandler"]
    cmd += ["-m", "pytest", "-q", str(path)] if NEEDS_PYTEST.search(text) else [str(path)]
    pipe = subprocess.PIPE if capture else None
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=pipe, stderr=subprocess.STDOUT if capture else None,
                            text=True, encoding="utf-8", errors="replace")
    ok, text_out = False, ""
    try:
        text_out, _ = proc.communicate(timeout=timeout)
        ok = proc.returncode == 0
        out.append(f"--- {name}: {'ok' if ok else 'FALLITO'} in {time.time() - start:.1f} s")
    except subprocess.TimeoutExpired:
        out.append(f"!! {name}: fermo da piu' di {timeout:.0f} s, dump dei thread e interruzione")
        if os.name == "posix":
            proc.send_signal(signal.SIGABRT)  # faulthandler stampa dove sono ferme le pile
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            proc.kill()
        text_out, _ = proc.communicate()
    if capture and text_out:
        out.insert(1, text_out.rstrip())
    print("\n".join(out), flush=True)
    return ok


def main(argv: list[str]) -> int:
    shard = None
    if argv[:1] == ["--shard"]:
        k, n = (int(x) for x in argv[1].split("/"))
        shard, argv = (k, n), argv[2:]
    jobs = 1
    if argv[:1] == ["-j"]:
        jobs, argv = int(argv[1]) or os.cpu_count() or 1, argv[2:]
    wanted = argv or discover()
    if shard:  # a turno, cosi' i test pesanti (e2e) si distribuiscono
        wanted = wanted[shard[0] - 1 :: shard[1]]
    timeout = limit()
    if jobs > 1:
        with ThreadPoolExecutor(jobs) as pool:
            results = list(pool.map(lambda n: run(n, timeout, capture=True), wanted))
    else:
        results = [run(n, timeout) for n in wanted]
    failed = [n for n, ok in zip(wanted, results) if not ok]
    print(flush=True)
    if failed:
        print(f"TEST DA SISTEMARE ({len(failed)}): " + ", ".join(failed), flush=True)
        return 1
    print(f"TUTTI I TEST OK ({len(wanted)} script)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
