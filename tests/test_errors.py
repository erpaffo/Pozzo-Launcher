"""Errori non previsti: l'app dice che errore e', dove e' nato e (se la riconosce) la causa, invece di «Internal Server Error»."""
import errno
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import errors as ERR  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402


@pytest.mark.parametrize("exc, status, text", [
    (sqlite3.OperationalError("table games has no column named md5"), 500, "ricostruisci la libreria"),
    (sqlite3.OperationalError("no such table: games"), 500, "ricostruisci la libreria"),
    (sqlite3.OperationalError("database is locked"), 503, "occupato"),
    (sqlite3.OperationalError("disk I/O error"), 500, "Errore del database"),
    (sqlite3.DatabaseError("file is not a database"), 500, "danneggiato"),
    (PermissionError(13, "Permission denied", "C:/x/gioco.exe"), 500, "Permesso negato su «C:/x/gioco.exe»"),
    (FileNotFoundError(2, "No such file", "E:/Games/a.rom"), 500, "«E:/Games/a.rom»"),
    (OSError(errno.ENOSPC, "No space left on device"), 500, "Spazio su disco esaurito"),
    (httpx.ReadTimeout("lento"), 504, "non ha risposto in tempo"),
    (httpx.ConnectError("refused"), 502, "Rete non raggiungibile"),
    (ValueError("boh"), 500, "Errore imprevisto (ValueError: boh)"),
])
def test_explain(exc, status, text):
    s, msg = ERR.explain(exc)
    assert s == status and text in msg, msg
    assert type(exc).__name__ in msg, "la causa tecnica e' sempre in coda"


def test_explain_tronca_i_messaggi_lunghi():
    assert len(ERR.explain(RuntimeError("x" * 5000))[1]) < 400


def _raise_in(filename: str):
    ns = {}
    exec(compile("def f():\n    raise ValueError('x')", filename, "exec"), ns)
    try:
        ns["f"]()
    except ValueError as e:
        return e


def test_where_punta_al_codice_di_pozzo():
    assert ERR.where(_raise_in("C:/qualcosa/pozzo/app/routes/manual.py")) == "pozzo/app/routes/manual.py:2 (f)"
    assert ERR.where(_raise_in("/home/me/pozzo/pozzo/library/build.py")) == "pozzo/library/build.py:2 (f)", "vale la cartella piu' interna"
    assert ERR.where(_raise_in("C:/u/PozzoLauncher/extensions/sgdb/backend.py")) == "extensions/sgdb/backend.py:2 (f)", "estensioni"
    assert ERR.where(_raise_in("/altro/libreria.py")) == "libreria.py:2 (f)", "fuori da pozzo/: almeno l'ultimo punto"
    assert ERR.where(ValueError("mai sollevata")) == ""


@pytest.fixture
def client(tmp_path):
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp_path, rom)
    app = create_app(tmp_cfg(tmp_path, rom))

    # rotta che fallisce, con un nome di file «dentro pozzo/» come quelle vere
    ns = {}
    exec(compile("import sqlite3, httpx\n"
                 "def boom(kind: str):\n"
                 "    raise {'db': sqlite3.OperationalError('table games has no column named md5'),\n"
                 "           'net': httpx.ConnectError('refused')}.get(kind) or RuntimeError('boom')\n",
                 "C:/x/pozzo/app/routes/boom.py", "exec"), ns)
    app.add_api_route("/api/_boom/{kind}", ns["boom"], methods=["GET"])
    # raise_server_exceptions=False: come il server vero, dove l'eccezione viene rilanciata solo per il registro
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as c:
        yield c


def test_eccezione_non_gestita_dice_che_errore_e(client):
    r = client.get("/api/_boom/x")
    d = r.json()
    assert r.status_code == 500 and d["code"] == "internal_error" and d["error"] == "RuntimeError"
    assert d["detail"] == "Errore imprevisto (RuntimeError: boom)" and d["where"] == "pozzo/app/routes/boom.py:3 (boom)", d
    assert r.text != "Internal Server Error"


def test_database_e_rete_con_la_loro_causa(client):
    r = client.get("/api/_boom/db")
    assert r.status_code == 500 and "ricostruisci la libreria" in r.json()["detail"] and r.json()["error"] == "OperationalError"
    r = client.get("/api/_boom/net")
    assert r.status_code == 502 and r.json()["code"] == "bad_gateway"


def test_gli_errori_voluti_restano_come_prima(client):
    r = client.get("/api/game/99999")  # gioco inesistente: 404 con la sua forma, non un errore imprevisto
    assert r.status_code == 404 and r.json()["code"] == "not_found" and "where" not in r.json()
