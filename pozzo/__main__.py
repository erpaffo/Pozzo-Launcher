import sys

try:
    from .cli import main
except ModuleNotFoundError as e:  # dipendenze non installate (rich...): errore chiaro, non un traceback
    from .deps import hint
    raise SystemExit(hint(e)) from e

if __name__ == "__main__":
    if sys.argv[1:2] == ["test"] and not getattr(sys, "frozen", False):  # python -m pozzo test: suite come la CI
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "packaging"))
        import test_dashboard
        sys.exit(test_dashboard.main(sys.argv[2:]))
    # eseguibile aperto con un doppio clic (nessun argomento): si avvia l'app, non lo scraping
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        sys.argv.append("app")
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()  # hashing in processi separati anche nell'eseguibile
    main()
