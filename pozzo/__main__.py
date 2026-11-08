import sys

from .cli import main

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
