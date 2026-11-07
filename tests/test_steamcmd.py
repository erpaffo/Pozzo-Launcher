"""SteamCMD: comandi (mai la password nei log), avanzamento, rilevamento di Steam Guard/password, flusso con processo finto."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo.downloads.engines import steamcmd as S
from pozzo.downloads.task import DownloadTask

SAMPLE = """Redirecting stderr to 'logs/stderr.txt'
Logging directory: './logs'
 Update state (0x3) reconfiguring, progress: 0.00 (0 / 0)
 Update state (0x61) downloading, progress: 12.34 (1234 / 10000)\r Update state (0x61) downloading, progress: 50.00 (5000 / 10000)
 Update state (0x81) verifying update, progress: 99.00 (9900 / 10000)
Success! App '730' fully installed.
"""


def test_commands_never_expose_password():
    cmd = [str(Path("steamcmd.exe")), *S.login_args("bob", "hunter2", "ABCDE"), "+quit"]
    assert cmd[1:5] == ["+login", "bob", "hunter2", "ABCDE"]
    shown = S.mask(cmd)
    assert "hunter2" not in shown and "ABCDE" not in shown and "bob" in shown and shown.endswith("+quit")
    inst = S.install_cmd(Path("steamcmd.exe"), "D:/g", "bob", "730")
    assert "+login" in inst and inst[inst.index("+login") + 1] == "bob" and "bob" in S.mask(inst)
    assert inst[inst.index("+app_update") + 1:] == ["730", "validate", "+quit"]
    assert S.login_args("bob") == ["+login", "bob"]


def test_progress_parsing():
    assert S.parse_progress(" Update state (0x61) downloading, progress: 12.34 (1234 / 10000)") == ("61", "downloading", 12.34, 1234, 10000)
    assert S.parse_progress("Success! App '730' fully installed.") is None


def test_classify():
    assert S.classify("Steam Guard code:") == "guard"
    assert S.classify("This computer has not been authenticated... Two-factor code:") == "guard"
    assert S.classify("FAILED (Account Logon Denied)") == "guard"
    assert S.classify("FAILED login with result code Invalid Password") == "password"
    assert S.classify("FAILED (Two-factor code mismatch)") == "guard_bad"
    assert S.classify("FAILED (Rate Limit Exceeded)") == "ratelimit"
    assert S.classify("FAILED (Cached credentials not found)") == "nocache"
    assert S.classify("Logged in OK") is None


class FakeProc:
    def __init__(self, text):
        chunks = iter([text.encode(), b""])
        self.stdout = SimpleNamespace(read1=lambda n: next(chunks))

    def wait(self):
        return 0

    def terminate(self):
        pass


def fake(monkeypatch, text, seen=None):
    def popen(cmd, **kw):
        if seen is not None:
            seen.append(cmd)
        return FakeProc(text)
    monkeypatch.setattr(S.subprocess, "Popen", popen)


def cfg_ready(tmp_path):
    cfg = SimpleNamespace(cache=tmp_path)
    (tmp_path / "steamcmd").mkdir()
    (tmp_path / "steamcmd" / S.EXE).write_text("x")
    (tmp_path / "steamcmd" / ".ready").write_text("1")
    return cfg


def test_login_flow(tmp_path, monkeypatch):
    cfg = cfg_ready(tmp_path)
    fake(monkeypatch, "Logging in user 'bob'...\nLogged in OK\nWaiting for user info...OK\n")
    assert S.login(cfg, "bob", "pw") == {"ok": True}
    st = S.status(cfg)
    assert st["logged_in"] and st["user"] == "bob"
    assert "pw" not in (tmp_path / "steamcmd" / "account.json").read_text()
    S.logout(cfg)
    assert not S.status(cfg)["logged_in"]
    fake(monkeypatch, "FAILED login with result code Invalid Password pw\n")
    r = S.login(cfg, "bob", "pw")
    assert not r["ok"] and r["code"] == "password" and "pw" not in r["error"].replace("password", "")
    fake(monkeypatch, "Steam Guard code:\n")
    assert S.login(cfg, "bob", "pw")["code"] == "guard"


def test_run_progress_and_failure(tmp_path, monkeypatch):
    cfg = cfg_ready(tmp_path)
    seen = []
    fake(monkeypatch, SAMPLE, seen)
    t = DownloadTask(source="steamcmd://730", save_path=str(tmp_path / "g"), type="steamcmd", name="CS", options={"appid": "730", "user": "bob"})
    asyncio.run(S.run(t, cfg))
    assert t.size == 10000 and t.done == 10000 and seen[0][-3:] == ["730", "validate", "+quit"]
    assert not any("pw" in l["msg"] for l in t.logs)
    fake(monkeypatch, "ERROR! Failed to install app '730' (No subscription)\n")
    try:
        asyncio.run(S.run(t, cfg))
    except RuntimeError as e:
        assert "No subscription" in str(e)
    else:
        raise AssertionError
    fake(monkeypatch, "FAILED (Cached credentials not found)\n")
    try:
        asyncio.run(S.run(t, cfg))
    except RuntimeError as e:
        assert "Steam" in str(e)
    else:
        raise AssertionError


def test_folder_for():
    assert S.folder_for("D:/dl", 'Half: Life/2?', "220").endswith("Half Life2")
