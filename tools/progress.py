"""Aggiorna docs/TODO.md e pozzo-progressi.csv insieme, a fine di ogni task.

  python tools/progress.py done "<titolo>" [--status Done|"In progress"] [--version v0.12.0]
  python tools/progress.py add  "<titolo>" --priority H|M|L --group "<gruppo>" [--version v0.12.0] [--notes "..."]

Il titolo si cerca per sottostringa e deve essere unico. Un file di blocco evita che due agenti scrivano insieme.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODO = ROOT / "docs" / "TODO.md"
CSV = ROOT / "pozzo-progressi.csv"
LOCK = ROOT / ".progress.lock"
PRIORITY = {"H": "High", "M": "Medium", "L": "Low"}
ITEM = re.compile(r"^\[( |x)\] (\*\*\[[HML]\]\*\* )?(.*?)( — v[\d.]+)?$")


def _read_csv(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows(rows)


def _find(items: list[str], title: str) -> int:
    hits = [i for i, t in enumerate(items) if title.lower() in t.lower()]
    if len(hits) != 1:
        raise SystemExit(f"«{title}»: {len(hits)} corrispondenze, serve un titolo unico")
    return hits[0]


def done(todo: Path, csv_path: Path, title: str, status: str = "Done", version: str = "") -> None:
    rows = _read_csv(csv_path)
    row = rows[_find([r[1] for r in rows[1:]], title) + 1]
    row[0], row[2] = ("Yes" if status in ("Done", "Dropped") else "No"), status
    if version:
        row[4] = version
    lines = todo.read_text(encoding="utf-8").split("\n")
    idx = [i for i, line in enumerate(lines) if (m := ITEM.match(line)) and row[1].lower() in m.group(3).lower()]
    if len(idx) == 1:
        m = ITEM.match(lines[idx[0]])
        mark = "x" if status in ("Done", "Dropped") else " "
        ver = f" — {version}" if version else (m.group(4) or "")
        lines[idx[0]] = f"[{mark}] {m.group(2) or ''}{m.group(3)}{ver}"
        todo.write_text("\n".join(lines), encoding="utf-8")
    _write_csv(csv_path, rows)


def add(todo: Path, csv_path: Path, title: str, priority: str, group: str, version: str = "", notes: str = "") -> None:
    rows = _read_csv(csv_path)
    if any(r[1].lower() == title.lower() for r in rows[1:]):
        raise SystemExit(f"«{title}» esiste già")
    rows.append(["No", title, "Not started", PRIORITY[priority], version, f"[{group}] {notes}".strip()])
    _write_csv(csv_path, rows)
    ver = f" — {version}" if version else ""
    entry = f"[ ] **[{priority}]** {title}{ver}\n" + (f"    - {notes}\n" if notes else "")
    text = todo.read_text(encoding="utf-8")
    head = re.search(rf"^## {re.escape(group)}\s*$", text, re.M)
    if not head:
        text = text.rstrip("\n") + f"\n\n## {group}\n\n{entry}"
    else:
        nxt = re.search(r"^## ", text[head.end():], re.M)
        end = head.end() + nxt.start() if nxt else len(text)
        text = text[:end].rstrip("\n") + "\n" + entry + ("\n" if nxt else "") + text[end:]
    todo.write_text(text, encoding="utf-8")


def locked(fn, *args, **kw):
    for _ in range(100):  # shortcut: blocco semplice, 10 s di attesa: basta per qualche agente in parallelo
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            time.sleep(0.1)
    else:
        raise SystemExit("blocco occupato: se nessuno sta scrivendo, cancella .progress.lock")
    try:
        return fn(*args, **kw)
    finally:
        os.close(fd)
        os.unlink(LOCK)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["done", "add"])
    ap.add_argument("title")
    ap.add_argument("--status", default="Done")
    ap.add_argument("--version", default="")
    ap.add_argument("--priority", choices=list(PRIORITY), default="M")
    ap.add_argument("--group", default="")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)
    if a.action == "done":
        locked(done, TODO, CSV, a.title, a.status, a.version)
    else:
        if not a.group:
            raise SystemExit("add richiede --group")
        locked(add, TODO, CSV, a.title, a.priority, a.group, a.version, a.notes)
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1:])
