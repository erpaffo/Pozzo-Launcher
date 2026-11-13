"""Backup completo: copertura, credenziali escluse, anteprima, ripristino a giro, rotazione, copia automatica opzionale."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import backup, config  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402


def make(t):
    tmp = Path(t)
    (tmp / "config.toml").write_text("[paths]", encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    Path(cfg.cache).mkdir()
    config.save_settings(cfg, emulators={"ryujinx": "C:/R/Ryujinx.exe"}, rawg={"api_key": "SEGRETA"})
    (tmp / "themes").mkdir()
    (tmp / "themes" / "mio.css").write_text("body{}", encoding="utf-8")
    return cfg


def test_round_trip_preview_and_secrets():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = make(t)
        user = UserData(Path(cfg.cache) / "userdata.db")
        user.set_flag("gba/AAA", "favorite", 1)
        # senza credenziali: la chiave API non finisce nello zip
        out = backup.create(cfg, secrets=False)
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
            assert {"userdata.db", "settings.json", "manifest.json", "themes/mio.css"} <= names, names
            assert b"SEGRETA" not in z.read("settings.json")
            assert json.loads(z.read("manifest.json"))["secrets"] is False
        # anteprima: non cambia niente e dice cosa si sovrascrive
        user.set_flag("gba/BBB", "favorite", 1)
        (Path(t) / "themes" / "mio.css").unlink()
        pv = backup.preview(cfg, out.name)
        by = {i["file"]: i for i in pv["items"]}
        assert by["settings.json"]["action"] == "overwrite" and by["themes/mio.css"]["action"] == "create", by
        g = {c["table"]: c for c in by["userdata.db"]["counts"]}["user_games"]
        assert (g["now"], g["backup"]) == (2, 1), g
        assert pv["secrets"] is False
        assert len(user.games()) == 2  # l'anteprima non ha toccato i dati
        # ripristino: dati della copia, credenziali attuali conservate, tema ricreato
        r = backup.restore(cfg, out.name, user=user)
        assert {"userdata.db", "settings.json", "themes/mio.css"} <= set(r["restored"]), r
        assert list(user.games()) == ["gba/AAA"]
        s = json.loads(config.settings_path(cfg).read_text(encoding="utf-8"))
        assert s["rawg"]["api_key"] == "SEGRETA" and s["emulators"]["ryujinx"].endswith("Ryujinx.exe"), s
        assert (Path(t) / "themes" / "mio.css").read_text(encoding="utf-8") == "body{}"
        user.db.close()


def test_secrets_included_and_rotation_and_auto():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = make(t)
        UserData(Path(cfg.cache) / "userdata.db").close()
        assert backup.options(cfg) == {"auto": True, "keep": 10, "secrets": True}  # accesa di default
        with zipfile.ZipFile(backup.create(cfg)) as z:
            assert b"SEGRETA" in z.read("settings.json")
        config.save_settings(cfg, app={"backup_auto": False})
        assert backup.auto(cfg) is None  # spenta dall'utente
        config.save_settings(cfg, app={"backup_auto": True, "backup_keep": 2})
        assert backup.options(cfg)["auto"] is True
        assert backup.auto(cfg) is None  # c'e' gia' una copia di oggi
        for b in backup.list_backups(cfg):
            (backup.folder(cfg) / b["name"]).unlink()
        first = backup.auto(cfg)
        assert first is not None and backup.auto(cfg) is None  # poi, per una settimana, niente
        for i in range(4):
            p = backup.create(cfg, f"r{i}")
        names = [b["name"] for b in backup.list_backups(cfg)]
        assert len(names) == 2 and p.name in names, names  # rotazione: ultime N


def _copia_con_settings(cfg, raw_settings):
    # copia normale, poi si sostituisce solo settings.json
    out = backup.create(cfg, secrets=False)
    with zipfile.ZipFile(out) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    entries["settings.json"] = raw_settings
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in entries.items():
            z.writestr(n, b)
    return out


def test_settings_non_valido_non_tocca_il_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = make(t)
        user = UserData(Path(cfg.cache) / "userdata.db")
        for raw in (b"{rotto", b"[1, 2]"):  # JSON rotto; JSON valido ma non un oggetto
            name = _copia_con_settings(cfg, raw).name
            prima = config.settings_path(cfg).read_bytes()
            try:
                backup.restore(cfg, name, user=user)
            except ValueError:
                pass
            else:
                raise AssertionError(f"restore doveva fallire con {raw!r}")
            assert config.settings_path(cfg).read_bytes() == prima, raw
        user.db.close()


def test_api_preview_and_confirm():
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        cfg = make(t)
        UserData(Path(cfg.cache) / "userdata.db").close()
        c = TestClient(create_app(cfg))
        name = c.post("/api/backups").json()["name"]
        assert c.post("/api/backups/preview", json={"name": name}).json()["items"]
        assert c.post("/api/backups/restore", json={"name": name}).status_code == 400  # senza conferma niente ripristino
        assert c.post("/api/backups/settings", json={"auto": True, "keep": 3, "secrets": False}).json() == \
            {"auto": True, "keep": 3, "secrets": False}
        assert c.post("/api/backups/restore", json={"name": name, "confirm": True}).status_code == 200


if __name__ == "__main__":
    test_round_trip_preview_and_secrets()
    test_secrets_included_and_rotation_and_auto()
    test_settings_non_valido_non_tocca_il_file()
    test_api_preview_and_confirm()
    print("ok  backup completo")
