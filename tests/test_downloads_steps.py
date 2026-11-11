"""Post-download a passi: catena componibile, attesa del gruppo/dei volumi, password per pacchetto, regole di destinazione."""
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import finish, ingest as IN, manager as M  # noqa: E402
from pozzo.downloads.task import COMPLETED, RUNNING, STAGES, DownloadTask  # noqa: E402
from test_downloads_finish import Mgr, _ctx, _task  # noqa: E402


def _zip(tmp, name="Gioco.zip", inner="Gioco/Gioco [0100AAAA].xci"):
    z = tmp / "dl" / name
    z.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(inner, b"x" * 50)
    return z


def test_catena_di_passi_e_hook(tmp):
    assert finish.STEPS == ["extract", "convert", "verify", "library"]
    assert [i for i, _ in STAGES] == ["download", "extract", "convert", "verify", "library", "data"]
    ctx, calls, got, cfg = _ctx(tmp)
    _zip(tmp)
    seen = []
    finish.register_step("prova", lambda t, m, c, st: seen.append(bool(st.games)), dopo="extract")
    try:
        assert finish.STEPS == ["extract", "prova", "convert", "verify", "library"]
        t = _task(tmp, "Gioco.zip")
        finish.run(t, Mgr(), ctx)
    finally:
        finish.STEPS.remove("prova")
        finish._FN.pop("prova")
    assert seen == [True] and t.options["steps"]["prova"] == "done"
    assert [s["state"] for s in t.stages if s["id"] in ("convert", "verify")] == ["skip", "skip"]
    assert calls  # libreria raggiunta


