"use strict";
/* Pozzo Launcher - frontend: griglia virtualizzata e aggiornamento della libreria. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ griglia virtualizzata */
const scroller = $("#grid-scroll"), layer = $("#grid-layer"), sizer = $("#grid-sizer");

function layout() {
  const W = scroller.clientWidth - S.pad * 2;
  S.cols = Math.max(1, Math.floor((W + S.gap) / (S.zoom + S.gap)));
  S.tw = Math.floor((W - S.gap * (S.cols - 1)) / S.cols);
  S.th = Math.round(S.tw * 4 / 3) + 46;
  layer.style.setProperty("--tile", S.tw + "px");
  const rows = [];
  let y = 16;
  for (const sec of sections(S.items)) {
    if (sec.label !== null) { rows.push({ type: "h", y, h: 44, label: sec.label, count: sec.items.length }); y += 56; }
    for (let i = 0; i < sec.items.length; i += S.cols) {
      rows.push({ type: "t", y, h: S.th, items: sec.items.slice(i, i + S.cols) });
      y += S.th + S.gap;
    }
  }
  S.rows = rows;
  S.total = y + 60;
  sizer.style.height = S.total + "px";
  $("#empty").hidden = S.items.length > 0 || skeletonWanted();
  $("#empty").innerHTML = S.search ? esc(t("h.grid.noSearch", {q: S.search}))
    : !$("#loadbar").hidden ? ""
    : !S.games.length ? `<div class="empty-lib"><b>${t("h.grid.emptyLib")}</b><p class="muted">${t("h.grid.emptyHint")}</p>
        <button class="btn primary" onclick="SETUP.open(true).then(() => reload(true))">🧭 ${t("h.grid.wizard")}</button></div>`
    : t("h.grid.noView");
  skeletonSync();
}

/* Segnaposto mentre la libreria carica e non c'e' ancora nulla da mostrare (GSSkeleton in motion-settings.js). */
function skeletonWanted() {
  return !!window.GSSkeleton && !!$("#grid-scroll") && !$("#loadbar").hidden && !S.items.length;
}

function skeletonSync() {
  const box = $("#grid-scroll"), want = skeletonWanted(), has = !!box?.querySelector("[data-gs-skel]");
  if (want && !has) {
    // quante tessere stanno nel viewport: colonne x righe visibili, tra 12 e 24
    const rows = Math.ceil(scroller.clientHeight / ((S.th || 260) + S.gap));
    window.GSSkeleton.show(box, Math.min(24, Math.max(12, (S.cols || 1) * rows)));
  } else if (!want && has) window.GSSkeleton.hide(box);
}

function firstRow(top) {
  let lo = 0, hi = S.rows.length - 1, ans = S.rows.length;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (S.rows[mid].y + S.rows[mid].h >= top) { ans = mid; hi = mid - 1; } else lo = mid + 1;
  }
  return ans;
}

let raf = 0;
function scheduleRender() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); }); }

function render() {
  const top = scroller.scrollTop, h = scroller.clientHeight, buf = h * 0.8;
  const keep = new Set();
  for (let i = firstRow(top - buf); i < S.rows.length && S.rows[i].y < top + h + buf; i++) {
    const row = S.rows[i];
    if (row.type === "h") {
      const k = "h:" + row.y + ":" + row.label;
      keep.add(k);
      let el = S.nodes.get(k);
      if (!el) {
        el = document.createElement("div");
        el.className = "grid-header";
        el.innerHTML = `${esc(row.label)}<span>${row.count}</span>`;
        layer.appendChild(el); S.nodes.set(k, el);
      }
      el.style.transform = `translateY(${row.y}px)`;
      continue;
    }
    row.items.forEach((g, j) => {
      const k = g.id;
      keep.add(k);
      let el = S.nodes.get(k);
      if (!el) { el = tileEl(g); layer.appendChild(el); S.nodes.set(k, el); }
      el.style.transform = `translate(${S.pad + j * (S.tw + S.gap)}px, ${row.y}px)`;
    });
  }
  for (const [k, el] of S.nodes) if (!keep.has(k)) { stopCover(el); el.remove(); S.nodes.delete(k); }
  setRoving();
  // copertine solo a scorrimento fermo: uno scorrimento veloce non deve riempire la coda del browser
  clearTimeout(S.coverT);
  S.coverT = setTimeout(loadCovers, 120);
}

