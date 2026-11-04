"""Pianificazione della manutenzione notturna: orario dovuto, validazione, avviso solo se la situazione peggiora."""

import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pozzo  # noqa: E402
from pozzo import notify  # noqa: E402
from pozzo.app.routes import scan as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

ON = {"enabled": True, "day": 6, "time": "03:00"}  # domenica alle 03:00
SUNDAY_0300 = dt.datetime(2026, 11, 8, 3, 0)  # 2026-11-08 e' una domenica
SUNDAY_0259 = dt.datetime(2026, 11, 8, 2, 59)


def test_dovuta_all_ora_giusta():
    assert S.maintenance_due(SUNDAY_0300, ON, "") is True
    assert S.maintenance_due(dt.datetime(2026, 11, 8, 9, 30), ON, "") is True  # app chiusa all'ora: recupera


def test_non_dovuta_prima_dellora_o_altro_giorno_o_gia_fatta():
    assert S.maintenance_due(SUNDAY_0259, ON, "") is False
    assert S.maintenance_due(dt.datetime(2026, 11, 7, 3, 0), ON, "") is False  # sabato
    assert S.maintenance_due(SUNDAY_0300, ON, "2026-11-08") is False  # gia' fatta oggi
    assert S.maintenance_due(SUNDAY_0300, ON, "2026-11-01") is True  # l'ultima era una settimana fa
    assert S.maintenance_due(SUNDAY_0300, {**ON, "enabled": False}, "") is False


def test_impostazioni_validate():
    assert S._maint_settings(None) == S.MAINT_DEFAULT
    assert S._maint_settings({"enabled": True, "day": 0, "time": "23:59"}, strict=True) == {"enabled": True, "day": 0, "time": "23:59"}
    for bad in ({"day": 7}, {"day": True}, {"time": "24:00"}, {"time": "3:00"}, {"enabled": "si"}):
        with pytest.raises(HTTPException):
            S._maint_settings(bad, strict=True)
    assert S._maint_settings({"day": 7, "time": "24:00", "enabled": "si"}) == S.MAINT_DEFAULT  # in lettura: predefiniti
    assert S._maint_settings({"day": 2, "time": "bad"}) == {"enabled": False, "day": 2, "time": "03:00"}


class _FakeMaint:
    def __init__(self, diff_result):
        self.diff_result = diff_result
        self.calls = []

    def latest(self, cfg):
        return {"report": {"rom": 0}} if self.prev else {}

    def run(self, cfg, **kw):
        self.calls.append("run")
        self.kw = kw
        return {"rom": 3}

    def diff(self, prev, cur):
        self.calls.append("diff")
        return self.diff_result

    prev = True


@pytest.fixture
def fake(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send", lambda cfg, title, body="", action=None: sent.append((title, body)) or True)

    def make(diff_result, prev=True):
        m = _FakeMaint(diff_result)
        m.prev = prev
        monkeypatch.setitem(sys.modules, "pozzo.maintenance", m)
        monkeypatch.setattr(pozzo, "maintenance", m, raising=False)
        return m
    return make, sent


def test_avviso_solo_se_peggiora(fake):
    make, sent = fake
    cfg = SimpleNamespace(app={})
    m = make({"peggiora": False, "rom_nuove_mancanti": []})
    S.maintenance_execute(cfg)
    assert m.calls == ["run", "diff"] and sent == []


def test_avviso_con_riepilogo_se_peggiora(fake):
    make, sent = fake
    cfg = SimpleNamespace(app={})
    make({"peggiora": True, "rom_nuove_mancanti": [{}, {}, {}], "rom_ripristinate": [{}], "bios_nuovi_invalidi": [{}],
          "covers_delta": 5, "freeable_delta": 3 * 1024 ** 3 // 2})
    S.maintenance_execute(cfg)
    assert len(sent) == 1
    title, body = sent[0]
    assert title == "Pozzo Launcher"
    assert body == "Manutenzione: 3 ROM non trovate, 1 BIOS non valido, 5 copertine in più mancanti, 1,5 GB in più di doppioni"
    assert S._maint_summary({"covers_delta": -4, "freeable_delta": -10, "rom_nuove_mancanti": []}) ==         "Manutenzione: un controllo non è riuscito, apri il rapporto"  # miglioramenti: mai elencati


def test_primo_giro_senza_confronto_nessun_avviso(fake):
    make, sent = fake
    cfg = SimpleNamespace(app={})
    m = make({"peggiora": True, "rom_nuove_mancanti": [{}]}, prev=False)
    S.maintenance_execute(cfg)
    assert m.calls == ["run"] and sent == []


def test_salta_se_job_in_corso_e_ricarica_libreria(fake):
    from pozzo.app import jobs as J
    make, sent = fake
    loads = []
    lib = SimpleNamespace(load=lambda: loads.append(1))
    cfg = SimpleNamespace(app={})
    busy = J.ScrapeJob()
    busy.status = "running"
    job = {"current": busy, "store_refresh": J.StoreRefreshJob()}

    def claim(name, j):
        if job[name].status == "running":
            return False
        j.status, job[name] = "running", j
        return True

    m = make({"peggiora": False})
    assert S.maintenance_execute(cfg, job, {"building": False}, lib, claim) is False
    assert m.calls == [] and loads == []
    busy.status = "done"
    assert S.maintenance_execute(cfg, job, {"building": False}, lib, claim) is True
    assert m.calls == ["run", "diff"] and loads == [1]
    assert m.kw["store_job"] is job["store_refresh"] and m.kw["scrape_job"] is job["current"]
    assert job["current"].status != "running"  # lo slot dello scraping non resta occupato
