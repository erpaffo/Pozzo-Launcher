"""tools/package_manifests.py: manifest di winget, Scoop, AUR e Homebrew dai file della release."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_manifests as PM  # noqa: E402

V = "1.2.3"
ALL = [f"PozzoLauncher-{V}-windows-{a}{s}" for a in ("x64", "arm64") for s in ("-setup.exe", ".zip")] + \
      [f"PozzoLauncher-{V}-macos-{a}.dmg" for a in ("x64", "arm64")] + \
      [f"PozzoLauncher-{V}-linux-{a}.tar.gz" for a in ("x64", "arm64")]


def _release(d: Path, names) -> Path:
    rel = d / "release"
    rel.mkdir()
    for n in names:
        (rel / n).write_bytes(n.encode())  # contenuto diverso per ogni file: impronte diverse
    return rel


def test_tutte_le_varianti():
    with tempfile.TemporaryDirectory() as t:
        rel, out = _release(Path(t), ALL), Path(t) / "out"
        assert PM.write(V, rel, out, "o/r") == []
        sha = PM._sha(rel / f"PozzoLauncher-{V}-windows-arm64-setup.exe")

        inst = (out / "winget/manifests/e/erpaffo/PozzoLauncher" / V / "erpaffo.PozzoLauncher.installer.yaml").read_text()
        assert "Architecture: x64" in inst and "Architecture: arm64" in inst and sha.upper() in inst
        assert "https://github.com/o/r/releases/download/v1.2.3/PozzoLauncher-1.2.3-windows-arm64-setup.exe" in inst
        try:
            import yaml
            for f in (out / "winget/manifests/e/erpaffo/PozzoLauncher" / V).iterdir():
                assert yaml.safe_load(f.read_text())["PackageVersion"] == V, f
        except ImportError:
            pass

        sc = json.loads((out / "scoop/pozzo-launcher.json").read_text())
        assert set(sc["architecture"]) == {"64bit", "arm64"} and sc["version"] == V
        assert sc["architecture"]["arm64"]["url"].endswith("windows-arm64.zip")
        assert sc["autoupdate"]["architecture"]["64bit"]["url"].endswith("PozzoLauncher-$version-windows-x64.zip")

        pkg = (out / "aur/PKGBUILD").read_text()
        src = (out / "aur/.SRCINFO").read_text()
        assert "arch=('x86_64' 'aarch64')" in pkg and "source_aarch64=" in pkg and ".pozzo-managed" in pkg
        assert "\tarch = aarch64" in src and f"\tpkgver = {V}" in src and src.startswith("pkgbase = pozzo-launcher-bin")
        assert PM._sha(rel / f"PozzoLauncher-{V}-linux-arm64.tar.gz") in pkg
        if shutil.which("bash"):
            r = subprocess.run(["bash", "-n", str(out / "aur/PKGBUILD")], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr

        cask = (out / "homebrew/Casks/pozzo-launcher.rb").read_text()
        assert 'arch arm: "arm64", intel: "x64"' in cask and "auto_updates true" in cask
        assert 'macos-#{arch}.dmg"\n' in cask and '.dmg""' not in cask
        assert PM._sha(rel / f"PozzoLauncher-{V}-macos-x64.dmg") in cask
        if shutil.which("ruby"):
            r = subprocess.run(["ruby", "-c", str(out / "homebrew/Casks/pozzo-launcher.rb")], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
    print("ok  tutte le varianti: winget, Scoop, AUR e Homebrew")


def test_varianti_mancanti():
    with tempfile.TemporaryDirectory() as t:
        names = [f"PozzoLauncher-{V}-windows-x64-setup.exe", f"PozzoLauncher-{V}-macos-arm64.dmg"]
        rel, out = _release(Path(t), names), Path(t) / "out"
        assert sorted(PM.write(V, rel, out, "o/r")) == ["aur", "scoop"], "senza zip e tar.gz: saltati"
        inst = (out / "winget/manifests/e/erpaffo/PozzoLauncher" / V / "erpaffo.PozzoLauncher.installer.yaml").read_text()
        assert "arm64" not in inst
        cask = (out / "homebrew/Casks/pozzo-launcher.rb").read_text()
        assert "depends_on arch: :arm64" in cask and "arch arm:" not in cask and "macos-arm64.dmg\"\n" in cask
        if shutil.which("ruby"):
            r = subprocess.run(["ruby", "-c", str(out / "homebrew/Casks/pozzo-launcher.rb")], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
        assert not (out / "aur").exists() and not (out / "scoop").exists()
    print("ok  varianti mancanti: fuori dai manifest, gestori senza file saltati")


def test_versione_con_trattino():
    with tempfile.TemporaryDirectory() as t:
        v = "2.0.0-beta1"
        rel = Path(t) / "release"
        rel.mkdir()
        (rel / f"PozzoLauncher-{v}-linux-x64.tar.gz").write_bytes(b"x")
        out = Path(t) / "out"
        PM.write(v, rel, out, "o/r")
        pkg = (out / "aur/PKGBUILD").read_text()
        assert "pkgver=2.0.0_beta1" in pkg and "/v2.0.0-beta1/PozzoLauncher-2.0.0-beta1-linux-x64.tar.gz" in pkg
    print("ok  versione con trattino: pkgver valido per pacman, URL invariati")


if __name__ == "__main__":
    test_tutte_le_varianti()
    test_varianti_mancanti()
    test_versione_con_trattino()
    print("TUTTI I TEST OK")