/** Copertina non ancora arrivata: togliere src fa annullare la richiesta al browser (ha al massimo 6 connessioni). */
function stopCover(el) {
  const img = el.querySelector("img[src]:not(.ok)");
  if (img) img.removeAttribute("src");
}

/** Carica le copertine dello schermo piu' una riga sopra e una sotto; annulla quelle uscite da questa fascia. */
function loadCovers() {
  const pad = S.th + S.gap, top = scroller.scrollTop - pad, bottom = scroller.scrollTop + scroller.clientHeight + pad;
  const band = new Set();
  for (let i = firstRow(top); i < S.rows.length && S.rows[i].y < bottom; i++) {
    if (S.rows[i].type !== "h") for (const g of S.rows[i].items) band.add(g.id);
  }
  for (const [k, el] of S.nodes) {
    const img = el.querySelector("img[data-src]");
    if (!img) continue;
    if (!band.has(k)) stopCover(el);
    else if (!img.getAttribute("src")) img.src = img.dataset.src;
  }
}

function platIcon(pid) {
  // immagine della console (cache locale); se manca, il pallino colorato di prima
  const dot = `<span class="plat-dot" style="background:hsl(${hue(pid)} 60% 55%)"></span>`;
  return `<img class="pico" src="/icons/platform/${encodeURIComponent(pid)}" alt="" loading="lazy" onerror="this.outerHTML='${dot.replace(/"/g, "&quot;")}'">`;
}

function hue(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }

function tileEl(g) {
  const el = document.createElement("div");
  el.className = "tile" + (S.selected === g.id ? " selected" : "") + (g.store && !g.installed ? " notinst" : "");
  el.dataset.id = g.id;
  el.tabIndex = -1; // setRoving() (a fine render) lascia tabulabile solo la tessera corrente
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", t("h.grid.openAria", {title: g.title, plat: platName(g.platform)}));
  const pn = platName(g.platform);
  const showPlat = S.view.type !== "platform";
  const sub = (showPlat ? [pn, g.year] : [g.year, g.dev]).concat((S.sort === "-size" || S.sort === "size" || S.view.type === "shop") && g.size ? [fmtSize(g.size)] : [])
    .concat(S.discScore ? [scoreText(g, S.discScore)] : [])
    .concat((S.sort === "hltb" || S.sort === "-hltb") && g.hltb != null && S.discScore !== "hltb" ? [`⏱ ${fmtHours(g.hltb)}`] : []).filter(Boolean).join(" · ");
  const badges = (g.grp.favorite ? `<span class="badge fav">★</span>` : "")
    + (g.grp.status ? `<span class="badge st st-${g.grp.status}" title="${esc(STATUS[g.grp.status]?.label || "")}">${STATUS[g.grp.status]?.icon || ""}</span>` : "")
    + (S.oneVersion && g.grp.versions > 1 ? `<span class="badge ver">${g.grp.versions} ${g.store ? t("h.grid.stores") : t("h.grid.versions")}</span>` : "")
    + (g.store ? `<span class="badge plat">${esc(STORE_SHORT[g.store] || g.store.toUpperCase())}</span>`
      : showPlat ? `<span class="badge plat">${esc(SHORT[g.platform] || g.platform.toUpperCase())}</span>` : "")
    + (g.content === "dlc" ? `<span class="badge ext" title="${t("h.grid.dlcTitle")}">DLC</span>` : "")
    + (g.players >= 2 ? `<span class="badge ext" title="${t("h.grid.localMulti")}">👥 ${g.players}</span>` : "")
    + (g.store === "online" ? `<span class="badge inst">🌐 ${t("h.grid.download")}${g.size ? " · " + fmtSize(g.size) : ""}</span>`
      : g.store && !g.installed ? `<span class="badge inst">⬇ ${t("h.grid.install")}</span>` : "")
    + GS.ui.tileBadges.map((b) => { try { const t = b.render(g); return t ? `<span class="badge ext">${esc(t)}</span>` : ""; } catch { return ""; } }).join("");
  el.innerHTML = `<div class="cover" style="--h:${hue(g.title)}"><div class="ph">${esc(g.title)}<small>${esc(pn)}</small></div>`
    + (g.cover ? `<img alt="" decoding="async">` : "") + badges + `</div>`
    + `<div class="t" title="${esc(g.title)}">${esc(g.title)}</div><div class="s">${esc(sub)}</div>`;
  if (typeof GS.experience?.card === "function") {
    try {
      const card = GS.experience.card(g, el.innerHTML, { experience: GS.experience, state: S });
      if (typeof card === "string") el.innerHTML = card;
      else if (card instanceof Element) el.replaceChildren(card);
    } catch (e) { console.warn(`Scheda esperienza ${GS.experience.id}:`, e); }
  }
  if (g.cover) {
    const img = el.querySelector("img");
    img.onload = () => img.classList.add("ok");
    // q=1: una copertina remota non ancora scaricata non tiene occupato il collegamento (arriva con applyPatches)
    const src = `/img/${g.id}/cover?w=${Math.round(S.tw * (window.devicePixelRatio || 1))}&q=1`;
    let tries = 0;
    // un errore puo' essere passeggero (app che riparte, disco occupato) o dovuto a numeri di gioco vecchi dopo una
    // ricostruzione della libreria: si ricontrolla la libreria e si riprova prima di rinunciare
    img.onerror = () => {
      if (!img.getAttribute("src")) return; // annullata da stopCover: non e' un errore
      if (++tries > 2) return img.remove();
      syncLibrary();
      setTimeout(() => { if (img.isConnected && img.getAttribute("src")) img.src = img.dataset.src = `${src}&r=${tries}`; }, 1200 * tries);
    };
    img.dataset.src = src; // la richiesta parte da loadCovers, solo se la tessera e' sullo schermo
  }
  return el;
}

