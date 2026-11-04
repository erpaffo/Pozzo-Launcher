"""Storico della banda: accumulo per minuto, flush su disco, stats con zero-fill, ordine per host, prune. Nessuna rete."""

import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.downloads import bandwidth as B  # noqa: E402

T0 = 1_800_000_000 // 60 * 60 + 600  # inizio di un minuto, in epoch


@pytest.fixture
def clock(tmp, monkeypatch):
    """Orologio finto + DB in una cartella temporanea + stato pulito a ogni test."""
    now = {"t": float(T0)}
    monkeypatch.setattr(B, "_now", lambda: now["t"])
    monkeypatch.setattr(B, "_m", B._Meter())
    B.configure(tmp)
    B._m.last_flush = now["t"]  # niente flush automatico al primo record
    return now


@contextmanager
def _db(tmp):
    with closing(sqlite3.connect(tmp / "downloads.db")) as db:
        db.execute("CREATE TABLE IF NOT EXISTS bw(ts INTEGER, host TEXT, bytes INTEGER, PRIMARY KEY(ts,host))")
        yield db
        db.commit()


def _rows(tmp):
    with _db(tmp) as db:
        return sorted(db.execute("SELECT ts, host, bytes FROM bw").fetchall())


def test_record_accumula_e_flush_scrive(clock, tmp):
    B.record("a.com", 100)
    B.record("a.com", 50)
    B.record("b.com", 7)
    B.record("a.com", 0)  # niente da contare
    assert _rows(tmp) == []  # ancora in memoria: meno di 30 s, stesso minuto
    B.flush()
    assert _rows(tmp) == [(T0, "a.com", 150), (T0, "b.com", 7)]
    B.record("a.com", 10)
    B.flush()  # UPSERT: somma sulla riga esistente
    assert _rows(tmp) == [(T0, "a.com", 160), (T0, "b.com", 7)]


def test_flush_automatico_ogni_30_secondi_e_al_cambio_minuto(clock, tmp):
    B.record("a.com", 1)
    clock["t"] += 31  # stesso minuto, ma sono passati 30 s
    B.record("a.com", 2)
    assert _rows(tmp) == [(T0, "a.com", 3)]
    clock["t"] = float(T0 + 60)  # minuto nuovo: il vecchio viene scritto subito
    B.record("a.com", 4)
    assert _rows(tmp) == [(T0, "a.com", 3)]  # il byte nuovo resta in memoria
    B.flush()
    assert _rows(tmp) == [(T0, "a.com", 3), (T0 + 60, "a.com", 4)]


def test_flush_fallito_non_perde_i_byte(clock, tmp, monkeypatch):
    B.record("a.com", 5)
    real = B._conn

    def boom():
        raise sqlite3.OperationalError("disco pieno")

    monkeypatch.setattr(B, "_conn", boom)
    B.flush()  # non deve sollevare
    monkeypatch.setattr(B, "_conn", real)
    B.flush()
    assert _rows(tmp) == [(T0, "a.com", 5)]


def test_stats_zero_fill_e_pending(clock, tmp):
    B.record("a.com", 600)
    B.flush()
    B.record("b.com", 60)  # ancora in memoria: stats lo include
    s = B.stats(now=clock["t"])
    hour = s["last_hour"]
    assert len(hour) == 60
    assert hour[-1] == {"t": T0, "bytes": 660, "bps": 11.0}
    assert hour[0]["t"] == T0 - 59 * 60
    assert all(x["bytes"] == 0 and x["bps"] == 0 for x in hour[:-1])
    days = s["per_day"]
    assert len(days) == 30
    assert days[-1] == {"day": date.fromtimestamp(clock["t"]).isoformat(), "bytes": 660}
    assert all(d["bytes"] == 0 for d in days[:-1])
    assert s["total_bytes"] == 660


def test_stats_per_host_ordinato_e_30d(clock, tmp):
    B.record("piccolo.com", 10)
    B.record("grande.com", 500)
    B.record("medio.com", 100)
    B.record("grande.com", 0)  # ignorato
    with _db(tmp) as db:  # storico di 40 giorni fa: nel totale, non nei 30 giorni
        db.execute("INSERT INTO bw VALUES(?,?,?)", (T0 - 40 * 86400, "grande.com", 1000))
    B.flush()
    s = B.stats(now=clock["t"])
    assert [h["host"] for h in s["per_host"]] == ["grande.com", "medio.com", "piccolo.com"]
    assert s["per_host"][0] == {"host": "grande.com", "bytes_total": 1500, "bytes_30d": 500}
    assert s["total_bytes"] == 1610
    assert sum(d["bytes"] for d in s["per_day"]) == 610


def test_prune_una_volta_al_giorno(clock, tmp):
    with _db(tmp) as db:
        db.executemany("INSERT INTO bw VALUES(?,?,?)", [(T0 - 91 * 86400, "x", 1), (T0 - 89 * 86400, "x", 2)])
    B.record("x", 3)
    B.flush()  # primo flush: il prune gira
    assert _rows(tmp) == [(T0 - 89 * 86400, "x", 2), (T0, "x", 3)]
    with _db(tmp) as db:
        db.execute("INSERT INTO bw VALUES(?,?,?)", (T0 - 91 * 86400, "y", 9))
    clock["t"] += 3600  # stesso giorno: niente prune
    B.record("x", 1)
    B.flush()
    assert (T0 - 91 * 86400, "y", 9) in _rows(tmp)
    clock["t"] += 2 * 86400  # giorno dopo: prune di nuovo
    B.record("x", 1)
    B.flush()
    assert all(ts >= int(clock["t"]) - 90 * 86400 for ts, _, _ in _rows(tmp))


def test_stats_senza_cartella_non_crasha(clock, monkeypatch):
    monkeypatch.setattr(B, "_m", B._Meter())  # nessuna cartella configurata: resta in memoria
    B.record("a.com", 42)
    s = B.stats(now=clock["t"])
    assert s["total_bytes"] == 42 and len(s["last_hour"]) == 60
