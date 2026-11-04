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
  /** larghezza di una colonna dopo aver trascinato il suo bordo: mai sotto il minimo leggibile */
  const colW = (w, dx, min = 56) => Math.round(Math.max(w + dx, min));
  // le chiavi coincidono con lo stato dei task («Attivi» = in corso)
  const FILTERS = [["all", "Tutti"], ["running", "Attivi"], ["queued", "In coda"], ["paused", "In pausa"], ["completed", "Completati"], ["error", "Errori"]];
  function filter(tasks, f, q) {
    q = (q || "").trim().toLocaleLowerCase("it");
    return (tasks || []).filter((t) => (!f || f === "all" || t.status === f)
      && (!q || `${t.name || ""} ${t.source || ""}`.toLocaleLowerCase("it").includes(q)));
  }
  /** host mostrato nella tabella: «torrent» per magnet e .torrent, altrimenti il dominio del link */
  const host = (t) => (t.type === "torrent" ? "torrent" : urlHost(t.source) || "—");
  const SORT_VAL = { name: (t) => (t.name || t.source || "").toLocaleLowerCase("it"), host: (t) => host(t), size: (t) => t.size || 0,
    progress: (t) => t.progress || 0, speed: (t) => t.speed || 0, eta: (t) => (t.eta == null || t.status !== "running" ? Infinity : t.eta),
    status: (t) => status(t.status), priority: (t) => t.priority || 0 };
  /** ordina per colonna ({key, dir}); senza ordine resta quello di coda. Stabile: a parità vale l'ordine di coda. */
  function sortBy(list, s) {
    const f = s && SORT_VAL[s.key], d = s && s.dir === "desc" ? -1 : 1;
    if (!f) return list;
    return list.map((t, i) => [t, i]).sort((a, b) => {
      const x = f(a[0]), y = f(b[0]);
      return (x < y ? -1 : x > y ? 1 : 0) * d || a[1] - b[1];
    }).map((p) => p[0]);
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
  /** spazio libero in parole: «120 GB», «9,5 GB»; «—» se manca */
  function room(n) {
    if (n == null || !isFinite(n) || n < 0) return "—";
    let i = 0;
    while (n >= 1024 && i < UNITS.length - 1) { n /= 1024; i++; }
    return (n < 10 && i > 0 ? n.toFixed(1) : n.toFixed(0)).replace(".", ",") + " " + UNITS[i];
  }
  /** previsione di spazio per disco ({drive, free_now, after_queue, after_extract, ok, unknown}) in righe; bad = la coda non ci sta */
  const spaceLines = (drives) => (drives || []).map((d) => ({
    text: `${d.drive} libero ora ${room(d.free_now)} · dopo la coda ${room(d.after_queue)} · dopo l'estrazione ${room(d.after_extract)}`
      + (d.unknown > 0 ? ` (${d.unknown} senza dimensione)` : "")
      + (d.ok === false ? " · Spazio insufficiente: alcuni download restano in attesa" : ""),
    bad: d.ok === false,
  }));
  /* ---- gruppi: download della stessa partita (campo group), una testata con i totali */
  const KIND = { base: "Base", update: "Aggiornamento", dlc: "DLC", altro: "Altro" };
  const GROUP_STATUS = [["running", "in corso"], ["queued", "in coda"], ["paused", "in pausa"], ["error", "con errore"], ["completed", "completati"]];
  /** totali di un gruppo: barra solo su chi ha la dimensione nota, velocità sommate, tempo = rimanente / velocità */
  function groupAgg(m) {
    const known = m.filter((t) => t.size > 0);
    const size = known.reduce((a, t) => a + t.size, 0);
    const done = known.reduce((a, t) => a + Math.min(Math.max(t.done || 0, 0), t.size), 0);
    const speed = m.reduce((a, t) => a + (t.status === "running" ? t.speed || 0 : 0), 0);
    // il rimanente è di ciò che può ancora finire (né completato né in errore)
    const left = known.filter((t) => t.status !== "completed" && t.status !== "error").reduce((a, t) => a + Math.max(t.size - (t.done || 0), 0), 0);
    const counts = {};
    for (const t of m) counts[t.status] = (counts[t.status] || 0) + 1;
    // «pronto a giocare» della testata: il più tardi tra i membri che lo prevedono; pronto solo se lo sono tutti
    const readyEta = m.reduce((a, t) => (t.ready_eta != null && (a == null || t.ready_eta > a) ? t.ready_eta : a), null);
    return { size, done, speed, unknown: m.length - known.length, progress: size ? done / size : 0,
      eta: speed > 0 && left > 0 ? left / speed : null, counts, ready: m.length > 0 && m.every((t) => t.ready), ready_eta: readyEta,
      summary: GROUP_STATUS.filter(([k]) => counts[k]).map(([k, l]) => `${counts[k]} ${l}`).join(", "),
      kinds: Object.keys(KIND).filter((k) => m.some((t) => t.kind === k)) };
  }
  /** elenco mostrato → righe {task} per i download singoli, {group} alla posizione del primo membro se i membri visibili sono ≥2 */
  function groupRows(list) {
    const by = new Map();
    for (const t of list || []) if (t.group) by.set(t.group, [...(by.get(t.group) || []), t]);
    const out = [];
    for (const t of list || []) {
      const m = t.group ? by.get(t.group) : null;
      if (!m || m.length < 2) out.push({ task: t, group: null });
      else if (m[0] === t) {
        const title = (m.find((x) => x.group_title) || m[0]).group_title || m[0].name || m[0].source || "";
        out.push({ task: null, group: { key: t.group, title, members: m, ...groupAgg(m) } });
      }
    }
    return out;
  }
  /* ---- pronto a giocare: passi del download (stages) e ora prevista (ready_eta, secondi epoch) */
  const STAGE_LABEL = { download: "Scarico", extract: "Estrazione", library: "Libreria", data: "Dati" };
  const STAGE_STATE = { todo: "da fare", active: "in corso", done: "fatto", error: "errore" };
  /** «Pronto alle 21:40», «Pronto domani alle 21:40», «Pronto gio alle 21:40» più in là, «Pronto a giocare ✓»; "" se non si sa */
  function readyText(t, now = Date.now()) {
    if (!t) return "";
    if (t.ready) return "Pronto a giocare ✓";
    if (t.ready_eta == null || !isFinite(t.ready_eta)) return "";
    const d = new Date(Number(t.ready_eta) * 1000), n = new Date(now);
    const hm = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    const tom = new Date(n.getFullYear(), n.getMonth(), n.getDate() + 1).toDateString();
    const day = d.toDateString() === n.toDateString() ? "" : d.toDateString() === tom ? "domani "
      : d.toLocaleDateString("it-IT", { weekday: "short" }).replace(/\.$/, "") + " ";  // più in là: «Pronto gio alle 21:40»
    return "Pronto " + day + "alle " + hm;
  }
  /** passi visibili come lista (skip nascosti): pallino, nome, «Scarico 42%», «Estrazione ✓», «Libreria ✗»; "" se non ci sono */
  function stepperHtml(t) {
    const steps = ((t && t.stages) || []).filter((s) => s && STAGE_LABEL[s.id] && s.state !== "skip");
    if (!steps.length) return "";
    const items = steps.map((s) => {
      const st = STAGE_STATE[s.state] ? s.state : "todo", label = STAGE_LABEL[s.id];
      const pct = Math.round(Math.min(Math.max(Number(s.pct) || 0, 0), 100));
      // nota (attesa dell'installazione o della scansione) al posto della percentuale, che lì non avanza
      const note = st === "active" && s.note ? String(s.note).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`) : "";
      const now = note ? ` · ${note}` : ` ${pct}%`;
      const text = st === "done" ? `${label} ✓` : st === "error" ? `${label} ✗` : st === "active" ? `${label}${now}` : label;
      const aria = `${label}: ${STAGE_STATE[st]}${st === "active" ? now : ""}`;
      return `<li class="dl-step ${st}" role="listitem" aria-label="${aria}"><i class="dl-dot" aria-hidden="true"></i>${text}</li>`;
    });
    return `<ul class="dl-stepper" role="list" aria-label="Passi fino a giocare">${items.join("")}</ul>`;
  }
  /* ---- velocità: sparkline in SVG (niente librerie), campioni per task, storico per giorno */
  /** path SVG della linea (o dell'area chiusa sul fondo) su scala 0..max; NaN e negativi valgono 0; lista vuota = "" */
  function sparkPath(values, w, h, area = false) {
    const v = (values || []).map((x) => (isFinite(x) && x > 0 ? Number(x) : 0));
    if (!v.length) return "";
    const src = v.length === 1 ? [v[0], v[0]] : v, max = Math.max(...v);
    const y = (x) => (max > 0 ? h - 1 - (x / max) * (h - 2) : h - 1);
    const line = "M" + src.map((x, i) => `${((i * w) / (src.length - 1)).toFixed(1)},${y(x).toFixed(1)}`).join(" L");
    return area ? `${line} L${w},${h} L0,${h} Z` : line;
  }
  /** aggiunge un campione (byte/s) alla lista del task, al più `max` (i più vecchi via); restituisce la lista */
  function pushSample(map, id, v, max) {
    const a = [...(map.get(id) || []), isFinite(v) && v > 0 ? Number(v) : 0].slice(-max);
    map.set(id, a);
    return a;
  }
  /** GB da 1 GB in su, altrimenti MB/KB come bytes(); «—» se manca */
  const fmtGB = (n) => (n != null && isFinite(n) && n >= 1024 ** 3
    ? (n / 1024 ** 3).toFixed(n < 10 * 1024 ** 3 ? 2 : 1).replace(".", ",") + " GB" : bytes(n));
  /** colonne dello storico, una per giorno, alte in proporzione al giorno più pieno: {bars:[{day,bytes,x,y,width,height}], max} */
  function barsLayout(days, w, h) {
    const d = (days || []).map((x) => ({ day: String((x && x.day) ?? ""), bytes: isFinite(x && x.bytes) && x.bytes > 0 ? Number(x.bytes) : 0 }));
    const max = d.reduce((a, x) => Math.max(a, x.bytes), 0), slot = d.length ? w / d.length : 0, bw = slot * 0.7;
    return { max, bars: d.map((x, i) => {
      const bh = max > 0 ? (x.bytes / max) * h : 0;
      return { day: x.day, bytes: x.bytes, x: +(i * slot + (slot - bw) / 2).toFixed(1), y: +(h - bh).toFixed(1), width: +bw.toFixed(1), height: +bh.toFixed(1) };
    }) };
  }
  return { groupRows, groupAgg, KIND, spaceLines, copyable,logView, logMerge, logRel, logKind, logSummary, isMultiup, isMirrorSource, sortMirrors, mirrorView, defaultMirror, muTitle, bytes, speed, eta, status, FILE_PRIO, merge, summary, backoff, PRIO, clampPrio, prio, colW, FILTERS, filter, sortBy, host, select, limit, schedule,
    DEBRID, debridName, debridState, readyText, stepperHtml, sparkPath, pushSample, fmtGB, barsLayout };
})();
if (typeof module !== "undefined") module.exports = DLU;


const DL = { tasks: [], settings: {}, html: new WeakMap(), filter: "all", q: "", sel: new Set(), anchor: null, kbdMenu: 0, open: new Set(), sort: undefined, colW: {}, tab: "gen", panelId: "", panelHtml: "", panelH: 0, spaceAt: 0, spaceT: 0, spark: new Map(), stats: null, statsI: 0, statsBusy: false,plog: { id: "", lines: [], n: 0, loaded: false, busy: false }, log: { id: "", lines: [], n: 0, busy: false, timer: 0 } };
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
  if (S.view.type === "downloads") { dlSample(); dlRenderList(); dlSpace(); dlTrendNow(); }
}

/* ---- velocità per task: ultimi 40 campioni di ogni download in corso, a ogni aggiornamento della lista */
function dlSample() {
  for (const t of DL.tasks) if (t.status === "running") DLU.pushSample(DL.spark, t.id, t.speed, 40);
  for (const id of DL.spark.keys()) {
    const t = dlTask(id);
    if (!t || t.status === "completed" || t.status === "error") DL.spark.delete(id); // finito: niente più campioni
  }
}
/** mini grafico della velocità recente, accanto al valore («—» e nulla se non ci sono campioni) */
function dlSpark(id) {
  const v = DL.spark.get(id) || [], p = DLU.sparkPath(v, 80, 18);
  return p ? `<svg class="dl-spark" width="80" height="18" viewBox="0 0 80 18" role="img" focusable="false" aria-label="Velocità recente, picco ${esc(DLU.speed(Math.max(...v)))}"><path d="${p}" fill="none" stroke="currentColor" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>` : "";
}

/* ---- pannello velocità e storico: la velocità «adesso» viene dalla lista, il grafico e lo storico da /api/downloads/stats */
const DL_STATS_EVERY = 30000;
/** avvia il controllo ogni 30 s (solo mentre la pagina è visibile); una sola volta per pagina */
function dlTrendStart() {
  clearInterval(DL.statsI);
  DL.statsI = setInterval(() => { if (!$("#dl-trend")) return clearInterval(DL.statsI); dlStatsFetch(); }, DL_STATS_EVERY);
  dlStatsFetch();
}
async function dlStatsFetch() {
  if (DL.statsBusy || document.visibilityState !== "visible") return;
  DL.statsBusy = true;
  const el = $("#dl-trend");
  try {
    const s = await api("/api/downloads/stats");
    dlTrendDraw(s);
    if (el) el.hidden = false;
  } catch { if (el && !DL.stats) el.hidden = true; } // senza statistiche resta la lista, senza pannello
  finally { DL.statsBusy = false; dlFit(); }
}
function dlTrendNow() {
  const el = $("#dl-trend-now");
  if (!el) return;
  const { speed } = DLU.summary(DL.tasks);
  el.textContent = `Adesso ${speed > 0 ? DLU.speed(speed) : "fermo"}`;
}
function dlTrendDraw(s) {
  DL.stats = s;
  const chart = $("#dl-trend-chart"), hist = $("#dl-hist"), peakEl = $("#dl-trend-peak");
  if (!chart) return;
  const vals = (s.last_hour || []).map((x) => (x && x.bps) || 0);
  const peak = vals.reduce((a, v) => Math.max(a, isFinite(v) ? v : 0), 0), W = 600, H = 40;
  const line = DLU.sparkPath(vals, W, H), area = DLU.sparkPath(vals, W, H, true);
  chart.innerHTML = line
    ? `<svg class="dl-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${esc(`Velocità ultima ora, picco ${DLU.speed(peak)}`)}"><path class="dl-area" d="${area}"/><path class="dl-line" d="${line}" vector-effect="non-scaling-stroke"/></svg>`
    : `<p class="muted small">Nessuna velocità registrata nell'ultima ora.</p>`;
  peakEl.textContent = `picco ${DLU.speed(peak)}`;
  const days = s.per_day || [], total30 = days.reduce((a, d) => a + (d && d.bytes > 0 ? d.bytes : 0), 0);
  const B = DLU.barsLayout(days, W, 60);
  const aria = `GB al giorno, ultimi 30 giorni: totale ${DLU.fmtGB(total30)}, giorno più pieno ${DLU.fmtGB(B.max)}`;
  const cols = B.bars.map((b) => `<rect x="${b.x}" y="${b.y}" width="${b.width}" height="${b.height}"><title>${esc(b.day)}: ${DLU.fmtGB(b.bytes)}</title></rect>`).join("");
  const rows = (s.per_host || []).map((h) => `<tr><th scope="row">${esc(h.host || "—")}</th><td class="num">${DLU.fmtGB(h.bytes_30d)}</td><td class="num">${DLU.fmtGB(h.bytes_total)}</td></tr>`).join("");
  hist.innerHTML = (B.max > 0
    ? `<p class="muted small">GB al giorno, ultimi 30 giorni</p><svg class="dl-bars-svg" viewBox="0 0 ${W} 60" preserveAspectRatio="none" role="img" aria-label="${esc(aria)}">${cols}</svg>`
    : `<p class="muted small">Nessun download negli ultimi 30 giorni.</p>`)
    + (rows ? `<table class="dl-hosts"><thead><tr><th scope="col">Host</th><th scope="col" class="num">GB ultimi 30 giorni</th><th scope="col" class="num">GB totali</th></tr></thead>`
      + `<tbody>${rows}</tbody><tfoot><tr><th scope="row">Totale</th><td class="num">${DLU.fmtGB(total30)}</td><td class="num">${DLU.fmtGB(s.total_bytes)}</td></tr></tfoot></table>` : "");
}

/** la tabella (altezza fissa in app.css) si accorcia di quanto occupano previsione e grafico sopra di lei */
function dlFit() {
  const wrap = $("#dl-wrap");
  if (!wrap) return;
  const h = ["#dl-space", "#dl-trend"].reduce((a, q) => {
    const el = $(q);
    return a + (el && !el.hidden ? el.offsetHeight + (parseFloat(getComputedStyle(el).marginBottom) || 0) : 0);
  }, 0);
  wrap.style.setProperty("--dl-extra", Math.round(h) + "px");
}

/* ---- previsione dello spazio su disco: sopra la coda, al più ogni 5 s, nascosta se la coda è vuota */
const dlBusy = (t) => t.status === "queued" || t.status === "running" || t.status === "paused";
function dlSpace() {
  const el = $("#dl-space");
  if (!el) return;
  if (!DL.tasks.some(dlBusy)) { if (!el.hidden) { el.hidden = true; dlFit(); } return; }
  if (!DL.spaceT) DL.spaceT = setTimeout(dlSpaceFetch, Math.max(0, DL.spaceAt + 5000 - Date.now()));
}
async function dlSpaceFetch() {
  DL.spaceT = 0;
  DL.spaceAt = Date.now();
  const el = $("#dl-space");
  if (!el) return;
  if (!DL.tasks.some(dlBusy)) { el.hidden = true; return; }
  try {
    const lines = DLU.spaceLines((await api("/api/downloads/space")).drives);
    el.innerHTML = lines.map((l) => `<div class="dl-space-row${l.bad ? " bad" : ""}">${esc(l.text)}</div>`).join("");
    el.hidden = !lines.length;
  } catch { el.hidden = true; } // senza previsione la coda funziona lo stesso
  dlFit();
}

/** ordinamento scelto (colonna e verso) ricordato nel browser; null = ordine di coda */
function dlSortLoad() {
  try { const s = JSON.parse(localStorage.getItem("dlSort") || "null"); return s && s.key ? { key: String(s.key), dir: s.dir === "desc" ? "desc" : "asc" } : null; } catch { return null; }
}
function dlSortSave() {
  try { localStorage.setItem("dlSort", JSON.stringify(DL.sort)); } catch { /* modalità privata: vale solo per questa visita */ }
}
/** larghezze delle colonne scelte trascinando i bordi (px); vuoto = larghezze standard */
function dlColsLoad() {
  try { const w = JSON.parse(localStorage.getItem("dlCols") || "{}"); return w && typeof w === "object" ? w : {}; } catch { return {}; }
}
function dlColsSave() {
  try { localStorage.setItem("dlCols", JSON.stringify(DL.colW)); } catch { /* modalità privata: vale solo per questa visita */ }
}
/** download mostrati, nell'ordine in cui compaiono (la selezione a intervallo usa lo stesso) */
const dlVisible = () => DLU.sortBy(DLU.filter(DL.tasks, DL.filter, DL.q), DL.sort);
/** righe che si vedono davvero, in ordine: i membri di un gruppo chiuso non ci sono (selezione e frecce usano queste) */
const dlShown = () => DLU.groupRows(dlVisible()).flatMap((e) => (e.group ? (DL.open.has(e.group.key) ? e.group.members : []) : [e.task]));

const DL_COLS = [["name", "Nome", ""], ["host", "Host", "hide-s"], ["size", "Dimensione", "num"], ["progress", "Avanzamento", "c-prog"],
  ["speed", "Velocità", "num"], ["eta", "ETA", "num hide-s"], ["status", "Stato", "c-st"], ["priority", "Priorità", "hide-s"]];

/* ---- pagina */
async function renderDownloads(pv) {
  DL.sort ??= dlSortLoad();
  try { DL.panelH = Number(localStorage.getItem("dlPanelH")) || 0; } catch { DL.panelH = 0; }
  DL.panelHtml = ""; // la pagina è nuova: il pannello va ridisegnato
  DL.spark = new Map(); // i campioni ripartono con la pagina
  pv.innerHTML = `<div class="page dl-page">
    <div class="dl-tools" role="toolbar" aria-label="Download">
      <button class="btn primary" id="dl-add" type="button">＋ Aggiungi</button>
      <button class="btn" id="dl-resume-all" type="button" title="Avvia o riprende tutti i download">▶ Avvia tutto</button>
      <button class="btn" id="dl-pause-all" type="button">⏸ Pausa tutto</button>
      <button class="btn" id="dl-clear-done" type="button" title="Toglie dall'elenco i download completati">🧹 Completati</button>
      <button class="btn" id="dl-clear-err" type="button" title="Toglie dall'elenco i download falliti ed elimina i file parziali">🗑 Falliti</button>
      <div class="chips dl-chips" role="group" aria-label="Mostra">${DLU.FILTERS.map(([k, l]) =>
        `<button class="chip" type="button" data-filter="${k}" aria-pressed="${DL.filter === k}">${l}</button>`).join("")}</div>
      <input class="field" type="search" id="dl-q" placeholder="Cerca per nome o link" aria-label="Cerca nei download" value="${esc(DL.q)}">
    </div>
    <div class="dl-space" id="dl-space" hidden></div>
    <section class="dl-trend" id="dl-trend" aria-label="Velocità e storico" hidden>
      <div class="dl-trend-head"><b id="dl-trend-now"></b><span class="muted small" id="dl-trend-peak"></span></div>
      <div id="dl-trend-chart"></div>
      <p class="muted small dl-trend-cap">ultima ora</p>
      <details class="dl-hist" id="dl-hist-box"><summary>Storico download</summary><div id="dl-hist"></div></details>
    </section>
    <div class="dl-wrap" id="dl-wrap"${DL.panelH ? ` style="--dl-panel-h:${DL.panelH}px"` : ""}>
      <div class="dl-scroll">
        <table class="dl-grid"><thead><tr>${DL_COLS.map(([k, l, c]) =>
          `<th class="${c}" data-col="${k}" aria-sort="none"><button class="dl-th" type="button" data-sort="${k}">${l}<span class="dl-arrow" aria-hidden="true"></span></button><span class="dl-rs" role="separator" aria-orientation="vertical" aria-label="Larghezza colonna ${l}" tabindex="0"></span></th>`).join("")}
          <th class="c-act"><span class="sr-only">Azioni</span></th></tr></thead>
          <tbody id="dl-rows"></tbody></table>
        <div id="dl-empty"></div>
      </div>
      <div class="dl-split" id="dl-split" role="separator" aria-orientation="horizontal" aria-label="Altezza del pannello dettagli" tabindex="0"></div>
      <section class="dl-panel" aria-label="Dettagli del download">
        <div class="dl-ptabs" role="tablist">${[["gen", "Generale"], ["files", "File"], ["log", "Registro"]].map(([k, l]) =>
          `<button class="dl-ptab" type="button" role="tab" data-ptab="${k}" aria-selected="${DL.tab === k}">${l}</button>`).join("")}</div>
        <div class="dl-pbody" id="dl-pbody" role="tabpanel" tabindex="0"></div>
      </section>
    </div>
    <div class="dl-status" id="dl-status" role="status">
      <span id="dl-s-down" title="Velocità totale in download"></span><span id="dl-s-up" title="Velocità totale in invio"></span>
      <span id="dl-s-slots" title="Download attivi / massimo contemporanei"></span>
      <button class="dl-lim" id="dl-s-lim" type="button" title="Limite globale di velocità: apri le impostazioni"></button>
      <button class="btn" id="dl-alt" type="button" aria-pressed="false">🐢 Modalità lenta</button>
      <span id="dl-s-game" hidden title="Modalità gioco attiva: i download rallentano mentre giochi">🎮 Modalità gioco</span>
    </div></div>`;
  $("#dl-add", pv).onclick = dlOpenAdd;
  $("#dl-hist-box", pv).addEventListener("toggle", dlFit);
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
  $("#dl-s-lim", pv).onclick = () => { if (typeof openSettings === "function") openSettings("download"); };
  $(".dl-chips", pv).addEventListener("click", (e) => {
    const c = e.target.closest("[data-filter]");
    if (!c) return;
    DL.filter = c.dataset.filter;
    for (const b of c.parentElement.children) b.setAttribute("aria-pressed", b === c);
    dlRenderList();
  });
  $("#dl-q", pv).addEventListener("input", (e) => { DL.q = e.target.value; dlRenderList(); });
  // maniglione: trascinando (o con ↑/↓) cambia l'altezza del pannello, ricordata nel browser
  const wrap = $("#dl-wrap", pv), split = $("#dl-split", pv);
  const setH = (h, save) => {
    DL.panelH = Math.round(Math.min(Math.max(h, 90), Math.max(140, wrap.clientHeight - 110)));
    wrap.style.setProperty("--dl-panel-h", DL.panelH + "px");
    if (save) try { localStorage.setItem("dlPanelH", String(DL.panelH)); } catch { /* solo per questa visita */ }
  };
  split.addEventListener("pointerdown", (e) => {
    const y0 = e.clientY, h0 = $(".dl-panel", pv).offsetHeight;
    split.setPointerCapture(e.pointerId);
    const move = (ev) => setH(h0 + y0 - ev.clientY, false);
    const up = () => { split.removeEventListener("pointermove", move); split.removeEventListener("lostpointercapture", up); setH(DL.panelH, true); };
    split.addEventListener("pointermove", move);
    split.addEventListener("lostpointercapture", up); // rilascio o trascinamento interrotto
  });
  split.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    setH($(".dl-panel", pv).offsetHeight + (e.key === "ArrowUp" ? 24 : -24), true);
  });
  // bordi delle colonne: trascinando (o con ←/→) la colonna si allarga e le altre si stringono fino al minimo,
  // poi la tabella scorre. Doppio clic sul bordo: tornano le larghezze standard. Tutto ricordato nel browser.
  const COL_MIN = 64;
  const head = $(".dl-grid thead", pv);
  const colThs = () => [...head.querySelectorAll("th[data-col]")].filter((t) => t.getBoundingClientRect().width > 0);
  DL.colW = dlColsLoad();
  for (const [k, w] of Object.entries(DL.colW)) {
    const t = $(`th[data-col="${k}"]`, head);
    if (t && Number(w) > 0) t.style.width = Number(w) + "px";
  }
  // larghezze di partenza del gesto, fissate in px: da qui si calcola tutto, senza accumulare errori
  const colStart = () => {
    const m = new Map();
    for (const t of colThs()) m.set(t, Math.round(t.getBoundingClientRect().width));
    for (const [t, w] of m) { t.style.width = w + "px"; DL.colW[t.dataset.col] = w; }
    dlColsSave();
    return m;
  };
  const setColW = (th, start, w) => {
    const px = DLU.colW(w, 0), d = px - start.get(th);
    th.style.width = px + "px";
    DL.colW[th.dataset.col] = px;
    // lo spazio che si libera o serve lo prende l'avanzamento (la colonna elastica); se è lei a muoversi, il nome
    const flex = $(`th[data-col="${th.dataset.col === "progress" ? "name" : "progress"}"]`, head);
    if (d > 0) { // lo spazio lo danno le altre colonne; se hanno già il minimo, la tabella si allarga e scorre
      const others = [...start.keys()].filter((t) => t !== th);
      const room = others.reduce((a, t) => a + Math.max(0, start.get(t) - COL_MIN), 0), take = Math.min(d, room);
      for (const t of others) {
        const nw = DLU.colW(start.get(t), -(room ? take * Math.max(0, start.get(t) - COL_MIN) / room : 0), COL_MIN);
        t.style.width = nw + "px";
        DL.colW[t.dataset.col] = nw;
      }
    } else if (d < 0 && flex && flex !== th && start.has(flex)) {
      const nw = DLU.colW(start.get(flex), -d);
      flex.style.width = nw + "px";
      DL.colW[flex.dataset.col] = nw;
    }
    dlColsSave();
  };
  head.addEventListener("pointerdown", (e) => {
    const h = e.target.closest(".dl-rs");
    if (!h) return;
    e.preventDefault();
    const th = h.parentElement, start = colStart(), x0 = e.clientX, w0 = start.get(th);
    h.setPointerCapture(e.pointerId);
    const move = (ev) => setColW(th, start, w0 + ev.clientX - x0);
    const up = () => { h.removeEventListener("pointermove", move); h.removeEventListener("lostpointercapture", up); };
    h.addEventListener("pointermove", move);
    h.addEventListener("lostpointercapture", up); // rilascio o trascinamento interrotto
  });
  head.addEventListener("keydown", (e) => {
    const h = e.target.closest(".dl-rs");
    if (!h || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    const th = h.parentElement;
    // la larghezza chiesta, non quella disegnata: la tabella riempie lo spazio e le altre colonne si allargano
    const w = parseFloat(th.style.width) || th.getBoundingClientRect().width;
    setColW(th, colStart(), w + (e.key === "ArrowRight" ? 16 : -16));
  });
  head.addEventListener("dblclick", (e) => {
    if (!e.target.closest(".dl-rs")) return;
    DL.colW = {};
    dlColsSave();
    for (const th of head.querySelectorAll("th[data-col]")) th.style.width = "";
  });
  const page = $(".dl-page", pv);
  const rowId = (el) => el.closest(".dl-row")?.dataset.id || DL.panelId; // i controlli del pannello valgono per il task mostrato
  page.addEventListener("click", (e) => {
    if (e.target.id === "dl-empty-add") return dlOpenAdd();
    const h = e.target.closest("[data-sort]");
    if (h) { // asc -> desc -> ordine di coda
      const k = h.dataset.sort, s = DL.sort;
      DL.sort = !s || s.key !== k ? { key: k, dir: "asc" } : s.dir === "asc" ? { key: k, dir: "desc" } : null;
      dlSortSave();
      return dlRenderList();
    }
    const tb = e.target.closest("[data-ptab]");
    if (tb) { DL.tab = tb.dataset.ptab; return dlRenderPanel(); }
    const g = e.target.closest("[data-gact]");
    if (g) return dlGroupAct(g.closest("[data-gid]").dataset.gid, g.dataset.gact);
    const b = e.target.closest("button[data-act]");
    if (b) return dlAct(rowId(b), b.dataset.act, b);
    const row = e.target.closest(".dl-row");
    if (row && !e.target.closest("a, button, input, select, label")) dlSelect(row.dataset.id, e.shiftKey ? "range" : e.ctrlKey || e.metaKey ? "toggle" : "one");
  });
  page.addEventListener("dblclick", (e) => {
    const row = e.target.closest(".dl-row");
    if (row && !e.target.closest("a, button, input, select, label")) dlLog(row.dataset.id);
  });
  page.addEventListener("mousedown", (e) => { if (e.shiftKey && e.target.closest(".dl-row")) e.preventDefault(); }); // niente testo evidenziato con Maiusc+clic
  page.addEventListener("change", (e) => {
    const c = e.target.closest("[data-act]");
    if (c) dlAct(rowId(c), c.dataset.act, c);
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
    if (row && (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10"))) {
      e.preventDefault();
      DL.kbdMenu = Date.now();
      const r = e.target.getBoundingClientRect();
      return dlMenu(row.dataset.id, { x: r.left, y: r.bottom });
    }
    // ↑/↓ cambiano selezione, Canc annulla, Spazio pausa/riprendi: solo nella tabella e mai dentro i campi
    if (!e.target.closest(".dl-scroll") || e.target.closest("input, select, textarea") || e.altKey || e.ctrlKey || e.metaKey) return;
    const ids = dlShown().map((t) => t.id), cur = DL.sel.has(DL.anchor) ? DL.anchor : [...DL.sel][0];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!ids.length) return;
      e.preventDefault();
      const down = e.key === "ArrowDown", i = ids.indexOf(cur);
      const n = ids[Math.min(Math.max((i < 0 ? (down ? -1 : ids.length) : i) + (down ? 1 : -1), 0), ids.length - 1)];
      dlSelect(n, "one");
      $(`#dl-rows .dl-row[data-id="${CSS.escape(n)}"]`)?.focus();
      return;
    }
    const tasks = DL.tasks.filter((t) => DL.sel.has(t.id));
    if (e.key === "Delete" && tasks.length) { e.preventDefault(); dlCancel(tasks); }
    else if (e.key === " " && tasks.length && !e.target.closest("button, a")) {
      e.preventDefault();
      const live = (x) => x.status === "running" || x.status === "queued";
      const run = tasks.filter(live).map((x) => x.id), stop = tasks.filter((x) => x.status === "paused" || x.status === "error").map((x) => x.id);
      (run.length ? dlEach(run, "pause") : dlEach(stop, "resume")).catch((err) => toast(err.message, true));
    }
  });
  dlTrendStart();
  try { await dlLoad(); } catch (e) { $("#dl-empty", pv).innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
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

/** barra di stato: i nodi sono fissi, cambia solo il testo (il fuoco non si perde) */
function dlStatus() {
  const { speed, up } = DLU.summary(DL.tasks), s = DL.settings || {};
  const running = DL.tasks.filter((t) => t.status === "running" && !(t.options || {}).seeding).length;
  const set = (id, txt) => { const el = $(id); if (el && el.textContent !== txt) el.textContent = txt; };
  const pre = s.alt_active ? "alt_" : "", d = s[pre + "limit_down"] || 0, u = s[pre + "limit_up"] || 0;
  set("#dl-s-down", "↓ " + (speed > 0 ? DLU.speed(speed) : "0 B/s"));
  set("#dl-s-up", "↑ " + (up > 0 ? DLU.speed(up) : "0 B/s"));
  set("#dl-s-slots", s.max_active ? `${running}/${s.max_active} attivi` : `${running} attivi`);
  set("#dl-s-lim", d || u ? `Limite ${d ? "↓ " + d + " KB/s" : ""}${d && u ? " " : ""}${u ? "↑ " + u + " KB/s" : ""}` : "Nessun limite");
  const g = $("#dl-s-game");
  if (g) g.hidden = !s.game_active;
}

/** stepper «pronto a giocare» e testo dell'ora sotto il nome (riga o testata di gruppo); "" se non ci sono */
function dlReadyHtml(t) {
  const txt = DLU.readyText(t);
  return DLU.stepperHtml(t) + (txt ? `<span class="dl-ready${t.ready ? " ok" : ""}">${txt}</span>` : "");
}

/** una riga della tabella; ▸ (solo torrent) apre la scheda File del pannello */
function dlRow(t, member = false) {
  const o = t.options || {}, tor = t.type === "torrent", name = t.name || t.source || "";
  const pct = Math.round(Math.min(Math.max(t.progress || 0, 0), 1) * 100), p = DLU.clampPrio(t.priority);
  const btn = (act, ico, label, extra = "") => `<button class="icon-btn" type="button" data-act="${act}" title="${label}" aria-label="${label}: ${esc(name)}"${extra}>${ico}</button>`;
  const live = t.status === "running" || t.status === "queued";
  const install = !!o.setup && t.status === "completed"; // repack estratto: il setup si avvia da qui
  const st = o.seeding ? "In condivisione" : DLU.status(t.status);
  const note = t.status === "error" ? t.error || t.phase : t.phase; // errore corto in riga, completo nel title
  return `<tr class="dl-row${member ? " dl-member" : ""}" tabindex="0" data-id="${esc(t.id)}" data-status="${esc(t.status)}"${o.seeding ? ' data-seed="1"' : ""}>
    <td class="c-name"><span class="dl-ico" aria-hidden="true" title="${tor ? "Torrent" : "HTTP"}">${tor ? "🧲" : "🌐"}</span>${tor ? btn("toggle", "▸", "File e dettagli") : ""}<b title="${esc(t.source)}">${esc(name)}</b>${o.start_at ? `<span class="dl-type" title="Avvio pianificato">⏰ ${esc(o.start_at)}</span>` : ""}${dlReadyHtml(t)}</td>
    <td class="hide-s">${esc(DLU.host(t))}</td>
    <td class="num">${t.size ? DLU.bytes(t.size) : "?"}</td>
    <td class="c-prog"><div class="dl-bar" role="progressbar" aria-label="Avanzamento: ${esc(name)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><span class="num">${pct}%</span></td>
    <td class="num">${t.status === "running" ? DLU.speed(t.speed) + dlSpark(t.id) : "—"}</td>
    <td class="num hide-s">${t.status === "running" ? DLU.eta(t.eta) : "—"}</td>
    <td class="c-st"${note ? ` title="${esc(t.status === "error" && t.error ? t.error : t.phase)}"` : ""}><span class="dl-st">${esc(st)}</span>${note ? `<span class="dl-now${t.status === "error" ? " bad" : ""}">${esc(note)}</span>` : ""}</td>
    <td class="hide-s">${p ? `<span class="dl-type${p > 0 ? " hi" : ""}">${p > 0 ? "↑" : "↓"} ${DLU.prio(p)}</span>` : "Normale"}</td>
    <td class="c-act">${install ? `<button class="btn" type="button" data-act="install" title="Avvia il setup del repack: a installazione finita il gioco entra in libreria">📦 Installa</button>` : ""}${live ? btn("pause", "⏸", "Pausa") : t.status !== "completed" ? btn("resume", "▶", "Riprendi") : ""}${btn("menu", "⋯", "Altre azioni", ' aria-haspopup="menu"')}</td>
  </tr>`;
}

/* ---- gruppi: una testata con i totali sopra i membri (righe normali, aperte dal ▸) */
/** testata di un gruppo: stessi campi delle colonne della tabella, con i totali del gruppo */
function dlGroupRow(g, open) {
  const title = esc(g.title), pct = Math.round(Math.min(Math.max(g.progress, 0), 1) * 100);
  const live = g.members.some((x) => x.status === "running" || x.status === "queued");
  const stop = g.members.some((x) => x.status === "paused" || x.status === "error");
  const btn = (act, ico, label) => `<button class="icon-btn" type="button" data-gact="${act}" title="${label}" aria-label="${label}: ${title}">${ico}</button>`;
  const kinds = g.kinds.map((k) => `<span class="dl-kind">${DLU.KIND[k]}</span>`).join("");
  return `<tr class="dl-group" data-gid="${esc(g.key)}">
    <td class="c-name"><button class="icon-btn dl-gtog" type="button" data-gact="toggle" aria-expanded="${open}" title="${open ? "Nascondi" : "Mostra"} i download" aria-label="${open ? "Nascondi" : "Mostra"} i download di ${title}">▸</button>` +
    `<b>${title}</b>${kinds}<span class="muted small dl-gcount">${g.members.length} download</span>${dlReadyHtml(g)}</td>
    <td class="hide-s"></td>
    <td class="num">${g.size ? DLU.bytes(g.size) : "?"}</td>
    <td class="c-prog"><div class="dl-bar" role="progressbar" aria-label="Avanzamento: ${title}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><span class="num">${g.size ? pct + "%" : "—"}</span>${g.unknown ? ` <span class="muted small">+${g.unknown} senza dimensione</span>` : ""}</td>
    <td class="num">${DLU.speed(g.speed)}</td>
    <td class="num hide-s">${DLU.eta(g.eta)}</td>
    <td class="c-st"><span class="dl-st">${esc(g.summary)}</span></td>
    <td class="hide-s"></td>
    <td class="c-act">${live ? btn("pause", "⏸", "Pausa tutti") : ""}${stop ? btn("resume", "▶", "Riprendi tutti") : ""}${btn("cancel", "🗑", "Annulla tutti")}</td>
  </tr>`;
}

/** Pausa/Riprendi/Annulla della testata: le stesse azioni delle righe, applicate ai membri mostrati */
function dlGroupAct(key, act) {
  if (act === "toggle") { DL.open.has(key) ? DL.open.delete(key) : DL.open.add(key); return dlRenderList(); }
  const g = DLU.groupRows(dlVisible()).find((e) => e.group && e.group.key === key)?.group;
  if (!g) return;
  if (act === "cancel") return dlCancel(g.members);
  const ids = g.members.filter((x) => (act === "pause" ? x.status === "running" || x.status === "queued" : x.status === "paused" || x.status === "error")).map((x) => x.id);
  dlEach(ids, act).catch((err) => toast(err.message, true));
}

/** voci della tabella in ordine: un download, o la testata di un gruppo seguita dai membri se è aperta */
function dlItems(list) {
  return DLU.groupRows(list).flatMap((e) => {
    if (!e.group) return [{ key: e.task.id, html: dlRow(e.task) }];
    const g = e.group, open = DL.open.has(g.key);
    return [{ key: "g:" + g.key, html: dlGroupRow(g, open) }, ...(open ? g.members.map((t) => ({ key: t.id, html: dlRow(t, true) })) : [])];
  });
}
/** chiave di un elemento della tabella (per riusarlo al ridisegno) */
const dlRowKey = (el) => (el.dataset.gid != null ? "g:" + el.dataset.gid : el.dataset.id);

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
  dlStatus();
  const list = dlVisible(), empty = $("#dl-empty");
  const items = dlItems(list);
  document.querySelectorAll(".dl-grid th[data-col]").forEach((th) => {
    const on = DL.sort && DL.sort.key === th.dataset.col;
    th.setAttribute("aria-sort", on ? (DL.sort.dir === "desc" ? "descending" : "ascending") : "none");
    th.querySelector(".dl-arrow").textContent = on ? (DL.sort.dir === "desc" ? "▼" : "▲") : "";
  });
  if (!list.length) {
    box.replaceChildren();
    empty.innerHTML = `<div class="dl-empty muted">${!DL.tasks.length
      ? `<div class="dl-empty-ico" aria-hidden="true">⬇</div><p>Nessun download.</p>
         <p class="small">Incolla un link http, un magnet o un file .torrent.</p>
         <button class="btn primary" type="button" id="dl-empty-add">＋ Aggiungi un download</button>`
      : "Nessun download corrisponde al filtro o alla ricerca."}</div>`;
    return dlMarkSel();
  }
  if (empty.firstChild) empty.replaceChildren();
  const act = document.activeElement, focusRow = box.contains(act) ? act.closest(".dl-row, .dl-group") : null;
  const old = new Map([...box.children].map((el) => [dlRowKey(el), el]));
  // il pulsante con il fuoco si ritrova per il suo attributo (data-act delle righe, data-gact delle testate)
  const sel = (x) => (x.dataset.act ? `[data-act="${x.dataset.act}"]` : x.dataset.gact ? `[data-gact="${x.dataset.gact}"]` : null);
  let refocus = null;
  items.forEach(({ key, html }, i) => {
    let el = old.get(key);
    old.delete(key);
    if (!el || DL.html.get(el) !== html) {
      const tpl = document.createElement("template");
      tpl.innerHTML = `<table><tbody>${html}</tbody></table>`; // un <tr> da solo non si legge fuori da una tabella
      const nu = tpl.content.querySelector("tr");
      DL.html.set(nu, html);
      if (el) {
        if (el === focusRow) refocus = [nu, act === el ? "" : sel(act)];
        el.replaceWith(nu);
      }
      el = nu;
    }
    if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null);
  });
  old.forEach((el) => el.remove());
  if (refocus) (refocus[1] === "" ? refocus[0] : refocus[1] && refocus[0].querySelector(refocus[1]))?.focus({ preventScroll: true });
  dlMarkSel();
}

/* ---- selezione multipla: la classe si mette a parte, così la riga non va ridisegnata */
function dlSelect(id, mode) {
  ({ sel: DL.sel, anchor: DL.anchor } = DLU.select(DL.sel, dlShown().map((t) => t.id), DL.anchor, id, mode));
  dlMarkSel();
}

function dlMarkSel() {
  document.querySelectorAll("#dl-rows .dl-row").forEach((el) => el.classList.toggle("sel", DL.sel.has(el.dataset.id)));
  dlRenderPanel();
}

/* ---- pannello dettagli: il task selezionato (l'ultimo cliccato); si ridisegna solo se l'HTML cambia */
function dlPanelTask() {
  return dlTask(DL.sel.has(DL.anchor) ? DL.anchor : [...DL.sel].pop());
}

function dlPanelGeneral(t) {
  const o = t.options || {}, tor = t.type === "torrent";
  const when = (s) => (s ? new Date(s * 1000).toLocaleString("it-IT") : "");
  const kv = [["Nome", t.name], ["Sorgente", t.source], ["Cartella", t.save_path],
    ["Stato", `${o.seeding ? "In condivisione" : DLU.status(t.status)}${t.phase ? " · " + t.phase : ""}`],
    ["Dimensione", `${DLU.bytes(t.done)} di ${t.size ? DLU.bytes(t.size) : "?"}`],
    ["Via", o.resolved_by ? DLU.debridName(o.resolved_by) : ""], ["Pianificazione", o.start_at ? "Avvio alle " + o.start_at : ""],
    ["Limite", DLU.limit(o.limit)], ["Priorità", DLU.prio(t.priority)],
    ["Peer", tor && o.peers != null ? `${o.peers} peer, ${o.seeds ?? 0} seed` : ""], ["Invio", tor && o.upload_rate ? DLU.speed(o.upload_rate) : ""],
    ["Rapporto", tor && o.ratio != null ? Number(o.ratio).toFixed(2).replace(".", ",") : ""],
    ["Creato", when(t.created)], ["Finito", when(t.finished)], ["Errore", t.status === "error" ? t.error : ""]];
  return `<dl class="dl-kv">${kv.filter(([, v]) => v).map(([k, v]) => `<dt>${k}</dt><dd${k === "Errore" ? ' class="bad"' : ""}>${esc(String(v))}</dd>`).join("")}</dl>`;
}

/** scheda Registro: stesse righe del modale (dlLogRow), ma lette per il task mostrato e accodate a ogni aggiornamento */
function dlPanelLog(t) {
  const L = DL.plog;
  if (L.id !== t.id) Object.assign(L, { id: t.id, lines: [], n: 0, loaded: false });
  if (!L.busy && (dlLogLive(t) || t.log_n !== L.n || !L.loaded)) dlPanelLogFetch(t.id);
  const t0 = (L.lines[0] || {}).t;
  return L.lines.length ? `<div class="dl-logbox" role="log" aria-label="Registro del download">${L.lines.map((l) => dlLogRow(l, t0)).join("")}</div>`
    : `<p class="muted small">${L.loaded ? "Nessuna riga nel registro." : "Carico il registro…"}</p>`;
}

async function dlPanelLogFetch(id) {
  const L = DL.plog;
  L.busy = true;
  try {
    const r = await api(`${dlUrl(id)}log?after=${L.n}`);
    if (L.id !== id) return;
    const st = DLU.logMerge(L, r), first = !L.loaded;
    Object.assign(L, { lines: st.lines, n: st.n, loaded: true });
    if (first || st.added.length || st.fresh) dlPanelDraw();
  } catch { /* si riprova al prossimo aggiornamento */ }
  finally { L.busy = false; }
}

function dlRenderPanel() {
  const t = dlPanelTask();
  if (!$("#dl-pbody")) return;
  DL.panelId = t ? t.id : "";
  if (DL.tab === "files" && (!t || t.type !== "torrent")) DL.tab = "gen";
  document.querySelectorAll(".dl-ptab").forEach((b) => {
    b.setAttribute("aria-selected", b.dataset.ptab === DL.tab);
    if (b.dataset.ptab === "files") b.hidden = !t || t.type !== "torrent";
  });
  dlPanelDraw();
}

function dlPanelDraw() {
  const t = dlPanelTask(), body = $("#dl-pbody");
  if (!body) return;
  const id = t ? t.id : "", same = body.dataset.id === id && body.dataset.tab === DL.tab;
  const html = !t ? `<p class="muted small">Seleziona un download per vedere i dettagli.</p>`
    : DL.tab === "files" ? dlTorrentBox(t) : DL.tab === "log" ? dlPanelLog(t) : dlPanelGeneral(t);
  if (same && html === DL.panelHtml) return;
  const act = document.activeElement;
  if (same && body.contains(act) && act.tagName === "SELECT") return; // tendina aperta: si aggiorna al giro dopo
  const top = body.scrollTop, bottom = body.scrollHeight - top - body.clientHeight < 24;
  const re = body.contains(act) && act.dataset.act ? `[data-act="${act.dataset.act}"]${act.dataset.file != null ? `[data-file="${act.dataset.file}"]` : ""}` : "";
  body.innerHTML = html;
  DL.panelHtml = html;
  Object.assign(body.dataset, { id, tab: DL.tab });
  body.scrollTop = !same ? 0 : DL.tab === "log" && bottom ? body.scrollHeight : top;
  if (re) body.querySelector(re)?.focus({ preventScroll: true });
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

/* ---- «Avvia alle»: il download resta in coda e parte da solo (la pianificazione sopravvive a un riavvio) */
async function dlSchedule(id, at = null) {
  const t = dlTask(id);
  if (!t) return;
  let when = at;
  if (when == null) {
    when = prompt("A che ora deve partire? (HH:MM, per esempio 23:30)", (t.options || {}).start_at || "23:00");
    if (when == null) return; // finestra chiusa: niente da fare
    when = when.trim();
    if (!when) return;
  }
  try {
    await api(dlUrl(id) + "schedule", { body: { start_at: when } });
  } catch (e) { return toast(e.message, true); }
  const options = { ...(t.options || {}) };
  if (when) options.start_at = when; else delete options.start_at;
  dlApply([{ id, options }]);
  toast(when ? `Avvio alle ${when}` : "Pianificazione annullata");
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
    + (many ? "" : (t.options || {}).start_at
      ? it("⏰ Annulla pianificazione", () => dlSchedule(id, ""))
      : it("⏰ Avvia alle…", () => dlSchedule(id)))
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
  if (act === "toggle") { dlSelect(id, "one"); DL.tab = "files"; return dlRenderPanel(); }
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

function dlLogRow(l, t0 = (DL.log.lines[0] || l).t) {
  const v = DLU.logView(l), k = DLU.logKind(l.msg);
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
  box.insertAdjacentHTML("beforeend", (st.fresh ? st.lines : st.added).map((l) => dlLogRow(l)).join(""));
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
    (opener && opener.isConnected ? opener : $(`#dl-rows .dl-row[data-id="${CSS.escape(id)}"]`))?.focus();
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

/* «Avvia alle» nel dialog di aggiunta: il campo non sta in index.html, si crea qui una volta sola */
function dlAddStartField() {
  const dlg = $("#dl-add-dlg");
  if (!dlg || $("#dl-start", dlg)) return;
  const html = `<label class="lbl-field">Avvia alle (facoltativo)
    <input class="field" id="dl-start" type="time">
    <span class="muted small">Resta in coda e parte da solo a quest'ora.</span></label>`;
  const end = $(".dlg-body > .row.end", dlg);
  if (end) end.insertAdjacentHTML("beforebegin", html);
  else $(".dlg-body", dlg)?.insertAdjacentHTML("beforeend", html);
}

function dlOpenAdd() {
  dlMuDone.clear();
  $("#dl-mu-list").replaceChildren();
  $("#dl-mu-go").hidden = true;
  $("#dl-links").value = "";
  $("#dl-file").value = "";
  $("#dl-dest").value = DL.settings.dir || "";
  dlAddStartField();
  $("#dl-start").value = "";
  $("#dl-add-dlg").showModal();
  $("#dl-links").focus();
}

async function dlSubmit() {
  // le righe espanse in provider sono sostituite dai provider spuntati (nessuno spuntato: la riga non parte)
  const picked = [...$("#dl-mu-list").querySelectorAll("input:checked")];
  const links = $("#dl-links").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    .flatMap((l) => (dlMuDone.has(l) ? picked.filter((i) => i.closest("fieldset").dataset.src === l).map((i) => i.value) : [l]));
  const file = $("#dl-file").files[0], save_path = $("#dl-dest").value.trim();
  const start_at = ($("#dl-start")?.value || "").trim(); // facoltativo: il download parte da solo a quest'ora
  if (!links.length && !file) return toast("Incolla almeno un link o scegli un file .torrent", true);
  const go = $("#dl-add-go");
  go.disabled = true;
  const added = [];
  try {
    if (links.length) {
      added.push(...((await api("/api/downloads", { body: { links, save_path, start_at } })).tasks || []));
      $("#dl-links").value = ""; // se poi fallisce il .torrent, i link non si rimandano due volte
    }
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      if (save_path) fd.append("save_path", save_path);
      if (start_at) fd.append("start_at", start_at);
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
  ["#dls-game-mode", "game_mode", "str"], ["#dls-game-limit", "game_limit_kbps", "int"],
  ["#dls-game-http", "game_pause_http", "bool"],
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
