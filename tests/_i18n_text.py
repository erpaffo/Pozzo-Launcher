"""Le stringhe della UI ora stanno in pozzo/data/locales/it.json: i test che cercano testo italiano nei .js lo trovano
leggendo anche il catalogo. Importare questo modulo basta (aggiunge il catalogo in coda ai .js sotto static/)."""
from pathlib import Path

_STATIC = Path(__file__).resolve().parents[1] / "pozzo" / "app" / "static"
_CAT = (Path(__file__).resolve().parents[1] / "pozzo" / "data" / "locales" / "it.json").read_text(encoding="utf-8")
_orig = Path.read_text


def _read_text(self, *a, **k):
    text = _orig(self, *a, **k)
    return text + "\n" + _CAT if self.suffix == ".js" and _STATIC in self.resolve().parents else text


Path.read_text = _read_text
