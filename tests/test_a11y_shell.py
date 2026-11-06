"""Accessibilita' della shell (index.html): link di salto, un solo <main>, pulsanti con nome, regione live dei toast.

Esegui: python tests/test_a11y_shell.py
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"
INDEX = STATIC / "index.html"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Shell(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.first_tag: tuple[str, dict] | None = None
        self.skip_text = ""
        self.in_skip = False
        self.stack: list[tuple[str, bool]] = []  # (tag, aria-hidden) dei contenitori aperti
        self.open_buttons: list[dict] = []
        self.buttons: list[dict] = []
        self.mains: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.nav_items: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "body":
            self.in_body = True
            return
        if not self.in_body:
            return
        if self.first_tag is None:
            self.first_tag = (tag, a)
            self.in_skip = True
        if tag == "main":
            self.mains.append(a)
        if "id" in a:
            self.by_id[a["id"]] = a
        if "nav-item" in a.get("class", "").split():
            self.nav_items.append(a)
        if tag == "button":
            self.open_buttons.append({"attrs": a, "text": ""})
        if tag not in VOID:
            self.stack.append((tag, a.get("aria-hidden") == "true"))

    def handle_endtag(self, tag):
        if not self.in_body:
            return
        if tag == "a":
            self.in_skip = False
        if tag == "button" and self.open_buttons:
            self.buttons.append(self.open_buttons.pop())
        while self.stack:  # chiude fino al tag corrispondente
            name, _ = self.stack.pop()
            if name == tag:
                break

    def handle_data(self, data):
        if not self.in_body:
            return
        if self.in_skip:
            self.skip_text += data
        if any(hidden for _, hidden in self.stack):
            return  # testo di emoji e icone decorative: non conta come nome
        for b in self.open_buttons:
            b["text"] += data


import json as _json
_CAT = _json.loads((Path(__file__).resolve().parents[1] / "pozzo" / "data" / "locales" / "it.json").read_text(encoding="utf-8"))


def _label(el):
    return el.get("aria-label") or _CAT.get(el.get("data-i18n-aria", ""), "")


def test_shell() -> None:
    p = Shell()
    p.feed(INDEX.read_text(encoding="utf-8"))

    # link di salto: primo elemento del body, punta a #main, e #main esiste
    assert p.first_tag is not None and p.first_tag[0] == "a", "il primo elemento del body deve essere il link di salto"
    assert "skip-link" in p.first_tag[1].get("class", "").split(), "link di salto: classe skip-link mancante"
    assert p.first_tag[1].get("href") == "#main", "link di salto: href deve essere #main"
    assert p.skip_text.strip() == "Vai al contenuto", f"testo del link di salto: {p.skip_text!r}"
    assert "main" in p.by_id and p.by_id["main"].get("tabindex") == "-1", "#main deve esistere con tabindex=-1"

    # un solo <main>
    assert len(p.mains) == 1, f"<main> trovati: {len(p.mains)}"

    # ogni pulsante ha un nome: testo visibile o aria-label
    assert p.buttons, "nessun <button> trovato: il parser non funziona"
    unnamed = [
        b["attrs"].get("id") or b["attrs"].get("class") or "?"
        for b in p.buttons
        if not (b["attrs"].get("aria-label", "").strip() or b["attrs"].get("data-i18n-aria") or b["text"].strip())
    ]
    assert not unnamed, f"pulsanti senza nome accessibile: {unnamed}"

    # regione live dei toast
    live = p.by_id.get("toast-live")
    assert live is not None, "manca #toast-live"
    assert live.get("aria-live") in ("polite", "assertive"), "#toast-live senza aria-live"

    # landmark di navigazione, ricerca con etichetta, foglio di stile dell'a11y collegato
    assert _label(p.by_id.get("experience-nav", {})) == "Navigazione principale", "nav principale senza etichetta"
    assert _label(p.by_id.get("search", {})), "campo di ricerca senza aria-label"
    assert 'href="/static/a11y.css' in INDEX.read_text(encoding="utf-8"), "a11y.css non collegato"


def test_focus_and_live() -> None:
    p = Shell()
    p.feed(INDEX.read_text(encoding="utf-8"))
    static = STATIC

    # voci della barra laterale: raggiungibili da tastiera e con ruolo pulsante
    assert p.nav_items, "nessuna voce .nav-item in index.html"
    bad = [a.get("data-view") for a in p.nav_items if a.get("tabindex") != "0" or a.get("role") != "button"]
    assert not bad, f"voci nav senza tabindex=0 / role=button: {bad}"
    assert "a.tabIndex = 0" in (static / "js" / "events.js").read_text(encoding="utf-8"), "voci nav dinamiche non rese focusabili"

    # toast: la regione live resta nel DOM (sr-only, non hidden); il box visivo #toast e' nascosto con hidden
    live = p.by_id.get("toast-live")
    assert live is not None, "manca #toast-live"
    assert "hidden" not in live and "sr-only" in live.get("class", "").split(), "#toast-live deve restare renderizzata (sr-only)"
    assert live.get("aria-live") == "polite", "#toast-live senza aria-live"
    settings = (static / "js" / "settings.js").read_text(encoding="utf-8")
    assert 'removeAttribute("role")' not in settings.split("function savedToast")[0], "toast() non deve rimuovere role"
    assert re.search(r'role",\s*err \? "alert" : "status"', settings), "toast: errori con role=alert, altrimenti status"
    assert re.search(r"toastLive\(msg, err\)", settings) and "toastLive(label, false)" in settings, "toast/savedToast devono annunciare via toastLive"

    # dettaglio: dialog solo se modale, complementary in pannello
    detail = (static / "js" / "detail.js").read_text(encoding="utf-8")
    assert 'mode === "panel" ? "complementary" : "region"' in detail, "presentDetail: panel deve essere complementary"
    assert "f.coll.remove_aria" in detail and _CAT["f.coll.remove_aria"] == "Rimuovi {name}", "chip: pulsante di rimozione senza aria-label"
    assert "f.rate.aria" in detail and _CAT["f.rate.aria"] == "Valuta {n} stelle" and "aria-pressed" in detail, "stelle senza aria-label/aria-pressed"

    # emoji + testo: l'emoji e' nascosta ai lettori di schermo
    html = INDEX.read_text(encoding="utf-8")
    for emoji in ("📁", "⚙"):
        assert f'<span aria-hidden="true">{emoji}</span>' in html, f"emoji {emoji} non nascosta (aria-hidden)"


def main() -> None:
    test_shell()
    test_focus_and_live()
    print("ok  shell: link di salto, un <main>, pulsanti con nome, toast in aria-live")
    print("ok  focus: voci nav focusabili, toast live sr-only, dettaglio complementary, aria su chip/stelle/emoji")


if __name__ == "__main__":
    main()
