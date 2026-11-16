"""Aggiornamento dall'app: file della release per processore e copie installate da un gestore di pacchetti."""
import importlib
import platform
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pozzo import updates  # noqa: E402
import release_manifest  # noqa: E402


def _con_processore(machine: str):
    saved = platform.machine
    platform.machine = lambda: machine
    try:
        return importlib.reload(updates)
    finally:
        platform.machine = saved


def test_nomi_per_processore():
    try:
        u = _con_processore("x86_64")  # le copie gia' installate (Windows x64, Linux x64) cercano i nomi di sempre
        assert u.SUFFIX["win"] == "-windows-x64.zip" and u.SUFFIX["setup"] == "-windows-x64-setup.exe"
        assert u.SUFFIX["linux"] == "-linux-x64.tar.gz" and u.SUFFIX["deb"] == "_amd64.deb"
        assert u.SUFFIX["mac"] == "-macos-x64.zip" and u.PLATFORM["mac"] == "macos-x64"
        u = _con_processore("arm64")  # Mac Apple Silicon: lo stesso nome di prima
        assert u.SUFFIX["mac"] == "-macos-arm64.zip" and u.PLATFORM["mac"] == "macos-arm64"
        u = _con_processore("aarch64")
        assert u.SUFFIX["linux"] == "-linux-arm64.tar.gz" and u.SUFFIX["deb"] == "_arm64.deb"
        u = _con_processore("ARM64")  # Windows ARM64
        assert u.SUFFIX["setup"] == "-windows-arm64-setup.exe" and u.PLATFORM["win"] == "windows-arm64"
    finally:
        importlib.reload(updates)
    print("ok  nomi dei file per x64 e ARM64")


def test_pacchetto_gestito():
    with tempfile.TemporaryDirectory() as t:
        app = Path(t) / "PozzoLauncher"
        app.mkdir()
        saved = (getattr(sys, "frozen", None), updates.app_dir)
        sys.frozen, updates.app_dir = True, (lambda: app)
        try:
            assert updates.install_kind() is not None
            (app / updates.MANAGED).write_text("aur\n")
            assert updates.install_kind() is None, "pacchetto AUR: si aggiorna con pacman, non dall'app"
        finally:
            if saved[0] is None:
                del sys.frozen
            else:
                sys.frozen = saved[0]
            updates.app_dir = saved[1]
    print("ok  copia di un gestore di pacchetti: nessuna installazione dall'app")


def test_manifest_tutte_le_varianti():
    import tarfile
    import zipfile
    with tempfile.TemporaryDirectory() as t:
        rel = Path(t)
        with zipfile.ZipFile(rel / "PozzoLauncher-1.0-windows-arm64.zip", "w") as z:
            z.writestr("PozzoLauncher/PozzoLauncher.exe", "a")
        src = rel / "x"
        (src / "PozzoLauncher").mkdir(parents=True)
        (src / "PozzoLauncher" / "PozzoLauncher").write_text("b")
        with tarfile.open(rel / "PozzoLauncher-1.0-linux-arm64.tar.gz", "w:gz") as tf:
            tf.add(src / "PozzoLauncher", "PozzoLauncher")
        import json
        m = json.loads(release_manifest.create(rel, "1.0", payloads=False).read_text())
        paths = {f["path"].split("/")[0] for f in m["file"]}
        assert paths == {"windows-arm64", "linux-arm64"}, paths
        # ogni copia deve accettare il manifest intero, anche con i file degli altri processori
        assert updates._manifest(m, "1.0")["version"] == "1.0"
    print("ok  manifest di aggiornamento con le varianti ARM64")


if __name__ == "__main__":
    test_nomi_per_processore()
    test_pacchetto_gestito()
    test_manifest_tutte_le_varianti()
    print("TUTTI I TEST OK")
