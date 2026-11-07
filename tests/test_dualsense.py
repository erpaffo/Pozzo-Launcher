"""DualSense/DS4: batteria dai report di ingresso e report di uscita per la barra luminosa (senza hardware)."""
import zlib

import pytest

from pozzo.remote import dualsense as D


def rep(size, rid, idx, val):
    b = bytearray(size)
    b[0], b[idx] = rid, val
    return bytes(b)


def test_battery_dualsense_usb_and_bt():
    assert D.parse_battery(False, False, rep(64, 1, 53, 0x07)) == {"percent": 75, "charging": False, "full": False}
    assert D.parse_battery(False, False, rep(64, 1, 53, 0x15))["charging"] is True
    assert D.parse_battery(False, False, rep(64, 1, 53, 0x20)) == {"percent": 100, "charging": False, "full": True}
    assert D.parse_battery(False, False, rep(64, 1, 53, 0xFF)) is None  # errore di lettura
    assert D.parse_battery(False, True, rep(78, 0x31, 54, 0x0A))["percent"] == 100
    assert D.parse_battery(False, True, rep(78, 1, 54, 0x0A)) is None  # report semplice Bluetooth: senza batteria
    assert D.parse_battery(False, False, b"") is None


def test_battery_ds4():
    assert D.parse_battery(True, False, rep(64, 1, 30, 0x04))["percent"] == 45
    assert D.parse_battery(True, False, rep(64, 1, 30, 0x1B))["full"] is True
    assert D.parse_battery(True, True, rep(78, 0x11, 32, 0x18))["percent"] == 72


def test_led_usb():
    r = D.build_led(False, False, (1, 2, 3))
    assert len(r) == 63 and r[0] == 0x02 and r[1] == 0 and r[2] & 0x04 and r[45:48] == b"\x01\x02\x03"


def test_led_bt_crc():
    r = D.build_led(False, True, (9, 8, 7), seq=5)
    assert len(r) == 78 and r[0] == 0x31 and r[1] == 0x50 and r[4] & 0x04 and r[47:50] == b"\x09\x08\x07"
    assert r[74:] == zlib.crc32(b"\xA2" + r[:74]).to_bytes(4, "little")


def test_led_ds4():
    u = D.build_led(True, False, (1, 2, 3))
    assert len(u) == 32 and u[0] == 5 and u[6:9] == b"\x01\x02\x03" and u[4:6] == b"\0\0"
    b = D.build_led(True, True, (1, 2, 3))
    assert len(b) == 78 and b[0] == 0x11 and b[8:11] == b"\x01\x02\x03" and b[74:] == zlib.crc32(b"\xA2" + b[:74]).to_bytes(4, "little")


def test_colour_mapping():
    assert D.hex_rgb("#5b8cff") == (0x5B, 0x8C, 0xFF)
    with pytest.raises(ValueError):
        D.hex_rgb("#fff")
