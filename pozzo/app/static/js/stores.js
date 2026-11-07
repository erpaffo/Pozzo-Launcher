"use strict";
/* Pozzo Launcher - frontend: store, fonti dei dati, account, aspetto. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ---- metadati degli store (solo database offline) */
let smetaTimer = 0, smetaRunning = false;
async function pollStoreMeta(started = false) {
  clearTimeout(smetaTimer);
  let js;
  try { js = await api("/api/stores/metadata"); } catch { return; }
  if (started && js.status !== "running") js.status = "running";
  renderJobInto($("#smeta-progress"), js);
  const run = js.status === "running";
  $("#smeta-all").disabled = $("#smeta-missing").disabled = run;
  $("#smeta-stop").hidden = !run;
  if (run) { smetaRunning = true; smetaTimer = setTimeout(pollStoreMeta, 700); return; }
  if (smetaRunning) {
    smetaRunning = false;
    if (js.status === "done") { await reload(true); toast(js.phase); } else if (js.status === "error") toast(js.phase, true);
  }
}
async function startStoreMeta(missing) {
  try { await api("/api/stores/metadata", { body: { missing } }); } catch (e) { return toast(e.message, true); }
  pollStoreMeta(true);
}

let storeTimer = 0;
async function pollStores(started = false) {
  clearTimeout(storeTimer);
  let js;
  try { js = await api("/api/stores/refresh"); } catch { return; }
  if (started && js.status !== "running") js.status = "running"; // appena avviato
  const box = $("#acc-progress");
  if (box && settingsActive("store")) renderJobInto(box, js);
  if (js.status === "running") { storeTimer = setTimeout(pollStores, 1000); SET.storesRunning = true; return; }
  if (SET.storesRunning) {
    SET.storesRunning = false;
    if (js.status === "done") {
      await reload(true);
      toast(t("h.st.updatedLib"));
      if (S.view.type === "ports") { S.ports = null; renderPorts($("#plugin-view")); } // pulsante «Gioca» del port appena installato
    }
    else if (js.status === "error") toast(js.phase, true);
    if (settingsActive("store")) loadAccounts();
  }
}

function renderJobInto(box, js) {
  const bars = (js.tasks || []).filter((t) => t.total > 0).map((t) => {
    const pct = Math.min(100, Math.round((100 * t.done) / t.total));
    return `<div class="bar"><span>${esc(t.name)}</span><div class="track"><div class="fill" style="width:${pct}%"></div></div>`
      + `<span class="n">${Math.round(t.done).toLocaleString(GSI18n.lang)} / ${Math.round(t.total).toLocaleString(GSI18n.lang)}</span></div>`;
  }).join("");
  box.innerHTML = js.status === "idle" ? "" : `<div class="phase">${esc(js.phase || "")}</div><div class="bars">${bars}</div>`
    + `<pre class="log">${esc((js.log || []).join("\n"))}</pre>`;
}


/* ---- impostazioni › fonti dei dati */
async function loadSources() {
  let d;
  try { d = await api("/api/sources"); } catch (e) { return toast(e.message, true); }
  SET.sources = d;
  renderSources(d.sources);
  $("#bulk-list").innerHTML = d.bulk.map((b) => `<div class="bulk-row"><div class="grow"><b>${esc(b.name)}</b>
      <div class="muted small">${esc(b.description)}</div>
      <div class="muted small">${b.ready ? t("h.src.bulkReady", {n: b.games.toLocaleString(GSI18n.lang), mb: b.size_mb, d: new Date(b.updated * 1000).toLocaleDateString(GSI18n.lang)})
        : t("h.src.bulkNotYet")} · ${t("h.src.every", {n: b.refresh_days})}</div></div>
      <button class="btn" data-bulk="${esc(b.id)}">↻ ${t("h.src.updateNow")}</button></div>`).join("");
  const sch = d.schedule || {};
  $("#sch-on").checked = !!sch.enabled;
  $("#sch-time").value = sch.time || "03:00";
  $("#sch-mode").value = sch.mode || "missing";
  SET.sourcesSaved = collectSources(false);
  $("#sch-last").textContent = d.schedule_last ? t("h.src.last", {d: d.schedule_last}) : "";
  $("#rawg-key").placeholder = d.sources.find((x) => x.id === "rawg")?.has_key ? t("h.src.keySaved") : t("h.src.pasteKey");
  if (d.bulk_job.status === "running") pollBulk();
}

