"use strict";
/* Pozzo Launcher - frontend: popover, avvio, menu contestuale, giochi PC, lista dei desideri. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ popover (collezioni / testo) */
function closePopover() { $("#popover").hidden = true; $("#popover").innerHTML = ""; }

// un <dialog> modale rende inattivo tutto il resto: popover e notifiche vanno spostati dentro
function overlayHost() { return document.querySelector("dialog[open]") || $("#app"); }

function placePopover(anchor) {
  const p = $("#popover"), r = anchor.getBoundingClientRect();
  if (p.parentElement !== overlayHost()) overlayHost().appendChild(p);
  p.hidden = false;
  const left = Math.min(r.left, window.innerWidth - 316), top = Math.min(r.bottom + 6, window.innerHeight - p.offsetHeight - 10);
  p.style.left = Math.max(8, left) + "px";
  p.style.top = Math.max(8, top) + "px";
}

function askText(anchor, placeholder, initial = "") {
  return new Promise((resolve) => {
    const p = $("#popover");
    p.innerHTML = `<input placeholder="${esc(placeholder)}" value="${esc(initial)}"><div style="display:flex;gap:6px;justify-content:flex-end">
      <button class="btn" data-a="cancel">Annulla</button><button class="btn primary" data-a="ok">OK</button></div>`;
    placePopover(anchor);
    const inp = $("input", p);
    inp.focus(); inp.select();
    const done = (v) => { closePopover(); resolve(v); };
    inp.onkeydown = (e) => { if (e.key === "Enter") done(inp.value.trim() || null); if (e.key === "Escape") done(null); };
    p.onclick = (e) => { const a = e.target.dataset.a; if (a === "ok") done(inp.value.trim() || null); if (a === "cancel") done(null); };
  });
}

function pickCollection(anchor, gameId, current) {
  const p = $("#popover");
  p.innerHTML = `<input placeholder="Cerca o crea collezione…"><div class="opts"></div>`;
  placePopover(anchor);
  const inp = $("input", p), opts = $(".opts", p);
  const cur = new Set(current);
  const draw = () => {
    const f = fold(inp.value.trim());
    const list = S.colls.filter((c) => !cur.has(c.slug) && !c.hidden && (!f || fold(c.name).includes(f)))
      .sort((a, b) => (S.collCounts.get(b.idx) || 0) - (S.collCounts.get(a.idx) || 0)).slice(0, 60);
    const exact = S.colls.some((c) => fold(c.name) === f);
    opts.innerHTML = (f && !exact ? `<div class="opt hl" data-new="1">＋ Nuova collezione «${esc(inp.value.trim())}»</div>` : "")
      + list.map((c) => `<div class="opt" data-slug="${esc(c.slug)}"><span>${esc(c.name)}</span><span class="muted">${S.collCounts.get(c.idx) || 0}</span></div>`).join("");
  };
  draw();
  inp.focus();
  inp.oninput = draw;
  inp.onkeydown = (e) => { if (e.key === "Enter") opts.querySelector(".opt")?.click(); if (e.key === "Escape") closePopover(); };
  opts.onclick = async (e) => {
    const o = e.target.closest(".opt");
    if (!o) return;
    try {
      if (o.dataset.new) await api("/api/collections", { body: { name: inp.value.trim(), game: gameId } });
      else await api(`/api/collections/${encodeURIComponent(o.dataset.slug)}/members`, { body: { game: gameId, action: "add" } });
    } catch (err) { return toast(err.message, true); }
    closePopover();
    await reload(true);
    if (S.detail?.id === gameId) openDetail(gameId);
  };
}

/* ------------------------------------------------------------------ avvio giochi */
async function play(id, body = {}) {
  let r;
  try { r = await api(`/api/game/${id}/play`, { body }); } catch (e) { return toast(e.message, true); }
  if (r.ask) { const w = await askWindow(); return w && play(id, w); }
  const btn = S.detail?.id === id && $("#d-play");
  if (btn) { btn.classList.add("mo-launch"); btn.addEventListener("animationend", () => btn.classList.remove("mo-launch"), { once: true }); }
  pollRunning();
}

/** Port senza modalità salvata: {window, remember} scelti dall'utente, null se chiude. */
function askWindow() {
  const dlg = $("#win-dlg");
  $("#win-remember").checked = false;
  dlg.returnValue = "";
  dlg.showModal();
  return new Promise((ok) => dlg.addEventListener("close", () => ok(dlg.returnValue ? { window: dlg.returnValue, remember: $("#win-remember").checked } : null), { once: true }));
}

/* ------------------------------------------------------------------ menu del tasto destro su un gioco */
function closeCtx() { document.getElementById("ctxmenu")?.remove(); }

