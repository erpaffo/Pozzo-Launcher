"""Test di pozzo.netaddr: classificazione IP e IP pubblico."""

from __future__ import annotations

import httpx
import pytest

from pozzo import netaddr as NA


@pytest.mark.parametrize("ip", ["192.168.1.5", "10.0.0.2", "172.16.3.4"])
def test_rete_locale_lan(ip):
    assert NA.address_kind(ip)["kind"] == "lan"


def test_loopback():
    assert NA.address_kind("127.0.0.1")["kind"] == "loopback"


def test_vpn_shared():
    assert NA.address_kind("100.64.0.1")["kind"] == "shared"


def test_pubblico():
    assert NA.address_kind("8.8.8.8")["kind"] == "public"


def test_non_valido():
    res = NA.address_kind("abc")
    assert res["kind"] == "invalid"
    assert res["tip"] == "Indirizzo non valido."


class _Resp:
    def __init__(self, text, ok=True):
        self.text = text
        self.is_success = ok


def test_public_ip_ok(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp("  93.184.216.34\n"))
    assert NA.public_ip() == "93.184.216.34"


def test_public_ip_timeout(monkeypatch):
    def _boom(*a, **k):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "get", _boom)
    assert NA.public_ip() == ""


def test_public_ip_testo_non_ip(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp("<html>errore</html>"))
    assert NA.public_ip() == ""
