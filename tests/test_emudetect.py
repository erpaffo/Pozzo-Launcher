import sys
import types

from pozzo import emudetect


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


def test_detect_all_roots_registry_no_duplicates(tmp_path, monkeypatch):
    monkeypatch.setattr(emudetect, "_roots", lambda: [])
    a = _touch(tmp_path / "pf" / "Dolphin" / "Dolphin.exe")
    b = _touch(tmp_path / "scoop" / "retroarch.exe")
    steam = _touch(tmp_path / "lib" / "steamapps" / "common" / "RetroArch" / "retroarch.exe")
    reg_exe = _touch(tmp_path / "reg" / "pcsx2-qt.exe")
    dup = _touch(tmp_path / "other" / "Dolphin.exe")
    r = emudetect.detect_all(
        extra_roots=[(tmp_path / "pf", "program-files", 3), (tmp_path / "scoop", "scoop", 1), (tmp_path / "other", "x", 2),
                     (tmp_path / "missing", "x", 2)],
        steam_libs=[tmp_path / "lib"],
        registry=lambda: [(str(reg_exe), "registry"), (str(tmp_path / "other"), "registry"), ("Z:/nope.exe", "registry")])
    assert r["dolphin"] == {"path": str(a), "source": "program-files"}
    assert r["retroarch"] == {"path": str(steam), "source": "steam"}  # primo trovato vince (Steam prima degli extra)
    assert b.exists()
    assert r["pcsx2"] == {"path": str(reg_exe), "source": "registry"}
    assert set(r) == {"dolphin", "retroarch", "pcsx2"} and r["dolphin"]["path"] != str(dup)


def test_steam_root_used(tmp_path, monkeypatch):
    monkeypatch.setattr(emudetect, "_roots", lambda: [])
    s = _touch(tmp_path / "lib" / "steamapps" / "common" / "RetroArch" / "retroarch.exe")
    r = emudetect.detect_all(steam_libs=[tmp_path / "lib"], registry=lambda: [])
    assert r == {"retroarch": {"path": str(s), "source": "steam"}}


def test_winreg_simulated(tmp_path, monkeypatch):
    exe = _touch(tmp_path / "Cemu" / "Cemu.exe")
    tree = {("HKLM", emudetect._UNINSTALL): {"Cemu": {"InstallLocation": str(exe.parent)}}}

    class K:
        def __init__(self, hive, path): self.d = tree.get((hive, path)) if isinstance(path, str) and (hive, path) in tree else None
        def __enter__(self): return self
        def __exit__(self, *a): pass

    fake = types.SimpleNamespace(HKEY_LOCAL_MACHINE="HKLM", HKEY_CURRENT_USER="HKCU", KEY_READ=1, KEY_WOW64_32KEY=0)

    def open_key(h, p, *a):
        if isinstance(h, K):
            if h.d is None or p not in h.d:
                raise OSError
            k = K(None, None); k.d = h.d[p]; return k
        if (h, p) not in tree:
            raise OSError
        k = K(None, None); k.d = tree[(h, p)]; return k
    fake.OpenKey = open_key
    fake.QueryInfoKey = lambda k: (len(k.d), 0, 0)
    fake.EnumKey = lambda k, i: list(k.d)[i]
    def q(k, name):
        if name in k.d: return (k.d[name], 1)
        raise OSError
    fake.QueryValueEx = q
    monkeypatch.setattr(emudetect, "winreg", fake)
    assert ("%s" % exe.parent, "registry") in emudetect._registry()
    monkeypatch.setattr(emudetect, "_roots", lambda: [])
    assert emudetect.detect_all()["cemu"]["source"] == "registry"


def test_no_winreg_is_empty(monkeypatch):
    monkeypatch.setattr(emudetect, "winreg", None)
    assert emudetect._registry() == []


def test_emuinstall_skips_when_present(tmp_path):
    from pozzo import emuinstall
    exe = _touch(tmp_path / "x.exe")
    cfg = types.SimpleNamespace(emulators={"dolphin": str(exe)}, app={})
    msgs = []
    assert emuinstall.install(cfg, "dolphin", say=msgs.append) == str(exe) and "gia'" in msgs[0]


def test_registro_non_scansiona_cartelle_estranee(tmp_path, monkeypatch):
    from pozzo import emudetect as E
    other = tmp_path / "Office"
    other.mkdir()
    seen = []
    monkeypatch.setattr(E, "detect_emulators", lambda p, max_depth=3: seen.append(p) or {})
    E.detect_all(None, extra_roots=[], steam_libs=[], registry=lambda: [(str(other), "registry")])
    assert other not in seen