async function setGrp(g, field, value) {
  await api(`/api/game/${g.id}/flag`, { body: { field, value } });
  if (field === "last_played") g.grp.last = 0;
  else g.grp[field] = field === "status" ? value || "" : value ? 1 : 0;
  renderSidebar();
  refreshGrid(true);
  if (S.detail?.id === g.id) openDetail(g.id);
}

/** Le categorie da cui il gioco si puo' togliere: preferiti, giocati di recente, stato e collezioni. */
function ctxRemovals(g) {
  const grp = g.grp, out = [];
  if (grp.favorite) out.push({ l: "Preferiti", view: "favorites", f: () => setGrp(g, "favorite", false) });
  if (grp.last > 0) out.push({ l: "Giocati di recente", view: "recent", f: () => setGrp(g, "last_played", null) });
  if (grp.status) out.push({ l: STATUS[grp.status]?.label || grp.status, view: "status", id: grp.status, f: () => setGrp(g, "status", "") });
  for (const i of grp.colls) {
    const c = S.colls[i];
    if (!c || c.hidden) continue;
    out.push({ l: c.name, view: "collection", id: c.slug, f: async () => {
      await api(`/api/collections/${encodeURIComponent(c.slug)}/members`, { body: { game: g.id, action: "remove" } });
      await reload(true);
    } });
  }
  return out;
}

function openCtx(e, g) {
  closeCtx();
  const grp = g.grp, rem = ctxRemovals(g);
  const here = rem.find((r) => r.view === S.view.type && (r.id ?? null) === (S.view.id ?? null));
  const pt = { getBoundingClientRect: () => ({ left: e.clientX, bottom: e.clientY }) };
  const rows = [];
  if (g.store !== "online") rows.push({ l: "▶ Gioca", f: () => play(g.id) });
  rows.push({ l: "Dettagli", f: () => openDetail(g.id) });
  if (!g.store) rows.push({ l: "📂 Mostra nella cartella", f: () => api(`/api/game/${g.id}/open-folder`, { body: {} }) });
  rows.push({ l: "🖼 Cerca immagini…", f: () => openMediaPick(g) });
  if (g.store !== "online") rows.push({ l: "🔗 Applicazioni abbinate…", f: () => openProfile(g) });
  if (here) rows.push("-", { l: `✖ Rimuovi da «${here.l}»`, f: here.f, hl: 1 });
  rows.push("-", { l: grp.favorite ? "★ Togli dai preferiti" : "☆ Aggiungi ai preferiti", f: () => setGrp(g, "favorite", !grp.favorite) });
  rows.push({ l: "＋ Aggiungi a una collezione…", f: () => pickCollection(pt, g.id, grp.colls.map((i) => S.colls[i]?.slug)) });
  rows.push({ h: "Stato" });
  for (const [k, s] of Object.entries(STATUS)) if (grp.status !== k) rows.push({ l: `${s.icon} ${s.label}`, f: () => setGrp(g, "status", k) });
  const others = rem.filter((r) => r !== here);
  if (others.length) rows.push({ h: "Rimuovi da" }, ...others.map((r) => ({ l: `✖ ${r.l}`, f: r.f })));
  rows.push("-", { l: grp.hidden ? "Mostra di nuovo" : "Nascondi dalla libreria", f: () => setGrp(g, "hidden", !grp.hidden) });
  if (g.store === "manual") rows.push({ l: "🗑 Rimuovi dalla libreria", f: () => removeManual(g) });

  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.innerHTML = rows.map((r, i) => r === "-" ? "<hr>" : r.h ? `<div class="ch">${esc(r.h)}</div>`
    : `<div class="ci${r.hl ? " hl" : ""}" data-i="${i}">${esc(r.l)}</div>`).join("");
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + "px";
  m.onclick = async (ev) => {
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    try { await rows[+it.dataset.i].f(); } catch (err) { toast(err.message, true); }
  };
}

/** Toglie un gioco aggiunto a mano dalla libreria: i file sul disco non vengono toccati. */
async function removeManual(g) {
  if (!confirm(`Rimuovere «${g.title}» dalla libreria? Il gioco sul disco non viene toccato.`)) return;
  await api(`/api/manual/${encodeURIComponent(g.key)}`, { method: "DELETE" });
  if (S.detail?.id === g.id) closeDetail();
  await reload(true);
  toast("Rimosso dalla libreria");
}

/* ---- immagine scelta a mano: ricerca su Google Immagini (titolo gia' scritto) e indirizzo incollato */
let MD = null;
function googleImages() {
  const q = $("#md-q").value.trim() || MD?.title || "";
  $("#md-google").href = `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(q)}`;
}

function openMediaPick(g) {
  MD = g;
  $("#md-game").textContent = `— ${g.title}`;
  $("#md-q").value = g.title;
  $("#md-url").value = "";
  googleImages();
  $("#media-dlg").showModal();
}

