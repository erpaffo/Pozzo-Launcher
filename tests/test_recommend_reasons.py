"""Motivi del consiglio emulatore (pozzo/emuinstall_extra.py): ogni console ha fedelta', prestazioni e controller
non vuoti, e recommend() li restituisce insieme al vecchio campo «reason». Nessuna rete, nessun Windows richiesto.

Esegui: python tests/test_recommend_reasons.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import emuinstall_extra as X  # noqa: E402
from pozzo import platforms as P  # noqa: E402

CHIAVI = {"fedelta", "prestazioni", "controller"}


def test_consigliati_hanno_tre_motivi():
    for console, (emu, why, motivi) in X.CONSIGLIATI.items():
        assert emu and why, console
        assert set(motivi) == CHIAVI, (console, motivi)
        assert all(motivi[k].strip() for k in CHIAVI), console


def test_ogni_console_ha_motivi_da_scelta():
    for console in P.PLATFORMS:
        motivi = X._scelta(console)[3]
        assert set(motivi) == CHIAVI, (console, motivi)
        assert all(motivi[k].strip() for k in CHIAVI), console


def test_recommend_restituisce_reason_e_reasons():
    # cfg non serve per il calcolo dei motivi: EI.installed legge la cartella degli emulatori, qui basta un finto
    import pozzo.emuinstall as EI
    saved = EI.installed
    EI.installed = lambda cfg: []
    try:
        r = X.recommend("ps2", cfg=object())
    finally:
        EI.installed = saved
    assert r["emulator"] == "pcsx2" and r["reason"] == X.CONSIGLIATI["ps2"][1]
    assert set(r["reasons"]) == CHIAVI and all(r["reasons"].values())


if __name__ == "__main__":
    test_consigliati_hanno_tre_motivi()
    test_ogni_console_ha_motivi_da_scelta()
    test_recommend_restituisce_reason_e_reasons()
    print("ok  recommend: motivi fedelta/prestazioni/controller per ogni console")
