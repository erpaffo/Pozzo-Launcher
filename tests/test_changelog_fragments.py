"""`tools/version.py fragments` su una copia di prova: i frammenti finiscono in «in preparazione» e vengono cancellati.

Esegui: python tests/test_changelog_fragments.py   (o pytest tests/test_changelog_fragments.py)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "tools" / "version.py"
OLD = "# Changelog\n\nIntro.\n\n## 0.2.1 (2026-01-01)\n\n### Corretto\n\n- vecchio\n"


def setup(t: Path) -> Path:
    (t / "tools").mkdir()
    shutil.copy(SRC, t / "tools" / "version.py")
    (t / "pozzo").mkdir()
    (t / "pozzo" / "__init__.py").write_text('__version__ = "0.2.1"\n')
    (t / "changelog.md").write_text(OLD)
    frag = t / "docs" / "changelog.d"
    frag.mkdir(parents=True)
    (frag / "b-task.md").write_text("### Aggiunto\nnuova cosa\n")
    (frag / "a-task.md").write_text("- uno\n")
    (frag / "README.md").write_text("istruzioni\n")
    # 0.2.1 e' gia' su GitHub (origin/main): il changelog sopra va in «in preparazione» come sezione nuova
    git = lambda *a: subprocess.run(["git", *a], cwd=t, check=True, capture_output=True)  # noqa: E731
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "Version 0.2.1")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    return frag


def run(t: Path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "tools/version.py", "fragments"], cwd=t, capture_output=True, text=True,
                          encoding="utf-8", env=env)


def test_fragments_go_to_pending_and_are_removed():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        t = Path(d)
        frag = setup(t)
        r = run(t)
        assert r.returncode == 0, r.stderr
        text = (t / "changelog.md").read_text(encoding="utf-8")
        assert text.startswith("# Changelog\n\nIntro.\n\n## Non rilasciato\n"), text
        assert "### Cambiato\n\n- uno" in text, text
        assert "### Aggiunto\n\n- nuova cosa" in text, text
        assert text.endswith("### Corretto\n\n- vecchio\n"), text  # la versione pubblicata non si tocca
        assert not (frag / "a-task.md").exists() and not (frag / "b-task.md").exists()
        assert (frag / "README.md").exists()


def test_second_run_is_noop():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        t = Path(d)
        setup(t)
        assert run(t).returncode == 0
        before = (t / "changelog.md").read_text(encoding="utf-8")
        r = run(t)
        assert r.returncode == 0 and "Nessun frammento" in r.stdout, r.stdout
        assert (t / "changelog.md").read_text(encoding="utf-8") == before


def test_unknown_subsection_fails_and_keeps_fragments():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        t = Path(d)
        frag = setup(t)
        (frag / "c-task.md").write_text("### Inventato\n- roba\n")
        r = run(t)
        assert r.returncode != 0
        assert (frag / "c-task.md").exists() and (frag / "a-task.md").exists()
        assert (t / "changelog.md").read_text(encoding="utf-8") == OLD


if __name__ == "__main__":
    test_fragments_go_to_pending_and_are_removed()
    test_second_run_is_noop()
    test_unknown_subsection_fails_and_keeps_fragments()
    print("ok")