/* La libreria nella pagina puo' diventare vecchia: una ricostruzione fatta altrove (scansione, CLI, altra finestra)
   cambia i numeri dei giochi, e copertine e dati non si trovano piu'. Si confronta la data di costruzione. */
let syncBusy = false;
async function syncLibrary() {
  if (syncBusy || !S.games.length) return;
  syncBusy = true;
  try {
    const st = await api("/api/status");
    // libreria ricostruita altrove, oppure dati utente cambiati da un altro dispositivo (partita avviata dal telefono...)
    if (!st.building && ((st.built_at && st.built_at !== S.builtAt) || (st.user_rev != null && st.user_rev !== S.userRev))) await reload(true);
    else if (st.meta_rev != null && st.meta_rev !== S.metaRev) await applyPatches();
    if (!st.building) onGameDownloaded(st.downloaded); // dopo il ricaricamento: i numeri dei giochi sono quelli nuovi
    if (["starting", "extracting", "running"].includes(st.running) && $("#running").hidden) pollRunning();
  } catch { /* server non raggiungibile: si riprova al prossimo controllo */ } finally { syncBusy = false; }
}

/* Copertine e dati trovati mentre un lavoro e' in corso (o copertine appena scaricate): solo i giochi cambiati,
   senza ricaricare la libreria. I riquadri visibili si ricreano e compaiono un po' alla volta. */
async function applyPatches() {
  const d = await api(`/api/library/patches?since=${S.metaRev || 0}`);
  if (d.reset) return reload(true);
  S.metaRev = d.rev;
  for (const [id, cover, year, dev, genres] of d.games) {
    const g = S.byId.get(id);
    if (!g) continue;
    Object.assign(g, { cover, year, dev, genres });
    g.q = fold(`${g.title} ${g.dev} ${platName(g.platform)} ${g.platform} ${g.store || ""}`);
    const el = S.nodes.get(id);
    if (el) { el.remove(); S.nodes.delete(id); }
  }
  if (d.games.length) render();
}

/* ------------------------------------------------------------------ liste virtuali delle viste a pagina
   Stesso criterio della griglia, per liste e griglie di schede che stanno in una pagina (Top, desideri, giochi gratis,
   port): nel DOM restano solo le righe della finestra piu' una schermata sopra e sotto, le altre sono spaziatori. */
