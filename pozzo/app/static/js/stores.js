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
      toast("Store aggiornati: libreria aggiornata");
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
      + `<span class="n">${Math.round(t.done).toLocaleString("it")} / ${Math.round(t.total).toLocaleString("it")}</span></div>`;
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
      <div class="muted small">${b.ready ? `${b.games.toLocaleString("it")} giochi · ${b.size_mb} MB · aggiornato ${new Date(b.updated * 1000).toLocaleDateString("it")}`
        : "non ancora scaricato (avverrà al primo scraping)"} · ogni ${b.refresh_days} giorni</div></div>
      <button class="btn" data-bulk="${esc(b.id)}">↻ Aggiorna ora</button></div>`).join("");
  const sch = d.schedule || {};
  $("#sch-on").checked = !!sch.enabled;
  $("#sch-time").value = sch.time || "03:00";
  $("#sch-mode").value = sch.mode || "missing";
  SET.sourcesSaved = collectSources(false);
  $("#sch-last").textContent = d.schedule_last ? `ultimo: ${d.schedule_last}` : "";
  $("#rawg-key").placeholder = d.sources.find((x) => x.id === "rawg")?.has_key ? "chiave salvata (••••) — incolla per cambiarla" : "incolla la chiave";
  if (d.bulk_job.status === "running") pollBulk();
}

function renderSources(rows) {
  SET.srcRows = rows;
  $("#src-table").innerHTML = rows.map((x, i) => {
    const on = x.kind === "online";
    const num = (k, v) => on ? `<input class="field" data-lim="${k}" value="${v || ""}" placeholder="${k === "rate" ? "" : "nessuno"}">` : `<span class="muted">—</span>`;
    return `<tr data-src="${esc(x.id)}" class="${x.enabled ? "" : "src-off"}">
      <td><span class="src-move"><button class="icon-btn" data-mv="-1" title="Su">▲</button><button class="icon-btn" data-mv="1" title="Giù">▼</button></span></td>
      <td><label class="chk"><input type="checkbox" data-en ${x.enabled ? "checked" : ""}> <b>${esc(x.id)}</b></label>
        <span class="src-kind ${x.kind}">${x.kind}</span>${x.needs_key && !x.has_key ? ` <span class="status-bad">manca la chiave</span>` : ""}
        <div class="muted small">${esc(x.description)}</div></td>
      <td class="num">${on ? `${(x.usage.today || 0).toLocaleString("it")} / ${(x.usage.month || 0).toLocaleString("it")}` : "—"}</td>
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
  else if (settingsActive("fonti")) { loadSources(); if (d.bulk_job.status === "done") toast("Database aggiornato"); }
}

async function showPlan() {
  const box = $("#scan-plan-box");
  box.innerHTML = `<p class="muted">Calcolo della stima…</p>`;
  const sel = [...new Set([...document.querySelectorAll(".scan-sel:checked")].map((c) => c.dataset.p))];
  let d;
  try { d = await api("/api/scan/plan", { body: { platforms: sel, mode: $("#scan-mode").value } }); }
  catch (e) { box.innerHTML = ""; return toast(e.message, true); }
  const dur = (s) => (s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
  box.innerHTML = `<table class="emu plan"><tr><th>Fonte</th><th class="num">Giochi</th><th class="num">Richieste</th><th class="num">Tempo</th><th>Note</th></tr>`
    + d.plan.map((p) => `<tr><td>${esc(p.source)} ${p.offline ? `<span class="src-kind offline">offline</span>` : ""}</td>
      <td class="num">${p.games.toLocaleString("it")}</td><td class="num">${p.offline ? "0" : p.requests.toLocaleString("it")}</td>
      <td class="num">${p.offline ? "pochi secondi" : p.requests ? dur(p.seconds) : "—"}</td>
      <td class="muted small">${p.days > 1 ? `circa ${p.days} giorni (${esc(p.note || "limite giornaliero")})` : ""}
        ${p.month_left != null ? `restano ${p.month_left.toLocaleString("it")} richieste questo mese` : ""}</td></tr>`).join("")
    + `</table><p class="muted small">Valori massimi: in cascata le prime fonti riempiono i dati e le successive interrogano meno giochi.</p>`;
}


/* ---- store online per console */
async function openCatalog(pid) {
  SET.catPid = pid;
  $("#cat-title").textContent = `Store online · ${platName(pid)}`;
  const d = await api(`/api/catalogs/${pid}`);
  $("#cat-urls").value = d.pages.map((p) => p.url).join("\n");
  renderCatalog(d);
  $("#catalog-dlg").showModal();
  if (d.job.status === "running") pollCatalog();
  if (d.meta && d.meta.status === "running") pollMeta();
}

function renderCatalog(d) {
  $("#cat-pages").innerHTML = d.pages.map((p) => `<div class="muted">${esc(p.url)} — ${p.games.toLocaleString("it")} giochi`
    + (p.time ? ` · letta ${new Date(p.time * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })}` : " · mai letta") + `</div>`).join("");
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
      + `<span class="n">${(done || 0).toLocaleString("it")} / ${total.toLocaleString("it")}</span></div>`;
  };
  return `<div class="bars">${row("🖼 Copertine", s.covers ?? cov.covers)}${row("📝 Descrizioni", s.descriptions ?? cov.descriptions)}</div>`;
}

