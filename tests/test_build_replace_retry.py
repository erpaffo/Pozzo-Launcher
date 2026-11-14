"""build(): su Windows lo scambio di library.db fallisce (PermissionError) se un altro thread la sta leggendo in
quell'istante; si riprova invece di perdere la libreria appena costruita."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo.library import build as B  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        cfg = config.Config(roms=t / "roms", cache=t / "cache", output=t / "out")
        cfg.config_path = t / "config.toml"
        cfg.cache.mkdir()
        (cfg.roms / "Game Boy Advance").mkdir(parents=True)
        (cfg.roms / "Game Boy Advance" / "Zelda (USA).gba").write_bytes(b"z" * 100)

        async def no_franchises(*a, **k):
            return None
        B._enrich_franchises = no_franchises
        real, fails = os.replace, {"n": 0}

        def busy(src, dst):
            if Path(dst).name == "library.db" and fails["n"] < 3:  # occupata per qualche istante
                fails["n"] += 1
                raise PermissionError(13, "Accesso negato", str(dst))
            return real(src, dst)
        os.replace = busy
        try:
            stats = B.build(cfg, log=lambda m: None)
        finally:
            os.replace = real
        assert fails["n"] == 3 and stats["games"] >= 1 and (cfg.cache / "library.db").is_file(), (fails, stats)
    print("ok  scambio di library.db riprovato")


if __name__ == "__main__":
    main()
