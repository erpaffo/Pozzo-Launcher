"""Aggiornamento su macOS: nessun file non sigillato nel .app e riscrittura del sigillo dopo lo swap."""

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo import updates


def _swap(platform, base):
    old = sys.platform
    sys.platform = platform
    try:
        cmd = updates.swap_script(base, Path("/s/stage"), Path("/a/App"), 42)
    finally:
        sys.platform = old
    return Path(cmd[-1]).read_text(encoding="utf-8")


def test_stage_has_no_manifest_in_bundle():
    old = sys.platform
    sys.platform = "darwin"
    try:
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            app, stage, pkg = root / "P.app", root / ".P.app.stage-x", root / "p.zip"
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "a.txt").write_bytes(b"a")
            (app / updates.MANIFEST).write_text("vecchio")  # installazione precedente col manifest nel bundle
            new = {"version": "9.9.9", "file": {}}
            real = (updates._extract_package, updates._prune_removed, updates._overlay, updates._verify_files,
                    updates._platform_files)
            updates._extract_package = lambda p, u, k: u.mkdir()
            updates._prune_removed = lambda *a: None
            updates._overlay = lambda *a: None
            updates._verify_files = lambda *a: None
            updates._platform_files = lambda *a: {}
            try:
                updates._stage_full(app, stage, pkg, "portable", None, new, "macos")
            finally:
                updates._extract_package, updates._prune_removed, updates._overlay, updates._verify_files, \
                    updates._platform_files = real
            assert (root / ".P.app.manifest.json").is_file()
            assert not (stage / "Contents" / updates.MANIFEST).exists()
            # unico residuo ammesso nello stage: il vecchio manifest copiato, che lo swap rimuove
            assert {p.name for p in stage.iterdir()} <= {"Contents", updates.MANIFEST}
            assert updates._manifest_path(app) == root / ".P.app.manifest.json"
    finally:
        sys.platform = old


def test_swap_script_resigns_on_mac():
    with tempfile.TemporaryDirectory() as t:
        s = _swap("darwin", Path(t))
    assert "xattr -cr /a/App" in s and "codesign --force --deep -s - /a/App" in s
    assert s.index("rm -rf") < s.index("codesign") < s.index("open /a/App")
    assert f"rm -f /a/App/{updates.MANIFEST}" in s


def test_swap_script_unchanged_elsewhere():
    with tempfile.TemporaryDirectory() as t:
        assert _swap("linux", Path(t)) == (
            "#!/bin/sh\nwhile kill -0 42 2>/dev/null; do sleep 1; done\nmv /a/App /a/.App.old-42 || exit 1\n"
            "if ! mv /s/stage /a/App; then mv /a/.App.old-42 /a/App; exit 1; fi\nrm -rf /a/.App.old-42\n"
            "/a/App/PozzoLauncher &\n")
        assert _swap("win32", Path(t)) == (
            '@echo off\nchcp 65001 >nul\nset S=%SystemRoot%\\System32\n:wait\n"%S%\\tasklist.exe" /FI "PID eq 42" | '
            '"%S%\\find.exe" "42" >nul && ("%S%\\timeout.exe" /t 1 /nobreak >nul & goto wait)\n'
            'move "/a/App" "/a/.App.old-42" >nul\nif errorlevel 1 exit /b 1\n'
            'move "/s/stage" "/a/App" >nul\nif errorlevel 1 (move "/a/.App.old-42" "/a/App" >nul & exit /b 1)\n'
            'rmdir /S /Q "/a/.App.old-42"\nstart "" "/a/App/PozzoLauncher.exe"\n')
        old = sys.platform
        sys.platform = "linux"
        try:
            assert updates._manifest_path(Path("/a/App")) == Path("/a/App") / updates.MANIFEST
        finally:
            sys.platform = old


if __name__ == "__main__":
    test_stage_has_no_manifest_in_bundle()
    test_swap_script_resigns_on_mac()
    test_swap_script_unchanged_elsewhere()
    print("ok")
