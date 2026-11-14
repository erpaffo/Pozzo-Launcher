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
         mock.patch.object(trash, "_posix_trash", return_value=False), \
         mock.patch.object(trash.Path, "anchor", new_callable=mock.PropertyMock, return_value=str(tmp)), \
         mock.patch.object(trash.Path, "home", return_value=tmp / "home"):
        dest = trash.to_trash(d)
    assert not d.exists() and (Path(dest) / "a.bin").read_bytes() == b"x" * 10
    assert Path(dest).parent == tmp / "home" / ".pozzo-trash"
    try:
        trash.to_trash(tmp / "non-esiste")
        raise SystemExit("doveva fallire")
    except FileNotFoundError:
        pass
    # fuori Windows: Finder (macOS) e gio (Linux) ricevono il percorso come argomento, senza shell
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return mock.Mock(returncode=0)

    f = tmp / 'Gioco "beta"\\x'
    f.mkdir()
    with mock.patch.object(trash.sys, "platform", "darwin"), \
         mock.patch.object(trash.subprocess, "run", side_effect=fake_run), \
         mock.patch.object(trash.Path, "exists", return_value=False):
        assert trash._posix_trash(f) is True
    script = calls[-1][-1]
    assert calls[-1][:3] == ["osascript", "-e", script]
    assert script == 'tell application "Finder" to delete POSIX file "' + str(f).replace("\\", "\\\\").replace('"', '\\"') + '"'

    with mock.patch.object(trash.sys, "platform", "linux"), \
         mock.patch.object(trash.shutil, "which", return_value="/usr/bin/gio"), \
         mock.patch.object(trash.subprocess, "run", side_effect=fake_run), \
         mock.patch.object(trash.Path, "exists", return_value=False):
        assert trash._posix_trash(f) is True
    assert calls[-1] == ["gio", "trash", str(f)]

    # gio assente: nessun comando lanciato, e to_trash ricade su ~/.pozzo-trash
    n = len(calls)
    g = tmp / "altro"
    g.mkdir()
    (g / "b.bin").write_bytes(b"y")
    with mock.patch.object(trash.sys, "platform", "linux"), \
         mock.patch.object(trash.shutil, "which", return_value=None), \
         mock.patch.object(trash.subprocess, "run", side_effect=fake_run), \
         mock.patch.object(trash, "_fixed_drive", return_value=False), \
         mock.patch.object(trash.Path, "home", return_value=tmp / "home"):
        dest = trash.to_trash(g)
    assert len(calls) == n and Path(dest).parent == tmp / "home" / ".pozzo-trash"
    assert (Path(dest) / "b.bin").read_bytes() == b"y"

    # win32: il comando del Cestino e' invariato (powershell, nessun osascript/gio)
    h = tmp / "win"
    h.mkdir()
    with mock.patch.object(trash.sys, "platform", "win32"), \
         mock.patch.object(trash, "_fixed_drive", return_value=True), \
         mock.patch.object(trash, "_win_recycle", return_value=True) as rec:
        assert trash.to_trash(h) == "cestino"
    rec.assert_called_once()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok")
