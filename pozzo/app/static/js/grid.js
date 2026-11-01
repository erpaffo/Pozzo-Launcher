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
  $("#empty").hidden = S.items.length > 0;
  $("#empty").innerHTML = S.search ? esc(`Nessun gioco trovato per «${S.search}».`)
    : !$("#loadbar").hidden ? ""
    : !S.games.length ? `<div class="empty-lib"><b>La libreria è vuota.</b><p class="muted">Scegli la cartella delle ROM o importa i giochi degli store.</p>
        <button class="btn primary" onclick="SETUP.open(true).then(() => reload(true))">🧭 Configurazione guidata</button></div>`
    : "Nessun gioco in questa vista.";
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
  el.tabIndex = 0;
  el.setAttribute("role", "button");
  el.setAttribute("aria-label", `Apri ${g.title}, ${platName(g.platform)}`);
  const pn = platName(g.platform);
  const showPlat = S.view.type !== "platform";
  const sub = (showPlat ? [pn, g.year] : [g.year, g.dev]).concat((S.sort === "-size" || S.sort === "size" || S.view.type === "shop") && g.size ? [fmtSize(g.size)] : [])
    .concat(S.discScore ? [scoreText(g, S.discScore)] : [])
    .concat((S.sort === "hltb" || S.sort === "-hltb") && g.hltb != null && S.discScore !== "hltb" ? [`⏱ ${fmtHours(g.hltb)}`] : []).filter(Boolean).join(" · ");
  const badges = (g.grp.favorite ? `<span class="badge fav">★</span>` : "")
    + (g.grp.status ? `<span class="badge st st-${g.grp.status}" title="${esc(STATUS[g.grp.status]?.label || "")}">${STATUS[g.grp.status]?.icon || ""}</span>` : "")
    + (S.oneVersion && g.grp.versions > 1 ? `<span class="badge ver">${g.grp.versions} ${g.store ? "store" : "versioni"}</span>` : "")
    + (g.store ? `<span class="badge plat">${esc(STORE_SHORT[g.store] || g.store.toUpperCase())}</span>`
      : showPlat ? `<span class="badge plat">${esc(SHORT[g.platform] || g.platform.toUpperCase())}</span>` : "")
    + (g.content === "dlc" ? `<span class="badge ext" title="Contenuto aggiuntivo (DLC/add-on): non è un gioco a sé">DLC</span>` : "")
    + (g.players >= 2 ? `<span class="badge ext" title="Multigiocatore locale">👥 ${g.players}</span>` : "")
    + (g.store === "online" ? `<span class="badge inst">🌐 Scarica${g.size ? " · " + fmtSize(g.size) : ""}</span>`
      : g.store && !g.installed ? `<span class="badge inst">⬇ Installa</span>` : "")
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