function renderSources(rows) {
  SET.srcRows = rows;
  $("#src-table").innerHTML = rows.map((x, i) => {
    const on = x.kind === "online";
    const num = (k, v) => on ? `<input class="field" data-lim="${k}" value="${v || ""}" placeholder="${k === "rate" ? "" : t("h.src.none")}">` : `<span class="muted">—</span>`;
    return `<tr data-src="${esc(x.id)}" class="${x.enabled ? "" : "src-off"}">
      <td><span class="src-move"><button class="icon-btn" data-mv="-1" title="Su">▲</button><button class="icon-btn" data-mv="1" title="Giù">▼</button></span></td>
      <td><label class="chk"><input type="checkbox" data-en ${x.enabled ? "checked" : ""}> <b>${esc(x.id)}</b></label>
        <span class="src-kind ${x.kind}">${x.kind}</span>${x.needs_key && !x.has_key ? ` <span class="status-bad">${t("h.src.noKey")}</span>` : ""}
        <div class="muted small">${esc(x.description)}</div></td>
      <td class="num">${on ? `${(x.usage.today || 0).toLocaleString(GSI18n.lang)} / ${(x.usage.month || 0).toLocaleString(GSI18n.lang)}` : "—"}</td>
      <td>${num("rate", x.policy.rate)}</td><td>${num("daily", x.policy.daily || "")}</td><td>${num("monthly", x.policy.monthly || "")}</td></tr>`;
  }).join("");
}

function collectSources(includeKey = true) {
  const order = [], limits = {};
  document.querySelectorAll("#src-table tr[data-src]").forEach((tr) => {
    const id = tr.dataset.src;
    if ($("[data-en]", tr).checked) order.push(id);
    const lim = {};
    tr.querySelectorAll("[data-lim]").forEach((i) => { lim[i.dataset.lim] = i.value.trim(); });
    if (Object.keys(lim).length) limits[id] = lim;
  });
  const body = { order, limits, schedule: { enabled: $("#sch-on").checked, time: $("#sch-time").value, mode: $("#sch-mode").value } };
  if (includeKey && $("#rawg-key").value.trim()) body.rawg_key = $("#rawg-key").value.trim();
  return body;
}

let sourceSaveTimer = 0, sourceSaveRevision = 0, sourceSaving = false;
function scheduleSourceSave() {
  sourceSaveRevision++;
  clearTimeout(sourceSaveTimer);
  if (sourceSaving) return;
  sourceSaveTimer = setTimeout(() => saveSourceSettings(sourceSaveRevision), 450);
}

async function saveSourceSettings(revision) {
  if (sourceSaving) return;
  sourceSaving = true;
  const previous = SET.sourcesSaved || collectSources(false);
  const body = collectSources(false);
  try {
    SET.sources = await api("/api/sources", { body });
    SET.sourcesSaved = body;
    savedToast(async () => {
      SET.sources = await api("/api/sources", { body: previous });
      SET.sourcesSaved = previous;
      loadSources();
    });
  } catch (e) { toast(e.message, true); }
  finally {
    sourceSaving = false;
    if (revision !== sourceSaveRevision) scheduleSourceSave();
  }
}

let bulkTimer = 0;
async function pollBulk() {
  clearTimeout(bulkTimer);
  const d = await api("/api/sources").catch(() => null);
  if (!d) return;
  $("#bulk-log").textContent = (d.bulk_job.log || []).slice(-8).join("\n");
  if (d.bulk_job.status === "running") bulkTimer = setTimeout(pollBulk, 1500);
  else if (settingsActive("fonti")) { loadSources(); if (d.bulk_job.status === "done") toast(t("h.src.dbUpdated")); }
}

