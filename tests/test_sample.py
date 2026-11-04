"""Gioco d'esempio: estrazione e voce in libreria una sola volta. Nessun eseguibile avviato."""
import zipfile
from types import SimpleNamespace

from pozzo import sample


class Cfg(SimpleNamespace):
    def __init__(self):
        super().__init__(app={}, cache=None)


def _zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("chocolate-doom.exe", b"MZ")
        z.writestr("freedoom1.wad", b"IWAD")
        z.writestr("../evasione.txt", b"no")  # percorso fuori cartella: non deve uscire


def test_primo_avvio_estrae_e_aggiunge_una_volta(tmp_path, monkeypatch):
    monkeypatch.setattr(sample, "ZIP", tmp_path / "doom.zip")
    monkeypatch.setattr(sample, "WINDOWS", True)
    monkeypatch.setattr(sample.C, "save_settings", lambda cfg, **kw: cfg.app.update(kw["app"]))
    _zip(tmp_path / "doom.zip")
    cfg, added = Cfg(), []
    user = SimpleNamespace(add_manual=lambda *a: added.append(a))
    dest = tmp_path / "esempi" / "doom"

    assert sample.seed(cfg, user, dest) is True
    assert (dest / "freedoom1.wad").read_bytes() == b"IWAD"
    assert not (tmp_path / "esempi" / "evasione.txt").exists() and not (tmp_path / "evasione.txt").exists()
    title, exe, args, cwd, kind = added[0]
    assert title == "Doom (Freedoom)" and exe == str(dest / "chocolate-doom.exe")
    assert args == ["-iwad", str(dest / "freedoom1.wad")] and cwd == str(dest) and kind == "game"

    assert sample.seed(cfg, user, dest) is False and len(added) == 1  # una sola volta, anche con la stessa versione


def test_fuori_da_windows_o_senza_zip_non_fa_nulla(tmp_path, monkeypatch):
    monkeypatch.setattr(sample, "ZIP", tmp_path / "doom.zip")
    user = SimpleNamespace(add_manual=lambda *a: (_ for _ in ()).throw(AssertionError("non chiamato")))
    monkeypatch.setattr(sample, "WINDOWS", False)
    _zip(tmp_path / "doom.zip")
    assert sample.seed(Cfg(), user, tmp_path / "x") is False
    monkeypatch.setattr(sample, "WINDOWS", True)
    monkeypatch.setattr(sample, "ZIP", tmp_path / "manca.zip")
    assert sample.seed(Cfg(), user, tmp_path / "x") is False
