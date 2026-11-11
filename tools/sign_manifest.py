"""Firma Ed25519 del manifest di aggiornamento.

  python tools/sign_manifest.py keygen [--out chiave.pem]   crea la coppia di chiavi (stampa la pubblica)
  python tools/sign_manifest.py sign MANIFEST [--key FILE]  scrive MANIFEST.sig (base64)

La chiave privata si legge da --key o dalla variabile MANIFEST_SIGNING_KEY (contenuto PEM): non va mai nel repo.
La pubblica (base64) si incolla in PUBKEY di pozzo/updates.py.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def public_b64(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def keygen(out: Path) -> str:
    if out.exists():
        raise SystemExit(f"{out} esiste già: non lo sovrascrivo")
    private = Ed25519PrivateKey.generate()
    out.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return public_b64(private)


def load_private(key_file: str | None) -> Ed25519PrivateKey:
    pem = Path(key_file).read_bytes() if key_file else os.environ.get("MANIFEST_SIGNING_KEY", "").encode()
    if not pem.strip():
        raise SystemExit("Chiave privata mancante: --key FILE oppure variabile MANIFEST_SIGNING_KEY")
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("La chiave non è Ed25519")
    return key


def sign(manifest: Path, key_file: str | None = None) -> Path:
    sig = base64.b64encode(load_private(key_file).sign(manifest.read_bytes()))
    out = manifest.with_name(manifest.name + ".sig")
    out.write_bytes(sig + b"\n")
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", default="manifest-signing-key.pem")
    s = sub.add_parser("sign")
    s.add_argument("manifest")
    s.add_argument("--key")
    a = ap.parse_args(argv)
    if a.cmd == "keygen":
        pub = keygen(Path(a.out))
        print(f"Chiave privata: {a.out} (custodiscila, NON committarla; il contenuto va nel secret MANIFEST_SIGNING_KEY)")
        print(f"Chiave pubblica da incollare in PUBKEY (pozzo/updates.py):\n{pub}")
    else:
        print(sign(Path(a.manifest), a.key))


if __name__ == "__main__":
    sys.exit(main())
