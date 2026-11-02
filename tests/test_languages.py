"""Verifica il parser delle lingue dei giochi usando Node.js."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")
if node:
    result = subprocess.run(
        [node, str(ROOT / "tests" / "test_languages.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        stdin=subprocess.DEVNULL,
    )
    print(result.stdout + result.stderr)
    assert result.returncode == 0, "test_languages.js fallito"
else:
    print("-- node non trovato: test saltato")
