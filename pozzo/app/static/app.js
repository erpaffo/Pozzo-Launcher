"use strict";
/* Pozzo Launcher - frontend.
 * Tutta la libreria arriva in un'unica risposta compatta: ricerca, filtri, ordinamenti e
 * raggruppamenti sono calcolati qui in memoria (istantanei anche con 15.000 giochi).
 * La griglia e' virtualizzata: esistono nel DOM solo le copertine visibili (+ un margine). */

// utilita' condivise (api, esc, fold, store, SHORT...) in core.js
// il resto del frontend e' diviso per area in js/*.js (caricati prima di questo file da index.html)

/* ------------------------------------------------------------------ avvio */
GS.toast = (m, err) => toast(m, err);
GS.openGame = (id) => openDetail(id);
GS.library = () => S;
GS.currentGame = () => S.detail;
GS.refresh = () => reload(true);
GS.redraw = () => { if (S.games.length) refreshGrid(true); };  // ridisegna le copertine (badge di un'estensione arrivati dopo)
// clic su una notifica di Windows: apre la sezione (e la pagina del port) indicata dall'avviso
window.gsNotifyAction = (a) => {
  if (!a || a.view !== "ports") return;
  closeSettings(); closeDetail();
  PORTS_F.open = typeof a.port === "string" && /^[\w.-]+$/.test(a.port) ? a.port : null;
  setView({ type: "ports" });
};

(async function main() {
  try { await loadSettingsMarkup(); } catch (e) {
    loading(null);
    toast(`Errore nel caricamento delle impostazioni: ${e.message}`, true);
    return;
  }
  bind();
  loading("Caricamento dei tuoi giochi…");
  await loadExtensions(); // prima della libreria: l'attesa si vede gia' col tema scelto
  const settingsHash = location.hash.match(/^#settings(?:\/([a-z0-9:_-]+))?$/i);
  if (settingsHash) showTab(settingsHash[1] || "generale");
  if (GS.experience.home && !store.get("view", null)) S.view = { type: "home" };
  loadProfile();
  try {
    await SETUP.open();  // primo avvio: configurazione guidata (non fa nulla se gia' configurato)
    if (!(await loadLibrary())) {
      const st = await api("/api/status");
      if (!st.has_library) { await waitFirstBuild(); await loadLibrary(); }
    }
  } catch (e) {
    loading(null);
    toast("Errore nel caricamento della libreria: " + e.message, true);
    return;
  }
  if (S.view.type === "collection" && !S.collBySlug.has(S.view.id)) S.view = { type: "all" };
  if (S.view.type === "platform" && !S.plats.has(S.view.id)) S.view = { type: "all" };
  if (S.view.type === "plugin" && !GS.ui.views.has(S.view.id)) S.view = { type: "all" };
  renderSidebar();
  setView(S.view);
  pollRunning();
  pollScan(); // se uno scraping era gia' in corso, ne mostra lo stato
})();
