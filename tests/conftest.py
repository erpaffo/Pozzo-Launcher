"""Fixture condivise: molti test nascono come script (`python tests/x.py`) e chiedono `tmp` o `t`."""
import asyncio
import inspect
import os
import shutil
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("POZZO_NO_SAMPLE", "1")  # niente gioco d'esempio nei test


@pytest.fixture
def tmp():
    # cartella breve come negli script: alcuni test misurano la lunghezza del percorso
    # rmtree(ignore_errors): TemporaryDirectory(ignore_cleanup_errors) su Windows/3.12 lascia passare un PermissionError
    # se un file (es. cache.db-shm di SQLite) e' ancora aperto da un thread che sta chiudendo
    d = tempfile.mkdtemp()
    try:
        yield Path(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def t(tmp):
    return tmp


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Esegue i test `async def` senza plugin aggiuntivi."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        args = {a: pyfuncitem.funcargs[a] for a in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(pyfuncitem.obj(**args))
        return True


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: emulatore reale + rete (CI notturna); escluso salvo `-m smoke`")


def pytest_collection_modifyitems(config, items):
    if "smoke" in (config.getoption("markexpr") or ""):
        return
    skipped = [i for i in items if "smoke" in i.keywords]
    if skipped:
        config.hook.pytest_deselected(items=skipped)
        items[:] = [i for i in items if i not in skipped]