async function useMedia(url) {
  const g = MD;
  if (!g || !/^https?:\/\//i.test(url || "")) return toast("Serve un indirizzo di immagine (http o https)", true);
  try { await api(`/api/game/${g.id}/media`, { body: { kind: $("#md-kind").value, url } }); }
  catch (e) { return toast(e.message, true); }
  $("#media-dlg").close();
  toast("Immagine salvata");
  await reload(true);
  if (S.detail?.id === g.id) openDetail(g.id);
}

/* ---- incolla una cartella per una console (o per i giochi PC) e cerca solo i giochi nuovi */
async function pasteFolder(platform) {
  let path = "";
  try { path = (await navigator.clipboard.readText() || "").trim().replace(/^"|"$/g, ""); }
  catch { /* permesso negato o pagina non in HTTPS: si chiede a mano */ }
  if (!path) path = prompt(`Percorso della cartella (${platform === "windows" ? "giochi PC" : platName(platform)})`) || "";
  path = path.trim().replace(/^"|"$/g, "");
  if (!path) return;
  let r;
  try { r = await api("/api/folders/add", { body: { platform, path } }); }
  catch (e) { return toast(e.message, true); }
  // giochi PC: {added}; console: lo stato dello scraping appena avviato (i giochi nuovi si vedono nella barra)
  if (r.added) toast(`Cartella aggiunta: ${r.added} ${r.added === 1 ? "gioco PC" : "giochi PC"}`);
  else if (r.status === "running" || (r.keys || []).length) { toast("Cartella aggiunta: cerco i giochi nuovi…"); SET.lastStatus = "running"; pollScan(); }
  else toast("Cartella aggiunta");
  await reload(true);
  loadScan();
}

let pollTimer = 0;
async function pollRunning() {
  clearTimeout(pollTimer);
  let r;
  try { r = await api("/api/running"); } catch { r = {}; }
  const bar = $("#running");
  const active = ["starting", "extracting", "running"].includes(r.status);
  if (active) {
    bar.hidden = false;
    bar.className = r.status === "extracting" ? "extracting" : "";
    const what = r.status === "extracting" ? (r.message || "Estrazione…") : r.status === "starting" ? "Avvio…" : `In esecuzione con ${esc(r.emulator)}`;
    bar.innerHTML = `<span class="dot"></span><b>${esc(r.title)}</b><span class="muted">${esc(what)}</span>`
      + (r.status === "running" ? `<button class="btn" id="run-stop" title="Chiude il gioco in esecuzione">■ Chiudi gioco</button><button class="btn" id="run-shot" title="Schermata del gioco (${esc(SHOTS.hotkey)} · controller: Select+R1)">📷${r.shots ? " " + r.shots : ""}</button>` : "");
    if (S.running && r.status === "running" && (r.shots || 0) > (S.running.shots || 0)) toast("📷 Schermata salvata");
    pollTimer = setTimeout(pollRunning, 1500);
  } else {
    bar.hidden = true;
    if (S.running && S.running.started === r.started) {
      if (r.status === "error") toast(r.message, true);
      if (r.status === "finished") {
        toast(`Sessione terminata: ${fmtTime(r.played)}${r.shots ? ` · ${r.shots} ${r.shots === 1 ? "schermata" : "schermate"}` : ""}`);
        reload(true);
        if (S.detail) openDetail(S.detail.id);
      }
    }
  }
  S.running = r;
}


/* ------------------------------------------------------------------ giochi PC: installa, aggiungi, store */
async function installGame(id) {
  try { await api(`/api/game/${id}/install`, { body: {} }); }
  catch (e) { return toast(e.message, true); }
  toast("Apro lo store per l'installazione. Al termine premi «↻ Aggiorna store» in Impostazioni › Account.");
}

function openAddGame(kind = "game") {
  const dlg = $("#add-game");
  $("#ag-exe").value = ""; $("#ag-title").value = ""; $("#ag-title").dataset.auto = ""; $("#ag-args").value = "";
  $("#ag-kind").value = kind;
  agKindChanged();
  dlg.showModal();
  $("#ag-exe").focus();
}

/** «Browser / URL»: il campo diventa un URL, niente Sfoglia e niente argomenti. */
function agKindChanged() {
  const web = $("#ag-kind").value === "browser";
  $("#ag-exe-lbl").textContent = web ? "URL" : "Eseguibile";
  $("#ag-exe").placeholder = web ? "https://www.chess.com" : "C:\\Giochi\\MioGioco\\gioco.exe";
  $("#ag-title").placeholder = web ? "se vuoto: titolo della pagina" : "se vuoto: nome del file .exe";
  $("#ag-pick").hidden = $("#ag-args-lbl").hidden = web;
}

/** Titolo = nome del file .exe (senza estensione), a meno che l'utente ne abbia scritto uno suo. */
function agTitleFromExe() {
  const t = $("#ag-title");
  if ($("#ag-kind").value === "browser" || (t.value && t.dataset.auto !== t.value)) return;
  const name = $("#ag-exe").value.trim().replace(/^"|"$/g, "").split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
  t.value = name;
  t.dataset.auto = name;
}

async function saveAddGame() {
  const exe = $("#ag-exe").value.trim();
  const kind = ({ app: "app", browser: "browser" })[$("#ag-kind").value] || "game";
  if (!exe) return toast(kind === "browser" ? "Inserisci l'URL del gioco" : kind === "app" ? "Scegli il file .exe dell'applicazione" : "Scegli il file .exe del gioco", true);
  const btn = $("#ag-save");
  btn.disabled = true;
  btn.textContent = "Aggiungo…";
  let res;
  try {
    res = await api("/api/manual", { body: kind === "browser" ? { url: exe, title: $("#ag-title").value.trim(), kind }
      : { exe, title: $("#ag-title").value.trim(), args: $("#ag-args").value, kind } });
  } catch (e) { return toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = "Aggiungi"; }
  $("#add-game").close();
  await reload(true);  // il gioco e' gia' in libreria: copertina e metadati arrivano dopo, solo per lui
  toast(res && res.warning ? `Gioco browser aggiunto. ${res.warning}` : kind === "app" ? "Applicazione aggiunta"
    : kind === "browser" ? "Gioco browser aggiunto" : "Gioco aggiunto: cerco copertina e dati…", !!(res && res.warning));
  pollManual();
}

/** Finche' il server cerca copertina e metadati dei giochi appena aggiunti, ricarica la libreria al termine. */
let manualTimer = 0;
async function pollManual() {
  clearTimeout(manualTimer);
  let r;
  try { r = await api("/api/manual/state"); } catch { return; }
  if (r.busy) { manualTimer = setTimeout(pollManual, 1000); return; }
  await reload(true);
  if (S.detail) openDetail(S.detail.id);
}

/* ---- immagini delle collezioni */
let caTimer = 0;
async function pollCollart(started = false) {
  clearTimeout(caTimer);
  let js;
  try { js = await api("/api/collart"); } catch { return; }
  if (started && js.status !== "running") js.status = "running";
  $("#collart-info").textContent = `${js.with_icon} collezioni su ${js.total} con un'icona · ${js.with_wiki} da Wikipedia`;
  renderJobInto($("#collart-progress"), js);
  const run = js.status === "running";
  $("#collart-missing").disabled = $("#collart-all").disabled = run;
  $("#collart-stop").hidden = !run;
  if (run && settingsOpen()) caTimer = setTimeout(pollCollart, 2000);
}
async function startCollart(mode) {
  try { await api("/api/collart", { body: { mode } }); } catch (e) { return toast(e.message, true); }
  pollCollart(true);
}

/* ---- HowLongToBeat */
let hltbTimer = 0, hltbRunning = false;
async function pollHltb(started = false) {
  clearTimeout(hltbTimer);
  let js;
  try { js = await api("/api/hltb"); } catch { return; }
  if (started && js.status !== "running") js.status = "running";
  $("#hltb-info").textContent = `${(js.with_hltb || 0).toLocaleString("it")} giochi con la durata · ${(js.known || 0).toLocaleString("it")} già cercati`;
  renderJobInto($("#hltb-progress"), js);
  const run = js.status === "running";
  $("#hltb-missing").disabled = $("#hltb-all").disabled = run;
  $("#hltb-stop").hidden = !run;
  if (run) { hltbRunning = true; hltbTimer = setTimeout(pollHltb, 1500); return; }
  if (hltbRunning) { hltbRunning = false; if (js.status === "done") { await reload(true); toast(js.phase); } else if (js.status === "error") toast(js.phase, true); }
}
async function startHltb(mode) {
  try { await api("/api/hltb", { body: { mode } }); } catch (e) { return toast(e.message, true); }
  pollHltb(true);
}

/* ---- lista dei desideri: badge degli avvisi */
async function pollWishBadge() {
  try {
    const w = await api("/api/wishlist");
    $("#cnt-wish").textContent = w.unseen ? `🔔 ${w.unseen}` : w.items.length || "";
    $("#cnt-wish").classList.toggle("alert", !!w.unseen);
    if (w.unseen && !pollWishBadge.told) {
      pollWishBadge.told = true;
      toast(`♡ Lista desideri: ${w.unseen} ${w.unseen === 1 ? "offerta" : "offerte"} da vedere`);
    }
  } catch { /* server non pronto */ }
  setTimeout(pollWishBadge, 10 * 60 * 1000);
}
