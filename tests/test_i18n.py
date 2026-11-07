"""Cataloghi coerenti con it.json e API delle traduzioni."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import i18n_check
from pozzo import i18n as I

assert not i18n_check.problems(), i18n_check.problems()
assert I.tr("app.language", "xx") == "Lingua"            # lingua sconosciuta -> italiano
assert I.tr("chiave.inesistente") == "chiave.inesistente"
assert I.catalog("en")["app.language"] == "Language"
assert set(I.languages()) == {"it", "en", "es", "fr", "de", "pt-BR", "tr"}
assert I.from_request("ru", None) == "en"                 # cookie di una lingua rimossa -> inglese
assert I.from_request(None, "ru-RU,ru;q=0.9") == "it"     # nessuna lingua supportata -> italiano
print("ok")
