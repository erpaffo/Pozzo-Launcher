"""Stringhe lunghe nelle lingue: etichette brevi in de, pt-BR, tr che superano 1.6 volte l'italiano.

Fallisce solo su chiavi mancanti o {segnaposto} diversi dall'italiano. Il resto e' informativo: stampa
le etichette piu' lunghe, da controllare a mano nel layout (pulsanti, voci della barra, tessere).

Esegui: PYTHONUTF8=1 python tests/test_i18n_long.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LOCALES = Path(__file__).resolve().parents[1] / "pozzo" / "data" / "locales"
LANGS = ["de", "pt-BR", "tr"]
SHORT_MAX = 20      # un'etichetta e' "breve" se l'italiano sta in 20 caratteri
RATIO_MAX = 1.6     # oltre questo rapporto la stringa e' segnalata
PH = re.compile(r"\{\w+\}")

it = json.loads((LOCALES / "it.json").read_text(encoding="utf-8"))
problems: list[str] = []
long_labels: list[tuple[float, str, str, str]] = []  # (rapporto, lingua, chiave, testo)

for lang in LANGS:
    cat = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    for key, src in it.items():
        if key not in cat:
            problems.append(f"{lang}: manca {key}")
            continue
        text = cat[key]
        if sorted(PH.findall(text)) != sorted(PH.findall(src)):
            problems.append(f"{lang}: segnaposto diversi in {key} ({PH.findall(src)} -> {PH.findall(text)})")
        if not isinstance(src, str) or not src or len(src) > SHORT_MAX or "\n" in src:
            continue
        ratio = len(text) / len(src)
        if ratio > RATIO_MAX:
            long_labels.append((ratio, lang, key, text))

assert not problems, "\n".join(problems[:50])

# informativo: conteggio per lingua e le piu' lunghe
for lang in LANGS:
    rows = [r for r in long_labels if r[1] == lang]
    print(f"{lang}: {len(rows)} etichette brevi oltre {RATIO_MAX}x l'italiano")
for ratio, lang, key, text in sorted(long_labels, reverse=True)[:25]:
    print(f"  {lang:6} {ratio:4.2f}x  {key}: {it[key]!r} -> {text!r}")

print("ok")
