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
  try { r = await api(`/api/game/${id}/play`, { body }); } catch (e) { return toastError(e); }
  if (r.ask) { const w = await askWindow(); return w && play(id, { ...body, ...w }); } // «disco veloce» resta anche dopo la scelta della finestra
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

/* Dove compare un gioco nelle varie viste e in quale attributo sta il suo id (selettore, chiave di dataset): il clic
   destro vale ovunque, non solo nella griglia. Una nuova vista con le sue schede si aggiunge qui (c'e' un test). */
const GAME_TARGETS = [
  [".tile[data-id]", "id"], [".nf-card[data-id]", "id"], [".top-row[data-id]", "id"], ["li[data-id]", "id"],
  ["[data-cnx-id]", "cnxId"], ["[data-console-game]", "consoleGame"], ["[data-console-open]", "consoleOpen"],
  ["[data-dashboard-game]", "dashboardGame"], ["[data-vetrina-game]", "vetrinaGame"],
    ["[data-shelf-game]", "shelfGame"],
  ];

/** Il gioco sotto il puntatore, in qualunque vista; null se non c'e' (id non numerici, schede non di un gioco). */
function gameFromEvent(e) {
  for (const [sel, key] of GAME_TARGETS) {
    const el = e.target.closest(sel);
    const g = el && S.byId.get(+el.dataset[key]);
    if (g) return g;
  }
  return null;
}

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
  if (grp.favorite) out.push({ l: t("h.app.navFavorites"), view: "favorites", f: () => setGrp(g, "favorite", false) });
  if (grp.last > 0) out.push({ l: t("h.title.recent"), view: "recent", f: () => setGrp(g, "last_played", null) });
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
  if (g.store !== "online") rows.push({ l: "▶ " + t("h.act.play"), f: () => play(g.id) });
  rows.push({ l: t("h.common.details"), f: () => openDetail(g.id) });
  if (!g.store) rows.push({ l: "📂 " + t("h.lb.showFolder"), f: () => api(`/api/game/${g.id}/open-folder`, { body: {} }) });
  rows.push({ l: "🖼 " + t("h.act.images"), f: () => openMediaPick(g) });
  if (g.store !== "online") rows.push({ l: "🔗 " + t("h.act.apps"), f: () => openProfile(g) });
  if (g.store && !["online", "manual"].includes(g.store)) {
    if (!g.installed) rows.push({ l: "⬇ " + t("h.grid.install"), f: () => installGame(g.id) });
    if (!g.installed && g.store === "steam") rows.push({ l: "⬇ " + t("h.steamcmd.menu"), f: () => steamcmdDownload(g.id) });
    rows.push({ l: "🛒 " + t("h.act.storePage"), f: () => api(`/api/game/${g.id}/store-page`, { body: {} }) });
  }
  if (g.store !== "online") rows.push({ l: "🖥 " + t("h.act.shortcut"), f: async () => {
    await api(`/api/game/${g.id}/shortcut`, { body: {} });
    toast(t("h.act.shortcutMade", {name: g.title}));
  } });
  rows.push({ l: "📋 " + t("h.act.copyTitle"), f: () => navigator.clipboard.writeText(g.title).then(() => toast(t("h.act.titleCopied"))) });
  if (here) rows.push("-", { l: "✖ " + t("h.act.removeFrom", {l: here.l}), f: here.f, hl: 1 });
  rows.push("-", { l: grp.favorite ? "★ " + t("h.act.unfav") : "☆ " + t("h.act.fav"), f: async () => {
    await setGrp(g, "favorite", !grp.favorite);
    toast(grp.favorite ? t("h.act.inFavs", {name: g.title}) : t("h.act.outFavs", {name: g.title})); // nella Home non cambia nulla a vista
  } });
  rows.push({ l: "＋ " + t("h.act.addColl"), f: () => pickCollection(pt, g.id, grp.colls.map((i) => S.colls[i]?.slug)) });
  rows.push({ h: t("h.act.rating") }, { stars: true });
  rows.push({ h: t("h.act.status") });
  for (const [k, s] of Object.entries(STATUS)) if (grp.status !== k) rows.push({ l: `${s.icon} ${s.label}`, f: async () => {
    await setGrp(g, "status", k);
    toast(t("h.act.statusSet", {name: g.title, s: s.label}));
  } });
  const others = rem.filter((r) => r !== here);
  if (others.length) rows.push({ h: t("h.act.removeFromH") }, ...others.map((r) => ({ l: `✖ ${r.l}`, f: r.f })));
  rows.push("-", { l: grp.hidden ? t("h.act.showAgain") : t("h.act.hideLib"), f: () => setGrp(g, "hidden", !grp.hidden) });
  if (g.store === "manual") rows.push({ l: "🗑 " + t("h.act.removeLib"), f: () => removeManual(g) });

  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.innerHTML = rows.map((r, i) => r === "-" ? "<hr>" : r.h ? `<div class="ch">${esc(r.h)}</div>`
    : r.stars ? `<div class="stars">${[5, 4, 3, 2, 1].map((n) => `<span class="st" data-n="${n}" title="${n}/5">★</span>`).join("")}</div>`
    : `<div class="ci${r.hl ? " hl" : ""}" data-i="${i}">${esc(r.l)}</div>`).join("");
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + "px";
  m.onclick = async (ev) => {
    const star = ev.target.closest(".st");
    if (star) {
      closeCtx();
      try {
        await api(`/api/game/${g.id}/flag`, { body: { field: "my_rating", value: +star.dataset.n } });
        toast(t("h.act.ratedTo", {n: star.dataset.n, name: g.title}));
        if (S.detail?.id === g.id) openDetail(g.id);
      } catch (err) { toast(err.message, true); }
      return;
    }
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    try { await rows[+it.dataset.i].f(); } catch (err) { toastError(err); }
  };
}

