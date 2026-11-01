"""Fixture condivise: molti test nascono come script (`python tests/x.py`) e chiedono `tmp` o `t`."""
import asyncio
import inspect
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp():
    # cartella breve come negli script: alcuni test misurano la lunghezza del percorso
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        yield Path(d)


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
