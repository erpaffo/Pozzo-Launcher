"""Firma Ed25519 del manifest di aggiornamento: valida, manomessa, assente con/senza chiave."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sign_manifest  # noqa: E402
from pozzo import updates  # noqa: E402

assert updates.PUBKEY == "" or len(updates.PUBKEY) == 44, "PUBKEY deve essere vuota o base64 di 32 byte"

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    pub = sign_manifest.keygen(d / "k.pem")
    m = d / "m.json"
    m.write_bytes(b'{"version":"1.0.0","file":[]}\n')
    sig = sign_manifest.sign(m, str(d / "k.pem")).read_bytes()
    raw = m.read_bytes()

    assert updates.verify_manifest_signature(raw, sig, pub) is True  # valida


    def rejected(raw, sig, pub):
        try:
            updates.verify_manifest_signature(raw, sig, pub)
        except updates.SignatureError:
            return True
        return False

    assert rejected(raw + b" ", sig, pub)  # manifest manomesso
    assert rejected(raw, b"AAAA" + sig[4:], pub)  # firma alterata
    assert rejected(raw, b"non-base64!!", pub)  # firma illeggibile
    assert rejected(raw, None, pub)  # assente con chiave impostata
    other = sign_manifest.keygen(d / "k2.pem")
    assert rejected(raw, sig, other)  # firmato con un'altra chiave

# senza chiave la verifica e' saltata, con o senza firma
assert updates.verify_manifest_signature(b"x", None, "") is False
assert updates.verify_manifest_signature(b"x", b"qualsiasi", "") is False
print("ok")