/** Toglie un gioco aggiunto a mano dalla libreria: i file sul disco non vengono toccati. */
async function removeManual(g) {
  if (!confirm(t("h.act.confirmRemove", {name: g.title}))) return;
  await api(`/api/manual/${encodeURIComponent(g.key)}`, { method: "DELETE" });
  if (S.detail?.id === g.id) closeDetail();
  await reload(true);
  toast(t("h.act.removed"));
}

/* ---- immagine scelta a mano: ricerca su Google Immagini (titolo gia' scritto) e indirizzo incollato */
let MD = null;
function googleImages() {
  const q = $("#md-q").value.trim() || MD?.title || "";
  $("#md-google").href = `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(q)}`;
}

/* ---- immagini del gioco: per tipo, quelle delle fonti e quelle scelte a mano (file dal PC o indirizzo) */
let MDK = null;  // risposta di GET /api/game/{id}/media

async function openMediaPick(g, kind = "cover") {
  MD = g;
  MDK = null;
  $("#md-game").textContent = `— ${g.title}`;
  $("#md-q").value = g.title;
  $("#md-url").value = "";
  $("#md-tiles").innerHTML = `<p class="muted small">${t("h.media.loading")}</p>`;
  googleImages();
  $("#media-dlg").showModal();
  try { MDK = await api(`/api/game/${g.id}/media`); } catch (e) { return toast(e.message, true); }
  renderMedia(kind);
}

function renderMedia(kind) {
  if (!MDK) return;
  const sel = $("#md-kind");
  if (sel.options.length !== MDK.kinds.length) sel.innerHTML = MDK.kinds.map((k) => `<option value="${k.kind}">${esc(k.label)}</option>`).join("");
  sel.value = kind;
  const t = Date.now();  // stesso indirizzo /img/… con un file nuovo: si forza il ricaricamento
  $("#md-tiles").innerHTML = MDK.kinds.map((k) => `<button type="button" class="md-tile${k.kind === kind ? " on" : ""}" data-kind="${k.kind}" aria-pressed="${k.kind === kind}">
    <span class="md-img">${k.url ? `<img src="${k.url}?w=300&t=${t}" alt="" loading="lazy">` : `<span class="muted small">${window.t("h.media.none")}</span>`}</span>
    <span class="md-cap">${esc(k.label)}<span class="muted small">${k.custom ? window.t("h.media.chosen") : k.source ? window.t("h.media.fromSrc") : "—"}</span></span></button>`).join("");
  const cur = MDK.kinds.find((k) => k.kind === kind);
  $("#md-reset").hidden = !cur?.custom;
  $("#md-reset").textContent = cur?.source ? "↺ " + window.t("h.media.restore") : "🗑 " + window.t("h.media.remove");
  sgdbCands(kind);
}

