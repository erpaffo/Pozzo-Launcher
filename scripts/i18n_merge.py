"""Unisce i blocchi tradotti scratch/i18n/tr/<lingua>/NN.json in pozzo/data/locales/<lingua>.json.
Si accetta chiave per chiave: il valore deve avere gli stessi {segnaposto} e gli stessi tag HTML dell'italiano e non
essere vuoto. Le chiavi scartate o mancanti vanno in scratch/i18n/tr/redo_<lingua>.json (da ritradurre); nel
frattempo l'app ricade sull'italiano. Uso: python scripts/i18n_merge.py [lingua ...]"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TR = ROOT / "scratch" / "i18n" / "tr"
OUT = ROOT / "pozzo" / "data" / "locales"
ph = lambda s: sorted(re.findall(r"\{\w+\}", s))
tags = lambda s: sorted(re.findall(r"</?\w+", s))


def good(src: str, v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and ph(v) == ph(src) and tags(v) == tags(src)


def main(langs: list[str]) -> int:
    srcs = sorted(TR.glob("src_*.json"))
    langs = langs or sorted(p.name for p in TR.iterdir() if p.is_dir())
    pending = 0
    for lang in langs:
        merged, redo, missing = {}, {}, []
        for s in srcs:
            n = s.stem.split("_")[1]
            src = json.loads(s.read_text(encoding="utf-8"))
            f = TR / lang / f"{n}.json"
            got = None
            if f.is_file():
                try:
                    got = json.loads(f.read_text(encoding="utf-8"))
                except ValueError as e:
                    print(f"{lang}/{n}: JSON non valido ({e})")
            if got is None:
                missing.append(n)
                continue
            for k, v in src.items():
                if k in got and good(v, got[k]):
                    merged[k] = got[k]
                else:
                    redo[k] = v
        if merged:
            (OUT / f"{lang}.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        redo_file = TR / f"redo_{lang}.json"
        if redo:
            redo_file.write_text(json.dumps(redo, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            redo_file.unlink(missing_ok=True)
        pending += len(redo) + len(missing)
        print(f"{lang}: {len(merged)} chiavi unite, da rifare {len(redo)}" + (f", blocchi mancanti {missing}" if missing else ""))
    return 1 if pending else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
