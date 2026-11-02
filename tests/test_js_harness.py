"""Esegue con node gli harness JS senza un proprio script Python (onboarding, suggerimenti, palette)."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if not node:
    print("-- node non trovato: test saltato")
    sys.exit(0)
for name in ("test_onboarding.js", "test_hints.js", "test_palette.js"):
    # stdin chiuso: con stdin ereditato node resta appeso su alcuni runner (macOS della CI)
    r = subprocess.run([node, str(ROOT / "tests" / name)], capture_output=True, text=True, encoding="utf-8",
                       timeout=60, stdin=subprocess.DEVNULL)
    print(r.stdout + r.stderr)
    assert r.returncode == 0, f"{name} fallito"