/* candidati di SteamGridDB per il tipo scelto, se l'estensione c'e' e ha la chiave (risultati tenuti per gioco e tipo) */
const SGDB = { cache: new Map(), off: false };
async function sgdbCands(kind) {
  const box = $("#md-sgdb"), g = MD;
  if (SGDB.off || !g) { box.hidden = true; return; }
  const ck = `${g.id}:${kind}`;
  let r = SGDB.cache.get(ck);
  if (!r) {
    box.hidden = false;
    $("#md-sgdb-msg").textContent = t("h.media.searching");
    $("#md-cands").innerHTML = "";
    try { r = await api(`/plugin-api/steamgriddb/cerca?q=${encodeURIComponent($("#md-q").value.trim() || g.title)}&kind=${kind}`); }
    catch (e) {
      // estensione non installata (404): la sezione sparisce; chiave mancante o rete: si dice perche'
      if (/not found/i.test(e.message)) { SGDB.off = true; box.hidden = true; return; }
      r = { error: e.message, items: [] };
    }
    SGDB.cache.set(ck, r);
  }
  if (MD !== g || $("#md-kind").value !== kind) return;  // nel frattempo si e' scelto altro
  box.hidden = false;
  $("#md-sgdb-msg").textContent = r.error || (r.items.length ? t("h.media.sgdbFrom", {g: r.game ? t("h.media.sgdbGame", {g: r.game}) : ""}) : t("h.media.sgdbNone"));
  const img = (u) => /^https:\/\/cdn2\.steamgriddb\.com\//.test(u) ? `/remote-img?u=${encodeURIComponent(u)}` : u;
  $("#md-cands").innerHTML = r.items.map((i) => `<button type="button" data-url="${esc(i.url)}" title="${i.w && i.h ? `${i.w}×${i.h}` : ""}"><img src="${esc(img(i.thumb))}" alt="" loading="lazy"></button>`).join("");
}

async function mediaChanged(r, msg) {
  MDK = r;
  renderMedia($("#md-kind").value);
  toast(msg);
  const g = MD;
  await reload(true);
  if (S.detail?.id === g.id) openDetail(g.id);
}

