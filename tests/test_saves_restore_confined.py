"""restore(): mapping.yaml puo' arrivare da Ludusavi o da un altro PC. Si scrive solo dentro le cartelle note del
gioco (radici date dal chiamante, cartelle copiate intere, percorsi manuali); niente eseguibili, nemmeno travestiti
con punti o spazi finali (Windows li toglie)."""

import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo.library import saves as SV  # noqa: E402

KEY = "pc/confinato"


def _evil(cfg, d: Path, targets: list[Path]) -> str:
    """Aggiunge a mapping.yaml una copia «esterna» che scrive nei percorsi dati."""
    import yaml
    m = yaml.safe_load((d / "mapping.yaml").read_text(encoding="utf-8"))
    keys = [SV._mkey(p) for p in targets]
    with zipfile.ZipFile(d / "evil.zip", "w") as z:
        for k in keys:
            z.writestr(SV._entry(m["drives"], k), "x")
    m["backups"].append({"name": "evil.zip", "when": "2099-01-01T00:00:00Z",
                         "files": {k: {"hash": "", "size": 1} for k in keys}})
    (d / "mapping.yaml").write_text(yaml.safe_dump(m), encoding="utf-8")
    return "evil.zip"


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cfg = config.Config(cache=t / "cache")
        saves = t / "Gioco" / "Saves"
        saves.mkdir(parents=True)
        (saves / "slot1.sav").write_bytes(b"v1")
        b = SV.backup(cfg, KEY, "Gioco", [saves / "slot1.sav"])  # file singolo: nessuna cartella registrata
        (saves / "slot1.sav").write_bytes(b"rovinato")

        # copia legittima: torna nella cartella del gioco
        r = SV.restore(cfg, KEY, b.name, roots=[saves])
        assert (saves / "slot1.sav").read_bytes() == b"v1" and r["written"] == 1 and not r["skipped"], r
        # salvataggio cancellato (si ripristina proprio per questo): la radice c'e' anche se il file no
        (saves / "slot1.sav").unlink()
        assert SV.restore(cfg, KEY, b.name, roots=[saves])["written"] == 1

        # mapping.yaml che punta fuori dalle cartelle del gioco: saltato e segnalato
        outside = t / "altrove" / "autostart.txt"
        name = _evil(cfg, SV._game_dir(cfg, KEY), [outside, saves / "ok.sav"])
        r = SV.restore(cfg, KEY, name, roots=[saves])
        assert not outside.exists() and (saves / "ok.sav").exists(), r
        assert r["written"] == 1 and r["skipped"] == [str(Path(SV._mkey(outside)))], r
        assert SV.diff(cfg, KEY, name, roots=[saves])["skipped"] == [str(Path(SV._mkey(outside)))]
        # senza radici: si scrive solo nelle cartelle registrate dall'app o scelte dall'utente
        assert SV.restore(cfg, KEY, name)["written"] == 0
        SV.set_paths(cfg, KEY, [str(saves)])
        assert SV.restore(cfg, KEY, name)["written"] == 1
        # radici troppo generiche (disco, home) non valgono
        assert SV.restore(cfg, KEY, name, roots=[Path(outside.anchor), Path.home()])["written"] == 1
        assert not outside.exists()

    # eseguibili: nemmeno con punti/spazi finali (Windows li toglie) o flussi NTFS
    for n in ("evil.bat", "evil.bat.", "evil.bat ", "evil.BAT. .", "x.hta", "x.wsf", "x.desktop", "x.sh",
              "x.command", "evil.bat::$DATA", "x.pif", "x.cpl"):
        assert SV._risky(Path("/tmp") / n), n
    for n in ("slot1.sav", "save.dat", "Pokemon Rosso.srm", "prefs.plist", "x.state1"):
        assert not SV._risky(Path("/tmp") / n), n
    # Ludusavi su un PC nuovo: la cartella fissa del percorso vale anche se non esiste ancora
    from pozzo.library import ludusavi as LM
    man = {"games": {"G": {"files": [["<home>/Gioco/save*/*.sav", []], ["<home>/*.ini", []]]}}}
    assert LM.save_paths(man, "G", existing=False) == [Path.home() / "Gioco", Path.home()]
    print("ok  ripristino confinato alle cartelle del gioco, eseguibili rifiutati")


if __name__ == "__main__":
    main()
