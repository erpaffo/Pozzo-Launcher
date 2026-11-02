"""Esegue l'harness Node di gusto, ordine di gioco, consigli e classifica ROM (DOM e fetch finti, nessuna rete)."""

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
for f in (STATIC / "taste.js", STATIC / "franchise.js", STATIC / "recommend.js", ROOT / "tests" / "test_reco_ui.js"):
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
r = subprocess.run([node, str(ROOT / "tests" / "test_reco_ui.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
print(r.stdout + r.stderr)
assert r.returncode == 0, "harness fallito"