async function useMedia(url) {
  const g = MD;
  if (!g || !/^https?:\/\//i.test(url || "")) return toast(t("h.media.needUrl"), true);
  let r;
  try { r = await api(`/api/game/${g.id}/media`, { body: { kind: $("#md-kind").value, url } }); }
  catch (e) { return toast(e.message, true); }
  $("#md-url").value = "";
  await mediaChanged(r, t("h.media.saved"));
}

async function uploadMedia(file) {
  const g = MD;
  if (!g || !file) return;
  if (!/^image\//.test(file.type || "image/")) return toast(t("h.media.needImg"), true);
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/api/game/${g.id}/media/${$("#md-kind").value}/file`, { method: "POST", body: fd });
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch { /* risposta non JSON */ }
    return toast(m, true);
  }
  await mediaChanged(await r.json(), t("h.media.uploaded"));
}

async function resetMedia() {
  const g = MD;
  if (!g) return;
  let r;
  try { r = await api(`/api/game/${g.id}/media/${$("#md-kind").value}`, { method: "DELETE" }); }
  catch (e) { return toast(e.message, true); }
  await mediaChanged(r, t("h.media.removed"));
}

/* ---- incolla una cartella per una console (o per i giochi PC) e cerca solo i giochi nuovi */
async function pasteFolder(platform) {
  let path = "";
  try { path = (await navigator.clipboard.readText() || "").trim().replace(/^"|"$/g, ""); }
  catch { /* permesso negato o pagina non in HTTPS: si chiede a mano */ }
  if (!path) path = prompt(t("h.paste.askPath", {p: platform === "windows" ? t("h.paste.pcGames") : platName(platform)})) || "";
  path = path.trim().replace(/^"|"$/g, "");
  if (!path) return;
  let r;
  try { r = await api("/api/folders/add", { body: { platform, path } }); }
  catch (e) { return toast(e.message, true); }
  // giochi PC: {added}; console: lo stato dello scraping appena avviato (i giochi nuovi si vedono nella barra)
  if (r.added) toast(t("h.paste.added", {n: r.added, w: r.added === 1 ? t("h.paste.pc1") : t("h.paste.pcGames")}));
  else if (r.status === "running" || (r.keys || []).length) { toast(t("h.paste.searching")); SET.lastStatus = "running"; pollScan(); }
  else toast(t("h.paste.plain"));
  await reload(true);
  loadScan();
}

/** Errore di avvio. Con un crash (emulatore chiuso subito) mostra codice, durata e ultimo log; con un fallback il bottone per riprovare con quello. */
function launchErrorToast(r) {
  if (!r.crash && !r.fallback) return toast(r.message, true);
  const t = $("#toast"), c = r.crash;
  if (t.parentElement !== overlayHost()) overlayHost().appendChild(t);
  t.className = "err";
  t.setAttribute("role", "alert");
  const body = document.createElement("div");
  body.style.cssText = "display:grid;gap:6px;max-width:min(560px,90vw)";
  const text = document.createElement("div");
  text.textContent = c ? window.t("h.launch.crash", {code: c.code, s: Math.round(c.duration * 10) / 10}) : r.message;
  body.appendChild(text);
  if (c && c.log) {
    const det = document.createElement("details"), sum = document.createElement("summary"), pre = document.createElement("pre");
    sum.textContent = window.t("h.launch.lastLog");
    pre.textContent = c.log;  // textContent: il log dell'emulatore non e' HTML
    pre.style.cssText = "max-height:40vh;overflow:auto;white-space:pre-wrap;margin:6px 0 0;font-size:12px";
    det.append(sum, pre);
    body.appendChild(det);
  }
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap";
  const add = (label, onclick) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "toast-undo";
    b.textContent = label;
    b.onclick = onclick;
    bar.appendChild(b);
  };
  const g = [...S.byId.values()].find((x) => x.key === r.key);
  if (g && r.fallback) add(window.t("h.launch.tryWith", {l: r.fallback.label}), () => { t.hidden = true; play(g.id, { fallback: r.fallback.id }); });
  // «Perché?» apre il pannello di detail.js (window.openDiagnose): solo se caricato
  if (g && typeof openDiagnose === "function") add(window.t("h.launch.why"), () => { t.hidden = true; openDiagnose(g.id); });
  add(window.t("h.common.close"), () => { t.hidden = true; });
  t.replaceChildren(body, bar);
  t.hidden = false;
  clearTimeout(toastTimer);
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
    const what = r.status === "extracting" ? (r.message || t("h.run.extract")) : r.status === "starting" ? t("h.run.starting") : t("h.run.running", {e: esc(r.emulator)});
    bar.innerHTML = `<span class="dot"></span><b>${esc(r.title)}</b><span class="muted">${esc(what)}</span>`
      + (r.status === "running" ? `<button class="btn" id="run-stop" title="${t("h.run.closeTitle")}">■ ${t("h.run.close")}</button><button class="btn" id="run-shot" title="${t("h.run.shotTitle", {hk: esc(SHOTS.hotkey)})}">📷${r.shots ? " " + r.shots : ""}</button>` : "");
    if (S.running && r.status === "running" && (r.shots || 0) > (S.running.shots || 0)) toast("📷 " + t("h.run.shotSaved"));
    pollTimer = setTimeout(pollRunning, 1500);
  } else {
    bar.hidden = true;
    if (S.running && S.running.started === r.started) {
      if (r.status === "error") launchErrorToast(r);
      if (r.status === "finished") {
        toast(t("h.run.ended", {time: fmtTime(r.played)}) + (r.shots ? " · " + t("h.run.shots", {n: r.shots, w: r.shots === 1 ? t("h.run.shot1") : t("h.run.shotN")}) : ""));
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
  toast(t("h.act.installHint"));
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
  $("#ag-exe-lbl").textContent = web ? t("h.add.url") : t("h.add.exe");
  $("#ag-exe").placeholder = web ? "https://www.chess.com" : "C:\\Giochi\\MioGioco\\gioco.exe";
  $("#ag-title").placeholder = web ? t("h.add.titleWeb") : t("h.add.titleExe");
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
  if (!exe) return toast(kind === "browser" ? t("h.add.needUrl") : kind === "app" ? t("h.add.needAppExe") : t("h.add.needGameExe"), true);
  const btn = $("#ag-save");
  btn.disabled = true;
  btn.textContent = t("h.add.adding");
  let res;
  try {
    res = await api("/api/manual", { body: kind === "browser" ? { url: exe, title: $("#ag-title").value.trim(), kind }
      : { exe, title: $("#ag-title").value.trim(), args: $("#ag-args").value, kind } });
  } catch (e) { return toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = t("h.add.add"); }
  $("#add-game").close();
  await reload(true);  // il gioco e' gia' in libreria: copertina e metadati arrivano dopo, solo per lui
  toast(res && res.warning ? t("h.add.browserWarn", {w: res.warning}) : kind === "app" ? t("h.add.appAdded")
    : kind === "browser" ? t("h.add.browserAdded") : t("h.add.gameAdded"), !!(res && res.warning));
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
  $("#collart-info").textContent = t("h.col.info", {a: js.with_icon, b: js.total, c: js.with_wiki});
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
  $("#hltb-info").textContent = t("h.hltb.info", {a: (js.with_hltb || 0).toLocaleString(GSI18n.lang), b: (js.known || 0).toLocaleString(GSI18n.lang)});
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
      toast(t("h.act.wishToast", {n: w.unseen, o: w.unseen === 1 ? t("h.act.offer1") : t("h.act.offerN")}));
    }
  } catch { /* server non pronto */ }
  setTimeout(pollWishBadge, 10 * 60 * 1000);
}
