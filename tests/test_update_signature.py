"""Firma Ed25519 del manifest di aggiornamento: valida, manomessa, assente con/senza chiave."""
import base64
import contextlib
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


# install() con PUBKEY impostata e release senza manifest: deve fermarsi prima di toccare file o installer
PUBKEY_TEST = base64.b64encode(bytes(range(32))).decode()  # 32 byte qualsiasi: nessuna firma viene verificata qui
TAG, VERSION = "v0.18.0", "0.18.0"


@contextlib.contextmanager
def _patched(**attrs):
    """Sostituisce attributi di updates e li ripristina sempre, anche se il test fallisce."""
    saved = {name: getattr(updates, name) for name in attrs}
    try:
        for name, value in attrs.items():
            setattr(updates, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(updates, name, value)


def _release(*names):
    return {"newer": True, "latest": TAG, "assets": [
        {"name": n, "url": f"https://github.com/erpaffo/PozzoLauncher/releases/download/{TAG}/{n}",
         "size": 1000, "digest": None} for n in names]}


def test_pubkey_e_release_senza_manifest_zip(tmp_path):
    install_dir = tmp_path / "install"
    app = install_dir / "PozzoLauncher"
    app.mkdir(parents=True)
    (app / "PozzoLauncher.exe").write_bytes(b"vecchio")
    before = sorted(p.relative_to(install_dir) for p in install_dir.rglob("*"))
    downloads = []
    with _patched(PUBKEY=PUBKEY_TEST, install_kind=lambda: "win", app_dir=lambda: app,
                  check=lambda cache, force=False: _release(f"PozzoLauncher-{VERSION}-windows-x64.zip"),
                  _update_work_dir=lambda: tmp_path / "cache",
                  _download=lambda url, dest, **kw: downloads.append(url)):
        updates.install(None, lambda: None)
    assert updates.STATE["status"] == "error"
    assert "SignatureError" in updates.STATE["phase"] and "manifest" in updates.STATE["phase"]
    assert downloads == []
    assert (app / "PozzoLauncher.exe").read_bytes() == b"vecchio"
    assert sorted(p.relative_to(install_dir) for p in install_dir.rglob("*")) == before


def test_pubkey_e_installer_senza_manifest(tmp_path):
    detached, downloads = [], []
    with _patched(PUBKEY=PUBKEY_TEST, install_kind=lambda: "setup",
                  check=lambda cache, force=False: _release(f"PozzoLauncher-{VERSION}-windows-x64-setup.exe"),
                  _update_work_dir=lambda: tmp_path / "cache",
                  _detach=lambda cmd: detached.append(cmd),
                  _download=lambda url, dest, **kw: downloads.append(url)):
        updates.install(None, lambda: None)
    assert updates.STATE["status"] == "error"
    assert "SignatureError" in updates.STATE["phase"] and "manifest" in updates.STATE["phase"]
    assert detached == []  # l'installer non viene avviato
    assert downloads == []  # e nemmeno scaricato


with tempfile.TemporaryDirectory() as d:
    test_pubkey_e_release_senza_manifest_zip(Path(d))
    test_pubkey_e_installer_senza_manifest(Path(d))
print("ok")
