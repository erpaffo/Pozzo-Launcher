"""Esegue con node i tests/*.js che nessun altro test Python lancia (quelli di test_js_harness.py & co. sono esclusi)."""
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def orphans() -> list[Path]:
    py = "\n".join(p.read_text(encoding="utf-8") for p in TESTS.glob("test_*.py") if p.name != Path(__file__).name)
    return sorted(p for p in [*TESTS.glob("test_*.js"), *TESTS.glob("test_*.mjs")] if p.name not in py)


def run(js: Path):
    r = subprocess.run(["node", str(js)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    return js.name, r.returncode, (r.stdout + r.stderr)[-1500:]


def main() -> int:
    if not shutil.which("node"):
        print("SKIP test_js_ci: node non e' nel PATH")
        return 0
    files = orphans()
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(run, files))
    bad = [r for r in res if r[1] != 0]
    for name, code, out in bad:
        print(f"FAIL {name} (exit {code})\n{out}\n")
    print(f"{len(res) - len(bad)}/{len(res)} test JS ok")
    return 1 if bad else 0


def test_js_orphans():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