function renderMeta(m, cov) {
  const box = $("#cat-meta-info");
  const btn = $("#cat-meta-btn");
  SET.metaRunning = !!(m && m.status === "running");
  cov = cov || {};
  if (!m || m.status === "idle") {
    btn.textContent = "🖼 Copertine e descrizioni";
    box.innerHTML = cov.total ? `<span class="muted small">Ultimo giro:</span>${metaBars(null, cov)}` : "";
    return;
  }
  const s = m.summary || {};
  if (m.status === "running") {
    btn.textContent = "⏹ Ferma";
    box.innerHTML = `<div class="phase">${esc(m.phase || "In corso")} · ${(s.pages || 0).toLocaleString("it")} pagine lette</div>`
      + metaBars(m, cov);
  } else if (m.status === "done") {
    btn.textContent = "🖼 Copertine e descrizioni";
    box.innerHTML = `<div class="phase">${esc(m.phase)}</div>` + metaBars(m, cov);
  } else {
    btn.textContent = "🖼 Copertine e descrizioni";
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
  if (d.meta && d.meta.status === "done") { await reload(true); toast("Copertine e descrizioni aggiornate"); }
  else if (d.meta && d.meta.status === "error") toast("Lettura delle pagine non riuscita: vedi il registro", true);
}

let catTimer = 0;
async function pollCatalog() {
  clearTimeout(catTimer);
  const d = await api(`/api/catalogs/${SET.catPid}`).catch(() => null);
  if (!d) return;
  renderCatalog(d);
  if (d.job.status === "running") { catTimer = setTimeout(pollCatalog, 1200); return; }
  if (d.job.status === "done") { await reload(true); toast("Store online aggiornato"); }
  else if (d.job.status === "error") toast("Lettura non riuscita: vedi il registro", true);
}

/* ---- console personalizzate */
async function renderCustomConsoles() {
  const list = (await api("/api/platforms")).filter((p) => p.custom);
  $("#custom-consoles").innerHTML = list.length ? `<h3>Console aggiunte da te</h3>` + list.map((p) => `<div class="cust-row">
      <b>${esc(p.name)}</b><span class="muted grow">${esc(p.id)} · ${esc(p.exts)}${p.aliases.length ? " · cartelle: " + esc(p.aliases.join(", ")) : ""}</span>
      <button class="btn" data-cdel="${esc(p.id)}">Rimuovi</button></div>`).join("") : "";
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
        <option value="direct"${r.kind === "direct" ? " selected" : ""}>⬇ Download diretto</option></select></td>
      <td class="num">${r.games ? r.games.toLocaleString("it") : "—"}</td>
      <td><button class="btn" data-pcst-del="${esc(r.url)}">Rimuovi</button></td></tr>`).join("")
    : `<tr><td colspan="4" class="muted small">Nessuno store aggiunto${PCST.filter !== "all" ? " in questa categoria" : ""}.</td></tr>`;
  const jj = j || {};
  $("#pcst-info").textContent = jj.status === "running" ? (jj.phase || "Lettura degli elenchi…") : "";
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
  if (t.status === "error") return esc(t.error || "errore");
  if (t.status === "idle") return t.kind === "repack" ? "📦 Repack" : t.kind === "direct" ? "⬇ Diretto" : "";
  if (t.status === "pending") return t.position ? `in coda · posizione ${t.position}` : "in coda";
  const gameCount = t.status === "running" ? (t.seen || 0) : (t.games || 0);
  const bits = [];
  if (t.pages > 1) bits.push(`pagina ${t.page || 0}/${t.pages}`);
  if (gameCount) bits.push(`${gameCount.toLocaleString("it")} giochi`);
  if (t.rate) bits.push(`${t.rate.toLocaleString("it", { maximumFractionDigits: 2 })} s/pagina`);
  if (t.status === "running") {
    if (t.eta) bits.push(`≈ ${srfDur(t.eta)} alla fine`);
    bits.push(`da ${srfDur(t.elapsed)}`);
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
  stop.textContent = js.stopping ? "■ Interruzione…" : "■ Interrompi";
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
      <button class="icon-btn" data-srf-run="${esc(id)}" title="Aggiungi alla coda: aggiorna solo questo store"${busy ? " disabled" : ""}>⟳</button>
      <button class="icon-btn" data-srf-log="${esc(id)}" title="Log di questo store">📄</button></div>
      ${lastLog ? `<div class="srf-last muted small">${esc(lastLog.slice(0, 150))}</div>` : ""}
      ${open && log ? `<pre class="log srf-rowlog">${esc(log)}</pre>` : ""}`;
  }).join("");
  // il riquadro si ridisegna ogni 1,5 s: si conserva la posizione di scorrimento
  const scrolled = $("#srf-progress .srf-list")?.scrollTop || 0;
  const bar = js.status === "idle" ? "" : `<div class="bar"><span>${esc(js.phase || "")}</span>
      <div class="track"><div class="fill" style="width:${pct}%"></div></div>
      <span class="n">${done} / ${total} · ${(js.games || 0).toLocaleString("it")} giochi`
    + `${js.queued ? ` · ${js.queued} in coda` : ""}${js.running ? ` · ${js.running} in corso` : ""}</span></div>`;
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
  $("#srf-info").textContent = `${(d.stores || 0).toLocaleString("it")} elenchi configurati`
    + (last ? ` · ultimo: ${last}` : "")
    + (d.job?.log_file ? ` · log su file: ${d.job.log_file}` : "");
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
    else toast(`Store aggiornati: ${(d.job.games || 0).toLocaleString("it")} giochi`);
  }
  else if (d.job && d.job.status === "error") toast("Aggiornamento non riuscito: vedi il registro", true);
}

