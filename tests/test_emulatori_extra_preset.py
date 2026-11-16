# Emulatori in piu' (OpenEmu, mGBA, Mesen...): coda dei candidati, argomenti e riconoscimento dell'eseguibile.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.library import launcher as L

assert L.PRESETS["nes"][0] == ("retroarch", "mesen"), "il preferito di prima non cambia"
for emu, pid in [("openemu", "saturn"), ("mgba", "gba"), ("mesen", "nes"), ("rmg", "n64"), ("dosbox-staging", "dos")]:
    assert (emu, None) in L.PRESETS[pid], (emu, pid)
    assert L.STANDALONE_ARGS[emu] == ["{rom}"] and L.KNOWN_EXES[emu]
assert all(L.PRESETS[p] for p in L.PRESETS)
print("ok emulatori extra")
