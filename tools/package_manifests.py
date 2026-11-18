"""Manifest dei gestori di pacchetti per una release: winget, Scoop, AUR (PKGBUILD + .SRCINFO) e Homebrew (cask).

Uso: python tools/package_manifests.py <versione> <cartella-release> <cartella-uscita> [owner/repo]

Legge i file della release (nomi creati da .github/workflows/release.yml) per le impronte SHA-256. Una variante
senza file (build fallita) resta fuori dal manifest; un gestore senza nessun file per il suo sistema viene saltato
e lo dice. I job publish-* di release.yml copiano poi l'uscita nei repository dei rispettivi gestori.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESC = "Game library for ROMs and PC games from the stores, with covers and metadata."
NAME = "pozzo-launcher"  # Scoop, AUR (-bin) e Homebrew: stesso nome ovunque
WINGET_ID = "PozzoDev.PozzoLauncher"
# librerie del plugin xcb di Qt: le stesse del .deb (release.yml), con i nomi dei pacchetti di Arch
AUR_DEPENDS = ["libglvnd", "nss", "libxkbcommon-x11", "libxcb", "xcb-util-cursor", "xcb-util-wm", "xcb-util-image",
               "xcb-util-keysyms", "xcb-util-renderutil"]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def found(release: Path, version: str) -> dict[tuple[str, str], tuple[str, str]]:
    """{(tipo, arch): (nome del file, sha256)} per i file della release che servono ai manifest."""
    names = {("setup", "x64"): f"PozzoLauncher-{version}-windows-x64-setup.exe",
             ("setup", "arm64"): f"PozzoLauncher-{version}-windows-arm64-setup.exe",
             ("zip", "x64"): f"PozzoLauncher-{version}-windows-x64.zip",
             ("zip", "arm64"): f"PozzoLauncher-{version}-windows-arm64.zip",
             ("dmg", "x64"): f"PozzoLauncher-{version}-macos-x64.dmg",
             ("dmg", "arm64"): f"PozzoLauncher-{version}-macos-arm64.dmg",
             ("tar", "x64"): f"PozzoLauncher-{version}-linux-x64.tar.gz",
             ("tar", "arm64"): f"PozzoLauncher-{version}-linux-arm64.tar.gz"}
    return {k: (n, _sha(release / n)) for k, n in names.items() if (release / n).is_file()}


def winget(version: str, base: str, repo: str, a: dict) -> dict[str, str]:
    """I tre file di winget-pkgs (versione, metadati, installer); {} senza installer Windows."""
    inst = [(arch, *a[("setup", arch)]) for arch in ("x64", "arm64") if ("setup", arch) in a]
    if not inst:
        return {}
    head = f"PackageIdentifier: {WINGET_ID}\nPackageVersion: {version}\n"
    tail = "ManifestVersion: 1.6.0\n"
    installers = "".join(f"  - Architecture: {arch}\n    InstallerUrl: {base}/{n}\n    InstallerSha256: {s.upper()}\n"
                         for arch, n, s in inst)
    home = f"https://github.com/{repo}"
    return {
        f"{WINGET_ID}.yaml": head + "DefaultLocale: en-US\nManifestType: version\n" + tail,
        f"{WINGET_ID}.locale.en-US.yaml": head + (
            "PackageLocale: en-US\nPublisher: PozzoDev\n"
            f"PublisherUrl: {home}\nPublisherSupportUrl: {home}/issues\nPackageName: Pozzo Launcher\n"
            f"PackageUrl: {home}\nLicense: MIT\nLicenseUrl: {home}/blob/main/LICENSE\nShortDescription: {DESC}\n"
            "Moniker: pozzo\nTags:\n  - games\n  - rom\n  - emulation\n  - library\n"
            f"ReleaseNotesUrl: {home}/releases/tag/v{version}\nManifestType: defaultLocale\n") + tail,
        # setup Inno per-utente (PrivilegesRequired=lowest in installer.iss): Scope user, nessuna richiesta UAC
        f"{WINGET_ID}.installer.yaml": head + (
            "MinimumOSVersion: 10.0.0.0\nInstallerType: inno\nScope: user\nInstallerSwitches:\n"
            "  Silent: /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-\n"
            "  SilentWithProgress: /SILENT /SUPPRESSMSGBOXES /NORESTART /SP-\n"
            "UpgradeBehavior: install\nInstallers:\n" + installers + "ManifestType: installer\n") + tail,
    }


def scoop(version: str, base: str, repo: str, a: dict) -> str | None:
    """Manifest di Scoop (versione portatile); None senza zip Windows."""
    keys = {"x64": "64bit", "arm64": "arm64"}
    arch = {keys[x]: {"url": f"{base}/{a[('zip', x)][0]}", "hash": a[("zip", x)][1], "extract_dir": "PozzoLauncher"}
            for x in ("x64", "arm64") if ("zip", x) in a}
    if not arch:
        return None
    auto = {keys[x]: {"url": f"https://github.com/{repo}/releases/download/v$version/PozzoLauncher-$version-windows-{x}.zip"}
            for x in ("x64", "arm64") if keys[x] in arch}
    return json.dumps({"version": version, "description": DESC, "homepage": f"https://github.com/{repo}",
                       "license": "MIT", "architecture": arch, "bin": "PozzoLauncher.exe",
                       "shortcuts": [["PozzoLauncher.exe", "Pozzo Launcher"]], "checkver": "github",
                       "autoupdate": {"architecture": auto}}, indent=4) + "\n"


def aur(version: str, base: str, repo: str, a: dict) -> dict[str, str]:
    """PKGBUILD e .SRCINFO di pozzo-launcher-bin; {} senza tar.gz Linux."""
    arches = [(arch, *a[("tar", x)]) for x, arch in (("x64", "x86_64"), ("arm64", "aarch64")) if ("tar", x) in a]
    if not arches:
        return {}
    pkgver = version.replace("-", "_")  # pacman non accetta «-» nella versione
    raw = f"https://raw.githubusercontent.com/{repo}/v{version}"
    common = [(f"pozzo.png::{raw}/packaging/icon.png", _sha(ROOT / "packaging" / "icon.png")),
              (f"LICENSE::{raw}/LICENSE", _sha(ROOT / "LICENSE"))]
    q = lambda xs: " ".join(f"'{x}'" for x in xs)  # noqa: E731
    lines = [
        "# Maintainer: erpaffo",
        "# Generato da tools/package_manifests.py nel workflow di release: le modifiche vanno fatte li'.",
        f"pkgname={NAME}-bin", f"pkgver={pkgver}", "pkgrel=1", f'pkgdesc="{DESC}"',
        f"arch=({q(x for x, _, _ in arches)})", f'url="https://github.com/{repo}"', "license=('MIT')",
        f"depends=({q(AUR_DEPENDS)})", f"provides=('{NAME}')", f"conflicts=('{NAME}')",
        "options=('!strip' '!debug')",  # binari PyInstaller: strip li rompe
        f"source=({q(s for s, _ in common)})", f"sha256sums=({q(h for _, h in common)})",
    ]
    for arch, n, h in arches:
        lines += [f"source_{arch}=('{n}::{base}/{n}')", f"sha256sums_{arch}=('{h}')"]
    lines += ["", "package() {",
              '  install -d "$pkgdir/opt" "$pkgdir/usr/bin"',
              '  cp -a PozzoLauncher "$pkgdir/opt/PozzoLauncher"',
              "  # file di pacman: l'app non si aggiorna da sola (pozzo/updates.py, MANAGED)",
              '  echo aur > "$pkgdir/opt/PozzoLauncher/.pozzo-managed"',
              '  ln -s /opt/PozzoLauncher/PozzoLauncher "$pkgdir/usr/bin/pozzo"',
              '  install -Dm644 pozzo.png "$pkgdir/usr/share/pixmaps/pozzo.png"',
              '  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"',
              '  install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/pozzo.desktop" <<EOF',
              "[Desktop Entry]", "Type=Application", "Name=Pozzo Launcher",
              "Comment=Libreria di giochi: ROM e store PC", "Exec=/opt/PozzoLauncher/PozzoLauncher",
              "Icon=pozzo", "Categories=Game;", "EOF", "}", ""]
    # .SRCINFO: quello che makepkg --printsrcinfo scriverebbe (qui non c'e' Arch per lanciarlo)
    src = [f"pkgbase = {NAME}-bin", f"\tpkgdesc = {DESC}", f"\tpkgver = {pkgver}", "\tpkgrel = 1",
           f"\turl = https://github.com/{repo}", *(f"\tarch = {x}" for x, _, _ in arches), "\tlicense = MIT",
           *(f"\tdepends = {d}" for d in AUR_DEPENDS), f"\tprovides = {NAME}", f"\tconflicts = {NAME}",
           "\toptions = !strip", "\toptions = !debug", *(f"\tsource = {s}" for s, _ in common),
           *(f"\tsha256sums = {h}" for _, h in common)]
    for arch, n, h in arches:
        src += [f"\tsource_{arch} = {n}::{base}/{n}", f"\tsha256sums_{arch} = {h}"]
    src += ["", f"pkgname = {NAME}-bin", ""]
    return {"PKGBUILD": "\n".join(lines), ".SRCINFO": "\n".join(src)}


def brew(version: str, base: str, repo: str, a: dict) -> str | None:
    """Cask di Homebrew per il tap; None senza .dmg macOS."""
    have = [x for x in ("arm64", "x64") if ("dmg", x) in a]
    if not have:
        return None
    url = f"https://github.com/{repo}/releases/download/v#{{version}}/PozzoLauncher-#{{version}}-macos-"
    if len(have) == 2:
        arch = '  arch arm: "arm64", intel: "x64"\n\n'
        sha = f'  sha256 arm:   "{a[("dmg", "arm64")][1]}",\n         intel: "{a[("dmg", "x64")][1]}"\n'
        url += "#{arch}.dmg"
        dep = ""
    else:  # una sola variante: Homebrew deve rifiutarla sull'altro processore
        arch, x = "", have[0]
        sha = f'  sha256 "{a[("dmg", x)][1]}"\n'
        url += f"{x}.dmg"
        dep = f"  depends_on arch: :{'arm64' if x == 'arm64' else 'x86_64'}\n"
    return (
        "# Generato da tools/package_manifests.py nel workflow di release: le modifiche vanno fatte li'.\n"
        f'cask "{NAME}" do\n{arch}  version "{version}"\n{sha}\n  url "{url}"\n'
        f'  name "Pozzo Launcher"\n  desc "{DESC.rstrip(".")}"\n  homepage "https://github.com/{repo}"\n\n'
        "  livecheck do\n    url :url\n    strategy :github_latest\n  end\n\n"
        "  # l'app si aggiorna da sola (Impostazioni > Info): brew non la riporta indietro\n"
        f'  auto_updates true\n{dep}  depends_on macos: ">= :big_sur"\n\n  app "PozzoLauncher.app"\n\n'
        "  # firma ad-hoc, non notarizzata: senza togliere la quarantena macOS la dice «danneggiata»\n"
        "  postflight do\n"
        '    system_command "/usr/bin/xattr",\n'
        '                   args: ["-dr", "com.apple.quarantine", "#{appdir}/PozzoLauncher.app"]\n'
        "  end\nend\n")


def write(version: str, release: Path, out: Path, repo: str) -> list[str]:
    """Scrive i manifest in out/{winget,scoop,aur,homebrew}; ritorna i gestori saltati per mancanza di file."""
    a = found(release, version)
    base = f"https://github.com/{repo}/releases/download/v{version}"
    skipped = []
    files = winget(version, base, repo, a)
    for n, text in files.items():
        p = out / "winget" / "manifests" / "p" / "PozzoDev" / "PozzoLauncher" / version / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if not files:
        skipped.append("winget")
    for name, text, dest in (("scoop", scoop(version, base, repo, a), out / "scoop" / f"{NAME}.json"),
                             ("homebrew", brew(version, base, repo, a), out / "homebrew" / "Casks" / f"{NAME}.rb")):
        if text is None:
            skipped.append(name)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    files = aur(version, base, repo, a)
    for n, text in files.items():
        (out / "aur").mkdir(parents=True, exist_ok=True)
        (out / "aur" / n).write_text(text, encoding="utf-8")
    if not files:
        skipped.append("aur")
    return skipped


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    repo = sys.argv[4] if len(sys.argv) == 5 else os.environ.get("GITHUB_REPOSITORY", "erpaffo/Pozzo-Launcher")
    for m in write(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), repo):
        print(f"::warning::{m}: nessun file della release per questo gestore, manifest non generato")
