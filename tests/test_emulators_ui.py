"""Esegue l'harness Node di emulatori-extra.js (DOM e fetch finti, nessuna rete)."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "pozzo" / "app" / "static" / "settings" / "emulatori-extra.js"
node = shutil.which("node")
if not node:
    print("-- node non trovato: test saltato")
    sys.exit(0)
for f in (JS, ROOT / "tests" / "test_emulators_ui.js"):
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
r = subprocess.run([node, str(ROOT / "tests" / "test_emulators_ui.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
print(r.stdout + r.stderr)
assert r.returncode == 0, "harness fallito"