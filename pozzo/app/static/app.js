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

/* Finestra Media separata (#media-window): stessa interfaccia, ma solo la vista Media a tutta finestra.
 * Si decide subito, prima di main(), così la barra laterale non lampeggia nemmeno per un istante. */
if (location.hash === "#media-window") {
  document.body.classList.add("media-window");
  document.title = "Media · Pozzo Launcher";
  const st = document.createElement("style");
  st.textContent = "body.media-window #sidebar,body.media-window #experience-bar,body.media-window #drawer-scrim,body.media-window #menubar,"
    + "body.media-window #toolbar{display:none!important}body.media-window #app{grid-template-columns:1fr!important}";
  document.head.appendChild(st);
}

(async function main() {
  try { await loadSettingsMarkup(); } catch (e) {
    loading(null);
    toast(t("a.app.errSettings", { msg: e.message }), true);
    return;
  }
  const resumeEl = $("#resume-session-start");
  if (resumeEl) {
    resumeEl.checked = !!store.get("resumeSession", true);
    resumeEl.addEventListener("change", () => store.set("resumeSession", resumeEl.checked));
  }
  bind();
  loading(t("a.app.loadingGames"));
  await loadExtensions(); // prima della libreria: l'attesa si vede gia' col tema scelto
  const settingsHash = location.hash.match(/^#settings(?:\/([a-z0-9:_-]+))?$/i);
  if (settingsHash) showTab(settingsHash[1] || "generale");
  if (document.body.classList.contains("media-window")) {
    // seconda finestra dedicata a Media: niente libreria giochi, procedura guidata o sondaggi; si apre solo la vista Media
    loading(null);
    loadProfile();
    S.smart = S.smart || [];  // il titolo della pagina li legge anche se la libreria non e' stata caricata
    S.view = { type: "plugin", id: "media" };
    if (GS.ui.views.has("media")) setView(S.view);
    else $("#plugin-view").textContent = t("h.view.unavailable"), $("#plugin-view").hidden = false, $("#grid-scroll").hidden = true;
    return;
  }
  const resumeEnabled = !!store.get("resumeSession", true);
  let lastSession = null;
  if (resumeEnabled) {
    try {
      const raw = localStorage.getItem("gs.last_session");
      if (raw) lastSession = JSON.parse(raw);
    } catch {}
    if (lastSession?.view && typeof lastSession.view === "object" && lastSession.view.type) {
      S.view = lastSession.view;
    }
  }
  if (GS.experience.home && !store.get("view", null) && (!resumeEnabled || !lastSession?.view)) S.view = { type: "home" };
  loadProfile();
  try {
    await SETUP.open();  // primo avvio: configurazione guidata (non fa nulla se gia' configurato)
    if (!(await loadLibrary())) {
      const st = await api("/api/status");
      if (!st.has_library) { await waitFirstBuild(); await loadLibrary(); }
    }
  } catch (e) {
    loading(null);
    toast(t("a.app.errLibrary", { msg: e.message }), true);
    return;
  }
  if (S.view.type === "collection" && !S.collBySlug.has(S.view.id)) S.view = { type: "all" };
  if (S.view.type === "platform" && !S.plats.has(S.view.id)) S.view = { type: "all" };
  if (S.view.type === "plugin" && !GS.ui.views.has(S.view.id)) S.view = { type: "all" };
  renderSidebar();
  setView(S.view);
  if (resumeEnabled && lastSession?.gameId && S.games.some((g) => g.id === lastSession.gameId)) {
    openDetail(lastSession.gameId);
  }
  pollRunning();
  pollScan(); // se uno scraping era gia' in corso, ne mostra lo stato
})();
