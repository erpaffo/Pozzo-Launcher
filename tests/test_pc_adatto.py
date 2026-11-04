import importlib.util
from pathlib import Path

_s = importlib.util.spec_from_file_location("pc_adatto", Path(__file__).parent.parent / "extensions/pc-adatto/backend.py")
pa = importlib.util.module_from_spec(_s)
_s.loader.exec_module(pa)


def HW(c, g, r):
    return {"cpu": {"tier": c}, "gpu": {"tier": g}, "ram_gb": r, "incerto": False}


def test_tiers():
    assert pa.cpu_tier("Intel(R) Core(TM) i7-12700K") == (5, True)
    assert pa.cpu_tier("AMD Ryzen 5 3600 6-Core Processor") == (3, True)
    assert pa.cpu_tier("Intel Core i5-2500K") == (2, True)
    assert pa.cpu_tier("Mystery CPU") == (3, False)
    assert pa.gpu_tier("NVIDIA GeForce RTX 4090")[0] == 5
    assert pa.gpu_tier("NVIDIA GeForce GTX 1060")[0] == 3
    assert pa.gpu_tier("AMD Radeon RX 6600")[0] == 4
    assert pa.gpu_tier("Intel(R) UHD Graphics 620")[0] == 1


def test_console_verdict():
    assert pa.verdict_console("nes", HW(1, 1, 4))["verdict"] == "ok"
    assert pa.verdict_console("ps3", HW(2, 2, 8))["verdict"] == "insufficiente"
    r = pa.verdict_console("ps3", HW(3, 3, 8))
    assert r["verdict"] == "impostazioni" and r["suggestions"]
    assert pa.verdict_console("ps3", HW(5, 5, 32))["verdict"] == "ok"


def test_steam_parse():
    html = ('<strong>Minimi:</strong><br><ul class="bb_ul"><li>Processore: Intel Core i5-2500K / AMD FX-6300</li>'
            "<li>Memoria: 8 GB di RAM</li><li>Scheda video: NVIDIA GTX 760 / AMD R9 280</li></ul>")
    p = pa.parse_req(html)
    assert p["ram_gb"] == 8 and "GTX 760" in p["gpu"]
    assert pa.verdict_steam({"min": html, "rec": ""}, HW(1, 3, 16))["verdict"] == "insufficiente"
    assert pa.verdict_steam({"min": html, "rec": ""}, HW(4, 4, 16))["verdict"] == "ok"
    assert pa.verdict_steam({"min": "boh", "rec": ""}, HW(4, 4, 16))["verdict"] == "sconosciuto"