async function showPlan() {
  const box = $("#scan-plan-box");
  box.innerHTML = `<p class="muted">${t("h.plan.calc")}</p>`;
  const sel = [...new Set([...document.querySelectorAll(".scan-sel:checked")].map((c) => c.dataset.p))];
  let d;
  try { d = await api("/api/scan/plan", { body: { platforms: sel, mode: $("#scan-mode").value } }); }
  catch (e) { box.innerHTML = ""; return toast(e.message, true); }
  const dur = (s) => (s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  box.innerHTML = `<table class="emu plan"><tr><th>${t("h.plan.source")}</th><th class="num">${t("h.plan.games")}</th><th class="num">${t("h.plan.requests")}</th><th class="num">${t("h.plan.time")}</th><th>${t("h.plan.notes")}</th></tr>`
    + d.plan.map((p) => `<tr><td>${esc(p.source)} ${p.offline ? `<span class="src-kind offline">offline</span>` : ""}</td>
      <td class="num">${p.games.toLocaleString(GSI18n.lang)}</td><td class="num">${p.offline ? "0" : p.requests.toLocaleString(GSI18n.lang)}</td>
      <td class="num">${p.offline ? t("h.plan.fewSec") : p.requests ? dur(p.seconds) : "—"}</td>
      <td class="muted small">${p.days > 1 ? t("h.plan.days", {d: p.days, note: esc(p.note || t("h.plan.dailyLimit"))}) : ""}
        ${p.month_left != null ? t("h.plan.left", {n: p.month_left.toLocaleString(GSI18n.lang)}) : ""}</td></tr>`).join("")
    + `</table><p class="muted small">${t("h.plan.note")}</p>`;
}


/* ---- store online per console */
async function openCatalog(pid) {
  SET.catPid = pid;
  $("#cat-title").textContent = t("h.cat.title", {p: platName(pid)});
  const d = await api(`/api/catalogs/${pid}`);
  $("#cat-urls").value = d.pages.map((p) => p.url).join("\n");
  renderCatalog(d);
  $("#catalog-dlg").showModal();
  if (d.job.status === "running") pollCatalog();
  if (d.meta && d.meta.status === "running") pollMeta();
}

function renderCatalog(d) {
  $("#cat-pages").innerHTML = d.pages.map((p) => `<div class="muted">${t("h.cat.pageLine", {u: esc(p.url), n: p.games.toLocaleString(GSI18n.lang)})}`
    + (p.time ? ` · ${t("h.cat.read", {d: new Date(p.time * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" })})}` : " · " + t("h.cat.never")) + `</div>`).join("");
  $("#cat-log").textContent = (d.job.log || []).slice(-10).join("\n");
  renderMeta(d.meta, d.meta_coverage);
}

/* copertine e descrizioni delle voci online (GameTDB offline + pagine dei siti) */
function metaBars(m, cov) {
  const s = (m && m.summary) || {};
  const total = s.games || cov.total || 0;
  if (!total) return "";
  const row = (label, done) => {
    const pct = Math.min(100, Math.round((100 * (done || 0)) / total));
    return `<div class="bar"><span>${label}</span><div class="track"><div class="fill" style="width:${pct}%"></div></div>`
      + `<span class="n">${(done || 0).toLocaleString(GSI18n.lang)} / ${total.toLocaleString(GSI18n.lang)}</span></div>`;
  };
  return `<div class="bars">${row("🖼 " + t("h.cat.covers"), s.covers ?? cov.covers)}${row("📝 " + t("h.cat.descs"), s.descriptions ?? cov.descriptions)}</div>`;
}

function renderMeta(m, cov) {
  const box = $("#cat-meta-info");
  const btn = $("#cat-meta-btn");
  SET.metaRunning = !!(m && m.status === "running");
  cov = cov || {};
  if (!m || m.status === "idle") {
    btn.textContent = "🖼 " + t("h.cat.metaBtn");
    box.innerHTML = cov.total ? `<span class="muted small">${t("h.cat.lastRun")}</span>${metaBars(null, cov)}` : "";
    return;
  }
  const s = m.summary || {};
  if (m.status === "running") {
    btn.textContent = "⏹ " + t("h.common.stop");
    box.innerHTML = `<div class="phase">${esc(m.phase || t("h.cat.inProgress"))} · ${t("h.cat.pagesRead", {n: (s.pages || 0).toLocaleString(GSI18n.lang)})}</div>`
      + metaBars(m, cov);
  } else if (m.status === "done") {
    btn.textContent = "🖼 " + t("h.cat.metaBtn");
    box.innerHTML = `<div class="phase">${esc(m.phase)}</div>` + metaBars(m, cov);
  } else {
    btn.textContent = "🖼 " + t("h.cat.metaBtn");
    box.innerHTML = `<div class="phase">${esc(m.phase || m.status)}</div>` + metaBars(m, cov);
  }
}

let metaTimer = 0;
async function pollMeta() {
  clearTimeout(metaTimer);
  const d = await api(`/api/catalogs/${SET.catPid}`).catch(() => null);
  if (!d) return;
  renderCatalog(d);
  if (d.meta && d.meta.status === "running") { metaTimer = setTimeout(pollMeta, 2000); return; }
  if (d.meta && d.meta.status === "done") { await reload(true); toast(t("h.cat.metaUpdated")); }
  else if (d.meta && d.meta.status === "error") toast(t("h.cat.pagesErr"), true);
}

let catTimer = 0;
async function pollCatalog() {
  clearTimeout(catTimer);
  const d = await api(`/api/catalogs/${SET.catPid}`).catch(() => null);
  if (!d) return;
  renderCatalog(d);
  if (d.job.status === "running") { catTimer = setTimeout(pollCatalog, 1200); return; }
  if (d.job.status === "done") { await reload(true); toast(t("h.cat.updated")); }
  else if (d.job.status === "error") toast(t("h.cat.readErr"), true);
}

/* ---- console personalizzate */
async function renderCustomConsoles() {
  const list = (await api("/api/platforms")).filter((p) => p.custom);
  $("#custom-consoles").innerHTML = list.length ? `<h3>${t("h.cons.title")}</h3>` + list.map((p) => `<div class="cust-row">
      <b>${esc(p.name)}</b><span class="muted grow">${esc(p.id)} · ${esc(p.exts)}${p.aliases.length ? " · cartelle: " + esc(p.aliases.join(", ")) : ""}</span>
      <button class="btn" data-cdel="${esc(p.id)}">${t("h.common.remove")}</button></div>`).join("") : "";
}

/* ---- altri store PC: repack / download diretto */
let PCST = { rows: [], filter: "all", timer: 0 };

async function loadPcStores() {
  let d;
  try { d = await api("/api/pc-stores"); } catch (e) { return toast(e.message, true); }
  PCST.rows = d.stores || [];
  renderPcStores(d.job);
  if (d.job && d.job.status === "running") pollPcStores();
}

function renderPcStores(j) {
  const rows = PCST.rows.filter((r) => PCST.filter === "all" || r.kind === PCST.filter);
  $("#pcst-table").innerHTML = rows.length ? rows.map((r) => `<tr>
      <td class="small">${esc(r.url)}${r.type && r.type !== "filelist" ? ` <span class="src-kind offline">${esc(r.type)}</span>` : ""}</td>
      <td><select class="field" data-pcst-kind="${esc(r.url)}">
        <option value="repack"${r.kind === "repack" ? " selected" : ""}>📦 Repack</option>
        <option value="direct"${r.kind === "direct" ? " selected" : ""}>⬇ ${t("h.pcst.direct")}</option></select></td>
      <td class="num">${r.games ? r.games.toLocaleString(GSI18n.lang) : "—"}</td>
      <td><button class="btn" data-pcst-del="${esc(r.url)}">${t("h.common.remove")}</button></td></tr>`).join("")
    : `<tr><td colspan="4" class="muted small">${t("h.pcst.none")}${PCST.filter !== "all" ? " " + t("h.pcst.inCat") : ""}.</td></tr>`;
  const jj = j || {};
  $("#pcst-info").textContent = jj.status === "running" ? (jj.phase || t("h.pcst.reading")) : "";
  $("#pcst-log").textContent = (jj.log || []).slice(-8).join("\n");
  $("#pcst-refresh").disabled = jj.status === "running";
}

async function savePcStores(stores, refresh) {
  const body = { stores: stores.map((r) => ({ url: r.url, kind: r.kind })), refresh: !!refresh };
  let d;
  try { d = await api("/api/pc-stores", { body }); } catch (e) { return toast(e.message, true); }
  PCST.rows = d.stores || [];
  renderPcStores(d.job);
  if (refresh) pollPcStores();
}

async function pollPcStores() {
  clearTimeout(PCST.timer);
  const d = await api("/api/pc-stores").catch(() => null);
  if (!d) return;
  PCST.rows = d.stores || [];
  renderPcStores(d.job);   // la tabella si ridisegna; l'avanzamento lo segue il blocco «Aggiornamento degli store»
  if (d.job && d.job.status === "running") PCST.timer = setTimeout(pollPcStores, 3000);
}

/* ---- impostazioni › aggiornamento degli store (PC + console), in parallelo */
const SRF_ICON = { idle: "·", pending: "·", running: "⏳", done: "✓", error: "✕", skip: "⏭" };
const srfOpen = new Set(); // store con il log aperto (sopravvive ai aggiornamenti periodici)
let srfTimer = 0;
let srfLast = null;        // ultima risposta di /api/store-refresh (per ridisegnare senza rileggere)

function srfDur(sec) {
  if (!sec || sec < 1) return "—";
  if (sec < 90) return `${Math.round(sec)} s`;
  if (sec < 5400) return `${Math.round(sec / 60)} min`;
  return `${Math.floor(sec / 3600)} h ${String(Math.round((sec % 3600) / 60)).padStart(2, "0")}`;
}

/** Riga di dettaglio di uno store: pagina, ritmo e tempo che manca. */
function srfMeta(t) {
  if (t.status === "error") return esc(t.error || window.t("h.srf.error"));
  if (t.status === "idle") return t.kind === "repack" ? "📦 Repack" : t.kind === "direct" ? "⬇ " + window.t("h.srf.direct") : "";
  if (t.status === "pending") return t.position ? window.t("h.srf.queuePos", {n: t.position}) : window.t("h.srf.queued");
  const gameCount = t.status === "running" ? (t.seen || 0) : (t.games || 0);
  const bits = [];
  if (t.pages > 1) bits.push(window.t("h.srf.page", {p: t.page || 0, n: t.pages}));
  if (gameCount) bits.push(window.t("h.srf.games", {n: gameCount.toLocaleString(GSI18n.lang)}));
  if (t.rate) bits.push(window.t("h.srf.perPage", {s: t.rate.toLocaleString(GSI18n.lang, { maximumFractionDigits: 2 })}));
  if (t.status === "running") {
    if (t.eta) bits.push(window.t("h.srf.eta", {d: srfDur(t.eta)}));
    bits.push(window.t("h.srf.since", {d: srfDur(t.elapsed)}));
  } else if (t.status === "done") bits.push(srfDur(t.elapsed));
  return esc(bits.join(" · "));
}

function renderStoreRefreshJob(js, list) {
  const running = js.status === "running";
  // «Aggiorna tutti» resta sempre disponibile: aggiunge alla coda gli store non ancora in coda/in corso
  $("#srf-run").hidden = false;
  const stop = $("#srf-stop");
  // sparisce appena non c'è più nulla da interrompere (fine lettura, ricostruzione della libreria)
  stop.hidden = !js.stoppable;
  stop.disabled = !!js.stopping;
  stop.textContent = js.stopping ? "■ " + t("h.srf.stopping") : "■ " + t("h.srf.stop");
  $("#srf-log").textContent = (js.log || []).slice(-12).join("\n");
  // a riposo si mostrano comunque tutti gli store configurati; durante un aggiornamento lo stato
  // del singolo store si sovrappone alla lista, così le altre righe restano visibili
  const live = new Map((js.targets || []).map((t) => [t.id || t.url, t]));
  const base = (list && list.length) ? list : (js.targets || []);
  const targets = base.map((t) => live.get(t.id || t.url) || { ...t, status: "idle", log: [] });
  for (const t of (js.targets || [])) {
    if (!targets.some((x) => (x.id || x.url) === (t.id || t.url))) targets.push(t);
  }
  if (js.status === "idle" && !targets.length) { $("#srf-progress").innerHTML = ""; return; }
  const done = js.done || 0, total = js.total || 0;
  const pct = total ? Math.round((100 * done) / total) : 0;
  const rows = targets.map((t) => {
    const id = t.id || t.url;
    const open = srfOpen.has(id);
    const log = (t.log || []).slice(-12).join("\n");
    const lastLog = t.status === "running" && (t.log || []).length ? t.log[t.log.length - 1] : "";
    const busy = t.status === "pending" || t.status === "running";
    return `<div class="srf-row">
      <span class="srf-ico">${SRF_ICON[t.status] || "·"}</span>
      <span class="grow">${esc(t.label)}</span>
      <span class="muted small srf-meta">${srfMeta(t)}</span>
      <button class="icon-btn" data-srf-run="${esc(id)}" title="${window.t("h.srf.addQueue")}"${busy ? " disabled" : ""}>⟳</button>
      <button class="icon-btn" data-srf-log="${esc(id)}" title="${window.t("h.srf.logOne")}">📄</button></div>
      ${lastLog ? `<div class="srf-last muted small">${esc(lastLog.slice(0, 150))}</div>` : ""}
      ${open && log ? `<pre class="log srf-rowlog">${esc(log)}</pre>` : ""}`;
  }).join("");
  // il riquadro si ridisegna ogni 1,5 s: si conserva la posizione di scorrimento
  const scrolled = $("#srf-progress .srf-list")?.scrollTop || 0;
  const bar = js.status === "idle" ? "" : `<div class="bar"><span>${esc(js.phase || "")}</span>
      <div class="track"><div class="fill" style="width:${pct}%"></div></div>
      <span class="n">${done} / ${total} · ${t("h.srf.games", {n: (js.games || 0).toLocaleString(GSI18n.lang)})}`
    + `${js.queued ? ` · ${t("h.srf.queuedN", {n: js.queued})}` : ""}${js.running ? ` · ${t("h.srf.runningN", {n: js.running})}` : ""}</span></div>`;
  $("#srf-progress").innerHTML = `${bar}<div class="srf-list">${rows}</div>`;
  const list2 = $("#srf-progress .srf-list");
  if (list2 && scrolled) list2.scrollTop = scrolled;
}

function renderStoreRefresh(d) {
  srfLast = d;
  const sch = d.schedule || {};
  $("#srf-mode").value = sch.mode || "startup";
  $("#srf-time").value = sch.time || "03:00";
  $("#srf-time").disabled = sch.mode !== "daily";
  $("#srf-workers").value = sch.workers || 4;
  const last = d.last ? String(d.last).replace("T", " ") : "";
  $("#srf-info").textContent = `${t("h.srf.lists", {n: (d.stores || 0).toLocaleString(GSI18n.lang)})}`
    + (last ? ` · ${t("h.srf.lastRun", {d: last})}` : "")
    + (d.job?.log_file ? ` · ${t("h.srf.logFile", {f: d.job.log_file})}` : "");
  renderStoreRefreshJob(d.job || { status: "idle" }, d.list);
}

async function loadStoreRefresh() {
  let d;
  try { d = await api("/api/store-refresh"); } catch (e) { return toast(e.message, true); }
  renderStoreRefresh(d);
  if (d.job && d.job.status === "running") pollStoreRefresh();
}

async function pollStoreRefresh() {
  clearTimeout(srfTimer);
  const d = await api("/api/store-refresh").catch(() => null);
  if (!d) return;
  renderStoreRefresh(d);
  if (d.job && d.job.status === "running") { srfTimer = setTimeout(pollStoreRefresh, 1500); return; }
  if (d.job && d.job.status === "done") {
    await reload(true);
    if ((d.job.phase || "").startsWith("Interrotto")) toast(d.job.phase);
    else toast(t("h.srf.updated", {n: (d.job.games || 0).toLocaleString(GSI18n.lang)}));
  }
  else if (d.job && d.job.status === "error") toast(t("h.srf.failed"), true);
}

/* ---- impostazioni › account degli store */
async function loadAccounts() {
  loadSteamcmd();
  loadStoreRefresh(); // blocco «Aggiornamento degli store»: indipendente dagli account
  api("/api/ra").then((r) => { $("#ra-user").value = r.username; $("#ra-key").placeholder = r.has_key ? t("h.acc.raSaved") : ""; }).catch(() => {});
  let d;
  try { d = await api("/api/accounts"); } catch (e) { return toast(e.message, true); }
  SET.accounts = d;
  const when = d.refreshed ? new Date(d.refreshed * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" }) : t("h.acc.never");
  $("#acc-info").textContent = t("h.acc.lastUpdate", {d: when});
  $("#acc-table").innerHTML = d.stores.filter((x) => x.id !== "manual").map((x) => {
    const a = x.account || {};
    let ctrl = "";
    if (x.id === "ports") {
      ctrl = `<span class="muted small">${t("h.acc.portsInst")}</span> <button class="btn" data-ports-open>${t("h.acc.manage")}</button>`;
    } else if (x.id === "steam") {
      const accs = (a.accounts || []).map((u) => `<option value="${esc(u.steamid)}" ${u.steamid === a.steamid ? "selected" : ""}>${esc(u.persona || u.steamid)}</option>`).join("");
      ctrl = `<div class="acc-steam">
        <select class="field" id="steam-id" title="${t("h.acc.steamAcc")}">${accs || `<option value="">${t("h.acc.noAccount")}</option>`}</select>
        <input class="field grow" id="steam-key" placeholder="${a.has_key ? t("h.acc.apiSaved") : t("h.acc.apiHelp")}">
        <button class="btn" data-acc-save="steam">${t("h.common.save")}</button>
        <a href="#" data-open="https://steamcommunity.com/dev/apikey">${t("h.acc.getKey")}</a></div>`;
    } else if (x.login === "oauth") {
      ctrl = a.connected
        ? `<span class="status-ok">✓ ${t("h.acc.connected")}${a.user ? " " + t("h.acc.as") + " " + esc(a.user) : ""}</span> <button class="btn" data-acc-logout="${x.id}">${t("h.acc.disconnect")}</button>`
        : `<button class="btn primary" data-acc-login="${x.id}">${t("h.acc.connect")}</button>
           <div class="acc-manual" data-for="${x.id}" hidden>
             <ol class="small">${x.id === "epic"
               ? `<li>${t("h.acc.epic1")}</li>
                  <li>${t("h.acc.epic2")}</li>
                  <li>${t("h.acc.epic3")}</li>`
               : `<li>${t("h.acc.gog1")}</li>
                  <li>${t("h.acc.gog2")}
                      </li>`}</ol>
             <span class="row tight"><input class="field grow" placeholder="${t("h.acc.pasteHere")}">
             <button class="btn primary" data-acc-code="${x.id}">${t("h.acc.confirm")}</button>
             <a href="#" data-acc-login="${x.id}" data-browser="1">${t("h.acc.reopen")}</a></span></div>`;
    } else if (a.note) ctrl = `<span class="muted small">${esc(a.note)}</span>`;
    const st = x.detected ? `<span class="status-ok">✓ ${t("h.acc.detected")}</span>` : `<span class="muted">${t("h.acc.notFound")}</span>`;
    return `<tr><td><label class="chk"><input type="checkbox" data-acc-enable="${x.id}" ${x.enabled ? "checked" : ""}> <b>${esc(x.name)}</b></label>
      ${x.note ? `<div class="muted small">${esc(x.note)}</div>` : ""}</td><td>${st}</td>
      <td class="num">${x.installed} / ${x.games}</td><td>${ctrl}${x.id === "ports" ? "" : ` <button class="icon-btn" data-acc-refresh="${x.id}" title="${t("h.acc.refreshOne")}">⟳</button>`}</td></tr>`;
  }).join("");
  renderJobInto($("#acc-progress"), d.job);
  if (d.job.status === "running") pollStores();
}

async function accountAction(t) {
  const id = t.dataset.accLogin || t.dataset.accLogout || t.dataset.accCode || t.dataset.accSave;
  try {
    if (t.dataset.accSave === "steam") {
      const body = { steamid: $("#steam-id").value };
      if ($("#steam-key").value.trim()) body.api_key = $("#steam-key").value.trim();
      await api("/api/accounts/steam", { body });
      toast(window.t("h.acc.steamSaved"));
      await api("/api/stores/refresh", { body: { only: ["steam"] } });
      pollStores(true);
    } else if (t.dataset.accLogin) {
      const x = SET.accounts.stores.find((s) => s.id === id);
      // Prima la finestra integrata: cattura da sola il codice (nessun copia-incolla).
      const pw = window.pywebview && window.pywebview.api;
      if (pw && pw.login && !t.dataset.browser) {
        const r = await pw.login(id);
        if (r && r.ok) { toast(window.t("h.acc.linked")); pollStores(true); return loadAccounts(); }
      }
      // Fallback (app nel browser, accesso annullato, o "Accedi con Google/Apple" che la finestra integrata
      // non regge): login nel browser predefinito, poi si incolla qui il risultato.
      await api("/api/open", { body: { url: x.login_url } });
      const box = document.querySelector(`.acc-manual[data-for="${id}"]`);
      box.hidden = false;
      box.querySelector("input").focus();
      return; // niente ricaricamento: nasconderebbe il riquadro appena aperto
    } else if (t.dataset.accCode) {
      const v = document.querySelector(`.acc-manual[data-for="${id}"] input`).value.trim();
      if (!v) return toast(window.t("h.acc.pasteFirst"), true);
      await api(`/api/accounts/${id}/code`, { body: { code: v } });
      toast(window.t("h.acc.linked"));
      pollStores(true);
    } else if (t.dataset.accLogout) {
      await api(`/api/accounts/${id}/logout`, { body: {} });
    }
  } catch (e) { return toast(e.message, true); }
  loadAccounts();
}

/* ---- impostazioni › aspetto: temi e plugin */
function experiencePreviewMarkup(experience) {
  const views = {
    original: [t("h.app.navCollection"), "Console", t("h.app.navCollections")],
    catalog: [t("h.app.navCatalog"), t("h.app.navAllGames"), t("h.app.navFavorites")],
    shelves: [t("h.app.navHome"), t("h.app.navLibrary"), t("h.app.navFavorites")],
    console: [],
    dashboard: [t("h.app.navHome"), t("h.app.navLibrary"), t("h.app.navFavorites")],
    cinema: [t("h.app.navHome"), t("h.app.navLibrary"), t("h.app.navStore")],
    storefront: [t("h.app.navHome"), t("h.app.navFeatured"), t("h.app.navCategories")],
  };
  const labels = views[experience.id] || [t("h.app.navHome"), t("h.app.navLibrary")];
  const navigation = `<div class="experience-preview__navigation">${labels.map((label) => `<span>${label}</span>`).join("")}</div>`;
  const heroText = {
    original: [t("h.app.heroOriginal"), t("h.app.heroClassic")],
    catalog: [t("h.app.navAllGames"), t("h.app.heroCatalog")],
    shelves: [t("h.app.heroCollection"), t("h.app.heroContinue")],
    console: [t("h.app.heroSelected"), t("h.app.heroFocus")],
    dashboard: [t("h.app.heroForeground"), t("h.app.heroGroups")],
    cinema: [t("h.app.heroFeatured"), t("h.app.heroContinue")],
    storefront: [t("h.app.heroDiscover"), t("h.app.heroDetails")],
  }[experience.id] || [experience.name, experience.description || ""];
  const count = experience.id === "dashboard" ? 4 : 3;
  return `<div class="experience-preview experience-preview--${esc(experience.id)}" data-experience-preview="${esc(experience.id)}" aria-hidden="true">
    ${navigation}<div class="experience-preview__hero"><b>${esc(heroText[0])}</b><span>${esc(heroText[1])}</span></div>
    <div class="experience-preview__row">${Array.from({ length: count }, () => '<span class="experience-preview__tile"></span>').join("")}</div></div>`;
}

async function loadAppearance() {
  await GS.experiencesReady;
  let ext = GS.extensions;
  GS.extensions = null; // usata una sola volta: poi i dati tornano freschi dal server
  if (!ext) try { ext = await api("/api/extensions"); } catch (e) { return toast(e.message, true); }
  SET.theme = ext.active_theme;
  $("#experience-list").innerHTML = (ext.experiences || []).map((x) => {
    const experience = GS.experiences.get(x.id) || x;
    const error = GS.experienceErrors?.[x.id] || x.error;
    const available = x.available && !GS.experienceErrors?.[x.id];
    return `<label class="experience-choice">
      <span><input type="radio" name="experience" value="${esc(x.id)}" ${x.id === GS.experience.id ? "checked" : ""}
        ${available ? "" : "disabled"} aria-describedby="experience-description-${esc(x.id)}"><b>${esc(experience.name || x.name)}</b></span>
      <span class="muted small" id="experience-description-${esc(x.id)}">${esc(experience.description || x.description || "")}</span>
      ${experiencePreviewMarkup(experience)}
      ${error ? `<span class="status-bad">${esc(error)}</span>` : ""}</label>`;
  }).join("");
  $("#theme-list").innerHTML = ext.themes.map((t) => `<label class="theme-card ${t.id === ext.active_theme ? "on" : ""}">
      <input type="radio" name="theme" value="${esc(t.id)}" ${t.id === ext.active_theme ? "checked" : ""}>
      <span class="sw" style="background:${esc(t.preview || "#1c2030")}"></span>
      <b>${esc(t.name)}</b><span class="muted small">${esc(t.description || "")}${t.author ? " · " + esc(t.author) : ""}</span></label>`).join("");
  const plugins = [...(ext.plugins || [])].sort((a, b) => ((window.favExt?.(b.id) || 0) - (window.favExt?.(a.id) || 0)) || (a.name || a.id).localeCompare(b.name || b.id));
  $("#plugin-list").innerHTML = plugins.length ? plugins.map((p) => {
    const isFav = Boolean(window.favExt?.(p.id));
    return `<div class="plugin-row" style="display:flex;align-items:flex-start;gap:8px">
      <button type="button" class="fav-star ${isFav ? "is-fav" : ""}" data-toggle-fav-ext="${esc(p.id)}" title="${isFav ? t("h.fav.remove") : t("h.fav.add")}" aria-label="${isFav ? t("h.fav.remove") : t("h.fav.add")}" style="margin-top:2px">${isFav ? "★" : "☆"}</button>
      <div style="flex:1;min-width:0">

      <label class="chk"><input type="checkbox" data-plugin="${esc(p.id)}" ${p.enabled ? "checked" : ""} ${p.locked ? "disabled" : ""}> <b>${esc(p.name)}</b></label>
      <span class="muted small">v${esc(p.version || "?")}${p.author ? " · " + esc(p.author) : ""} — ${esc(p.description || "")}
      ${p.load_ms != null ? `<span class="plugin-timing">· ${t("h.app.loadMs", {ms: p.load_ms})}${p.load === "lazy" ? ` (${t("h.app.deferred")}${p.first_use_ms != null ? `, ${t("h.app.firstUse", {ms: p.first_use_ms})}` : ""})` : ""}</span>` : ""}
      ${p.error ? `<span class="status-bad">${esc(p.error)}</span>` : ""}</span></div></div>`;
  }).join("")
    : `<p class="muted">${t("h.app.noPlugins")}</p>`;
  $("#ext-credit").textContent = S.iconsCredit;
  $("#ext-paths").innerHTML = `${t("h.app.themes")}: <code>${esc(ext.paths.themes)}</code><br>Plugin: <code>${esc(ext.paths.plugins)}</code>`;
}

async function enterBigPicture() {
  const pw = window.pywebview && window.pywebview.api;
  try { if (pw && pw.set_fullscreen) await pw.set_fullscreen(true); } catch { /* browser */ }
  location.href = "/bigpicture";
}

// esporta in Steam
async function loadSteamExport() {
  let r;
  try { r = await api("/api/steam-export"); } catch { r = { users: [] }; }
  $("#sx-user").innerHTML = r.users.map((u) => `<option value="${esc(u.id)}">${esc(u.name || u.id)}</option>`).join("");
  $("#sx-plats").innerHTML = (r.platforms || []).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  $("#sx-info").textContent = r.users.length ? "" : t("g.steamx.none");
  for (const b of ["#sx-go", "#sx-rm"]) $(b).disabled = !r.users.length;
}

/* ---- Steam senza client (SteamCMD): accesso interattivo, la password non viene salvata da Pozzo */
function steamcmdLogin() {
  return new Promise((resolve) => {
    let dlg = document.getElementById("scmd-dlg");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "scmd-dlg";
      dlg.className = "small-dlg";
      dlg.setAttribute("aria-labelledby", "scmd-title");
      document.body.appendChild(dlg);
    }
    dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2 id="scmd-title">${t("h.steamcmd.title")}</h2><button class="icon-btn" value="" aria-label="${t("f.btn.close")}">✕</button></form>
      <form class="dlg-body" id="scmd-form" autocomplete="off">
        <p class="muted small">${t("h.steamcmd.hint")}</p>
        <label>${t("h.steamcmd.user")}<input class="field" id="scmd-user" required autocomplete="off"></label>
        <label>${t("h.steamcmd.password")}<input class="field" id="scmd-pass" type="password" required autocomplete="off"></label>
        <label>${t("h.steamcmd.guard")}<input class="field" id="scmd-guard" autocomplete="off" maxlength="12"></label>
        <p class="err" id="scmd-err" role="alert" hidden></p>
        <div class="row end"><button class="btn primary" id="scmd-go" type="submit">${t("h.steamcmd.login")}</button></div>
      </form>`;
    let ok = false;
    dlg.onclose = () => resolve(ok);
    dlg.querySelector("#scmd-form").onsubmit = async (e) => {
      e.preventDefault();
      const go = dlg.querySelector("#scmd-go"), err = dlg.querySelector("#scmd-err");
      go.disabled = true; err.hidden = true;
      try {
        await api("/api/steamcmd/login", { body: { user: $("#scmd-user").value.trim(), password: $("#scmd-pass").value, guard: $("#scmd-guard").value.trim() } });
        ok = true; $("#scmd-pass").value = ""; dlg.close();
      } catch (x) { err.textContent = x.message; err.hidden = false; go.disabled = false; $("#scmd-pass").value = ""; }
    };
    dlg.showModal();
    dlg.querySelector("#scmd-user").focus();
  });
}

async function steamcmdDownload(gameId) {
  try {
    let st = await api("/api/steamcmd");
    if (!st.logged_in && !(await steamcmdLogin())) return;
    if (!confirm(t("h.steamcmd.drm"))) return;
    await api("/api/steamcmd/install", { body: { game_id: gameId } });
    toast(t("h.steamcmd.started"));
  } catch (e) { toast(e.message, true); }
}

async function loadSteamcmd() {
  const box = $("#scmd-status");
  if (!box) return;
  try {
    const st = await api("/api/steamcmd");
    box.textContent = st.logged_in ? t("h.steamcmd.loggedAs", {user: st.user}) : t("h.steamcmd.notLogged");
    $("#scmd-logout").hidden = !st.logged_in;
  } catch { box.textContent = ""; }
}

if (typeof document !== "undefined") document.addEventListener("click", async (e) => {
  const b = e.target.closest && e.target.closest("#scmd-login, #scmd-logout, #d-scmd");
  if (!b) return;
  if (b.id === "d-scmd") return steamcmdDownload(S.detail.id);
  if (b.id === "scmd-login") await steamcmdLogin();
  else try { await api("/api/steamcmd/logout", { body: {} }); } catch (x) { toast(x.message, true); }
  loadSteamcmd();
});
