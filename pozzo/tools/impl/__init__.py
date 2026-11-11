"""Un modulo per strumento: importarlo lo registra (jobs.register). Elenco esplicito e non pkgutil, perché
PyInstaller non vede i moduli caricati dinamicamente. Un modulo mancante o rotto non blocca gli altri."""
import importlib

MODULES = ("nup", "chd", "rvz", "cso", "dump", "verify", "m3u", "patch")


def load():
    for name in MODULES:
        try:
            importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"{__name__}.{name}":  # modulo esistente ma con una dipendenza mancante
                print(f"[strumenti] {name} non caricato: {e}")
        except Exception as e:
            print(f"[strumenti] {name} non caricato: {e}")
