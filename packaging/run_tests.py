"""Esegue i test (tests/test_*.py e tests/catalog) uno per uno, con un limite di tempo per ognuno.

Serve alla CI: un test bloccato (per esempio una chiamata di rete che non risponde) faceva restare il
job appeso per sempre, senza dire dove. Qui ogni script e' un processo a se': se supera il limite gli si
chiede un dump dei thread (SIGABRT + faulthandler) e poi viene terminato, cosi' il log dice dove si e'
fermato. Uso: python packaging/run_tests.py [nome_test.py ...]
"""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import time
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


def run(name: str, timeout: float) -> bool:
    path = ROOT / "tests" / name
    if not path.is_file():
        print(f"!! {name}: file mancante", flush=True)
        return False
    print(f"\n=== {name}", flush=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
    start = time.time()
    text = path.read_text(encoding="utf-8", errors="replace")
    cmd = [sys.executable, "-X", "faulthandler"]
    cmd += ["-m", "pytest", "-q", str(path)] if NEEDS_PYTEST.search(text) else [str(path)]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"!! {name}: fermo da piu' di {timeout:.0f} s, dump dei thread e interruzione", flush=True)
        if os.name == "posix":
            proc.send_signal(signal.SIGABRT)  # faulthandler stampa dove sono ferme le pile
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        return False
    took = time.time() - start
    print(f"--- {name}: {'ok' if code == 0 else 'FALLITO'} in {took:.1f} s", flush=True)
    return code == 0


def main(argv: list[str]) -> int:
    wanted = argv or discover()
    timeout = limit()
    failed = [name for name in wanted if not run(name, timeout)]
    print(flush=True)
    if failed:
        print(f"TEST DA SISTEMARE ({len(failed)}): " + ", ".join(failed), flush=True)
        return 1
    print(f"TUTTI I TEST OK ({len(wanted)} script)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
