"""Compressione APFS via ditto (solo macOS)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.library import wof

if sys.platform != "darwin":
    print("skip")
    sys.exit(0)
with tempfile.TemporaryDirectory() as t:
    d = Path(t) / "g"
    (d / "sub").mkdir(parents=True)
    (d / "a.txt").write_text("ciao " * 50000)
    (d / "sub" / "b.txt").write_text("x" * 200000)
    wof.mac_rewrite(d)
    assert (d / "a.txt").read_text() == "ciao " * 50000 and (d / "sub" / "b.txt").read_text() == "x" * 200000
    assert wof.mac_compressed(d)
    wof.mac_rewrite(d, True)
    assert not wof.mac_compressed(d) and (d / "a.txt").read_text() == "ciao " * 50000
    assert sorted(p.name for p in Path(t).iterdir()) == ["g"]
print("ok")
