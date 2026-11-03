"use strict";
/* Pozzo Launcher - frontend: pagina «Download» (coda HTTP e torrent), contatore nella barra laterale e impostazioni.
 * Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html).
 * Le funzioni pure (DLU) sono provate con node da tests/test_downloads_ui.js. */

const DLU = (() => {
  const UNITS = ["B", "KB", "MB", "GB", "TB"];
  /** come fmtSize di core.js, ma 0 resta «0 B»: un download appena partito ha 0 byte, non «niente» */
  function bytes(n) {
    if (n == null || !isFinite(n) || n < 0) return "—";
    let i = 0;
    while (n >= 1024 && i < UNITS.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n.toFixed(0) : n < 10 ? n.toFixed(2) : n.toFixed(1)).replace(".", ",") + " " + UNITS[i];
  }
  const speed = (n) => (n > 0 ? bytes(n) + "/s" : "—");
  function eta(s) {
    if (s == null || !isFinite(s) || s < 0) return "—";
    s = Math.round(s);
    const two = (n) => String(n).padStart(2, "0");
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min ${two(s % 60)} s`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ${two(Math.floor(s / 60) % 60)} min`;
    return `${Math.floor(s / 86400)} g ${Math.floor(s / 3600) % 24} h`;
  }
  const STATUS = { queued: "In coda", running: "In corso", paused: "In pausa", completed: "Completato", error: "Errore" };
  const status = (s) => STATUS[s] || s || "—";
  const FILE_PRIO = [[0, "Salta"], [1, "Normale"], [4, "Alta"], [7, "Massima"]];
  // stesso ordine del server: priorità più alta prima, poi i più vecchi
  const order = (a, b) => (b.priority || 0) - (a.priority || 0) || (a.created || 0) - (b.created || 0);
  /** unisce gli aggiornamenti (task interi o parziali, per id) allo stato; restituisce un nuovo elenco ordinato */
  function merge(tasks, updates) {
    const byId = new Map((tasks || []).map((t) => [t.id, t]));
    for (const u of updates || []) if (u && u.id) byId.set(u.id, { ...byId.get(u.id), ...u });
    return [...byId.values()].sort(order);
  }
  /** download attivi (in corso o in coda) e velocità totali in byte/s (giù e su) */
  function summary(tasks) {
    let active = 0, total = 0, up = 0;
    for (const t of tasks || []) {
      if (t.status === "running" || t.status === "queued") active++;
      if (t.status === "running") total += t.speed || 0;
      up += (t.options && t.options.upload_rate) || 0; // chi è in condivisione carica anche da completato
    }
    return { active, speed: total, up };
  }
  /** attesa prima di riaprire lo stream dopo l'n-esimo errore di fila (ms) */
  const BACKOFF = [2000, 5000, 10000, 30000];
  const backoff = (n) => BACKOFF[Math.min(Math.max(n | 0, 0), BACKOFF.length - 1)];
  const PRIO = [[2, "Massima"], [1, "Alta"], [0, "Normale"], [-1, "Bassa"], [-2, "Minima"]];
  const clampPrio = (p) => Math.min(Math.max(Math.round(Number(p)) || 0, -2), 2);
  const prio = (p) => PRIO.find(([v]) => v === clampPrio(p))[1];
  // le chiavi coincidono con lo stato dei task («Attivi» = in corso)
  const FILTERS = [["all", "Tutti"], ["running", "Attivi"], ["queued", "In coda"], ["paused", "In pausa"], ["completed", "Completati"], ["error", "Errori"]];
  function filter(tasks, f, q) {
    q = (q || "").trim().toLocaleLowerCase("it");
    return (tasks || []).filter((t) => (!f || f === "all" || t.status === f)
      && (!q || `${t.name || ""} ${t.source || ""}`.toLocaleLowerCase("it").includes(q)));
  }
  /** selezione come in Esplora file: "one" solo quella riga, "toggle" (Ctrl) aggiunge o toglie, "range" (Maiusc) dall'ancora
   *  nell'ordine visibile `ids`, "ctx" (tasto destro) tiene la selezione se la riga ne fa parte. Restituisce { sel, anchor } nuovi. */
  function select(sel, ids, anchor, id, mode) {
    if (mode === "ctx" && sel.has(id)) return { sel, anchor };
    if (mode === "toggle") {
      const s = new Set(sel);
      if (!s.delete(id)) s.add(id);
      return { sel: s, anchor: id };
    }
    const a = ids.indexOf(anchor), b = ids.indexOf(id);
    if (mode === "range" && a >= 0 && b >= 0) return { sel: new Set(ids.slice(Math.min(a, b), Math.max(a, b) + 1)), anchor };
    return { sel: new Set([id]), anchor: id };
  }
  /** limite di velocità di un singolo download (options.limit, KB/s) come etichetta; "" se non c'è */
  function limit(l) {
    const out = [];
    if (l && l.down > 0) out.push(`↓ ${l.down} KB/s`);
    if (l && l.up > 0) out.push(`↑ ${l.up} KB/s`);
    return out.join(" ");
  }
  const DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]; // 0 = lunedì, come il server
  /** programmazione della modalità lenta in parole; "" se spenta */
  function schedule(s) {
    if (!s || !s.enabled) return "";
    const d = [...new Set(s.days ?? [0, 1, 2, 3, 4, 5, 6])].filter((x) => x >= 0 && x <= 6).sort();
    const k = d.join();
    const days = d.length === 7 ? "ogni giorno" : k === "0,1,2,3,4" ? "dal lunedì al venerdì" : k === "5,6" ? "sabato e domenica"
      : d.length ? d.map((i) => DAYS[i]).join(", ") : "nessun giorno";
    return `${days}, dalle ${s.from || "00:00"} alle ${s.to || "00:00"}`;
  }
  const DEBRID = [["realdebrid", "Real-Debrid", "https://real-debrid.com/apitoken"], ["alldebrid", "AllDebrid", "https://alldebrid.com/apikeys"],
    ["premiumize", "Premiumize", "https://www.premiumize.me/account"], ["torbox", "TorBox", "https://torbox.app/settings"],
    ["debridlink", "Debrid-Link", "https://debrid-link.com/webapp/apikey"]];
  const debridName = (id) => (DEBRID.find(([k]) => k === id) || [])[1] || id;
  /** esito di «Verifica» ({ok, user, premium, expires, error}) in una riga; expires in secondi, millisecondi o ISO */
  function debridState(r) {
    if (!r || !r.ok) return `✗ ${(r && r.error) || "Verifica non riuscita"}`;
    let out = `✓ Account ${r.user || "valido"}`;
    if (r.premium) {
      const n = Number(r.expires), d = r.expires ? new Date(isFinite(n) ? (n < 1e12 ? n * 1000 : n) : r.expires) : null;
      out += " · Premium" + (d && !isNaN(d) ? ` fino al ${d.toLocaleDateString("it-IT")}` : "");
    } else out += " · senza Premium";
    return out;
  }
  /* ---- MultiUp: mai il pulsante generico, ogni provider (mirror) è un pulsante a sé */
  const urlHost = (u) => { try { return new URL(u).hostname.toLowerCase().replace(/^www\./, ""); } catch { return ""; } };
  const MU_HOST = /(^|\.)multiup\./;
  /** link di un gioco ({provider, host, url}) o URL nudo che porta a MultiUp */
  const isMultiup = (x) => (typeof x === "string" ? MU_HOST.test(urlHost(x))
    : /multiup/i.test((x && x.provider) || "") || MU_HOST.test((x && x.host) || urlHost(x && x.url)));
  /** URL incollato a mano che si può espandere in provider: pagina MultiUp o accorciatore (ouo) */
  const isMirrorSource = (u) => /^https?:\/\//i.test(u) && (isMultiup(u) || /^ouo\.(io|press)$/.test(urlHost(u)));
  // come DL_HOST_RANK di detail.js: i host che il download manager risolve da soli prima, DataNodes (solo browser) ultimo
  const MIRROR_RANK = { "krakenfiles.com": 0, "megaup.net": 0, "1fichier.com": 1, "datanodes.to": 3 };
  const needsBrowser = (m) => /datanodes/i.test(`${m.host || ""} ${m.name || ""}`);
  const mirrorRank = (m) => MIRROR_RANK[(m.host || "").toLowerCase()] ?? 2;
  /** attivi prima, poi per preferenza; a parità resta l'ordine del server */
  const sortMirrors = (list) => (list || []).map((m, i) => [m, i])
    .sort((a, b) => ((a[0].live === false) - (b[0].live === false)) || (mirrorRank(a[0]) - mirrorRank(b[0])) || (a[1] - b[1])).map((x) => x[0]);
  /** come mostrare un mirror: etichetta, nota accanto, disattivato se offline */
  function mirrorView(m) {
    const dead = m.live === false, browser = !dead && needsBrowser(m);
    const label = m.name || m.host || "?";
    return { label, dead, browser, note: dead ? "offline" : browser ? "richiede il browser" : "",
      title: `${label}${m.host && m.host !== label ? " → " + m.host : ""}${dead ? " (offline)" : browser ? " (si scarica nel browser, con conto alla rovescia)" : ""}` };
  }
  /** il mirror da spuntare di default: il primo attivo che il manager scarica da solo, altrimenti il primo attivo */
  function defaultMirror(list) {
    const s = sortMirrors(list).filter((m) => m.live !== false);
    return s.find((m) => !needsBrowser(m)) || s[0] || null;
  }
  const muTitle = (n) => (n == null ? "MultiUp — elenca i provider" : `MultiUp — ${n} provider`);
  /* ---- registro del download */
  const LOG_LEVELS = { info: ["", "INFO"], warn: ["⚠ ", "AVVISO"], error: ["⛔ ", "ERRORE"] }; // l'icona e la parola dicono il livello anche senza colore
  const LOG_CAP = 1000; // righe tenute dalla finestra
  const two = (n) => String(n).padStart(2, "0");
  /** una riga del server {t, level, msg} pronta da mostrare: ora locale HH:MM:SS, livello, testo */
  function logView(l) {
    const d = new Date((Number(l && l.t) || 0) * 1000), lv = LOG_LEVELS[l && l.level] ? l.level : "info";
    const time = isFinite(d) ? `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}` : "--:--:--";
    const msg = String((l && l.msg) ?? "");
    return { time, level: lv, icon: LOG_LEVELS[lv][0], label: LOG_LEVELS[lv][1], msg, text: `${time} ${LOG_LEVELS[lv][1].padEnd(6)} ${msg}` };
  }
  /** secondi dall'inizio del registro: «+0,4 s», «+1 min 05 s» */
  function logRel(t, t0) {
    const s = Math.max(0, (Number(t) || 0) - (Number(t0) || 0));
    if (s < 60) return "+" + s.toFixed(1).replace(".", ",") + " s";
    return `+${Math.floor(s / 60)} min ${two(Math.floor(s % 60))} s`;
  }
  /** «step»: sotto-passo di un risolutore (riga che inizia con →); «key»: tappa del download; altrimenti "" */
  function logKind(msg) {
    const m = String(msg || "");
    if (/^\s*\u2192/.test(m)) return "step";
    return /^(Completato|Nella libreria|Link finale|Link risolto|Estratto|Errore|Avviato|Aggiunto|Console riconosciuta)/.test(m) ? "key" : "";
  }
  /** riepilogo in testa al registro: durata dal primo all'ultimo messaggio e conteggio avvisi/errori */
  function logSummary(lines) {
    const n = lines.length, a = lines.filter((l) => l.level === "warn").length, e = lines.filter((l) => l.level === "error").length;
    return { n, warn: a, error: e, span: n ? logRel(lines[n - 1].t, lines[0].t).slice(1) : "" };
  }
  /** unisce la risposta di /log?after= ({lines, n}) allo stato {lines, n}: `added` = righe nuove da accodare,
   *  `fresh` se il registro è un altro (n scende: download rimpiazzato) e va ridisegnato tutto */
  function logMerge(st, r) {
    const fresh = !st || r.n < st.n, add = r.lines || [];
    return { lines: ((fresh ? [] : st.lines).concat(add)).slice(-LOG_CAP), n: r.n, added: add, fresh };
  }
  /** da copiare e aprire a mano nel browser: solo indirizzi http(s), niente magnet; senza doppioni */
  const copyable = (urls) => [...new Set((urls || []).map((u) => String(u || "").trim()).filter((u) => /^https?:\/\//i.test(u)))];
  return { copyable, logView, logMerge, logRel, logKind, logSummary, isMultiup, isMirrorSource, sortMirrors, mirrorView, defaultMirror, muTitle, bytes, speed, eta, status, FILE_PRIO, merge, summary, backoff, PRIO, clampPrio, prio, FILTERS, filter, select, limit, schedule,
    DEBRID, debridName, debridState };
})();
if (typeof module !== "undefined") module.exports = DLU;


const DL = { tasks: [], settings: {}, open: new Set(), html: new WeakMap(), filter: "all", q: "", sel: new Set(), anchor: null, kbdMenu: 0, log: { id: "", lines: [], n: 0, busy: false, timer: 0 } };
const dlTask = (id) => DL.tasks.find((x) => x.id === id);
/** provider di un link MultiUp (o accorciatore): una risposta per URL in memoria per tutta la sessione; gli errori non si ricordano */
const MU_CACHE = new Map();
function muFetch(url, fresh = false) {
  if (fresh) MU_CACHE.delete(url);
  if (!MU_CACHE.has(url)) {
    const p = api("/api/links/mirrors", { body: { url } }).then((r) => {
      if (!r.ok || !(r.mirrors || []).length) throw new Error(r.reason || "Nessun provider trovato per questo link.");
      return { ...r, mirrors: DLU.sortMirrors(r.mirrors) };
    });
    p.catch(() => MU_CACHE.delete(url));
    MU_CACHE.set(url, p);
  }
  return MU_CACHE.get(url);
}

const dlUrl = (id) => `/api/downloads/${encodeURIComponent(id)}/`;

async function dlLoad() {
  const d = await api("/api/downloads");
  DL.settings = d.settings || {};
  DL.tasks = DLU.merge([], d.tasks);
  dlRefresh();
}

function dlApply(updates) {
  DL.tasks = DLU.merge(DL.tasks, updates);
  dlRefresh();
}

function dlRefresh() {
  const { active, speed } = DLU.summary(DL.tasks);
  const cnt = $("#cnt-dl");
  if (cnt) {
    cnt.textContent = active || "";
    cnt.closest(".nav-item").title = active ? `${active} download attivi · ${DLU.speed(speed)}` : "Download";
  }
  dlAltButton();
  dlsAltState();
  if (S.view.type === "downloads") dlRenderList();
}

/** righe compatte: scelta ricordata nel browser */
function dlDense() {
  try { return !!localStorage.getItem("dlDense"); } catch { return false; }
}

/* ---- pagina */
async function renderDownloads(pv) {
  pv.innerHTML = `<div class="page dl-page${dlDense() ? " dense" : ""}">
    <div class="page-head"><div><h2>⬇ Download</h2></div>
      <div class="dl-tools">
        <span class="dl-seg" role="group" aria-label="Tutti i download">
          <button class="btn" id="dl-pause-all" type="button">⏸ Pausa tutto</button>
          <button class="btn" id="dl-resume-all" type="button">▶ Riprendi tutto</button></span>
        <span class="dl-seg" role="group" aria-label="Pulizia dell'elenco">
          <button class="btn" id="dl-clear-done" type="button" title="Toglie dall'elenco i download completati">🧹 Completati</button>
          <button class="btn" id="dl-clear-err" type="button" title="Toglie dall'elenco i download falliti ed elimina i file parziali">🗑 Falliti</button></span>
        <button class="btn" id="dl-density" type="button" aria-pressed="${dlDense()}" title="Righe compatte">↕ Compatta</button>
        <button class="btn" id="dl-alt" type="button" aria-pressed="false">🐢 Modalità lenta</button>
        <button class="btn primary" id="dl-add" type="button">＋ Aggiungi</button></div></div>
    <div class="dl-stats" id="dl-total"></div>
    <div class="dl-filters">
      <div class="chips dl-chips" role="group" aria-label="Mostra">${DLU.FILTERS.map(([k, l]) =>
        `<button class="chip" type="button" data-filter="${k}" aria-pressed="${DL.filter === k}">${l}</button>`).join("")}</div>
      <input class="field" type="search" id="dl-q" placeholder="Cerca per nome o link" aria-label="Cerca nei download" value="${esc(DL.q)}">
    </div>
    <div class="dl-list" id="dl-rows"></div></div>`;
  $("#dl-add", pv).onclick = dlOpenAdd;
  $("#dl-density", pv).onclick = () => {
    const on = !dlDense();
    try { localStorage.setItem("dlDense", on ? "1" : ""); } catch { /* modalità privata: vale solo per questa visita */ }
    $(".dl-page", pv).classList.toggle("dense", on);
    $("#dl-density", pv).setAttribute("aria-pressed", on);
  };
  const all = (what) => async () => {
    try { await api(`/api/downloads/${what}`, { body: {} }); } catch (e) { toast(e.message, true); }
  };
  $("#dl-pause-all", pv).onclick = all("pause-all");
  $("#dl-resume-all", pv).onclick = all("resume-all");
  const clear = (status, purge) => () => {
    const tasks = DL.tasks.filter((t) => t.status === status);
    if (!tasks.length) return toast(status === "error" ? "Nessun download fallito" : "Nessun download completato");
    dlCancel(tasks, purge);
  };
  $("#dl-clear-done", pv).onclick = clear("completed", { title: "Pulire i completati?", ok: "Pulisci", del: false,
    text: (n) => `${n} download completati verranno tolti dall'elenco.` });
  $("#dl-clear-err", pv).onclick = clear("error", { title: "Pulire i falliti?", ok: "Pulisci", del: true,
    text: (n) => `${n} download falliti verranno tolti dall'elenco, con i loro file parziali.` });
  $("#dl-alt", pv).onclick = async () => {
    try { DL.settings = await api("/api/downloads/alt-speed", { body: { on: !DL.settings.alt_active } }); } catch (e) { return toast(e.message, true); }
    dlRefresh();
    toast(DL.settings.alt_active ? "🐢 Modalità lenta attiva" : "Modalità lenta disattivata");
  };
  $(".dl-chips", pv).addEventListener("click", (e) => {
    const c = e.target.closest("[data-filter]");
    if (!c) return;
    DL.filter = c.dataset.filter;
    for (const b of c.parentElement.children) b.setAttribute("aria-pressed", b === c);
    dlRenderList();
  });
  $("#dl-q", pv).addEventListener("input", (e) => { DL.q = e.target.value; dlRenderList(); });
  const page = $(".dl-page", pv);
  page.addEventListener("click", (e) => {
    if (e.target.id === "dl-empty-add") return dlOpenAdd();
    const b = e.target.closest("button[data-act]");
    if (b) return dlAct(b.closest(".dl-row").dataset.id, b.dataset.act, b);
    const row = e.target.closest(".dl-row");
    if (row && !e.target.closest("a, button, input, select, label, .dl-x")) dlSelect(row.dataset.id, e.shiftKey ? "range" : e.ctrlKey || e.metaKey ? "toggle" : "one");
  });
  page.addEventListener("dblclick", (e) => {
    const row = e.target.closest(".dl-row");
    if (row && !e.target.closest("a, button, input, select, label, .dl-x")) dlLog(row.dataset.id);
  });
  page.addEventListener("mousedown", (e) => { if (e.shiftKey && e.target.closest(".dl-row")) e.preventDefault(); }); // niente testo evidenziato con Maiusc+clic
  page.addEventListener("change", (e) => {
    const c = e.target.closest("[data-act]");
    if (c) dlAct(c.closest(".dl-row").dataset.id, c.dataset.act, c);
  });
  // menu della riga: tasto destro, tasto Menu o Maiusc+F10 (il WebView genera anche «contextmenu»: kbdMenu evita il doppio)
  page.addEventListener("contextmenu", (e) => {
    const row = e.target.closest(".dl-row");
    if (!row || e.target.closest("input, select, textarea")) return;
    e.preventDefault();
    if (Date.now() - DL.kbdMenu < 500) return;
    const r = e.target.getBoundingClientRect();
    dlMenu(row.dataset.id, e.clientX || e.clientY ? { x: e.clientX, y: e.clientY } : { x: r.left, y: r.bottom });
  });
  page.addEventListener("keydown", (e) => {
    const row = e.target.closest(".dl-row");
    if (!row || !(e.key === "ContextMenu" || (e.shiftKey && e.key === "F10"))) return;
    e.preventDefault();
    DL.kbdMenu = Date.now();
    const r = e.target.getBoundingClientRect();
    dlMenu(row.dataset.id, { x: r.left, y: r.bottom });
  });
  try { await dlLoad(); } catch (e) { $("#dl-rows", pv).innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

function dlAltButton() {
  const b = $("#dl-alt");
  if (!b) return;
  const on = !!DL.settings.alt_active, sch = DLU.schedule(DL.settings.alt_schedule);
  b.classList.toggle("on", on);
  b.setAttribute("aria-pressed", on);
  b.title = (on ? "Modalità lenta attiva: limiti di velocità alternativi" : "Usa i limiti di velocità alternativi (Impostazioni › Download)")
    + (sch ? ` · programmata ${sch}` : "");
}

function dlRow(t) {
  const o = t.options || {}, tor = t.type === "torrent", name = t.name || t.source || "";
  const pct = Math.round(Math.min(Math.max(t.progress || 0, 0), 1) * 100), open = DL.open.has(t.id);
  const btn = (act, ico, label, extra = "") => `<button class="icon-btn" type="button" data-act="${act}" title="${label}" aria-label="${label}: ${esc(name)}"${extra}>${ico}</button>`;
  const live = t.status === "running" || t.status === "queued", p = DLU.clampPrio(t.priority), lim = DLU.limit(o.limit);
  const install = !!o.setup && t.status === "completed"; // repack estratto: il setup si avvia da qui
  return `<div class="dl-row" data-id="${esc(t.id)}" data-status="${esc(t.status)}"${o.seeding ? ' data-seed="1"' : ""}>
    <div class="dl-main">
      ${tor ? `<button class="icon-btn" type="button" data-act="toggle" aria-expanded="${open}" aria-controls="dl-x-${esc(t.id)}" title="File e dettagli" aria-label="File e dettagli: ${esc(name)}">${open ? "▾" : "▸"}</button>` : "<span></span>"}
      <div class="dl-info">
        <div class="dl-name"><b title="${esc(t.source)}">${esc(name)}</b><span class="dl-type">${tor ? "Torrent" : "HTTP"}</span>
          ${p ? `<span class="dl-type${p > 0 ? " hi" : ""}" title="Priorità">${p > 0 ? "↑" : "↓"} ${DLU.prio(p)}</span>` : ""}
          ${lim ? `<span class="dl-type" title="Limite di velocità di questo download">⏱ ${lim}</span>` : ""}
          ${o.resolved_by ? `<span class="dl-type">via ${esc(DLU.debridName(o.resolved_by))}</span>` : ""}
          <span class="dl-st">${o.seeding ? "In condivisione" : esc(DLU.status(t.status))}</span></div>
        <div class="dl-bar" role="progressbar" aria-label="Avanzamento: ${esc(name)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div>
        ${t.phase ? `<div class="dl-now${t.status === "error" ? " bad" : ""}" title="Passaggio prima del download">${t.status === "error" ? "Fermo a: " : ""}${esc(t.phase)}</div>` : ""}
        <div class="dl-meta muted small">${pct}% · ${DLU.bytes(t.done)} di ${t.size ? DLU.bytes(t.size) : "?"}${t.status === "running" ? ` · ${DLU.speed(t.speed)} · mancano ${DLU.eta(t.eta)}` : ""}${tor && o.peers != null ? ` · ${o.peers} peer, ${o.seeds ?? 0} seed` : ""}${tor && o.upload_rate ? ` · ↑ ${DLU.speed(o.upload_rate)}` : ""}${tor && o.ratio != null ? ` · rapporto ${Number(o.ratio).toFixed(2).replace(".", ",")}` : ""}
          ${t.status === "error" && t.error ? `<div class="dl-err">${esc(t.error)}</div>` : ""}</div>
      </div>
      <div class="dl-acts">
        ${install ? `<button class="btn" type="button" data-act="install" title="Avvia il setup del repack: a installazione finita il gioco entra in libreria">📦 Installa</button>` : ""}
        <span class="dl-more">${btn("up", "▲", "Priorità più alta")}${btn("down", "▼", "Priorità più bassa")}${btn("open-folder", "📂", "Apri cartella")}${btn("cancel", "✕", "Annulla")}</span>
        ${live ? btn("pause", "⏸", "Pausa") : t.status !== "completed" ? btn("resume", "▶", "Riprendi") : ""}
        ${btn("log", "📋", "Registro")}${btn("menu", "⋯", "Altre azioni", ' aria-haspopup="menu"')}
      </div>
    </div>
    ${tor && open ? dlTorrentBox(t) : ""}
  </div>`;
}

function dlTorrentBox(t) {
  const o = t.options || {}, files = o.files || [];
  if (o.metadata === false) return `<div class="dl-x" id="dl-x-${esc(t.id)}"><p class="muted small">In attesa dei metadati…</p></div>`;
  return `<div class="dl-x" id="dl-x-${esc(t.id)}">
    <label class="chk"><input type="checkbox" data-act="seq"${o.sequential ? " checked" : ""}> Download sequenziale <span class="muted small">(in ordine: utile per vedere un video mentre scarica)</span></label>
    ${files.length ? `<table class="dl-files"><thead><tr><th>File</th><th>Dimensione</th><th>Avanzamento</th><th>Priorità</th></tr></thead><tbody>
      ${files.map((f) => `<tr><td>${esc(f.name)}</td><td>${DLU.bytes(f.size)}</td>
        <td class="dl-fpct"><span class="dl-fbar" role="progressbar" aria-label="Avanzamento: ${esc(f.name)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round((f.progress || 0) * 100)}"><i style="width:${Math.round((f.progress || 0) * 100)}%"></i></span>${Math.round((f.progress || 0) * 100)}%</td>
        <td><select class="field" data-act="fprio" data-file="${esc(f.index)}" aria-label="Priorità: ${esc(f.name)}">${DLU.FILE_PRIO.map(([v, l]) => `<option value="${v}"${(f.priority ?? 1) === v ? " selected" : ""}>${l}</option>`).join("")}</select></td></tr>`).join("")}
    </tbody></table>` : ""}
  </div>`;
}

/** aggiorna solo le righe cambiate: chi sta usando i tasti o una tendina non perde il punto */
function dlRenderList() {
  const box = $("#dl-rows");
  if (!box) return;
  const { active, speed, up } = DLU.summary(DL.tasks), list = DLU.filter(DL.tasks, DL.filter, DL.q);
  const total = $("#dl-total");
  if (total) {
    const n = (s) => DL.tasks.filter((t) => t.status === s).length;
    total.innerHTML = [["Attivi", active || "0"], ["↓", DLU.speed(speed)], ["↑", DLU.speed(up)],
      ["Completati", n("completed")], ["Errori", n("error")]]
      .map(([k, v]) => `<div class="dl-stat${k === "Errori" && v ? " bad" : ""}"><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`).join("");
  }
  if (!list.length) {
    box.innerHTML = `<div class="dl-empty muted">${!DL.tasks.length
      ? `<div class="dl-empty-ico" aria-hidden="true">⬇</div><p>Nessun download.</p>
         <p class="small">Incolla un link http, un magnet o un file .torrent.</p>
         <button class="btn primary" type="button" id="dl-empty-add">＋ Aggiungi un download</button>`
      : "Nessun download corrisponde al filtro o alla ricerca."}</div>`;
    return;
  }
  box.querySelector(".dl-empty")?.remove();
  const act = document.activeElement, focusRow = box.contains(act) ? act.closest(".dl-row") : null;
  const old = new Map([...box.children].map((el) => [el.dataset.id, el]));
  let refocus = null;
  list.forEach((t, i) => {
    const html = dlRow(t);
    let el = old.get(t.id);
    old.delete(t.id);
    // una tendina con il fuoco non si ridisegna (si chiuderebbe): si aggiorna al giro dopo
    if (!el || (DL.html.get(el) !== html && !(el === focusRow && act.tagName === "SELECT"))) {
      const tpl = document.createElement("template");
      tpl.innerHTML = html;
      const nu = tpl.content.firstElementChild;
      DL.html.set(nu, html);
      if (el) {
        if (el === focusRow && act.dataset.act) refocus = [nu, `[data-act="${act.dataset.act}"]${act.dataset.file != null ? `[data-file="${act.dataset.file}"]` : ""}`];
        el.replaceWith(nu);
      }
      el = nu;
    }
    if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null);
  });
  old.forEach((el) => el.remove());
  if (refocus) refocus[0].querySelector(refocus[1])?.focus();
  dlMarkSel();
}

/* ---- selezione multipla: la classe si mette a parte, così la riga non va ridisegnata */
function dlSelect(id, mode) {
  ({ sel: DL.sel, anchor: DL.anchor } = DLU.select(DL.sel, DLU.filter(DL.tasks, DL.filter, DL.q).map((t) => t.id), DL.anchor, id, mode));
  dlMarkSel();
}

function dlMarkSel() {
  document.querySelectorAll("#dl-rows .dl-row").forEach((el) => el.classList.toggle("sel", DL.sel.has(el.dataset.id)));
}

/** la stessa azione su più download; continua anche se uno fallisce e poi segnala il primo errore */
async function dlEach(ids, path, body = {}) {
  let err = null;
  for (const id of ids) {
    try { await api(dlUrl(id) + path, { body }); } catch (e) { err ??= e; }
  }
  if (err) throw err;
}

async function dlPriority(ids, priority) {
  await dlEach(ids, "priority", { priority });
  dlApply(ids.map((id) => ({ id, priority })));
}

/* ---- menu della riga: vale per tutte le righe selezionate */
function dlMenu(id, pt) {
  const t = dlTask(id);
  if (!t) return;
  dlSelect(id, "ctx");
  const tasks = DL.tasks.filter((x) => DL.sel.has(x.id)), ids = tasks.map((x) => x.id), many = ids.length > 1;
  const live = (x) => x.status === "running" || x.status === "queued";
  const tor = tasks.filter((x) => x.type === "torrent").map((x) => x.id);
  const acts = [];
  const it = (l, f, o = {}) => {
    acts.push(f);
    return `<div class="ci${o.hl ? " hl" : ""}" role="${o.role || "menuitem"}" tabindex="-1" data-i="${acts.length - 1}"${o.role ? ` aria-checked="${!!o.on}"` : ""}>`
      + `${o.role ? `<span class="ck" aria-hidden="true">${o.on ? "✓" : ""}</span>` : ""}${esc(l)}</div>`;
  };
  const toPause = tasks.filter(live).map((x) => x.id), toResume = tasks.filter((x) => x.status === "paused" || x.status === "error").map((x) => x.id);
  let html = (toPause.length ? it("⏸ Pausa", () => dlEach(toPause, "pause")) : "")
    + (toResume.length ? it("▶ Riprendi", () => dlEach(toResume, "resume")) : "")
    + `<hr role="separator"><div role="group" aria-labelledby="dl-ctx-prio"><div class="ch" id="dl-ctx-prio">Priorità</div>`
    + DLU.PRIO.map(([v, l]) => it(l, () => dlPriority(ids, v), { role: "menuitemradio", on: !many && DLU.clampPrio(t.priority) === v })).join("")
    + `</div><hr role="separator">`
    + it("⤒ Sposta in cima", () => dlEach([...ids].reverse(), "move", { to: "top" })) // al contrario: la prima resta in cima
    + it("⤓ Sposta in fondo", () => dlEach(ids, "move", { to: "bottom" }))
    + it("⏱ Limite di velocità…", () => dlLimit(ids))
    + (many ? "" : it("📋 Registro…", () => dlLog(id)))
    + (many ? "" : it("📂 Apri cartella", () => api(dlUrl(id) + "open-folder", { body: {} })))
    + (many || !(t.options || {}).setup || t.status !== "completed" ? "" : it("📦 Installa il repack", () => api(dlUrl(id) + "install", { body: {} })))
    + it(many ? "📋 Copia i link" : "📋 Copia link", () => navigator.clipboard.writeText(tasks.map((x) => x.source).join("\n")).then(() => toast(many ? "Link copiati" : "Link copiato")));
  if (tor.length) {
    const seq = t.type === "torrent" && !!(t.options || {}).sequential;
    html += `<hr role="separator">` + it("Download sequenziale", () => dlEach(tor, "sequential", { on: !seq }), { role: "menuitemcheckbox", on: seq })
      + it("⟳ Ricontrolla i file", () => dlEach(tor, "recheck"))
      + it("📣 Riannuncia ai tracker", () => dlEach(tor, "reannounce"));
  }
  html += `<hr role="separator">` + it(many ? `🗑 Elimina ${ids.length} download…` : "🗑 Elimina…", () => dlCancel(tasks), { hl: 1 });

  closeCtx();
  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.setAttribute("role", "menu");
  m.setAttribute("aria-label", many ? `${ids.length} download selezionati` : t.name || t.source || "Download");
  m.innerHTML = html;
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(pt.x, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(pt.y, innerHeight - m.offsetHeight - 8)) + "px";
  const items = [...m.querySelectorAll(".ci")];
  const back = () => { closeCtx(); $(`#dl-rows .dl-row[data-id="${CSS.escape(id)}"] [data-act="menu"]`)?.focus(); };
  items[0]?.focus();
  m.addEventListener("keydown", (e) => {
    const i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
    else if (e.key === "Home" || e.key === "End") items[e.key === "Home" ? 0 : items.length - 1].focus();
    else if (e.key === "Enter" || e.key === " ") document.activeElement.click();
    else if (e.key === "Escape" || e.key === "Tab") back();
    else return;
    e.preventDefault();
    e.stopPropagation();
  });
  m.onclick = async (ev) => {
    const el = ev.target.closest(".ci");
    if (!el) return;
    back();
    try { await acts[+el.dataset.i](); } catch (err) { toast(err.message, true); }
  };
}

async function dlAct(id, act, el) {
  const t = dlTask(id);
  if (!t) return;
  if (act === "toggle") { if (!DL.open.delete(id)) DL.open.add(id); return dlRenderList(); }
  if (act === "cancel") return dlCancel([t]);
  if (act === "log") return dlLog(id);
  if (act === "menu") { const r = el.getBoundingClientRect(); return dlMenu(id, { x: r.left, y: r.bottom }); }
  if (act === "install") { // setup del repack: si apre la finestra dell'installer, il gioco entra in libreria da solo
    try {
      await api(dlUrl(id) + "install", { body: {} });
      toast("Setup del repack avviato: a installazione finita il gioco compare in libreria");
    } catch (e) { toast(e.message, true); }
    return;
  }
  const url = dlUrl(id);
  try {
    if (act === "up" || act === "down") {
      const priority = DLU.clampPrio((t.priority || 0) + (act === "up" ? 1 : -1));
      if (priority !== (t.priority || 0)) await dlPriority([id], priority);
    } else if (act === "fprio") await api(url + "files", { body: { priorities: { [el.dataset.file]: Number(el.value) } } });
    else if (act === "seq") await api(url + "sequential", { body: { on: el.checked } });
    else await api(url + act, { body: {} }); // pause, resume, open-folder
  } catch (e) { toast(e.message, true); }
}

/** `purge`: pulizia dell'elenco (completati / falliti) invece dell'annullamento; `del` = file eliminati di default. */
function dlCancel(tasks, purge = null) {
  const d = $("#dl-cancel-dlg");
  $("#dl-cancel-title").textContent = purge ? purge.title : "Annullare il download?";
  $("#dl-cancel-no").textContent = purge ? "Annulla" : "Continua a scaricare";
  $("#dl-cancel-ok").textContent = purge ? purge.ok : "Annulla il download";
  $("#dl-cancel-name").textContent = purge ? purge.text(tasks.length)
    : tasks.length > 1 ? `${tasks.length} download selezionati` : tasks[0].name || tasks[0].source;
  $("#dl-cancel-del").checked = !!(purge && purge.del);
  d.returnValue = "";
  d.onclose = async () => {
    if (d.returnValue !== "ok") return;
    const gone = new Set();
    let err = null;
    for (const t of tasks) {
      try { await api(dlUrl(t.id) + "cancel", { body: { delete_files: $("#dl-cancel-del").checked } }); gone.add(t.id); }
      catch (e) { err ??= e; }
    }
    DL.tasks = DL.tasks.filter((x) => !gone.has(x.id)); // il server non annuncia i task annullati
    gone.forEach((id) => DL.sel.delete(id));
    dlRefresh();
    if (err) toast(err.message, true);
  };
  d.showModal();
}

function dlLimit(ids) {
  const d = $("#dl-limit-dlg"), l = (dlTask(ids[0])?.options || {}).limit || {};
  $("#dl-limit-name").textContent = ids.length > 1 ? `${ids.length} download selezionati` : dlTask(ids[0])?.name || "";
  $("#dl-lim-down").value = l.down || 0;
  $("#dl-lim-up").value = l.up || 0;
  d.returnValue = "";
  d.onclose = async () => {
    if (d.returnValue !== "ok") return;
    const kb = (sel) => Math.max(0, Math.round(Number($(sel).value) || 0));
    try { await dlEach(ids, "limit", { down: kb("#dl-lim-down"), up: kb("#dl-lim-up") }); } catch (e) { return toast(e.message, true); }
    toast("Limite di velocità salvato");
  };
  d.showModal();
  $("#dl-lim-down").select();
}

/* ---- registro del download: finestra con le righe nuove accodate (aria-live), senza ridisegnare */
const dlLogLive = (t) => !!t && (t.status === "running" || t.status === "queued");

function dlLogRow(l) {
  const v = DLU.logView(l), k = DLU.logKind(l.msg), t0 = (DL.log.lines[0] || l).t;
  return `<div class="dl-ll ${v.level}${k ? " " + k : ""}"><time title="${v.time}" data-abs="${v.time}">${DLU.logRel(l.t, t0)}</time>`
    + `<b>${v.icon}${v.label}</b><span>${esc(v.msg.replace(/^\s*\u2192\s*/, ""))}</span></div>`;
}

/** riepilogo sopra il registro: avanzamento, durata, avvisi ed errori */
function dlLogSummary() {
  const t = dlTask(DL.log.id), s = DLU.logSummary(DL.log.lines), el = $("#dl-log-sum");
  if (!el) return;
  const pct = t ? Math.round(Math.min(Math.max(t.progress || 0, 0), 1) * 100) : 0;
  el.innerHTML = [t ? `<span><b>${pct}%</b> ${DLU.bytes(t.done)} di ${t.size ? DLU.bytes(t.size) : "?"}</span>` : "",
    s.n ? `<span>${s.n} righe in <b>${esc(s.span)}</b></span>` : "",
    s.warn ? `<span class="warn">${s.warn} avvisi</span>` : "", s.error ? `<span class="error">${s.error} errori</span>` : ""].join("");
}

function dlLogHead() {
  const t = dlTask(DL.log.id), d = $("#dl-log-dlg");
  d.dataset.status = t ? t.status : "";
  $("#dl-log-title").textContent = t ? `Registro: ${t.name || t.source}` : "Registro: download rimosso";
  $("#dl-log-st").textContent = !t ? "" : (t.options || {}).seeding ? "In condivisione" : DLU.status(t.status);
  dlLogSummary();
}

function dlLogShow(st) {
  const L = DL.log, box = $("#dl-log-box");
  if (st.fresh) box.replaceChildren();
  box.querySelector(".dl-log-empty")?.remove();
  box.insertAdjacentHTML("beforeend", (st.fresh ? st.lines : st.added).map(dlLogRow).join(""));
  if (!L.lines.length) box.innerHTML = `<p class="dl-log-empty muted small">Nessuna riga nel registro.</p>`;
  dlLogSummary();
  if ($("#dl-log-follow").checked) box.scrollTop = box.scrollHeight;
}

/** `reset`: riparte da zero (apertura, «Aggiorna»); `quiet`: dal timer, senza avvisi */
async function dlLogFetch(reset = false, quiet = true) {
  const L = DL.log, id = L.id;
  if (!id || L.busy) return;
  L.busy = true;
  try {
    if (reset) { L.lines = []; L.n = 0; }
    const r = await api(`${dlUrl(id)}log?after=${L.n}`);
    if (L.id !== id) return;
    const st = DLU.logMerge(reset ? null : L, r);
    L.lines = st.lines;
    L.n = st.n;
    if (reset || st.added.length || st.fresh) dlLogShow(reset ? { ...st, fresh: true } : st);
  } catch (e) {
    if (!quiet) toast(e.message, true);
  } finally { L.busy = false; }
}

function dlLog(id) {
  const t = dlTask(id), d = $("#dl-log-dlg"), L = DL.log, opener = document.activeElement;
  if (!t) return;
  clearInterval(L.timer);
  Object.assign(L, { id, lines: [], n: 0, busy: false });
  $("#dl-log-box").replaceChildren();
  $("#dl-log-follow").checked = true;
  dlLogHead();
  // si aggiorna se il download lavora o se ha scritto qualcosa che non abbiamo (il contatore log_n arriva con ogni evento)
  L.timer = setInterval(() => {
    const x = dlTask(id);
    dlLogHead();
    if (!x) return clearInterval(L.timer);
    if (dlLogLive(x) || x.log_n !== L.n) dlLogFetch();
  }, 1000);
  d.onclose = () => {
    clearInterval(L.timer);
    L.id = "";
    (opener && opener.isConnected ? opener : $(`#dl-rows .dl-row[data-id="${CSS.escape(id)}"] [data-act="log"]`))?.focus();
  };
  d.showModal();
  $("#dl-log-box").focus();
  dlLogFetch(true, false);
}

function dlLogInit() {
  const box = $("#dl-log-box"), follow = $("#dl-log-follow");
  box.addEventListener("scroll", () => { follow.checked = box.scrollHeight - box.scrollTop - box.clientHeight < 24; }); // salire a mano toglie «Segui»
  $("#dl-log-filter").addEventListener("click", (e) => { // solo avvisi / solo errori: si nasconde, non si ridisegna
    const c = e.target.closest("[data-lf]");
    if (!c) return;
    box.dataset.f = c.dataset.lf;
    for (const b of c.parentElement.children) b.setAttribute("aria-pressed", b === c);
  });
  $("#dl-log-abs").onchange = (e) => $("#dl-log-dlg").classList.toggle("abs", e.target.checked);
  follow.onchange = () => { if (follow.checked) box.scrollTop = box.scrollHeight; };
  $("#dl-log-refresh").onclick = () => dlLogFetch(true, false);
  $("#dl-log-copy").onclick = () => {
    const text = DL.log.lines.map((l) => DLU.logView(l).text).join("\n");
    navigator.clipboard.writeText(text).then(() => toast("Registro copiato"), () => toast("Non riesco a copiare negli appunti", true));
  };
  $("#dl-log-clear").onclick = async () => {
    try { await api(dlUrl(DL.log.id) + "log/clear", { body: {} }); } catch (e) { return toast(e.message, true); }
    DL.log.lines = [];
    dlLogShow({ fresh: true, lines: [], added: [] });
  };
}

/* ---- finestra «Aggiungi» */
/** righe espanse in provider nella finestra: riga incollata -> true; le scelte sono le caselle spuntate di #dl-mu-list */
const dlMuDone = new Set();
function dlMuSources() { return $("#dl-links").value.split(/\r?\n/).map((s) => s.trim()).filter(DLU.isMirrorSource); }

function dlMuSync() { // tiene il pulsante «Elenca provider» solo se c'è qualcosa da espandere e toglie i gruppi di righe cancellate
  const src = dlMuSources();
  $("#dl-mu-go").hidden = !src.some((u) => !dlMuDone.has(u));
  for (const g of $("#dl-mu-list").querySelectorAll("fieldset")) if (!src.includes(g.dataset.src)) { dlMuDone.delete(g.dataset.src); g.remove(); }
}

async function dlMuList() {
  const go = $("#dl-mu-go"), box = $("#dl-mu-list");
  const todo = dlMuSources().filter((u) => !dlMuDone.has(u));
  go.disabled = true;
  box.setAttribute("aria-busy", "true");
  go.textContent = "Cerco i provider…";
  try {
    for (const url of todo) {
      const g = document.createElement("fieldset");
      g.dataset.src = url;
      g.innerHTML = `<legend class="small">${esc(url.length > 60 ? url.slice(0, 57) + "…" : url)}</legend>`;
      box.append(g);
      try {
        const r = await muFetch(url);
        const pick = DLU.defaultMirror(r.mirrors);
        g.insertAdjacentHTML("beforeend", r.mirrors.map((m) => {
          const v = DLU.mirrorView(m);
          return `<label class="small" style="display:block" title="${esc(v.title)}"><input type="checkbox" value="${esc(m.url)}"
            ${v.dead ? "disabled" : ""} ${m === pick ? "checked" : ""}> ${esc(v.label)}${v.note ? ` <span class="muted">${esc(v.note)}</span>` : ""}</label>`;
        }).join(""));
        dlMuDone.add(url);
      } catch (e) {
        g.insertAdjacentHTML("beforeend", `<p class="small err" role="alert">${esc(e.message)} Premi di nuovo «Elenca provider» per riprovare.</p>`);
      }
    }
  } finally {
    box.removeAttribute("aria-busy");
    go.disabled = false;
    go.textContent = "Elenca provider";
    dlMuSync();
    box.querySelector("input:not(:disabled)")?.focus();
  }
}

function dlOpenAdd() {
  dlMuDone.clear();
  $("#dl-mu-list").replaceChildren();
  $("#dl-mu-go").hidden = true;
  $("#dl-links").value = "";
  $("#dl-file").value = "";
  $("#dl-dest").value = DL.settings.dir || "";
  $("#dl-add-dlg").showModal();
  $("#dl-links").focus();
}

async function dlSubmit() {
  // le righe espanse in provider sono sostituite dai provider spuntati (nessuno spuntato: la riga non parte)
  const picked = [...$("#dl-mu-list").querySelectorAll("input:checked")];
  const links = $("#dl-links").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    .flatMap((l) => (dlMuDone.has(l) ? picked.filter((i) => i.closest("fieldset").dataset.src === l).map((i) => i.value) : [l]));
  const file = $("#dl-file").files[0], save_path = $("#dl-dest").value.trim();
  if (!links.length && !file) return toast("Incolla almeno un link o scegli un file .torrent", true);
  const go = $("#dl-add-go");
  go.disabled = true;
  const added = [];
  try {
    if (links.length) {
      added.push(...((await api("/api/downloads", { body: { links, save_path } })).tasks || []));
      $("#dl-links").value = ""; // se poi fallisce il .torrent, i link non si rimandano due volte
    }
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      if (save_path) fd.append("save_path", save_path);
      const r = await fetch("/api/downloads/torrent-file", { method: "POST", body: fd });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || r.statusText);
      added.push(...(j.tasks || (j.task ? [j.task] : [])));
    }
    $("#dl-add-dlg").close();
    toast(added.length === 1 ? "Download aggiunto" : `${added.length} download aggiunti`);
  } catch (e) { toast(e.message, true); }
  finally { go.disabled = false; if (added.length) dlApply(added); }
}

/* ---- impostazioni › Download: ogni campo salva da solo (corpo parziale), il server risponde con i valori riportati nei limiti */
const DLS_FIELDS = [
  ["#dls-dir", "dir", "str"], ["#dls-max", "max_active", "int"], ["#dls-max-http", "max_active_http", "int"],
  ["#dls-max-tor", "max_active_torrent", "int"], ["#dls-seg", "segments", "int"],
  ["#dls-extract", "auto_extract", "bool"], ["#dls-showbrowser", "show_browser", "bool"], ["#dls-clip", "clipboard", "bool"],
  ["#dls-down", "limit_down", "int"], ["#dls-up", "limit_up", "int"],
  ["#dls-alt-down", "alt_limit_down", "int"], ["#dls-alt-up", "alt_limit_up", "int"], ["#dls-alt-on", "alt_enabled", "bool"],
  ["#dls-port", "port", "int"], ["#dls-enc", "encryption", "str"],
  ["#dls-ratio", "seed_ratio", "num"], ["#dls-seed-min", "seed_minutes", "int"], ["#dls-trackers", "trackers", "lines"],
];

function dlsRead(el, kind) {
  if (kind === "bool") return el.checked;
  if (kind === "lines") return el.value.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  if (kind === "str") return el.value.trim();
  const n = Number(el.value) || 0;
  return kind === "int" ? Math.round(n) : n;
}

function dlsFill(s) {
  for (const [sel, k, kind] of DLS_FIELDS) {
    const el = $(sel);
    if (kind === "bool") el.checked = !!s[k];
    else if (kind === "lines") el.value = (s[k] || []).join("\n");
    else if (s[k] != null) el.value = s[k];
  }
  const sch = s.alt_schedule || {}, days = sch.days ?? [0, 1, 2, 3, 4, 5, 6];
  $("#dls-sch-on").checked = !!sch.enabled;
  $("#dls-sch-from").value = sch.from || "";
  $("#dls-sch-to").value = sch.to || "";
  document.querySelectorAll("#dls-sch-days [data-day]").forEach((c) => { c.checked = days.includes(+c.dataset.day); });
  document.querySelectorAll("[data-disc]").forEach((c) => { c.checked = !!(s.discovery || {})[c.dataset.disc]; });
  document.querySelectorAll("#dls-debrid [data-svc]").forEach((box) => {
    const d = (s.debrid || {})[box.dataset.svc] || {};
    $("[data-deb=on]", box).checked = !!d.enabled;
    $("[data-deb=saved]", box).hidden = !d.key_set;
    $("[data-deb=key]", box).placeholder = d.key_set ? "Incolla una nuova chiave per sostituirla" : "Incolla la chiave API";
  });
  dlsAltState();
}

function dlsAltState() {
  const el = $("#dls-alt-state");
  if (!el) return;
  const sch = DLU.schedule(DL.settings.alt_schedule);
  el.textContent = (DL.settings.alt_active ? "🐢 Attiva adesso" : "Non attiva adesso") + (sch ? ` · programmata ${sch}` : "");
}

async function dlsSave(body) {
  DL.settings = await api("/api/downloads/settings", { body });
  dlsFill(DL.settings);
  dlAltButton();
}

async function loadDownloadSettings() {
  const dir = $("#dls-dir");
  if (!dir) return;
  if (!dir.dataset.bound) dlsBind();
  try { DL.settings = (await api("/api/downloads")).settings || {}; } catch (e) { return toast(e.message, true); }
  dlsFill(DL.settings);
}

function dlsBind() {
  const dir = $("#dls-dir"), pane = dir.closest("[data-pane]") || document;
  dir.dataset.bound = "1";
  $("#dls-debrid").innerHTML = DLU.DEBRID.map(([svc, label, url]) => `<div class="dls-deb" data-svc="${svc}">
    <label class="chk"><input type="checkbox" data-deb="on"> Usa <b>${label}</b></label>
    <div class="row wrap">
      <label class="lbl-field grow">Chiave API di ${label}
        <input class="field" type="password" data-deb="key" autocomplete="off" spellcheck="false"></label>
      <button class="btn" type="button" data-deb="test">Verifica</button>
    </div>
    <p class="small"><span data-deb="saved" hidden>✓ Chiave salvata <button class="btn" type="button" data-deb="del">Rimuovi</button> · </span>
      <a href="#" data-open="${url}">Dove trovo la chiave</a> <span data-deb="state" role="status"></span></p>
  </div>`).join("");
  for (const [sel, k, kind] of DLS_FIELDS) autosaveControl($(sel), () => dlsSave({ [k]: dlsRead($(sel), kind) }));
  const schedule = () => ({ enabled: $("#dls-sch-on").checked, from: $("#dls-sch-from").value, to: $("#dls-sch-to").value,
    days: [...pane.querySelectorAll("#dls-sch-days [data-day]:checked")].map((c) => +c.dataset.day) });
  for (const el of pane.querySelectorAll("#dls-sch-on, #dls-sch-from, #dls-sch-to, #dls-sch-days [data-day]")) {
    autosaveControl(el, () => dlsSave({ alt_schedule: schedule() }));
  }
  const discovery = () => Object.fromEntries([...pane.querySelectorAll("[data-disc]")].map((c) => [c.dataset.disc, c.checked]));
  for (const el of pane.querySelectorAll("[data-disc]")) autosaveControl(el, () => dlsSave({ discovery: discovery() }));
  for (const box of pane.querySelectorAll("#dls-debrid [data-svc]")) {
    const svc = box.dataset.svc, key = $("[data-deb=key]", box), state = $("[data-deb=state]", box);
    const deb = (o) => dlsSave({ debrid: { [svc]: o } });
    let pending = null; // «Verifica» aspetta la chiave appena incollata
    autosaveControl($("[data-deb=on]", box), (on) => deb({ enabled: on }));
    key.addEventListener("change", () => {
      const v = key.value.trim();
      if (!v) return;
      key.value = ""; // la chiave non resta nella pagina
      pending = deb({ key: v }).then(() => toast("Chiave salvata"), (e) => { key.value = v; toast(e.message, true); });
    });
    $("[data-deb=del]", box).onclick = async () => {
      try { await deb({ key: "" }); } catch (e) { return toast(e.message, true); }
      state.textContent = "";
      toast("Chiave rimossa");
    };
    $("[data-deb=test]", box).onclick = async (e) => {
      const b = e.currentTarget;
      b.disabled = true;
      state.textContent = "Verifica…";
      try {
        await pending;
        state.textContent = DLU.debridState(await api(`/api/downloads/debrid/${svc}/test`, { body: {} }));
      } catch (err) { state.textContent = `✗ ${err.message}`; }
      finally { b.disabled = false; }
    };
  }
  $("#dls-dir-pick").onclick = async () => {
    const p = await pickPath("folder");
    if (!p) return;
    dir.focus(); // autosaveControl ricorda il valore precedente al focus (per «Annulla»)
    dir.value = p;
    dir.dispatchEvent(new Event("change"));
  };
}

/* ---- avvio: stato iniziale e aggiornamenti dal server */
/** stream SSE; se cade si interroga il server ogni 2 s e si riprova lo stream con attese crescenti (DLU.backoff).
 *  Alla riconnessione si smette di interrogare e si rilegge tutto: nel buco possono essersi perse delle notifiche. */
function dlStream() {
  let fails = 0, poll = null;
  const connect = () => {
    const es = new EventSource("/api/downloads/events");
    es.addEventListener("downloads", (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.settings) DL.settings = d.settings; // es. modalità lenta accesa dalla programmazione
        dlApply(d.tasks || []);
      } catch { /* fotogramma non valido */ }
    });
    es.onopen = () => {
      if (poll) { clearInterval(poll); poll = null; dlLoad().catch(() => {}); }
      fails = 0;
    };
    es.onerror = () => {
      es.close();
      poll ??= setInterval(() => { if (document.visibilityState === "visible") dlLoad().catch(() => {}); }, 2000);
      setTimeout(connect, DLU.backoff(fails++));
    };
  };
  connect();
}

if (typeof window !== "undefined") {
  $("#dl-add-go").onclick = dlSubmit;
  dlLogInit();
  $("#dl-links").addEventListener("input", dlMuSync);
  $("#dl-mu-go").onclick = dlMuList;
  $("#dl-dest-pick").onclick = async () => { const p = await pickPath("folder"); if (p) $("#dl-dest").value = p; };
  dlLoad().catch(() => { /* server senza coda download: il contatore resta vuoto */ });
  if (window.EventSource) dlStream();
  else setInterval(() => { if (document.visibilityState === "visible") dlLoad().catch(() => {}); }, 2000);
}
