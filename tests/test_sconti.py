"""Estensione Sconti e bundle: parsing dei bundle ITAD, abbinamento dei titoli, scadenza della cache."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("pozzo_ext_sconti", ROOT / "extensions" / "sconti" / "backend.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

SAMPLE = [
    {"id": 1, "title": "RimWorld Bundle", "page": {"name": "Fanatical"}, "url": "https://x/rw", "isMature": False,
     "expiry": "2030-01-01T00:00:00+01:00",
     "tiers": [{"price": {"amount": 8.5, "currency": "EUR"}, "addon": False,
                "games": [{"title": "RimWorld", "type": "game"}, {"title": "RimWorld - Royalty", "type": "dlc"},
                          {"title": "RimWorld", "type": "game"}]},
               {"price": {"amount": 12, "currency": "EUR"}, "addon": True, "games": [{"title": "Extra Pack"}]}]},
    {"id": 2, "title": "Adult Pack", "page": {"name": "Shop"}, "isMature": True, "tiers": []},
    {"id": 3, "title": "Witcher Week", "page": {"name": "GOG"}, "details": "https://itad/3", "expiry": None,
     "tiers": [{"price": {"amount": 4, "currency": "EUR"}, "games": [{"title": "The Witcher 3: Wild Hunt"}]}]},
]


def test_parse_bundles_fields_and_filters():
    out = S.parse_bundles(SAMPLE)
    assert [b["title"] for b in out] == ["RimWorld Bundle", "Witcher Week"]  # il bundle per adulti esce
    rw = out[0]
    assert rw["store"] == "Fanatical" and rw["url"] == "https://x/rw" and rw["expiry"].startswith("2030")
    assert rw["games"] == ["RimWorld", "RimWorld - Royalty", "Extra Pack"]  # senza duplicati
    assert rw["tiers"][0] == {"price": 8.5, "currency": "EUR", "addon": False,
                              "games": ["RimWorld", "RimWorld - Royalty", "RimWorld"]}
    assert rw["tiers"][1]["addon"] is True
    assert out[1]["url"] == "https://itad/3"  # senza url: si usa la pagina di dettaglio


def test_parse_bundles_tolerates_junk():
    assert S.parse_bundles(None) == []
    assert S.parse_bundles([None, "x", {"title": ""}]) == []


def test_mark_mine_normalized_title_match():
    bundles = S.parse_bundles(SAMPLE)
    owned = {S.matching.normalize("Witcher 3 Wild Hunt")}  # la libreria scrive il titolo in un altro modo
    marked = S.mark_mine(bundles, owned)
    assert marked[0]["mine"] is False
    assert marked[1]["mine"] is True
    owned2 = {S.matching.normalize("RimWorld - Royalty")}
    assert S.mark_mine(bundles, owned2)[0]["mine"] is True


def test_deals_sorted_with_historical_low():
    rows = [
        {"title": "A", "price": 5.0, "regular": 10.0, "cut": 50, "shop": "Steam", "url": "u", "low": 5.0},
        {"title": "B", "price": 9.0, "regular": 10.0, "cut": 10, "shop": "GOG", "url": "v", "low": 4.0},
        {"title": "C", "price": 10.0, "regular": 10.0, "cut": 0, "shop": "Steam", "url": "w", "low": None},
        {"title": "D", "price": None, "regular": None, "cut": 30, "shop": "", "url": "", "low": None},
    ]
    out = S.deals(rows)
    assert [d["title"] for d in out] == ["A", "B"]
    assert out[0]["historical_low"] is True and out[1]["historical_low"] is False
    assert out[0]["cut_percent"] == 50 and out[0]["store"] == "Steam"


def test_cache_expiry_and_error_ttl(tmp_path):
    path = tmp_path / "bundles.json"
    calls = []

    def build_ok():
        calls.append("ok")
        return ["x"]

    t0 = 1_000_000.0
    rec = S.cached(path, build_ok, now=lambda: t0)
    assert rec["ok"] and rec["data"] == ["x"] and calls == ["ok"]

    # dentro le 6 ore: nessuna nuova richiesta
    S.cached(path, build_ok, now=lambda: t0 + 6 * 3600 - 1)
    assert calls == ["ok"]
    # oltre le 6 ore: si riscarica
    S.cached(path, build_ok, now=lambda: t0 + 6 * 3600 + 1)
    assert calls == ["ok", "ok"]

    # errore: non viene rilanciato, resta il dato precedente, e si riprova dopo 30 minuti
    def build_fail():
        raise RuntimeError("rete giu'")

    later = t0 + 13 * 3600  # oltre le 6 ore dall'ultimo dato buono
    rec = S.cached(path, build_fail, now=lambda: later)
    assert rec["ok"] is False and "rete giu'" in rec["error"] and rec["data"] == ["x"]
    S.cached(path, build_ok, now=lambda: later + 29 * 60)  # errore ancora fresco: non si richiama build
    assert calls == ["ok", "ok"]
    rec = S.cached(path, build_ok, now=lambda: later + 31 * 60)
    assert rec["ok"] and calls == ["ok", "ok", "ok"]


def test_cache_unreadable_file_is_ignored(tmp_path):
    path = tmp_path / "free.json"
    path.write_text("{non json", encoding="utf-8")
    rec = S.cached(path, lambda: [1], now=lambda: 5.0)
    assert rec["data"] == [1]
    assert json.loads(path.read_text(encoding="utf-8"))["data"] == [1]
