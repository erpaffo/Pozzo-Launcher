"""Collegamento sul desktop fuori da Windows: .command (macOS) e .desktop (Linux).

Esegui: PYTHONUTF8=1 python tests/test_shortcut_posix.py
"""
import shlex
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.library import shortcut as SC

REAL = sys.platform

with tempfile.TemporaryDirectory() as t:
    SC.desktop_dir = lambda: Path(t) / "Desktop"
    base = '"/opt/Pozzo Launcher/pozzo-cli" -c "/x/c.toml"'
    for plat, ext in (("darwin", ".command"), ("linux", ".desktop")):
        sys.platform = plat
        p = SC.create('Gioco: "A"/B', base, "/opt/Pozzo Launcher", "k$1", "/x/i.png")
        assert p.name == f"Gioco AB{ext}" and (REAL == "win32" or p.stat().st_mode & stat.S_IXUSR)  # chmod +x non esiste su Windows
        txt = p.read_text(encoding="utf-8")
        assert "play --key" in txt and "pozzo-cli" in txt
        if plat == "darwin":
            assert txt.startswith("#!/bin/sh") and shlex.split(txt.splitlines()[2])[-1] == "k$1"
        else:
            assert "Type=Application" in txt and "Icon=/x/i.png" in txt and 'Exec=sh -c "' in txt
sys.platform = "darwin"
print("ok")
