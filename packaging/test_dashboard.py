"""Esegue tutta la suite come la CI (3 parti per sistema) su questo PC (Windows/macOS/Linux) e su Linux in Docker,
tutto in parallelo, con una barra di avanzamento per sistema.

Uso: python -m pozzo test [--no-docker] [--no-local]
Per ogni parte (shard) il log completo e' in una cartella temporanea, indicata alla fine.
Esce con 1 se qualche test e' fallito.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_tests  # noqa: E402

ROOT = run_tests.ROOT
SHARDS = 3
SUMMARY = re.compile(r"(\d+) (passed|failed|skipped|error|errors)\b.* in [\d.]+s")
SINGLE = re.compile(r"(\d+) (passed|failed|skipped|errors?)")
RESET, GREEN, RED, YELLOW, DIM = "\033[0m", "\033[32m", "\033[31m", "\033[33m", "\033[2m"

DOCKER_SCRIPT = (
    "echo '@@ copio i sorgenti nel container'; "
    "cp -r /src /work && cd /work && find . -name '*.py' -not -path './.git/*' -exec sed -i 's/\\r$//' {{}} + ; "
    "echo '@@ apt-get: installo librerie di sistema (libegl1, libnss3)'; "
    "(apt-get update -qq && apt-get install -y -qq libegl1 libnss3 >/dev/null) 2>&1 | tail -n 1; "
    "echo '@@ pip: installo le dipendenze Python'; "
    "pip install -q -r requirements.txt -r requirements-dev.txt 2>&1 | tail -n 3; "
    "echo '@@ avvio dei test'; PYTHONUTF8=1 python packaging/run_tests.py --shard {k}/{n}"
)


class Shard:
    def __init__(self, group: str, k: int, total: int, cmd: list[str], logdir: Path):
        self.group, self.k, self.total, self.cmd = group, k, total, cmd
        self.done = self.failed = 0
        self.passed = self.skipped = self.nfailed = 0
        self.current = "docker: avvio il container (la prima volta scarica python:3.12)" if group.startswith("Linux") else "avvio..."
        self.failed_names: list[str] = []
        self.finished = False
        self.code: int | None = None
        self.log = (logdir / f"{group.split()[0].lower()}-{k}.log").open("w", encoding="utf-8")

    def feed(self, line: str) -> None:
        self.log.write(line + "\n")
        self.last = line.strip() or getattr(self, "last", "")  # ultima riga non vuota: la causa se il processo muore subito
        if line.startswith("@@ "):  # passo di preparazione del container
            self.current = line[3:]
        elif m := re.match(r"=== (\S+)", line):
            self.current = m.group(1)
        elif m := re.match(r"--- (\S+): (ok|FALLITO)", line):
            self.done += 1
            if m.group(2) == "FALLITO":
                self.failed += 1
                self.failed_names.append(m.group(1).rstrip(":"))
        elif m := re.match(r"!! (\S+): (fermo|file mancante)", line):
            self.failed_names.append(m.group(1).rstrip(":") + " (bloccato)")
        elif SUMMARY.search(line) and "passed" in line + "failed" + "skipped":
            for n, kind in SINGLE.findall(line):
                if kind == "passed":
                    self.passed += int(n)
                elif kind == "skipped":
                    self.skipped += int(n)
                else:
                    self.nfailed += int(n)

    def run(self) -> None:
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"}
        try:
            p = subprocess.Popen(self.cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace")
            for line in p.stdout:  # type: ignore[union-attr]
                self.feed(line.rstrip())
            self.code = p.wait()
        except OSError as e:  # es. docker non installato: senza questo il thread muore e il ciclo non finisce mai
            self.feed(f"impossibile avviare '{self.cmd[0]}': {e.strerror or e}")
            self.code = 127
        finally:
            self.finished = True
            self.log.close()


def count_scripts() -> list[int]:
    names = run_tests.discover()
    return [len(names[k - 1 :: SHARDS]) for k in range(1, SHARDS + 1)]


def bar(done: int, total: int, width: int = 30) -> str:
    n = width * done // max(total, 1)
    return "█" * n + "░" * (width - n)


def render(groups: dict[str, list[Shard]], start: float) -> str:
    out = [f"Test Pozzo - {time.time() - start:.0f} s\n"]
    for name, shards in groups.items():
        done, total = sum(s.done for s in shards), sum(s.total for s in shards)
        p, f, sk = (sum(s.passed for s in shards), sum(s.nfailed for s in shards) + sum(s.failed for s in shards),
                    sum(s.skipped for s in shards))
        colour = RED if f else GREEN if done == total else YELLOW
        out.append(f"{name:<14}{colour}{bar(done, total)}{RESET} {100 * done // max(total, 1):>3}%  "
                   f"script {done}/{total}  {GREEN}passati {p}{RESET}  {RED}falliti {f}{RESET}  {YELLOW}saltati {sk}{RESET}")
        for s in shards:
            state = "finito" if s.finished else s.current
            out.append(f"  {DIM}parte {s.k}/{SHARDS}: {s.done}/{s.total}  {state}{RESET}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-docker", action="store_true")
    ap.add_argument("--no-local", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  # la barra usa █ ░, non in cp1252
    subprocess.run("", shell=True)  # abilita i colori ANSI nel terminale di Windows
    totals = count_scripts()
    logdir = Path(tempfile.mkdtemp(prefix="pozzo-test-"))
    local = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux (locale)")
    groups: dict[str, list[Shard]] = {}
    if not args.no_local:
        groups[local] = [Shard(local, k, totals[k - 1], [sys.executable, str(ROOT / "packaging" / "run_tests.py"),
                         "--shard", f"{k}/{SHARDS}"], logdir) for k in range(1, SHARDS + 1)]
    if not args.no_docker:
        groups["Linux (Docker)"] = [Shard("Linux", k, totals[k - 1], ["docker", "run", "--rm", "-v", f"{ROOT}:/src:ro",
                                    "python:3.12", "bash", "-c", DOCKER_SCRIPT.format(k=k, n=SHARDS)], logdir)
                                    for k in range(1, SHARDS + 1)]
    shards = [s for g in groups.values() for s in g]
    threads = [threading.Thread(target=s.run, daemon=True) for s in shards]
    start = time.time()
    for t in threads:
        t.start()
    lines = 0
    while True:
        text = render(groups, start)
        print((f"\033[{lines}F\033[J" if lines else "") + text, flush=True)
        lines = text.count("\n") + 1
        if all(s.finished for s in shards):
            break
        time.sleep(0.5)
    bad = False
    for name, g in groups.items():
        for s in g:
            if s.code != 0 or s.failed_names:
                bad = True
                print(f"{RED}{name} parte {s.k}: {', '.join(s.failed_names) or getattr(s, 'last', 'errore (vedi log)')}{RESET}")
    print(f"\nLog completi: {logdir}")
    print(f"{RED}CI ROSSA{RESET}" if bad else f"{GREEN}TUTTO VERDE{RESET}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
