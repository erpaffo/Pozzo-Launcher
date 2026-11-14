"""Radici salvataggi fuori da Windows e cartella temporanea archive-run."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.library import archiverun, saves

H = Path.home()
if sys.platform != "win32":
    saves.sys = types.SimpleNamespace(platform="darwin")
    assert saves.user_roots()[0] == H / "Library" / "Application Support" and H / "Documents" in saves.user_roots()
    saves.sys = types.SimpleNamespace(platform="linux")
    assert H / ".config" in saves.user_roots() or saves.user_roots()[1].name
    archiverun.sys = types.SimpleNamespace(platform="linux")
    import os
    os.environ.pop("LOCALAPPDATA", None)
    assert archiverun.temp_root(types.SimpleNamespace(app={}, cache="/c")).parts[-2:] == ("Pozzo", "run")
print("ok")
