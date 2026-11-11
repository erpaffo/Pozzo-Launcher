"""Spazio e cestino degli strumenti: rifiuto prima di scrivere, mai cancellazione definitiva."""
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.tools import space, trash

tmp = Path(tempfile.mkdtemp())
try:
    # spazio: stima enorme -> NoSpace con messaggio; stima piccola -> ok
    space.check(1, tmp)
    try:
        space.check(10**18, tmp)
        raise SystemExit("doveva rifiutare")
    except space.NoSpace as e:
        assert "servono" in str(e) and "liberi" in str(e)
    # cartella destinazione non ancora creata: si guarda il primo genitore esistente
    space.check(1, tmp / "nuova" / "sotto")
    # stesso volume per due cartelle: fabbisogno sommato
    free = shutil.disk_usage(tmp).free
    est = free // 2
    try:
        space.check(est, tmp, tmp / "x")
        raise SystemExit("due cartelle sullo stesso volume vanno sommate")
    except space.NoSpace:
        pass

    d = tmp / "Gioco"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 10)
    assert space.tree_size(d) == 10

    # cestino: senza cestino di sistema finisce in .pozzo-trash, il file esiste ancora
    with mock.patch.object(trash, "_fixed_drive", return_value=False), \
         mock.patch.object(trash.Path, "anchor", new_callable=mock.PropertyMock, return_value=str(tmp)):
        dest = trash.to_trash(d)
    assert not d.exists() and (Path(dest) / "a.bin").read_bytes() == b"x" * 10
    try:
        trash.to_trash(tmp / "non-esiste")
        raise SystemExit("doveva fallire")
    except FileNotFoundError:
        pass
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok")
