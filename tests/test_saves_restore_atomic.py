"""restore(): una copia danneggiata non deve lasciare i salvataggi a meta' (si legge tutto prima di toccare il disco)."""

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo.library import saves as SV  # noqa: E402

KEY = "pc/atomic"


def setup(root: Path):
    """cfg finto + cartella salvataggi con una copia fatta sulla cartella (cosi' restore gestisce gli «extra»)."""
    (root / "cache").mkdir()
    cfg = config.Config(cache=root / "cache", output=root / "out")
    sd = root / "saves" / "Game1"
    sd.mkdir(parents=True)
    (sd / "slot1.sav").write_bytes(b"vecchio")
    out = SV.backup(cfg, KEY, "Game1", [sd], "manuale")
    assert out is not None
    return cfg, sd, out


def test_restore_corrupt_backup_leaves_disk_untouched():
    with tempfile.TemporaryDirectory() as t:
        cfg, sd, out = setup(Path(t))
        (sd / "slot1.sav").write_bytes(b"nuovo")
        (sd / "extra.sav").write_bytes(b"x")
        if out.is_dir():  # copia come cartella: si toglie il file
            hit = [f for f in out.rglob("slot1.sav")]
            assert hit, list(out.rglob("*"))
            for f in hit:
                f.unlink()
        else:  # zip: lo si riscrive senza l'entry di slot1.sav
            with zipfile.ZipFile(out) as z:
                keep = {n: z.read(n) for n in z.namelist() if not n.endswith("slot1.sav")}
            with zipfile.ZipFile(out, "w") as z:
                for n, data in keep.items():
                    z.writestr(n, data)
        try:
            SV.restore(cfg, KEY, out.name)
        except Exception:
            pass
        else:
            assert False, "restore doveva fallire su una copia danneggiata"
        assert (sd / "slot1.sav").read_bytes() == b"nuovo", "il file non va toccato"
        assert (sd / "extra.sav").exists(), "il file extra non va cancellato"


def test_restore_ok_rolls_back_and_removes_extra():
    with tempfile.TemporaryDirectory() as t:
        cfg, sd, out = setup(Path(t))
        (sd / "slot1.sav").write_bytes(b"nuovo")
        (sd / "extra.sav").write_bytes(b"x")
        r = SV.restore(cfg, KEY, out.name)
        assert (sd / "slot1.sav").read_bytes() == b"vecchio"
        assert not (sd / "extra.sav").exists()
        assert r["removed"] == 1 and r["written"] == 1, r


if __name__ == "__main__":
    test_restore_corrupt_backup_leaves_disk_untouched()
    test_restore_ok_rolls_back_and_removes_extra()
    print("OK")
