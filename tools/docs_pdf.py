"""Manuale in PDF: i capitoli di docs/ nell'ordine del "nav" di mkdocs.yml, uniti e convertiti con Pandoc + XeLaTeX.

Uso:  python tools/docs_pdf.py [uscita.pdf] [--font "DejaVu Serif"] [--sans "DejaVu Sans"] [--mono "DejaVu Sans Mono"]
Serve pandoc nel PATH e una distribuzione LaTeX con xelatex (TeX Live, MiKTeX).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# emoji e simboli: i font LaTeX (DejaVu Serif) non li hanno, nel PDF si tolgono o si convertono in ASCII
EMOJI = re.compile(
    "["
    "\u2100-\u214f"          # Letterlike Symbols (ℹ U+2139, ecc.)
    "\u2300-\u23ff"          # Miscellaneous Technical (⏱ U+23F1, ⏳ U+23F3, ⏰ U+23F0, ⏭ U+23ED, ⏮ U+23EE, ecc.)
    "\u2600-\u27bf"          # Miscellaneous Symbols & Dingbats (☀-➿)
    "\u2980-\u29ff"          # Miscellaneous Mathematical Symbols-B (⧉ U+29C9, ecc.)
    "\u2b00-\u2bff"          # Miscellaneous Symbols and Arrows (⬀-⯿)
    "\U0001F000-\U0001FAFF"  # Emoji e simboli supplementari
    "\ufe00-\ufe0f\u200d\u20e3" # Selettori di variazione e combinatori
    "]"
)


def clean_text(text: str) -> str:
    # Sostituzioni di simboli Unicode con equivalenti ASCII
    text = text.replace("\uff0b", "+")   # ＋ fullwidth plus -> +
    text = text.replace("\u22ef", "...") # ⋯ midline horizontal ellipsis -> ...
    return EMOJI.sub("", text)


# blocchi di codice che vanno a capo invece di uscire dal margine
HEADER = r"""
\usepackage{graphicx}
\usepackage{fvextra}
\DefineVerbatimEnvironment{Highlighting}{Verbatim}{breaklines,breakanywhere,commandchars=\\\{\}}
\usepackage{xurl}
\setkeys{Gin}{width=\linewidth,keepaspectratio}
"""

SKIP_PDF = {"index.md", "download.md"}


def pages(nav, lang: str = "it", is_root: bool = True) -> list[str]:
    """File del nav di mkdocs, in ordine (le sezioni si appiattiscono), filtrati per lingua."""
    out = []
    for item in nav:
        for key, value in item.items():
            if is_root:
                if lang == "it" and key == "English Manual":
                    continue
                if lang == "en" and key != "English Manual":
                    continue
            if isinstance(value, str):
                if Path(value).name not in SKIP_PDF:
                    out.append(value)
            else:
                out += pages(value, lang=lang, is_root=False)
    return out


def chapter(name: str) -> str:
    """Un capitolo: titolo con id = nome del file, link fra pagine trasformati in link interni al PDF."""
    text = (DOCS / name).read_text(encoding="utf-8")
    stem = Path(name).stem.lower()
    text = re.sub(r"\A# (.+)", lambda m: f"# {m[1]} {{#{stem}}}", text, count=1)
    text = re.sub(r"\]\((?:en/)?([\w-]+)\.md#([\w-]+)\)", r"](#\2)", text)  # pagina.md#sezione -> #sezione
    text = re.sub(r"\]\((?:en/)?([\w-]+)\.md\)", lambda m: f"](#{m[1].lower()})", text)  # pagina.md -> #pagina
    text = re.sub(r"^> (?:Il manuale è disponibile|The manual is also available).*?(?:\n>.*)*\n", "", text, flags=re.M)
    # Nel markdown temporaneo del PDF, ../images/ e ../img/ diventano images/ e img/
    text = re.sub(r'(?<=[(\"=])\.\./(images|img)/', r'\1/', text)
    return clean_text(text).strip() + "\n"


def version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "pozzo" / "__init__.py").read_text(encoding="utf-8"))
    return m[1] if m else ""


def build(out: Path, font: str, sans: str, mono: str, lang: str | None = None) -> Path:
    if lang is None:
        lang = "en" if ("-en" in out.name or "manual.pdf" in out.name.lower()) else "it"
    nav = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
    md = "\n\n".join(chapter(p) for p in pages(nav, lang=lang))
    subtitle = f"Manual · version {version()}" if lang == "en" else f"Manuale · versione {version()}"
    with tempfile.TemporaryDirectory() as t:
        src, head = Path(t) / "manuale.md", Path(t) / "header.tex"
        shutil.copytree(DOCS / "images", Path(t) / "images")  # le immagini del manuale, accanto al markdown
        if (DOCS / "img").exists():
            shutil.copytree(DOCS / "img", Path(t) / "img")
        src.write_text(md, encoding="utf-8")
        head.write_text(HEADER, encoding="utf-8")
        sep = ";" if os.name == "nt" else ":"
        resource_path = sep.join([".", str(t), str(DOCS), str(DOCS / "images"), str(DOCS / "img")])
        subprocess.run([
            "pandoc", str(src), "-f", "markdown", "-o", str(out.resolve()), "--pdf-engine=xelatex",
            f"--resource-path={resource_path}",
            "--toc", "--toc-depth=2", "--number-sections", "--top-level-division=chapter", "-H", str(head),
            "-M", "title=Pozzo Launcher", "-M", f"subtitle={subtitle}", "-M", f"lang={lang}",
            "-V", "documentclass=report", "-V", "papersize=a4", "-V", "geometry:margin=2.2cm",
            "-V", f"mainfont={font}", "-V", f"sansfont={sans}", "-V", f"monofont={mono}",
            "-V", "colorlinks=true", "-V", "linkcolor=blue", "-V", "urlcolor=blue", "-V", "toccolor=black",
        ], check=True, cwd=t)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", nargs="?", default="PozzoLauncher-manuale.pdf")
    ap.add_argument("--lang", default=None, choices=["it", "en"])
    ap.add_argument("--font", default="DejaVu Serif")
    ap.add_argument("--sans", default="DejaVu Sans")
    ap.add_argument("--mono", default="DejaVu Sans Mono")
    a = ap.parse_args()
    print(build(Path(a.out), a.font, a.sans, a.mono, lang=a.lang))
