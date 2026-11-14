import plistlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.library import launcher as L


def _app(root, name, exe, plist=True):
    m = root / f"{name}.app" / "Contents" / "MacOS"
    m.mkdir(parents=True)
    (m / exe).write_text("x")
    if plist:
        with open(root / f"{name}.app" / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleExecutable": exe}, f)


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    _app(d, "Dolphin", "Dolphin")
    _app(d, "PCSX2-v2", "PCSX2")
    _app(d, "RetroArch", "RetroArch", plist=False)
    _app(d, "Safari", "Safari")
    assert L.match_app(d / "Dolphin.app") is None or L.match_app(d / "Dolphin.app")[0] == "dolphin"
    assert L.match_app(d / "Safari.app") is None
    if sys.platform == "darwin":
        r = L.detect_emulators(d)
        assert r["dolphin"].endswith("Dolphin.app/Contents/MacOS/Dolphin"), r
        assert r["pcsx2"].endswith("PCSX2-v2.app/Contents/MacOS/PCSX2"), r
        assert r["retroarch"].endswith("RetroArch.app/Contents/MacOS/RetroArch"), r
        assert "safari" not in r
print("ok")
