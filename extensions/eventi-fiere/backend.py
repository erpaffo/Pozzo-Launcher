"""Eventi e fiere: calendario di fiere videoludiche e promemoria (7 e 1 giorno prima).

Gli eventi stanno in eventi.json (modificabile): copiato dalla cartella dell'estensione alla cartella dati la prima volta.

GET /plugin-api/eventi-fiere/eventi -> {"eventi": [{nome, inizio, fine, luogo, url, giorni}]}
    giorni: giorni che mancano all'inizio (0 = oggi, negativo = in corso)
Lavoro «promemoria» (ogni 6 ore): una notifica per evento, quando mancano 7 giorni o meno e poi 1 giorno.
"""

import json
import shutil
from datetime import date
from pathlib import Path

PROMEMORIA_GIORNI = 7
INVIATI_MAX = 500  # le chiavi servono solo per la settimana prima dell'evento: basta una lista corta


def carica(path: Path, log=print) -> list[dict]:
    """Eventi validi dal file; le voci sbagliate si saltano con una riga di log."""
    if not path.exists():
        return []
    try:
        voci = json.loads(path.read_text("utf-8")).get("eventi", [])
    except (ValueError, AttributeError) as e:
        log(f"[eventi-fiere] eventi.json non leggibile: {e}")
        return []
    out = []
    for e in voci:
        try:
            inizio = date.fromisoformat(e["inizio"])
            fine = date.fromisoformat(e.get("fine") or e["inizio"])
            if fine < inizio:
                raise ValueError("fine prima dell'inizio")
            url = str(e.get("url") or "")
            out.append({"nome": str(e["nome"]).strip(), "inizio": inizio, "fine": fine, "luogo": str(e.get("luogo") or ""),
                        "url": url if url.startswith(("http://", "https://")) else ""})
        except (KeyError, TypeError, ValueError) as err:
            log(f"[eventi-fiere] voce saltata ({err}): {e}")
    return out


def vista(eventi: list[dict], oggi: date) -> list[dict]:
    """Eventi non ancora finiti, in ordine di data, con i giorni che mancano."""
    out = [{**e, "giorni": (e["inizio"] - oggi).days} for e in eventi if e["fine"] >= oggi]
    return sorted(out, key=lambda e: e["inizio"])


def da_avvisare(eventi: list[dict], oggi: date, gia: set[str]) -> list[tuple[str, str, str]]:
    """Promemoria da mandare adesso: (chiave, titolo, testo). `gia` sono le chiavi già inviate."""
    out = []
    for e in eventi:
        giorni = (e["inizio"] - oggi).days
        fase = "1" if giorni <= 1 else "7"  # un avviso a 7 giorni e uno a 1 giorno, per evento
        chiave = f"{e['nome']}|{e['inizio']}|{fase}"
        if 0 < giorni <= PROMEMORIA_GIORNI and chiave not in gia:
            titolo = f"{e['nome']} domani" if giorni == 1 else f"{e['nome']} tra {giorni} giorni"
            testo = f"Inizia il {e['inizio']:%d/%m/%Y}" + (f" · {e['luogo']}" if e["luogo"] else "")
            out.append((chiave, titolo, testo))
    return out


def register(gs):
    from pozzo.app.extensions import user_dir
    path = user_dir(gs.cfg, "eventi-fiere") / "eventi.json"
    if not path.exists():
        shutil.copyfile(Path(__file__).parent / "eventi.json", path)

    @gs.route("eventi")
    def eventi():
        return {"eventi": vista(carica(path, gs.log), date.today())}

    def promemoria():
        from pozzo import notify
        gia = gs.settings.get("inviati") or []
        nuovi = da_avvisare(carica(path, gs.log), date.today(), set(gia))
        for _, titolo, testo in nuovi:
            notify.send(gs.cfg, titolo, testo)
        if nuovi:
            gs.save_settings({"inviati": (gia + [k for k, _, _ in nuovi])[-INVIATI_MAX:]})

    gs.job("promemoria", promemoria, every=6 * 3600, run_at_start=True)