def test_passo_che_ferma_la_catena(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    _zip(tmp)
    finish.register_step("stop", lambda *a: False, dopo="extract")
    try:
        t = _task(tmp, "Gioco.zip")
        finish.run(t, Mgr(), ctx)
    finally:
        finish.STEPS.remove("stop")
        finish._FN.pop("stop")
    assert not calls and t.options["steps"].get("library") is None


def test_task_vecchio_senza_convert_e_verify(tmp):
    t = DownloadTask(source="https://x/a", save_path=str(tmp), status=COMPLETED)
    t.stages = [{"id": i, "label": l, "state": "done", "pct": 100} for i, l in STAGES if i not in ("convert", "verify")]
    assert t._stage("convert")["state"] == "skip"
    assert [s["id"] for s in t.stages] == [i for i, _ in STAGES]


def test_verify_sha256_altri_motori(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    (tmp / "dl").mkdir()
    (tmp / "dl" / "Gioco.xci").write_bytes(b"x" * 20)
    files = [{"name": "Gioco.xci", "priority": 1}]
    t = _task(tmp, "Gioco.xci", sha256="0" * 64, files=files)
    t.type = "torrent"
    finish.run(t, Mgr(), ctx)
    assert not calls and any(s["id"] == "verify" and s["state"] == "error" for s in t.stages)
    import hashlib
    ok = _task(tmp, "Gioco.xci", sha256=hashlib.sha256(b"x" * 20).hexdigest(), files=files)
    ok.type = "torrent"
    finish.run(ok, Mgr(), ctx)
    assert calls and any(s["id"] == "verify" and s["state"] == "done" for s in ok.stages)


def test_gruppo_aspetta_gli_altri_poi_estrae(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    z = _zip(tmp)
    t = _task(tmp, "Gioco.zip")
    other = DownloadTask(source="https://x/Gioco%20Update.zip", save_path=str(tmp / "dl"), name="Gioco.zip", status=RUNNING)
    mgr = Mgr()
    mgr.tasks = {t.id: t, other.id: other}
    finish.run(t, mgr, ctx)
    assert t.options.get("post_wait") and not t.options.get("post_done") and z.exists() and not calls
    assert "gruppo" in t.phase
    other.status = COMPLETED
    finish.run(t, mgr, ctx)
    assert not t.options.get("post_wait") and t.options["post_done"] and calls and not z.exists()


def test_volumi_mancanti_restano_in_attesa(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    (tmp / "dl").mkdir()
    (tmp / "dl" / "g.part1.rar").write_bytes(b"x")
    (tmp / "dl" / "g.part3.rar").write_bytes(b"x")
    t = _task(tmp, "g.part1.rar")
    mgr = Mgr()
    finish.run(t, mgr, ctx)
    finish.run(t, mgr, ctx)  # ricontrollo: il messaggio non si ripete
    assert t.options.get("post_wait") and not t.options.get("post_done") and not calls
    assert sum("Mancano" in l["msg"] for l in t.log_after(0)[0]) == 1
    (tmp / "dl" / "g.part2.rar").write_bytes(b"x")
    assert not finish.X.missing_volumes(tmp / "dl" / "g.part1.rar")


def test_password_pacchetto_poi_comuni_mai_nel_log(tmp, monkeypatch):
    ctx, calls, got, cfg = _ctx(tmp)
    z = _zip(tmp)
    tried = []

    def fake(archive, dest, *, password=None, log=None, **k):
        tried.append(password)
        if password != "tre-segreta":
            raise finish.X.BadPassword("Password errata")
        out = Path(dest) / "Gioco"
        out.mkdir(exist_ok=True)
        (out / "Gioco [0100AAAA].xci").write_bytes(b"x" * 50)
        return [out]

    monkeypatch.setattr(finish.X, "extract", fake)
    t = _task(tmp, "Gioco.zip", password="uno-segreta")
    finish.run(t, Mgr(passwords=["due-segreta", "tre-segreta"]), ctx)
    assert tried == ["uno-segreta", "due-segreta", "tre-segreta"] and calls and not z.exists()
    log = " ".join(l["msg"] for l in t.log_after(0)[0])
    assert "segreta" not in log and "provo la successiva" in log


def test_password_sbagliata_ovunque_e_errore(tmp, monkeypatch):
    ctx, calls, got, cfg = _ctx(tmp)
    _zip(tmp)

    def fake(*a, **k):
        raise finish.X.PasswordRequired("L'archivio e' protetto da password")

    monkeypatch.setattr(finish.X, "extract", fake)
    t = _task(tmp, "Gioco.zip")
    finish.run(t, Mgr(passwords=["a"]), ctx)
    assert not calls and any(s["id"] == "extract" and s["state"] == "error" for s in t.stages)


def test_regole_regex_invalide_ignorate_e_prima_che_combacia():
    logs = []
    rules = [{"match": "(["}, {"match": "zelda", "platform": "switch"}, {"match": "x"}, "boh"]
    r = IN.match_rule(rules, "The Legend of Zelda", log=lambda m, l="info": logs.append(m))
    assert r == rules[1] and len(logs) == 1
    assert IN.match_rule(rules, "Altro") is None and IN.match_rule(None, "x") is None


def test_target_dir_con_regola(tmp):
    from test_downloads_ingest import make_cfg
    cfg = make_cfg(tmp)
    base = IN.target_dir(cfg, "switch")
    d = IN.target_dir(cfg, "switch", rule={"subfolder": "../Mie\\Roba:"})
    assert d == base / "Mie" / "Roba" and d.is_dir()
    assert IN.target_dir(cfg, "snes", rule={"platform": "switch"}) == base


def test_regola_in_pipeline_sposta_in_sottocartella(tmp):
    ctx, calls, got, cfg = _ctx(tmp)
    _zip(tmp)
    t = _task(tmp, "Gioco.zip")
    finish.run(t, Mgr(rules=[{"match": "^gioco", "platform": "switch", "subfolder": "Preferiti"}]), ctx)
    placed = list(cfg.roms.rglob("*.xci"))
    assert len(placed) == 1 and "Preferiti" in placed[0].parts, [str(p) for p in placed]


def test_password_e_impostazioni_nel_manager(tmp):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    m = M.Manager(cfg, client_factory=net.make_client, save=lambda new: None)
    for bad in (123, "x" * 129):
        with pytest.raises(ValueError):
            m.add("https://x.test/a.zip", password=bad)
    t = m.add("https://x.test/a.zip", password="pw")
    assert t.options["password"] == "pw" and "password" not in t.view()["options"]
    s = m.update_settings({"passwords": ["a", "a", "", "b"], "rules": [{"match": "x", "subfolder": "y", "zz": 1}, {"match": " "}]})
    assert s["passwords"] == ["a", "b"] and s["rules"] == [{"match": "x", "platform": "", "subfolder": "y"}]
    with pytest.raises(ValueError):
        m.update_settings({"rules": "no"})
    assert M.DEFAULTS["passwords"] == [] and M.DEFAULTS["rules"] == []
