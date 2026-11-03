"""Esegue l'harness Node di detail-emucfg.js e del selettore per console (DOM e fetch finti, nessuna rete)."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "pozzo" / "app" / "static"
node = shutil.which("node")
if not node:
    print("-- node non trovato: test saltato")
    sys.exit(0)
for f in (STATIC / "js" / "detail-emucfg.js", STATIC / "settings" / "emulatori-extra.js", ROOT / "tests" / "test_emucfg_ui.js"):
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
r = subprocess.run([node, str(ROOT / "tests" / "test_emucfg_ui.js")], capture_output=True, text=True, encoding="utf-8",
                   timeout=60, stdin=subprocess.DEVNULL)
print(r.stdout + r.stderr)
assert r.returncode == 0, "harness fallito"
