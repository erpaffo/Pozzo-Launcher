"""extensions/eventi-fiere: lettura di eventi.json, calendario, promemoria a 7 e 1 giorno (una volta sola).
Nessuna rete: notifiche finte.

Esegui: python -m pytest tests/test_ext_eventi_fiere.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo import notify  # noqa: E402


def load():
    spec = importlib.util.spec_from_file_location("ext_eventi_fiere", ROOT / "extensions" / "eventi-fiere" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeGS:
    """Come PluginAPI: route, lavori e impostazioni salvate in memoria."""

    def __init__(self, cfg):
        self.cfg, self.routes, self.jobs, self.settings, self.logs = cfg, {}, {}, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[path] = fn
            return fn
        return deco

    def job(self, nome, fn, every, run_at_start=False):
        self.jobs[nome] = fn

    def save_settings(self, values):
        self.settings.update(values)


def test_carica_salta_le_voci_sbagliate(tmp_path):
    mod = load()
    f = tmp_path / "eventi.json"
    f.write_text(json.dumps({"eventi": [
        {"nome": "Gamescom", "inizio": "2026-08-26", "fine": "2026-08-30", "url": "javascript:alert(1)"},
        {"nome": "Senza data"},
        {"nome": "Fine prima", "inizio": "2026-05-10", "fine": "2026-05-01"},
        {"nome": "Data rotta", "inizio": "26/08/2026"},
    ]}), "utf-8")
    log = []
    ev = mod.carica(f, log.append)
    assert [e["nome"] for e in ev] == ["Gamescom"]
    assert ev[0]["url"] == "" and ev[0]["fine"] == date(2026, 8, 30)
    assert len(log) == 3
    f.write_text("{non json", "utf-8")
    assert mod.carica(f, log.append) == [] and mod.carica(tmp_path / "manca.json") == []


def test_vista_ordina_e_nasconde_i_passati():
    mod = load()
    ev = [
        {"nome": "B", "inizio": date(2026, 9, 1), "fine": date(2026, 9, 1), "luogo": "", "url": ""},
        {"nome": "Passato", "inizio": date(2026, 1, 1), "fine": date(2026, 1, 2), "luogo": "", "url": ""},
        {"nome": "In corso", "inizio": date(2026, 6, 1), "fine": date(2026, 6, 10), "luogo": "", "url": ""},
    ]
    v = mod.vista(ev, date(2026, 6, 5))
    assert [(e["nome"], e["giorni"]) for e in v] == [("In corso", -4), ("B", 88)]


def test_promemoria_a_7_e_1_giorno_una_volta_sola():
    mod = load()
    ev = [{"nome": "Gamescom", "inizio": date(2026, 8, 26), "fine": date(2026, 8, 30), "luogo": "Colonia", "url": ""}]
    assert mod.da_avvisare(ev, date(2026, 8, 18), set()) == []           # 8 giorni: ancora presto
    a = mod.da_avvisare(ev, date(2026, 8, 19), set())                    # 7 giorni
    assert [t for _, t, _ in a] == ["Gamescom tra 7 giorni"]
    assert mod.da_avvisare(ev, date(2026, 8, 20), {a[0][0]}) == []       # gia' inviato
    b = mod.da_avvisare(ev, date(2026, 8, 25), {a[0][0]})                # 1 giorno: avviso nuovo
    assert [t for _, t, _ in b] == ["Gamescom domani"] and b[0][0] != a[0][0]
    assert mod.da_avvisare(ev, date(2026, 8, 26), {a[0][0], b[0][0]}) == []  # il giorno stesso: niente


def test_promemoria_recupera_se_il_launcher_era_chiuso():
    mod = load()
    ev = [{"nome": "Gamescom", "inizio": date(2026, 8, 26), "fine": date(2026, 8, 30), "luogo": "", "url": ""}]
    # chiuso per una settimana: al primo avvio con 3 giorni mancanti arriva l'avviso a 7 giorni, non quello a 1
    assert [t for _, t, _ in mod.da_avvisare(ev, date(2026, 8, 23), set())] == ["Gamescom tra 3 giorni"]


def test_route_e_lavoro_promemoria(tmp_path, monkeypatch):
    mod = load()
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={})
    gs = FakeGS(cfg)
    mod.register(gs)
    dati = tmp_path / "eventi-fiere" / "eventi.json"
    assert dati.exists()  # copiato dal file dell'estensione alla prima attivazione
    inviate = []
    monkeypatch.setattr(notify, "send", lambda cfg, titolo, testo="", action=None: inviate.append(titolo) or True)

    inizio = (date.today() + timedelta(days=3)).isoformat()  # un evento che inizia tra 3 giorni, nel file dell'utente
    dati.write_text(json.dumps({"eventi": [{"nome": "Prova Fiera", "inizio": inizio, "luogo": "Roma"}]}), "utf-8")

    app = FastAPI()
    app.get("/eventi")(gs.routes["eventi"])
    r = TestClient(app).get("/eventi").json()
    assert r["eventi"][0]["nome"] == "Prova Fiera" and r["eventi"][0]["giorni"] == 3

    gs.jobs["promemoria"]()
    gs.jobs["promemoria"]()  # secondo giro: nessun doppione
    assert inviate == ["Prova Fiera tra 3 giorni"]
    assert len(gs.settings["inviati"]) == 1