/**
 * items: i dati; cell(item): HTML di un elemento; opt.cols(): elementi per riga (griglia di schede), opt.gap: px tra
 * le righe, opt.rowClass: classe di ogni riga (es. "free-grid" per le schede). box e' il contenitore che scorre.
 * Ogni chiamata sostituisce la lista precedente di quel box.
 */
function vlist(box, host, items, cell, { cols = () => 1, gap = 0, rowClass = "" } = {}) {
  let c = 0, rows = [], hs = [], a = -1, b = -1;
  const split = () => {
    c = Math.max(1, cols());
    rows = [];
    for (let i = 0; i < items.length; i += c) rows.push(items.slice(i, i + c));
    hs = new Array(rows.length).fill(0);
    a = b = -1;
  };
  // inizio di ogni riga: altezza misurata, o la media di quelle gia' disegnate (le altre righe non sono ancora state viste)
  const starts = () => {
    const known = hs.filter(Boolean), avg = known.length ? known.reduce((s, x) => s + x, 0) / known.length : 120;
    const y = [0];
    for (let r = 0; r < rows.length; r++) y.push(y[r] + (hs[r] || avg) + gap);
    return y;
  };
  const place = (y, from, to) => {
    host.firstElementChild.style.height = y[from] + "px";
    host.lastElementChild.style.height = (y[rows.length] - y[to]) + "px";
  };
  const draw = () => {
    if (!host.isConnected) return;
    if (!rows.length) { host.innerHTML = ""; return; }
    const y = starts(), off = host.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
    const top = box.scrollTop - off, buf = box.clientHeight * 0.5;
    let from = 0, hi = rows.length;
    while (from < hi) { const m = (from + hi) >> 1; if (y[m + 1] > top - buf) hi = m; else from = m + 1; }
    let to = from;
    while (to < rows.length && y[to] < top + box.clientHeight + buf) to++;
    if (from === a && to === b) return;
    a = from; b = to;
    host.innerHTML = `<div></div>` + rows.slice(a, b).map((r) => `<div class="${rowClass}" style="margin-bottom:${gap}px">${r.map(cell).join("")}</div>`).join("") + `<div></div>`;
    place(y, a, b);
    // le altezze vere sostituiscono le stime, e gli spaziatori si rifanno con quelle
    [...host.children].slice(1, -1).forEach((el, k) => { hs[a + k] = el.offsetHeight; });
    place(starts(), a, b);
  };
  host.style.display = "block"; // le righe si impilano come blocchi, anche se il contenitore e' una griglia o un flex
  split();
  box.onscroll = draw;
  box.__vlObserver?.disconnect();
  // ridimensionando la finestra cambia il numero di schede per riga: si rifanno le righe
  // se la vista e' stata sostituita (es. si e' passati allo Store) l'host non c'e' piu': cols() leggerebbe un elemento null
  box.__vlObserver = new ResizeObserver(() => { if (!host.isConnected) return; if (Math.max(1, cols()) !== c) split(); draw(); });
  box.__vlObserver.observe(box);
  draw();
}

function refreshGrid(keepScroll = false) {
  const st = scroller.scrollTop;
  computeItems();
  for (const el of S.nodes.values()) el.remove();
  S.nodes.clear();
  layout();
  scroller.scrollTop = keepScroll ? Math.min(st, S.total) : 0;
  render();
  updateHeader();
}

/* ------------------------------------------------------------------ navigazione da tastiera nella griglia
   Roving tabindex: Tab entra nella griglia sulla tessera corrente ed esce con un solo Tab. */
let kbIdx = 0; // tessera corrente nell'ordine visivo (le righe di sezione non contano)
const NAV_KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"];

/**
 * Indice (nell'ordine visivo) della tessera dopo un tasto di navigazione; null se il tasto non e' di navigazione.
 * cols: tessere per riga; rowsPerPage: righe di una schermata; ctrl: Ctrl+Home/Ctrl+End vanno a inizio/fine di tutto.
 * rowStarts (facoltativo): indice del primo elemento di ogni riga, quando le righe non sono tutte da cols (sezioni).
 */
