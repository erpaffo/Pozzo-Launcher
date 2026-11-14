"""Chiavi della CA locale e del certificato del server: leggibili solo dall'utente (fuori da Windows), anche quelle
create da versioni precedenti con i permessi predefiniti."""
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.remote import certs  # noqa: E402


def main():
    if os.name == "nt":  # permessi POSIX assenti: la cartella dati e' gia' privata
        print("saltato su Windows")
        return
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        old = os.umask(0o022)
        try:
            certs.ensure(t)
            for name in (certs.CA_KEY_FILE, certs.KEY_FILE):
                assert stat.S_IMODE((t / name).stat().st_mode) == 0o600, name
            # installazione precedente: chiave della CA con 0644, si sistema al prossimo avvio senza rifarla
            (t / certs.CA_KEY_FILE).chmod(0o644)
            before = (t / certs.CA_KEY_FILE).read_bytes()
            certs.ensure(t)
            assert stat.S_IMODE((t / certs.CA_KEY_FILE).stat().st_mode) == 0o600
            assert (t / certs.CA_KEY_FILE).read_bytes() == before  # stessa CA: il telefono resta abbinato
        finally:
            os.umask(old)
    print("ok  chiavi private con permessi 0600")


if __name__ == "__main__":
    main()
