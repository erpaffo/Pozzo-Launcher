"""Netplay: codice invito (andata/ritorno, limiti, validazione) e argomenti RetroArch.

Nessuna rete: tutto è calcolato in locale.
"""
import base64
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pozzo import netplay as NP  # noqa: E402

INFO = {"k": "mario", "e": "retroarch", "c": "snes", "h": "10.0.0.2", "p": 55435, "n": "Lu"}
# chiave, core e nick realistici: devono entrare interi
REAL = {"k": "snes/super-mario-world-usa-rev-1", "e": "retroarch", "c": "snes9x", "h": "192.168.178.123",
        "p": 55435, "n": "GiocatoreConNickLungo"}


def _raw(obj) -> str:
    """Costruisce un codice a mano (per testare i casi malformati)."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return NP.PREFIX + base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")


def test_supported_solo_retroarch():
    assert NP.supported("retroarch")
    assert not NP.supported("ppsspp")
    assert not NP.supported("")


def test_andata_e_ritorno():
    code = NP.encode(INFO)
    assert code.startswith(NP.PREFIX)
    d = NP.decode(code, now=time.time())
    assert d["v"] == 1
    assert d["x"] > time.time()
    for key, value in INFO.items():
        assert d[key] == value


def test_encode_riempie_v_e_scadenza_se_mancano():
    before = time.time()
    d = NP.decode(NP.encode(INFO), now=before)
    assert d["v"] == 1
    assert int(before) + NP.TTL - 2 <= d["x"] <= time.time() + NP.TTL + 2


def test_valori_realistici_restano_interi():
    d = NP.decode(NP.encode(REAL))
    for key, value in REAL.items():
        assert d[key] == value


def test_nick_lungo_viene_accorciato():
    info = dict(INFO, n="N" * 1000)
    code = NP.encode(info)
    assert len(code) - len(NP.PREFIX) <= NP.MAX_PAYLOAD
    d = NP.decode(code)
    assert 0 < len(d["n"]) < 1000
    assert info["n"].startswith(d["n"])
    assert d["c"] == INFO["c"]  # il core si tocca solo se il nick non basta


def test_core_svuotato_se_il_nick_non_basta():
    info = dict(INFO, n="", c="C" * 1000)
    code = NP.encode(info)
    assert len(code) - len(NP.PREFIX) <= NP.MAX_PAYLOAD
    assert NP.decode(code)["c"] == ""


def test_troppo_lungo_anche_senza_nick_e_core():
    with pytest.raises(ValueError):
        NP.encode(dict(INFO, k="K" * 1000))


def test_scaduto():
    code = NP.encode(dict(INFO, x=100.0))
    assert NP.decode(code, now=50.0)["k"] == INFO["k"]
    with pytest.raises(ValueError, match="scaduto"):
        NP.decode(code, now=200.0)


def test_ip_non_valido():
    with pytest.raises(ValueError, match="IP"):
        NP.decode(NP.encode(dict(INFO, h="non.un.ip")))
    with pytest.raises(ValueError, match="IP"):
        NP.decode(_raw(dict(INFO, v=1, x=time.time() + 60, h=12345)))


def test_ipv6_accettato():
    d = NP.decode(NP.encode(dict(INFO, h="fe80::1")))  # 8 caratteri in più, ci sta nel limite
    assert d["h"] == "fe80::1"


@pytest.mark.parametrize("porta", [0, 65536, -1, "55435", True, 55435.0])
def test_porta_fuori_intervallo(porta):
    base = dict(INFO, v=1, x=time.time() + 60)
    with pytest.raises(ValueError, match="porta"):
        NP.decode(_raw(dict(base, p=porta)))


def test_porte_limite_accettate():
    base = dict(INFO, v=1, x=time.time() + 60)
    assert NP.decode(_raw(dict(base, p=1)))["p"] == 1
    assert NP.decode(_raw(dict(base, p=65535)))["p"] == 65535


def test_prefisso_mancante():
    code = NP.encode(INFO)
    with pytest.raises(ValueError, match="prefisso"):
        NP.decode(code[len(NP.PREFIX):])


def test_spazi_e_a_capo_ignorati():
    code = NP.encode(INFO)
    spezzato = "  " + code[:10] + "\n" + code[10:] + "\t"
    assert NP.decode(spezzato)["k"] == INFO["k"]


@pytest.mark.parametrize("garbage", [
    "POZZO-",
    "POZZO-!!!!",
    "POZZO-abc+def",
    "POZZO-" + base64.urlsafe_b64encode(b"non json").decode().rstrip("="),
    "POZZO-" + base64.urlsafe_b64encode(b"[1,2]").decode().rstrip("="),
    "POZZO-" + base64.urlsafe_b64encode(b"\xff\xfe").decode().rstrip("="),
    "",
])
def test_spazzatura(garbage):
    with pytest.raises(ValueError):
        NP.decode(garbage)


def test_versione_diversa():
    with pytest.raises(ValueError, match="versione"):
        NP.decode(_raw(dict(INFO, v=2, x=time.time() + 60)))
    with pytest.raises(ValueError, match="versione"):
        NP.decode(_raw(dict(INFO, x=time.time() + 60)))  # v mancante


@pytest.mark.parametrize("campo", ["k", "n"])
def test_campi_non_stringa(campo):
    with pytest.raises(ValueError):
        NP.decode(_raw(dict(INFO, v=1, x=time.time() + 60, **{campo: 7})))


def test_gioco_vuoto():
    with pytest.raises(ValueError, match="gioco"):
        NP.decode(NP.encode(dict(INFO, k="")))


def test_args_host():
    assert NP.args("host", nick="Luca") == ["--host", "--port", "55435", "--nick", "Luca"]
    assert NP.args("host", port=7000) == ["--host", "--port", "7000"]


def test_args_join():
    assert NP.args("join", "10.0.0.2", nick="Anna") == [
        "--connect", "10.0.0.2", "--port", "55435", "--nick", "Anna",
    ]
    assert NP.args("join", "10.0.0.2", port=7000) == ["--connect", "10.0.0.2", "--port", "7000"]


def test_args_modalita_sconosciuta():
    with pytest.raises(ValueError):
        NP.args("spectate")
