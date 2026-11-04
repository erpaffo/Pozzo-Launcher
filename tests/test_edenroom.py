"""Stanze di Eden: comandi, qt-config.ini precompilato, processo finto. Non parte nessun Eden."""
import subprocess
import sys

from pozzo import edenroom as ER


def test_room_cmd_con_eden_room_accanto(tmp_path):
    (tmp_path / "eden.exe").write_text("")
    (tmp_path / "eden-room.exe").write_text("")
    c = ER.room_cmd(str(tmp_path / "eden.exe"), "Super Game!", 24872, "pw-1", "Super Game", 4)
    assert c[0].endswith("eden-room.exe") and c[1:5] == ["--room-name", "Super Game", "--port", "24872"]
    assert "--password" in c and "--preferred-game" in c and "--token" not in c  # privata


def test_room_cmd_senza_eden_room_usa_room_flag(tmp_path):
    c = ER.room_cmd(str(tmp_path / "eden.exe"), "ab", 1, "")
    assert c[1] == "--room" and c[c.index("--room-name") + 1] == "abPozzo" and "--password" not in c


def test_prefill_scrive_direct_connect_e_fa_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(ER.emusetup, "_running", lambda names: False)
    ini = tmp_path / "user" / "config" / "qt-config.ini"
    ini.parent.mkdir(parents=True)
    ini.write_bytes(b"[UI]\r\nlanguage=it\r\nMultiplayer\\ip=1.1.1.1\r\n[Core]\r\nx=1\r\n")
    p = ER.prefill(str(tmp_path / "eden.exe"), "Ale", "10.0.0.2", 24872)
    assert p == ini
    t = ini.read_bytes().decode("utf-8")
    assert "Multiplayer\\ip=10.0.0.2" in t and "Multiplayer\\port=24872" in t and "Multiplayer\\nickname=Ale" in t
    assert "language=it" in t and "[Core]" in t and "\r\n" in t
    assert list(ini.parent.glob("qt-config.ini.pozzo-*"))


def test_prefill_non_tocca_se_eden_aperto_o_manca(tmp_path, monkeypatch):
    ini = tmp_path / "user" / "config" / "qt-config.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text("[UI]\nx=1\n")
    monkeypatch.setattr(ER.emusetup, "_running", lambda names: True)
    assert ER.prefill(str(tmp_path / "eden.exe"), "Ale", "1.2.3.4", 1) is None
    assert ini.read_text() == "[UI]\nx=1\n"
    monkeypatch.setattr(ER.emusetup, "_running", lambda names: False)
    assert ER.prefill(str(tmp_path / "altro" / "eden.exe"), "Ale", "1.2.3.4", 1) in (None, ER.config_file(str(tmp_path / "altro" / "eden.exe")))


def test_alive_e_stop():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert ER.alive(p, 0.2)
    finally:
        ER.stop(p)
    assert p.poll() is not None
    q = subprocess.Popen([sys.executable, "-c", "pass"])
    assert not ER.alive(q, 5)
