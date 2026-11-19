"""Esegue con Node i test della pagina del telefono: tocchi sullo schermo DS (rotazione, proporzioni) e link incollati."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if not node:
    print("-- node non trovato: test saltato")
    sys.exit(0)
r = subprocess.run([node, "--check", str(ROOT / "pozzo" / "app" / "static" / "m" / "m.js")], capture_output=True, text=True,
                   encoding="utf-8", stdin=subprocess.DEVNULL)
assert r.returncode == 0, r.stderr
for name in ("test_phone_ds_touch.js", "test_phone_paste_ui.js"):
    r = subprocess.run([node, str(ROOT / "tests" / name)], capture_output=True, text=True, encoding="utf-8",
                       timeout=60, stdin=subprocess.DEVNULL)
    print(r.stdout + r.stderr)
    assert r.returncode == 0, f"{name} fallito"
