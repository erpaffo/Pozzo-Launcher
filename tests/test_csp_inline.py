"""Anti-regressione CSP: niente gestori inline (onclick=, onerror=...) e niente <script> inline nel frontend.
Con la CSP in enforce (script-src 'self') il browser bloccherebbe entrambi, quindi la UI si romperebbe in silenzio.
Le immagini rotte si gestiscono con data-onerr / data-fb (vedi pozzo/app/static/imgfallback.js).

Scansione statica: una regex per i gestori, una per i tag <script>. I blocchi JSON (type="application/json")
sono dati e sono ammessi, come i tag con src.
Uso: PYTHONUTF8=1 python tests/test_csp_inline.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [ROOT / "pozzo" / "app" / "static", ROOT / "extensions"]
# Cartelle di terze parti: non le scriviamo noi, non le scansioniamo (oggi non ce ne sono con questi nomi).
SKIP_DIRS = {"vendor", "lib", "third_party", "node_modules"}

HANDLER = re.compile(r""" on[a-z]+=["'\\]""", re.IGNORECASE)
SCRIPT = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
HAS_SRC = re.compile(r"(?:^|\s)src\s*=", re.IGNORECASE)
JSON_TYPE = re.compile(r"""type\s*=\s*["']application/json["']""", re.IGNORECASE)


def scan_text(src):
    """Ritorna [(riga, descrizione)] per ogni gestore inline o <script> inline in src."""
    out = []
    for m in HANDLER.finditer(src):
        out.append((src.count("\n", 0, m.start()) + 1, "gestore inline " + m.group(0).strip()))
    for m in SCRIPT.finditer(src):
        attrs = m.group(1)
        if HAS_SRC.search(attrs) or JSON_TYPE.search(attrs):
            continue
        out.append((src.count("\n", 0, m.start()) + 1, "<script> inline"))
    return sorted(out)


def strip_js_comments(src):
    """Nei .js le righe di solo commento // possono citare <script> senza che sia markup: le svuota (righe intatte)."""
    return "\n".join("" if ln.lstrip().startswith("//") else ln for ln in src.split("\n"))


def selftest():
    """La scansione deve distinguere il caso sicuro da quello vietato, altrimenti il test non vale niente."""
    assert scan_text(strip_js_comments("x();\n// usa <script> qui\ny();")) == []
    assert strip_js_comments("a\n// b\nc").count("\n") == 2
    for ok in ('el.addEventListener("click", f);', 'const json = 1; let on = 2;',
               '<script src="a.js"></script>', '<script type="application/json" id="x">{}</script>',
               '<img data-onerr="remove" data-fb="/x.png">', '<script type=\'application/json\'>[]</script>'):
        assert scan_text(ok) == [], ok
    for bad in ('<button onclick="f()">', "<img src='a' onerror='y'>", '<div onMouseOver="x">',
                '<script>alert(1)</script>', '<script type="module">x</script>', '<script\n  defer>x</script>'):
        assert scan_text(bad), bad
    assert scan_text('a\n<b onclick="x">') == [(2, "gestore inline onclick=\"")]


def scanned_files():
    files = []
    for base in SCAN_DIRS:
        for p in base.rglob("*"):
            if p.suffix not in (".html", ".js") or p.name.endswith(".min.js"):
                continue
            if set(p.relative_to(base).parts[:-1]) & SKIP_DIRS:
                continue
            files.append(p)
    return sorted(files)


def main():
    selftest()
    files = scanned_files()
    bad = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        src = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix == ".js":
            src = strip_js_comments(src)
        for line, what in scan_text(src):
            bad.append(f"{rel}:{line}: {what}")
    if bad:
        print("\n".join(bad))
    print(f"{len(files)} file scansionati, {len(bad)} violazioni CSP")
    assert not bad, "gestori o script inline: spostali in addEventListener / delega, o data-onerr per le immagini"


if __name__ == "__main__":
    main()
    print("OK")
    sys.exit(0)
