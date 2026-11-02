"""Clic destro sui giochi in tutte le viste: ogni scheda di gioco che le grafiche disegnano ha il suo selettore in
GAME_TARGETS (js/actions.js). Controllo statico, senza browser: aggiungi qui sotto una vista nuova se serve.

Esegui: python tests/test_context_menu.py"""

import re
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "pozzo" / "app" / "static"

# file -> [(testo che lo scrive nel file, attributo registrato in GAME_TARGETS)]: l'attributo che porta l'id del gioco
SCHEDE = {
    "js/grid.js": [("dataset.id", "data-id")],       # griglia della libreria (el.dataset.id = g.id)
    "js/home.js": [("data-id", "data-id"), ("data-shelf-game", "data-shelf-game")],  # «Per te» e home a scaffali
    "js/pages.js": [("data-id", "data-id")],         # Top e statistiche
    "experiences/cinema/experience.js": [("data-cnx-id", "data-cnx-id")],
    "experiences/console/experience.js": [("data-console-game", "data-console-game"), ("data-console-open", "data-console-open")],
    "experiences/dashboard/experience.js": [("data-dashboard-game", "data-dashboard-game")],
    "experiences/storefront/experience.js": [("data-vetrina-game", "data-vetrina-game")],
}


def test_ogni_scheda_ha_il_suo_selettore():
    actions = (STATIC / "js" / "actions.js").read_text(encoding="utf-8")
    targets = actions[actions.index("const GAME_TARGETS"):actions.index("function gameFromEvent")]
    for rel, voci in SCHEDE.items():
        text = (STATIC / rel).read_text(encoding="utf-8")
        for token, attr in voci:
            assert token in text, f"{rel}: «{token}» non c'e' piu': aggiorna SCHEDE e GAME_TARGETS"
            assert f"[{attr}]" in targets, f"{attr} ({rel}) non e' in GAME_TARGETS: il clic destro li ignorerebbe"


def test_il_clic_destro_e_di_pagina_non_della_griglia():
    events = (STATIC / "js" / "events.js").read_text(encoding="utf-8")
    assert re.search(r'document\.addEventListener\("contextmenu"', events), "il gestore deve stare sul documento"
    assert "layer.addEventListener(\"contextmenu\"" not in events, "il gestore solo-griglia e' tornato"
    assert "gameFromEvent(e)" in events


def test_il_menu_ha_le_azioni_utili():
    actions = (STATIC / "js" / "actions.js").read_text(encoding="utf-8")
    menu = actions[actions.index("function openCtx"):actions.index("async function removeManual")]
    for voce in ("Aggiungi ai preferiti", "Togli dai preferiti", "Aggiungi a una collezione", "Collegamento sul desktop",
                 "Copia il titolo", "Pagina dello store", "Installa", "Nascondi dalla libreria", "stars: true"):
        assert voce in menu, f"manca nel menu: {voce}"


if __name__ == "__main__":
    test_ogni_scheda_ha_il_suo_selettore()
    test_il_clic_destro_e_di_pagina_non_della_griglia()
    test_il_menu_ha_le_azioni_utili()
    print("ok  clic destro: selettori per ogni vista, gestore di pagina, azioni del menu")
    print("TUTTI I TEST OK")
