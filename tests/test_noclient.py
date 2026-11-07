"""Epic, GOG e Amazon senza client: scelta dei file di release, file di accesso, avanzamento, comandi, installati."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import noclient as NC  # noqa: E402
from pozzo import profilecfg as PC  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import cli as CLI  # noqa: E402


def names(*n):
    return [{"name": x, "url": "https://x/" + x, "size": 1, "sum": "ab"} for x in n]


# nomi veri delle release (derrod/legendary 0.21.1, heroic-gogdl v1.4.0, imLinguin/nile v1.2.0)
LEGENDARY = names("legendary_linux_arm64", "legendary_linux_x64", "legendary_macOS.zip", "legendary_macOS_arm64",
                  "legendary_macOS_x64", "legendary_windows_arm64.exe", "legendary_windows_x64.exe")
GOGDL = names("gogdl_linux_arm64", "gogdl_linux_x86_64", "gogdl_macos_arm64", "gogdl_macos_x86_64",
              "gogdl_windows_arm64.exe", "gogdl_windows_x86_64.exe")
NILE = names("nile_linux_arm64", "nile_linux_x86_64", "nile_macOS_arm64", "nile_macOS_x86_64", "nile_windows_x86_64.exe")


@pytest.mark.parametrize("store,assets,plat,machine,want", [
    ("epic", LEGENDARY, "win32", "AMD64", "legendary_windows_x64.exe"),
    ("epic", LEGENDARY, "win32", "ARM64", "legendary_windows_arm64.exe"),
    ("epic", LEGENDARY, "linux", "x86_64", "legendary_linux_x64"),
    ("epic", LEGENDARY, "darwin", "arm64", "legendary_macOS_arm64"),  # non il legendary_macOS.zip
    ("gog", GOGDL, "win32", "AMD64", "gogdl_windows_x86_64.exe"),
    ("gog", GOGDL, "linux", "aarch64", "gogdl_linux_arm64"),
    ("amazon", NILE, "win32", "AMD64", "nile_windows_x86_64.exe"),
    ("amazon", NILE, "win32", "ARM64", "nile_windows_x86_64.exe"),  # nile non ha Windows arm: x64 in emulazione
    ("amazon", NILE, "darwin", "x86_64", "nile_macOS_x86_64"),
])
def test_pick_asset(store, assets, plat, machine, want):
    assert NC.pick_asset(store, assets, plat, machine)["name"] == want


def test_pick_asset_none():
    assert NC.pick_asset("amazon", names("nile_linux_x86_64"), "win32", "AMD64") is None


@pytest.fixture
def cfg(tmp, monkeypatch):
    import importlib.util
    real = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("pozzo._pc_real", PC.__file__))
    spec.loader.exec_module(real)  # test_epic_manifests.py sostituisce PC.get all'import: qui serve quello vero
    monkeypatch.setattr(PC, "get", real.get)
    with PC.override("default"):  # altri test possono lasciare un profilo attivo nel contesto
        yield SimpleNamespace(app={}, config_path=tmp / "config.toml", cache=str(tmp / "cache"), emulators={})


def test_epic_auth_file(cfg):
    assert not NC.write_epic_auth(cfg, {})
    a = {"refresh_token": "RT1", "account_id": "acc", "displayName": "Gigi", "refresh_expires": 4102444800}
    assert NC.write_epic_auth(cfg, a)
    d = json.loads((NC.root(cfg) / "legendary" / "user.json").read_text("utf-8"))
    assert d["refresh_token"] == "RT1" and d["account_id"] == "acc" and d["displayName"] == "Gigi"
    assert d["expires_at"].startswith("1970") and d["expires_at"].endswith("Z")  # scaduto: legendary rinnova
    assert d["refresh_expires_at"].startswith("2100")
    assert d["client_id"] == "34a02cf8f4414e29b15921876da36f9a"


def test_gog_auth_file(cfg):
    assert NC.write_gog_auth(cfg, {}) is None
    f = NC.write_gog_auth(cfg, {"refresh_token": "G1", "user_id": "42"})
    d = json.loads(f.read_text("utf-8"))[NC.GOG_CLIENT_ID]
    assert d["refresh_token"] == "G1" and d["loginTime"] == 0 and d["expires_in"] == 0 and d["user_id"] == "42"
    from pozzo.stores.gog import CLIENT_ID
    assert NC.GOG_CLIENT_ID == CLIENT_ID


def test_sync_back_takes_rotated_tokens(cfg):
    PC.set(cfg, "epic", {"refresh_token": "old", "account_id": "a"})
    NC.write_epic_auth(cfg, PC.get(cfg, "epic"))
    f = NC.root(cfg) / "legendary" / "user.json"
    d = json.loads(f.read_text("utf-8"))
    d["refresh_token"], d["refresh_expires_at"] = "new", "2100-01-01T00:00:00.000Z"
    f.write_text(json.dumps(d), "utf-8")
    NC.sync_back(cfg, "epic")
    assert PC.get(cfg, "epic")["refresh_token"] == "new" and PC.get(cfg, "epic")["account_id"] == "a"
    PC.set(cfg, "gog", {"refresh_token": "g-old"})
    g = NC.write_gog_auth(cfg, PC.get(cfg, "gog"))
    j = json.loads(g.read_text("utf-8"))
    j[NC.GOG_CLIENT_ID]["refresh_token"] = "g-new"
    g.write_text(json.dumps(j), "utf-8")
    NC.sync_back(cfg, "gog")
    assert PC.get(cfg, "gog")["refresh_token"] == "g-new"


def test_prepare_requires_account(cfg):
    with pytest.raises(RuntimeError):
        NC.prepare(cfg, "epic")
    PC.set(cfg, "gog", {"refresh_token": "x"})
    NC.prepare(cfg, "gog")
    assert (NC.root(cfg) / "gogdl" / "auth.json").exists()


@pytest.mark.parametrize("store,line,want", [
    # legendary conta chunk (x/y): la dimensione viene da «Download size», non dai numeri della riga
    ("epic", "[DLManager] INFO: = Progress: 12.34% (123/1000), Running for 00:00:10, ETA: 00:01:05",
     {"pct": 12.34, "eta": 65}),
    ("epic", "[DLManager] INFO:  + Download\t- 12.50 MiB/s (raw) / 25.00 MiB/s (decompressed)", {"speed": 12.5 * 1048576}),
    ("epic", "[cli] INFO: Download size: 2048.00 MiB (Compression savings: 12.0%)", {"size": 2048 * 1048576}),
    # gogdl e nile: percentuale senza «%» e byte
    ("gog", "[PROGRESS] INFO: = Progress: 50.00 5000/10000, Running for: 00:00:10, ETA: 00:00:10",
     {"pct": 50.0, "done": 5000, "total": 10000, "eta": 10}),
    ("amazon", "[PROGRESS] INFO: = Progress: 3.10 310/10000, Running for: 00:00:01, ETA: 00:00:31",
     {"pct": 3.1, "done": 310, "total": 10000, "eta": 31}),
    ("gog", "[PROGRESS] INFO:  + Download\t- 8.00 MiB/s (raw) / 9.00 MiB/s (decompressed)", {"speed": 8 * 1048576}),
    ("epic", "[cli] INFO: Preparing download for Fortnite", {}),
])
def test_parse_line(store, line, want):
    assert NC.parse_line(store, line) == want


def test_commands(cfg):
    exe = str(NC.exe_path(cfg, "epic"))
    assert NC.command(cfg, "epic", "install", "Sugar", {"path": "D:/G"}) == [
        exe, "-y", "install", "Sugar", "--base-path", "D:/G", "--skip-dlcs"]
    assert "--with-dlcs" in NC.command(cfg, "epic", "install", "Sugar", {"path": "D:/G", "with_dlcs": True})
    assert NC.command(cfg, "epic", "verify", "Sugar")[1:] == ["-y", "repair", "Sugar"]
    assert NC.command(cfg, "amazon", "update", "amzn1.x", {"path": "D:/G"})[1:] == ["update", "amzn1.x"]
    assert NC.command(cfg, "amazon", "install", "amzn1.x", {"path": "D:/G"})[1:] == [
        "install", "amzn1.x", "--base-path", "D:/G"]
    g = NC.command(cfg, "gog", "install", "123", {"path": "D:/G", "title": "Tit: o?", "dlcs": [7, 8]})
    assert g[1:3] == ["--auth-config-path", str(NC.root(cfg) / "gogdl" / "auth.json")]
    assert g[3:5] == ["download", "123"] and "--skip-dlcs" in g
    assert g[g.index("--path") + 1] == str(Path("D:/G") / "Tit_ o_")
    assert g[g.index("--dlcs") + 1] == "7,8"
    assert NC.command(cfg, "gog", "verify", "123", {"path": "D:/G"})[3] == "repair"


def test_installed_readers(cfg, tmp):
    game = tmp / "Games" / "Sugar"
    game.mkdir(parents=True)
    ep = NC.root(cfg) / "legendary"
    ep.mkdir(parents=True)
    (ep / "installed.json").write_text(json.dumps({
        "Sugar": {"app_name": "Sugar", "title": "Sugar Game", "install_path": str(game), "install_size": 99, "version": "1"},
        "Sugar_dlc": {"app_name": "Sugar_dlc", "install_path": str(game), "is_dlc": True},
        "Gone": {"app_name": "Gone", "title": "G", "install_path": str(tmp / "nope")}}), "utf-8")
    got = NC.installed(cfg, "epic")
    assert list(got) == ["Sugar"] and got["Sugar"]["title"] == "Sugar Game" and got["Sugar"]["size"] == 99
    nile = NC.root(cfg) / "nile" / "nile"
    nile.mkdir(parents=True)
    (nile / "installed.json").write_text(json.dumps([{"id": "amzn1.a", "path": str(game), "version": "v", "size": 5}]), "utf-8")
    (nile / "library.json").write_text(json.dumps([{"id": "x", "product": {"id": "amzn1.a", "title": "Amz", "productDetail": {
        "iconUrl": "http://i"}}}, {"id": "y", "product": {}}]), "utf-8")
    (nile / "current_user.json").write_text(json.dumps({"name": "Ann", "user_id": "u"}), "utf-8")
    assert NC.installed(cfg, "amazon")["amzn1.a"]["path"] == str(game)
    assert NC.amazon_library(cfg) == [{"id": "amzn1.a", "title": "Amz", "icon": "http://i"}]
    assert NC.amazon_user(cfg) == "Ann"
    NC.record_gog(cfg, "123", str(game), "Gog Game")
    assert NC.installed(cfg, "gog")["123"]["title"] == "Gog Game"
    assert NC.installed(cfg, "gog")["123"]["platform"] == NC.gog_platform()


def test_launch_cmd_is_child_process_command(cfg):
    rec = {"path": "D:/G/Sugar"}
    ep = NC.launch_cmd(cfg, "epic", "Sugar", rec)
    assert ep["type"] == "exe" and ep["target"] == str(NC.exe_path(cfg, "epic")) and ep["args"] == ["launch", "Sugar"]
    assert ep["track_dir"] == "D:/G/Sugar"
    assert NC.launch_cmd(cfg, "gog", "123", rec)["args"] == ["launch", "D:/G/Sugar", "123", "--platform", NC.gog_platform()]
    assert NC.launch_cmd(cfg, "amazon", "a", rec)["args"] == ["launch", "a"]


def test_epic_app_from_uri():
    assert NC.epic_app("com.epicgames.launcher://apps/ns%3Acid%3ASugar?action=install") == "Sugar"
    assert NC.epic_app("") == ""


def test_amazon_code():
    u = "https://www.amazon.com/ap/maplanding?openid.oa2.authorization_code=ANabc123&openid.mode=x"
    assert NC.amazon_code(u) == "ANabc123" and NC.amazon_code("ANxyz") == "ANxyz"


# ---------------------------------------------------------------- motore con un processo finto

class FakeStdout:
    def __init__(self, lines):
        self.lines = [x.encode() + b"\n" for x in lines] + [b""]

    async def readline(self):
        return self.lines.pop(0)


class FakeProc:
    def __init__(self, lines, rc=0):
        self.stdout, self.rc, self.returncode, self.pid = FakeStdout(lines), rc, None, 1

    async def wait(self):
        self.returncode = self.rc
        return self.rc


def run_engine(cfg, store, lines, rc=0, **opts):
    seen = {}

    async def spawn(*argv, **kw):
        seen["argv"], seen["env"] = list(argv), kw["env"]
        return FakeProc(lines, rc)

    t = T.DownloadTask(source=CLI.source_of(store, "123"), save_path=str(Path(cfg.config_path).parent), type="cli",
                       options={"store": store, "game_id": "123", "action": "install", "title": "Tit", "path": "D:/G", **opts})
    asyncio.run(CLI.run(t, cfg, spawn))
    return t, seen


def ready(cfg, store):
    exe = NC.exe_path(cfg, store)
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("x")


def test_engine_gog_progress_and_register(cfg):
    PC.set(cfg, "gog", {"refresh_token": "G"})
    ready(cfg, "gog")
    t, seen = run_engine(cfg, "gog", ["[PROGRESS] INFO: = Progress: 25.00 2500/10000, Running for: 00:00:01, ETA: 00:00:03"])
    assert seen["argv"][3] == "download" and t.options["post_done"] and t.size == 10000 and t.done == 10000
    rec = json.loads((NC.root(cfg) / "gog_installed.json").read_text("utf-8"))
    assert rec["123"]["title"] == "Tit" and rec["123"]["path"].endswith("Tit")
    assert [s["state"] for s in t.stages if s["id"] in ("extract", "library", "data")] == ["skip", "done", "skip"]


def test_engine_epic_size_then_percent(cfg):
    PC.set(cfg, "epic", {"refresh_token": "E"})
    ready(cfg, "epic")
    lines = ["[cli] INFO: Download size: 100.00 MiB (x)", "[DLManager] INFO: = Progress: 40.00% (4/10), Running for 00:00:01, ETA: 00:00:01"]
    seen_done = []
    orig = CLI.apply
    CLI.apply = lambda t, s, i: (orig(t, s, i), seen_done.append(t.done))
    try:
        run_engine(cfg, "epic", lines)
    finally:
        CLI.apply = orig
    assert seen_done[-1] == int(100 * 1048576 * 0.4)


def test_engine_failure_carries_output(cfg):
    PC.set(cfg, "epic", {"refresh_token": "E"})
    ready(cfg, "epic")
    with pytest.raises(RuntimeError, match="codice 1.*disk full"):
        run_engine(cfg, "epic", ["[cli] ERROR: disk full"], rc=1)


def test_engine_needs_tool_and_account(cfg):
    with pytest.raises(RuntimeError):
        run_engine(cfg, "epic", [])  # nessun account
    PC.set(cfg, "epic", {"refresh_token": "E"})
    with pytest.raises(RuntimeError, match="non e' installato"):
        run_engine(cfg, "epic", [])


def test_cancel_kills_process(cfg):
    PC.set(cfg, "epic", {"refresh_token": "E"})
    ready(cfg, "epic")
    killed = []

    class Hang(FakeProc):
        async def wait(self):
            await asyncio.sleep(10)

    class HangOut(FakeStdout):
        async def readline(self):
            await asyncio.sleep(10)

    async def go():
        p = Hang([])
        p.stdout = HangOut([])

        async def spawn(*a, **k):
            return p
        t = T.DownloadTask(source=CLI.source_of("epic", "1"), save_path=str(cfg.config_path.parent), type="cli",
                           options={"store": "epic", "game_id": "1", "action": "install"})
        orig = CLI.kill
        CLI.kill = lambda proc: killed.append(proc)
        try:
            job = asyncio.ensure_future(CLI.run(t, cfg, spawn))
            await asyncio.sleep(0.05)
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job
        finally:
            CLI.kill = orig
    asyncio.run(go())
    assert len(killed) == 1


def test_manager_accepts_cli_task(tmp):
    from pozzo.downloads.manager import Manager
    cfg = SimpleNamespace(app={}, config_path=tmp / "config.toml", cache=str(tmp / "cache"), emulators={}, stores={})
    m = Manager(cfg, None)
    with pytest.raises(ValueError):
        m.add(CLI.source_of("epic", "1"), str(tmp))
    t = m.add(CLI.source_of("epic", "1"), str(tmp), name="X", store="epic", game_id="1", action="install")
    assert t.type == "cli" and t.options["store"] == "epic"
