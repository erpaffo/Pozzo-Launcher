"""backup(): se dimensione e mtime combaciano con l'ultima copia fatta da questo PC il file non si rilegge; un file
cambiato (stessa dimensione ma mtime nuovo, o dimensione nuova) viene copiato; mapping.yaml non si riparsa se non cambia."""

import os
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo.library import saves as SV  # noqa: E402

KEY = "pc/skiphash"


def _old(f: Path, age: int = 100):
    """mtime vecchio: quelli recentissimi non si considerano fidabili."""
    t = os.stat(f).st_mtime - age
    os.utime(f, (t, t))


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cfg = config.Config(cache=t / "cache")
        saves = t / "Gioco" / "Saves"
        saves.mkdir(parents=True)
        a, b = saves / "a.sav", saves / "b.sav"
        a.write_bytes(b"aaaa")
        b.write_bytes(b"bbbb")
        _old(a)
        _old(b)
        first = SV.backup(cfg, KEY, "Gioco", [saves])

        calls = []
        real = SV._sha1
        SV._sha1 = lambda f: (calls.append(Path(f).name), real(f))[1]
        parsed = []
        import yaml
        real_load = yaml.load
        yaml.load = lambda *x, **k: (parsed.append(1), real_load(*x, **k))[1]
        try:
            SV._MAPS.clear()
            # cartella invariata: stessa copia, nessun hash
            assert SV.backup(cfg, KEY, "Gioco", [saves]) == first and not calls, calls
            assert len(parsed) <= 1, f"mapping.yaml riparsato {len(parsed)} volte"

            # stessa dimensione, mtime nuovo e contenuto diverso: copia nuova
            time.sleep(1.1)  # le copie si ordinano per secondo
            a.write_bytes(b"AAAA")
            _old(a, 50)
            second = SV.backup(cfg, KEY, "Gioco", [saves])
            assert second != first and "a.sav" in calls, (second, calls)

            # stessa dimensione e stesso contenuto ma mtime nuovo: si controlla l'hash, nessun doppione
            calls.clear()
            _old(b, 10)
            assert SV.backup(cfg, KEY, "Gioco", [saves]) == second and "b.sav" in calls, calls

            # dimensione nuova
            time.sleep(1.1)
            b.write_bytes(b"bbbbbb")
            _old(b, 100)
            third = SV.backup(cfg, KEY, "Gioco", [saves])
            assert third not in (first, second)

            # ripristino: i file riscritti hanno mtime nuovo, quindi si riverificano (e il contenuto e' quello giusto)
            SV.restore(cfg, KEY, first.name, roots=[saves])
            assert a.read_bytes() == b"aaaa"
            calls.clear()
            SV.backup(cfg, KEY, "Gioco", [saves])
            assert "a.sav" in calls, calls
        finally:
            SV._sha1 = real
            yaml.load = real_load
    print("ok  backup senza rileggere i file invariati")


if __name__ == "__main__":
    main()