function nextIndex(key, idx, cols, total, rowsPerPage, ctrl, rowStarts) {
  if (!NAV_KEYS.includes(key) || total <= 0) return null;
  const last = total - 1, cur = Math.min(Math.max(0, idx), last);
  const starts = rowStarts || Array.from({ length: Math.ceil(total / Math.max(1, cols)) }, (_, r) => r * cols);
  let r = 0;
  while (r + 1 < starts.length && starts[r + 1] <= cur) r++;
  const end = (k) => (k + 1 < starts.length ? starts[k + 1] : total) - 1; // ultimo elemento della riga k
  // stessa colonna nella riga t (o l'ultima della riga, se questa e' piu' corta)
  const moveRows = (d) => { const t = Math.min(starts.length - 1, Math.max(0, r + d)); return Math.min(starts[t] + cur - starts[r], end(t)); };
  switch (key) {
    case "ArrowLeft": return Math.max(0, cur - 1);
    case "ArrowRight": return Math.min(last, cur + 1);
    case "ArrowUp": return moveRows(-1);
    case "ArrowDown": return moveRows(1);
    case "PageUp": return moveRows(-Math.max(1, rowsPerPage));
    case "PageDown": return moveRows(Math.max(1, rowsPerPage));
    case "Home": return ctrl ? 0 : starts[r];
    case "End": return ctrl ? last : end(r);
  }
  return null;
}

/** Tessere nell'ordine in cui si vedono, inizio di ogni riga e riga (per la posizione verticale). */
function gridOrder() {
  const list = [], starts = [], trows = [];
  for (const row of S.rows) {
    if (row.type !== "t") continue;
    trows.push(row); starts.push(list.length); list.push(...row.items);
  }
  return { list, starts, trows };
}

/** Solo la tessera corrente e' nel tab order; se non e' disegnata (fuori finestra), la prima disegnata. */
function setRoving() {
  const { list } = gridOrder();
  kbIdx = Math.min(kbIdx, Math.max(0, list.length - 1)); // dopo un filtro la lista puo' essere piu' corta
  let roving = list[kbIdx] && S.nodes.get(list[kbIdx].id);
  for (const el of S.nodes.values()) if (el.dataset.id !== undefined && !roving) roving = el;
  for (const el of S.nodes.values()) if (el.dataset.id !== undefined) el.tabIndex = el === roving ? 0 : -1;
}

/** Sposta il fuoco: scorre se la riga di destinazione non e' visibile, disegna e mette il fuoco sulla tessera. */
function moveFocus(key, ctrl) {
  const { list, starts, trows } = gridOrder();
  if (!list.length) return;
  kbIdx = Math.min(kbIdx, list.length - 1);
  const per = Math.max(1, Math.floor(scroller.clientHeight / ((S.th || 260) + S.gap)));
  const n = nextIndex(key, kbIdx, S.cols, list.length, per, ctrl, starts);
  if (n == null) return;
  kbIdx = n;
  let r = 0;
  while (r + 1 < starts.length && starts[r + 1] <= n) r++;
  const row = trows[r], top = scroller.scrollTop, h = scroller.clientHeight;
  if (row.y < top) scroller.scrollTop = row.y;
  else if (row.y + row.h > top + h) scroller.scrollTop = row.y + row.h - h;
  render(); // sincrono: la tessera di destinazione deve esistere prima di darle il fuoco
  S.nodes.get(list[n].id)?.focus({ preventScroll: true });
}

layer.addEventListener("keydown", (e) => {
  if (!NAV_KEYS.includes(e.key) || e.defaultPrevented || e.altKey || e.metaKey || e.shiftKey) return; // Alt+frecce e Mod+Alt sono scorciatoie
  if (e.ctrlKey && !["Home", "End"].includes(e.key)) return;
  const tile = e.target.closest?.(".tile[data-id]");
  // solo con il fuoco sulla tessera stessa: campi e pulsanti dentro la scheda tengono le loro frecce
  if (!tile || e.target !== tile || S.detail || document.querySelector("dialog[open]") || $("#popover")?.hidden === false) return;
  e.preventDefault();
  moveFocus(e.key, e.ctrlKey);
});
// il clic o il Tab su una tessera la rende quella corrente
layer.addEventListener("focusin", (e) => {
  const tile = e.target.closest?.(".tile[data-id]");
  if (!tile || e.target !== tile) return;
  const i = gridOrder().list.findIndex((g) => String(g.id) === tile.dataset.id);
  if (i >= 0) { kbIdx = i; setRoving(); }
});