/* ---- impostazioni › account degli store */
async function loadAccounts() {
  loadStoreRefresh(); // blocco «Aggiornamento degli store»: indipendente dagli account
  api("/api/ra").then((r) => { $("#ra-user").value = r.username; $("#ra-key").placeholder = r.has_key ? "già salvata (lascia vuoto per non cambiarla)" : ""; }).catch(() => {});
  let d;
  try { d = await api("/api/accounts"); } catch (e) { return toast(e.message, true); }
  SET.accounts = d;
  const when = d.refreshed ? new Date(d.refreshed * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" }) : "mai";
  $("#acc-info").textContent = `Ultimo aggiornamento: ${when}`;
  $("#acc-table").innerHTML = d.stores.filter((x) => x.id !== "manual").map((x) => {
    const a = x.account || {};
    let ctrl = "";
    if (x.id === "ports") {
      ctrl = `<span class="muted small">port non ufficiali installati</span> <button class="btn" data-ports-open>Gestisci</button>`;
    } else if (x.id === "steam") {
      const accs = (a.accounts || []).map((u) => `<option value="${esc(u.steamid)}" ${u.steamid === a.steamid ? "selected" : ""}>${esc(u.persona || u.steamid)}</option>`).join("");
      ctrl = `<div class="acc-steam">
        <select class="field" id="steam-id" title="Account Steam">${accs || `<option value="">nessun account trovato</option>`}</select>
        <input class="field grow" id="steam-key" placeholder="${a.has_key ? "chiave Web API salvata (••••)" : "chiave Web API, per vedere anche i giochi non installati"}">
        <button class="btn" data-acc-save="steam">Salva</button>
        <a href="#" data-open="https://steamcommunity.com/dev/apikey">Ottieni la chiave</a></div>`;
    } else if (x.login === "oauth") {
      ctrl = a.connected
        ? `<span class="status-ok">✓ collegato${a.user ? " come " + esc(a.user) : ""}</span> <button class="btn" data-acc-logout="${x.id}">Scollega</button>`
        : `<button class="btn primary" data-acc-login="${x.id}">Collega account</button>
           <div class="acc-manual" data-for="${x.id}" hidden>
             <ol class="small">${x.id === "epic"
               ? `<li>Nel browser che si è aperto accedi a Epic (va bene anche «Accedi con Google»).</li>
                  <li>Alla fine compare una pagina con del testo che contiene <code>"authorizationCode"</code>.</li>
                  <li>Copia <b>tutto il testo della pagina</b> (Ctrl+A, Ctrl+C) e incollalo qui sotto. Il codice scade in pochi minuti.</li>`
               : `<li>Nel browser che si è aperto accedi a GOG (va bene anche «Accedi con Google»).</li>
                  <li>Alla fine arrivi su una pagina quasi vuota: copia <b>l'indirizzo dalla barra del browser</b>
                      (contiene <code>code=</code>) e incollalo qui sotto.</li>`}</ol>
             <span class="row tight"><input class="field grow" placeholder="incolla qui">
             <button class="btn primary" data-acc-code="${x.id}">Conferma</button>
             <a href="#" data-acc-login="${x.id}">riapri la pagina di accesso</a></span></div>`;
    } else if (a.note) ctrl = `<span class="muted small">${esc(a.note)}</span>`;
    const st = x.detected ? `<span class="status-ok">✓ rilevato</span>` : `<span class="muted">non trovato</span>`;
    return `<tr><td><label class="chk"><input type="checkbox" data-acc-enable="${x.id}" ${x.enabled ? "checked" : ""}> <b>${esc(x.name)}</b></label>
      ${x.note ? `<div class="muted small">${esc(x.note)}</div>` : ""}</td><td>${st}</td>
      <td class="num">${x.installed} / ${x.games}</td><td>${ctrl}${x.id === "ports" ? "" : ` <button class="icon-btn" data-acc-refresh="${x.id}" title="Aggiorna solo questo store">⟳</button>`}</td></tr>`;
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
      toast("Account Steam salvato: aggiorno gli store…");
      await api("/api/stores/refresh", { body: { only: ["steam"] } });
      pollStores(true);
    } else if (t.dataset.accLogin) {
      const x = SET.accounts.stores.find((s) => s.id === id);
      // Il login si fa nel browser predefinito: le finestre integrate vengono bloccate da Google/Apple
      // ("Accedi con Google" non funzionerebbe). Poi si incolla qui il risultato.
      await api("/api/open", { body: { url: x.login_url } });
      const box = document.querySelector(`.acc-manual[data-for="${id}"]`);
      box.hidden = false;
      box.querySelector("input").focus();
      return; // niente ricaricamento: nasconderebbe il riquadro appena aperto
    } else if (t.dataset.accCode) {
      const v = document.querySelector(`.acc-manual[data-for="${id}"] input`).value.trim();
      if (!v) return toast("Incolla prima il codice o l'indirizzo copiato dal browser", true);
      await api(`/api/accounts/${id}/code`, { body: { code: v } });
      toast("Account collegato: aggiorno la libreria…");
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
    original: ["Raccolta", "Console", "Collezioni"],
    catalog: ["Catalogo", "Tutti i giochi", "Preferiti"],
    shelves: ["Home", "Libreria", "Preferiti"],
    console: [],
    dashboard: ["Home", "Libreria", "Preferiti"],
    cinema: ["Home", "Libreria", "Store"],
    storefront: ["Home", "In evidenza", "Categorie"],
  };
  const labels = views[experience.id] || ["Home", "Libreria"];
  const navigation = `<div class="experience-preview__navigation">${labels.map((label) => `<span>${label}</span>`).join("")}</div>`;
  const heroText = {
    original: ["Interfaccia originale", "Libreria classica"],
    catalog: ["Tutti i giochi", "Catalogo della libreria"],
    shelves: ["La tua raccolta", "Continua a giocare"],
    console: ["Gioco selezionato", "Focus sulla raccolta"],
    dashboard: ["In primo piano", "Gruppi di giochi"],
    cinema: ["Gioco in evidenza", "Continua a giocare"],
    storefront: ["Scopri la raccolta", "Dettagli e categorie"],
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
  $("#plugin-list").innerHTML = ext.plugins.length ? ext.plugins.map((p) => `<div class="plugin-row">
      <label class="chk"><input type="checkbox" data-plugin="${esc(p.id)}" ${p.enabled ? "checked" : ""} ${p.locked ? "disabled" : ""}> <b>${esc(p.name)}</b></label>
      <span class="muted small">v${esc(p.version || "?")}${p.author ? " · " + esc(p.author) : ""} — ${esc(p.description || "")}
      ${p.error ? `<span class="status-bad">${esc(p.error)}</span>` : ""}</span></div>`).join("")
    : `<p class="muted">Nessun plugin installato.</p>`;
  $("#ext-credit").textContent = S.iconsCredit;
  $("#ext-paths").innerHTML = `Temi: <code>${esc(ext.paths.themes)}</code><br>Plugin: <code>${esc(ext.paths.plugins)}</code>`;
}

async function enterBigPicture() {
  const pw = window.pywebview && window.pywebview.api;
  try { if (pw && pw.set_fullscreen) await pw.set_fullscreen(true); } catch { /* browser */ }
  location.href = "/bigpicture";
}
