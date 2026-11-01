"""tools/progress.py: spunta insieme TODO e CSV, aggiunge righe nel gruppo giusto.

Esegui: python tests/test_progress.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import progress  # noqa: E402

TODO_TEXT = "## Uno\n\n[ ] **[H]** Prima cosa — v0.12.0\n    - nota\n\n## Due\n\n[ ] **[M]** Seconda cosa — v0.13.0\n"
CSV_ROWS = [["Done", "Task", "Status", "Priority", "Version", "Notes"],
            ["No", "Prima cosa", "Not started", "High", "v0.12.0", "[Uno] nota"],
            ["No", "Seconda cosa", "Not started", "Medium", "v0.13.0", "[Due]"]]


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        todo, csv_path = Path(d) / "TODO.md", Path(d) / "p.csv"
        todo.write_text(TODO_TEXT, encoding="utf-8")
        progress._write_csv(csv_path, CSV_ROWS)

        progress.done(todo, csv_path, "prima", version="v0.12.1")
        text = todo.read_text(encoding="utf-8")
        assert "[x] **[H]** Prima cosa — v0.12.1" in text and "[ ] **[M]** Seconda" in text
        rows = list(csv.reader(open(csv_path, encoding="utf-8")))
        assert rows[1][:5] == ["Yes", "Prima cosa", "Done", "High", "v0.12.1"] and rows[2][0] == "No"

        progress.done(todo, csv_path, "seconda", status="In progress")
        assert "[ ] **[M]** Seconda cosa — v0.13.0" in todo.read_text(encoding="utf-8")

        progress.add(todo, csv_path, "Terza cosa", "L", "Uno", "v0.16.0", "dettaglio")
        text = todo.read_text(encoding="utf-8")
        assert text.index("Terza cosa") < text.index("## Due"), "la voce va nel gruppo Uno"
        assert list(csv.reader(open(csv_path, encoding="utf-8")))[-1][1:5] == ["Terza cosa", "Not started", "Low", "v0.16.0"]

        for bad in ("cosa", "inesistente"):  # ambiguo o assente
            try:
                progress.done(todo, csv_path, bad)
            except SystemExit:
                continue
            raise AssertionError(f"«{bad}» doveva fallire")
    print("ok  progress: done, add, titoli ambigui o mancanti")


if __name__ == "__main__":
    main()
