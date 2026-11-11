"""Hardening rete: telefono spento di default, avviso esposizione, pinning TOFU del certificato di Sunshine."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pozzo.remote import phone as PH
from pozzo.remote import sunshine as SUN

# 1) spento di default
hub = PH.PhoneHub(SimpleNamespace(app={}, config_path=None, cache="x"), lambda *a, **k: None)
assert hub.conf["enabled"] is False and hub.conf["devices"] == []

# 2) esposizione: LAN = nessun avviso
assert hub.exposure() == []
hub.cfg.app["phone"] = {"host": "192.168.1.5"}
assert hub.exposure() == []
hub.cfg.app["phone"] = {"public_url": "https://x.example"}
assert hub.exposure() == ["public_url"]
hub.cfg.app["phone"] = {"host": "8.8.8.8"}
assert hub.exposure() == ["host"]
hub.cfg.app["phone"] = {}
hub.lib_upnp = object()
assert hub.exposure() == ["upnp"]

# 3) pinning TOFU (impronta simulata)
cur = {"fp": "aa" * 32}
SUN.cert_fingerprint = lambda base=SUN.API, timeout=10: cur["fp"]
saved = {}
conf = {"user": "u", "password": "p"}
s = SUN.Sunshine.from_conf(conf, lambda c: saved.update(c))
s._verify()
assert conf["cert_sha256"] == "aa" * 32 and saved["cert_sha256"] == "aa" * 32  # primo uso: salvato
s2 = SUN.Sunshine.from_conf(conf)
s2._verify()  # stessa impronta: ok
cur["fp"] = "bb" * 32
s3 = SUN.Sunshine.from_conf(conf)
try:
    s3._verify()
    raise SystemExit("doveva rifiutare il certificato cambiato")
except SUN.CertChanged as e:
    assert isinstance(e, PermissionError) and "reimposta" in str(e)
conf.pop("cert_sha256")  # reset
s4 = SUN.Sunshine.from_conf(conf)
s4._verify()
assert conf["cert_sha256"] == "bb" * 32
print("ok")
