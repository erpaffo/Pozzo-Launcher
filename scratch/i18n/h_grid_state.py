import sys
sys.path.insert(0, "C:/Users/paffe/OneDrive/Desktop/GameScraper/scratch/i18n")
from h_apply import apply
G = [
(r'''S.search ? esc(`Nessun gioco trovato per «${S.search}».`)''', r'''S.search ? esc(t("h.grid.noSearch", {q: S.search}))''', 1),
(r'''<div class="empty-lib"><b>La libreria è vuota.</b><p class="muted">Scegli la cartella delle ROM o importa i giochi degli store.</p>''', r'''<div class="empty-lib"><b>${t("h.grid.emptyLib")}</b><p class="muted">${t("h.grid.emptyHint")}</p>''', 1),
(r'''🧭 Configurazione guidata</button>''', r'''🧭 ${t("h.grid.wizard")}</button>''', 1),
(r''': "Nessun gioco in questa vista.";''', r''': t("h.grid.noView");''', 1),
(r'''el.setAttribute("aria-label", `Apri ${g.title}, ${platName(g.platform)}`);''', r'''el.setAttribute("aria-label", t("h.grid.openAria", {title: g.title, plat: platName(g.platform)}));''', 1),
(r'''${g.store ? "store" : "versioni"}''', r'''${g.store ? t("h.grid.stores") : t("h.grid.versions")}''', 1),
(r'''title="Contenuto aggiuntivo (DLC/add-on): non è un gioco a sé"''', r'''title="${t("h.grid.dlcTitle")}"''', 1),
(r'''title="Multigiocatore locale"''', r'''title="${t("h.grid.localMulti")}"''', 1),
(r'''🌐 Scarica${g.size ? " · " + fmtSize(g.size) : ""}''', r'''🌐 ${t("h.grid.download")}${g.size ? " · " + fmtSize(g.size) : ""}''', 1),
(r'''⬇ Installa</span>''', r'''⬇ ${t("h.grid.install")}</span>''', 1),
]
GC = {
"h.grid.noSearch": "Nessun gioco trovato per «{q}».", "h.grid.emptyLib": "La libreria è vuota.",
"h.grid.emptyHint": "Scegli la cartella delle ROM o importa i giochi degli store.",
"h.grid.wizard": "Configurazione guidata", "h.grid.noView": "Nessun gioco in questa vista.",
"h.grid.openAria": "Apri {title}, {plat}", "h.grid.stores": "store", "h.grid.versions": "versioni",
"h.grid.dlcTitle": "Contenuto aggiuntivo (DLC/add-on): non è un gioco a sé",
"h.grid.localMulti": "Multigiocatore locale", "h.grid.download": "Scarica", "h.grid.install": "Installa",
}
apply("js/grid.js", G, GC)

S = [
(r'''loading("Caricamento dei giochi degli store…");''', r'''loading(t("h.state.loadingStores"));''', 1),
(r'''toast("Giochi degli store non caricati: " + e.message, true);''', r'''toast(t("h.state.storesErr", {msg: e.message}), true);''', 1),
(r'''<option value="">Tutte le lingue</option>''', r'''<option value="">${t("h.state.allLangs")}</option>''', 1),
(r'''(g.year ? String(g.year) : "Anno sconosciuto")''', r'''(g.year ? String(g.year) : t("h.state.unknownYear"))''', 1),
(r'''$("#sort").title = byDisc ? "Ordine deciso dal filtro Scopri" : "Ordinamento";''', r'''$("#sort").title = byDisc ? t("h.state.sortByDisc") : t("h.state.sortTitle");''', 1),
]
SC = {
"h.state.loadingStores": "Caricamento dei giochi degli store…", "h.state.storesErr": "Giochi degli store non caricati: {msg}",
"h.state.allLangs": "Tutte le lingue", "h.state.unknownYear": "Anno sconosciuto",
"h.state.sortByDisc": "Ordine deciso dal filtro Scopri", "h.state.sortTitle": "Ordinamento",
}
apply("js/state.js", S, SC)
