# Eglantine non deve condividere i dati di Eden: «user» accanto all'eseguibile lo mette in modalita' portatile.
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.library import launcher as L
from pozzo.emuadapters import eden

with tempfile.TemporaryDirectory() as d:
    exe = Path(d) / "eglantine.exe"
    exe.touch()
    L.isolate_eglantine(exe)
    if sys.platform == "darwin":
        assert not (Path(d) / "user").exists()
    else:
        assert (Path(d) / "user").is_dir() and eden._base(exe) == Path(d) / "user"
    assert eden._base(None) != Path(d) / "user"
print("ok eglantine isolato")
