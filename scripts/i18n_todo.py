"""Cosa manca da tradurre nei cataloghi, e come inserirlo.

  python scripts/i18n_todo.py            JSON {lingua: {chiave: {"it":..., "en":...}}} delle chiavi da tradurre:
                                         mancanti, oppure uguali all'inglese (copiate senza tradurre)
  python scripts/i18n_todo.py apply F    unisce F ({lingua: {chiave: traduzione}}) nei cataloghi, scartando i valori
                                         con {segnaposto} o tag diversi dall'italiano
Una voce uguale all'inglese puo' essere giusta (nomi propri, sigle): se lo e', basta lasciarla fuori da F.
"""
import json
import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "pozzo" / "data" / "locales"
ph = lambda s: sorted(re.findall(r"\{\w+\}", s))
tags = lambda s: sorted(re.findall(r"</?\w+", s))
load = lambda l: json.loads((DIR / f"{l}.json").read_text(encoding="utf-8"))


def todo() -> dict:
    it, en, out = load("it"), load("en"), {}
    for f in sorted(DIR.glob("*.json")):
        if f.stem in ("it", "en"):
            continue
        cat = load(f.stem)
        # shortcut: "uguale all'inglese" include nomi e sigle legittimi; li scarta chi traduce
        ks = [k for k in it if k not in cat or (cat[k] == en.get(k) and it[k] != en.get(k))]
        if ks:
            out[f.stem] = {k: {"it": it[k], "en": en.get(k, "")} for k in ks}
    return out


def apply(path: str) -> None:
    it, new = load("it"), json.loads(Path(path).read_text(encoding="utf-8"))
    for lang, tr in new.items():
        f = DIR / f"{lang}.json"
        raw = f.read_bytes().decode("utf-8")
        cat = json.loads(raw)
        bad = [k for k, v in tr.items() if k not in it or not isinstance(v, str) or not v.strip()
               or ph(v) != ph(it[k]) or tags(v) != tags(it[k])]
        cat.update({k: v for k, v in tr.items() if k not in bad})
        cat = {k: cat[k] for k in it if k in cat}  # stesso ordine di it.json
        text = json.dumps(cat, ensure_ascii=False, indent=1) + "\n"
        f.write_bytes((text.replace("\n", "\r\n") if "\r\n" in raw else text).encode("utf-8"))
        print(f"{lang}: {len(tr) - len(bad)} unite" + (f", scartate {bad}" if bad else ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows: cp1252
    if sys.argv[1:2] == ["apply"]:
        apply(sys.argv[2])
    else:
        print(json.dumps(todo(), ensure_ascii=False, indent=1))
