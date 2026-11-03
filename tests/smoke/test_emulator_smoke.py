"""Smoke test: RetroArch + core libero + ROM di test open-source, avviati col comando del launcher.

Non fa parte della suite normale (marker `smoke`, vedi tests/conftest.py): `pytest -m smoke tests/smoke`.
Serve RETROARCH_EXE (e RETROARCH_CORES_DIR con gambatte_libretro.*); senza, o senza rete, il test salta.
"""
import hashlib
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pozzo import platforms as P
from pozzo.library import launcher as L

pytestmark = pytest.mark.smoke

# Blargg cpu_instrs (test ROM open-source), commit fissato
ROM_URL = "https://raw.githubusercontent.com/retrio/gb-test-roms/c240dd7d700e5c0b00a7bbba52b53e4ee67b5f15/cpu_instrs/cpu_instrs.gb"
ROM_SHA256 = "8c5e12f41e0ba5bbca796944f92ffe6de28809198682c4332e38d1b3cf56fcf2"
ALIVE_SECONDS = float(os.environ.get("POZZO_SMOKE_SECONDS", "8"))


def test_retroarch_gambatte_starts_and_stays_alive(tmp_path):
    exe, cores = os.environ.get("RETROARCH_EXE"), os.environ.get("RETROARCH_CORES_DIR")
    if not exe or not Path(exe).exists():
        pytest.skip("RETROARCH_EXE non impostato o inesistente")
    try:
        data = urllib.request.urlopen(ROM_URL, timeout=30).read()
    except OSError as e:
        pytest.skip(f"ROM non scaricabile (rete?): {e}")
    if hashlib.sha256(data).hexdigest() != ROM_SHA256:
        pytest.skip("sha256 della ROM diverso dall'atteso")
    rom = tmp_path / "cpu_instrs.gb"
    rom.write_bytes(data)

    cfg = SimpleNamespace(emulators={"retroarch": exe, **({"retroarch_cores": cores} if cores else {})}, launch={})
    plan = L.plan(cfg, P.get("gb"))
    if not plan:
        pytest.skip("core gambatte non trovato")
    # video/audio nulli: nessuna finestra ne' scheda audio richieste
    (tmp_path / "null.cfg").write_text('video_driver = "null"\naudio_driver = "null"\nmenu_driver = "null"\n')
    cmd = [plan["exe"], *(a.replace("{core}", str(L._core_path(cfg, plan["core"]))).replace("{rom}", str(rom)) for a in plan["args"]),
           "--appendconfig", str(tmp_path / "null.cfg")]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(ALIVE_SECONDS)
        assert proc.poll() is None, f"RetroArch terminato (codice {proc.returncode}): {(proc.stderr.read() or b'')[-500:]!r}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
