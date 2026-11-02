"use strict";
/* Pozzo Launcher - frontend: scheda del gioco: HLTB, obiettivi, DLC, download, salvataggi. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ dettaglio */
function fmtTime(sec) {
  if (!sec) return "—";
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString("it", { dateStyle: "medium", timeStyle: "short" }) : "—"; }

function presentDetail() {
  const detail = $("#detail");
  const mode = ["panel", "page", "modal"].includes(GS.experience?.detail) ? GS.experience.detail : "panel";
  detail.dataset.presentation = mode;
  detail.classList.add("open");
  detail.setAttribute("aria-hidden", "false");
  detail.setAttribute("aria-labelledby", "detail-title");
  if (mode === "modal") {
    detail.setAttribute("role", "dialog");
    detail.setAttribute("aria-modal", "true");
    document.documentElement.dataset.detailModal = "true";
  } else {
    detail.setAttribute("role", "region");
    detail.removeAttribute("aria-modal");
    delete document.documentElement.dataset.detailModal;
  }
  if (mode !== "panel") $("#detail-close").focus();
  detail.scrollTop = 0;
}

async function openDetail(id) {
  const my = ++S.openSeq; // un fetch lento non deve sovrascrivere il gioco aperto dopo
  if (!S.detail) S.detailFocus = document.activeElement;
  S.selected = id;
  document.querySelectorAll(".tile.selected").forEach((t) => t.classList.remove("selected"));
  S.nodes.get(id)?.classList.add("selected");
  let d;
  try { d = await api(`/api/game/${id}`); } catch (e) { if (my === S.openSeq) { syncLibrary(); toast(e.message, true); } return; }
  if (my !== S.openSeq) return; // nel frattempo e' stato aperto (o chiuso) un altro gioco
  S.detail = d;
  const hero = d.media.hero || d.media.screenshot || d.media.title || d.media.header || d.media.cover;
  $("#detail .hero-bg").style.backgroundImage = hero ? `url("${hero}?w=1280")` : "none";
  const u = d.user;
  const dl = [
    ["Sviluppatore", d.developer], ["Editore", d.publisher], ["Uscita", d.release_date || d.year],
    ["Lingue", GSLanguages.labels(d.title).join(", ")],
    ["Generi", (d.genres || []).join(", ")], ["Giocatori", d.players_local],
    ["Regione", d.region], ["Dimensione", fmtSize(d.size)],
    ["Tempo di gioco", u.playtime ? fmtTime(u.playtime) : ""], ["Ultima partita", u.last_played ? fmtDate(u.last_played) : ""],
    ["Avvii", u.play_count || ""],
    ["Tempo su " + (d.store_name || "store"), d.store_playtime ? fmtTime(d.store_playtime) : ""],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");
  const shots = ["screenshot", "title", "wheel", "fanart", "marquee", "header"].filter((k) => d.media[k]);
  const pc = !!d.store;
  const online = d.store === "online";
  const dlSources = online ? (d.download_sources || []).filter((s) => s && s.url) : [];
  // giochi gia' scaricati che compaiono negli elenchi degli store online: link per riscaricarli
  const pages = !online ? (d.store_pages || []).filter((s) => s && s.url) : [];
  // gli aggiornamenti non sono il gioco: pulsanti a parte (⬆), non nella riga dei download
  const updates = (online ? dlSources : pages).filter((s) => s.update);
  const dlBase = dlSources.filter((s) => !s.update);
  // magnet che scarica solo questo gioco: per-file (nome del file dentro) o di un set Minerva (il server aggiunge so=<file>)
  const minerva = dlSources.some((s) => /minerva-archive\.org\/rom\?id=/i.test(s.url));
  const oneFile = !!d.magnet && (/dn=[^&]*\./.test(d.magnet) || /[?&]so=/.test(d.magnet) || minerva);
  const storePages = pages.filter((s) => !s.update);
  // una fonte sola: pulsante unico; due o piu' (es. NXBrew e Ziperto): un pulsante per sito
  const mainBtn = online
    ? (minerva ? "" : `<button class="btn primary" id="d-download" title="Apre i link del gioco, dell'aggiornamento e dei DLC già pronti per il download, saltando le pagine pubblicitarie">⬇ Scarica</button>`)
      // Minerva: la pagina web offre solo il torrent del set intero, il download vero e' il torrent del singolo file
      + (oneFile ? `<button class="btn${minerva && dlBase.length <= 1 ? " primary" : ""}" id="d-torrent" title="Apre il link nel client torrent: scarica solo questo gioco, non tutto il set">`
        + `${minerva && dlBase.length <= 1 ? "⬇ Scarica" : "🧲 Torrent"} (solo questo gioco)</button>` : "")
    : pc && !d.installed
    ? `<button class="btn primary" id="d-install" ${d.can_install ? "" : "disabled"}>⬇ Installa</button>`
    : `<button class="btn primary" id="d-play" ${d.emulator ? "" : "disabled"}>▶ Gioca</button>`;
  const actions = GS.ui.gameActions.filter((a) => { try { return !a.when || a.when(d); } catch { return false; } });
  $("#detail-body").innerHTML = `
    <div class="d-top">
      <div class="d-cover">${d.media.cover ? `<img src="${d.media.cover}?w=450" alt="">` : ""}</div>
      <div class="d-title"><h2 id="detail-title">${esc(d.title)}</h2><div class="muted">${esc(d.platform_name)}${d.year ? " · " + d.year : ""}</div></div>
    </div>
    <div class="d-actions">
      ${mainBtn}
      <button class="btn ${u.favorite ? "on" : ""}" id="d-fav">${u.favorite ? "★ Preferito" : "☆ Preferito"}</button>
      ${pc && d.page ? `<button class="btn" id="d-page">🛒 Pagina store</button>` : ""}
      ${!pc || (d.installed && d.files.length) ? `<button class="btn" id="d-folder">📁 Cartella</button>` : ""}
      <button class="btn" id="d-hide">${u.hidden ? "Mostra" : "Nascondi"}</button>
      ${d.store === "manual" ? `<button class="btn" id="d-manual-del">🗑 Rimuovi</button>` : ""}
      ${d.store === "ports" ? `<button class="btn" data-port="${esc(d.key.split(":").slice(1).join(":"))}">🕹 Gestisci port</button>` : ""}
      ${(d.ports || []).map((p) => `<button class="btn" data-port="${esc(p.slug)}" title="Versione nativa per PC: ${esc(p.name)}">🕹 Disponibile come port PC</button>`).join("")}
      ${actions.map((a) => `<button class="btn" data-ga="${esc(a.id)}">${esc((a.icon ? a.icon + " " : "") + a.label)}</button>`).join("")}
    </div>
    ${d.missing && d.missing.length ? `<div class="d-missing"><span>Mancano: ${esc(d.missing.join(", "))}</span>`
      + `<button class="btn" id="d-scrape" title="Riprova tutte le fonti per questo gioco (tutte le sue versioni)">⟳ Cerca dati mancanti</button></div>` : ""}
    ${online && d.magnet && !oneFile ? `<div class="d-note">Il link magnet scarica l'intero set:
      nel client torrent seleziona solo il file «${esc(d.file_name || d.title)}».</div>` : ""}
    <div class="d-emu muted">${online ? `${d.page_url ? `<img class="sico" src="/icons/site?url=${encodeURIComponent(d.page_url)}" alt="">` : "🌐"} Disponibile online${d.kind === "repack" ? " · 📦 Repack (gioco compresso: il download è corto, l'installazione lunga)" : d.kind === "direct" ? " · ⬇ Download diretto" : ""}${dlBase.length > 1 ? ` · ${dlBase.length} fonti (${dlBase.map((s) => esc(s.site)).join(", ")})` : ""} · ${esc(d.file_name || "")}`
      : pc ? `${esc(d.store_name)} · ${d.installed ? "installato" : "non installato"}`
      : d.emulator ? "Emulatore: " + esc(d.emulator) + (d.profile ? ` <span class="tag" title="Profilo di avvio di questo gioco">profilo</span>` : "")
      : `Nessun emulatore configurato per ${esc(d.platform_name)} — <a href="#" id="d-emu-cfg">impostazioni</a>`}
      ${!online ? `<a href="#" id="d-profile" title="${pc ? "Script prima e dopo il gioco" : "Emulatore, core, eseguibile, argomenti e script solo per questo gioco"}">⚙ Profilo di avvio</a>
      · <a href="#" id="d-shortcut" title="Collegamento sul desktop che avvia il gioco con Pozzo Launcher">🖥 Collegamento sul desktop</a>` : ""}</div>
    ${storePages.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>🌐 Pagine dello store:</span>
      ${storePages.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="Apri la pagina di download su ${esc(s.site || "questo sito")}">⬇ ${esc((s.site || "sito").replace(/^www\./, ""))}</button>`).join("")}
      </div>` : ""}
    ${updates.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>⬆ Aggiornamenti installabili (${updates.length}):</span>
      ${updates.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="${esc(s.name || "Aggiornamento")}">⬆ ${s.version ? "v" + esc(s.version) : "Update"}${s.size ? " · " + fmtSize(s.size) : ""}</button>`).join("")}
      </div>` : ""}
    ${online && dlBase.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>🌐 Pagina dello store:</span>
      ${dlBase.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="Apri la pagina di download su ${esc(s.site || "questo sito")}">${esc((s.site || "sito").replace(/^www\./, ""))} ↗</button>`).join("")}
      </div>` : ""}
    ${online || storePages.length ? `<div id="d-links"></div>` : ""}
    ${ratingBlock(d)}
    ${online ? "" : `<div class="d-status">${Object.entries(STATUS).map(([k, s]) =>
      `<button class="btn st-btn${u.status === k ? " on st-" + k : ""}" data-status="${k}">${s.icon} ${s.label}</button>`).join("")}</div>`}
    <div class="d-mine"><span class="muted small">Il mio voto</span><span class="d-stars">${[1, 2, 3, 4, 5].map((n) =>
      `<button class="star${n <= (u.my_rating || 0) ? " on" : ""}" data-myrate="${n}" title="${n}/5">★</button>`).join("")}</span></div>
    <textarea class="field d-note" id="d-note" rows="2" placeholder="Note personali (trucchi, a che punto sei, con chi giocarlo…)">${esc(u.note || "")}</textarea>
    ${GS.experience.detail === "modal" && !online ? `<div class="d-hltb" id="d-hltb" title="Tempi medi dei giocatori su HowLongToBeat">${hltbBlock(d.hltb)}</div>` : ""}
    <div class="d-h">Collezioni</div>
    <div class="chips">${d.collections.map((c) => `<span class="chip" data-slug="${esc(c.slug)}">${esc(c.name)}<button class="x" title="Togli da questa collezione">✕</button></span>`).join("")}
      <span class="chip add" id="d-add-coll">＋ Aggiungi</span></div>
    <dl class="d-grid">${dl.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    ${d.description ? `<div class="d-h">Descrizione</div><div class="d-desc">${esc(d.description)}</div>` : ""}
    ${d.shots ? `<div class="d-h">📷 Le tue schermate (${d.shots}) <a href="#" id="d-shots-all" class="muted small">vedi tutte</a></div>
      <div class="my-shots" id="d-myshots"></div>` : ""}
    ${shots.length ? `<div class="d-h">Immagini</div><div class="shots">${shots.map((k) => `<img loading="lazy" src="${d.media[k]}?w=700" alt="${k}">`).join("")}</div>` : ""}
    ${d.versions.length > 1 ? `<div class="d-h">Versioni (${d.versions.length})</div><div class="versions">${d.versions.map((v) =>
      `<div class="version ${v.primary ? "primary" : ""}"><span class="f" title="${esc(v.file)}">${esc(v.file)}</span>`
      + (v.store ? `<span class="muted">${v.installed ? "installato" : "non installato"}</span>` : "")
      + (v.primary ? `<span class="muted">principale</span>` : `<button class="btn" data-pref="${v.id}">Usa questa</button>`)
      + (v.store && !v.installed ? `<button class="btn" data-install="${v.id}">⬇</button>`
        : `<button class="btn" data-play="${v.id}" ${d.emulator ? "" : "disabled"}>▶</button>`) + `</div>`).join("")}</div>` : ""}
    <div id="d-saves"></div>
    <div id="d-ext"></div>
    <div class="d-h">File</div>
    <div class="files">${d.files.map(esc).join("<br>")}${d.crc ? `<br>CRC ${esc(d.crc)}` : ""}
      ${Object.keys(d.sources).length ? `<br>Fonti: ${esc([...new Set(Object.values(d.sources))].join(", "))}` : ""}</div>`;
  presentDetail();
  window.dispatchEvent(new CustomEvent("pozzo:detail-open", { detail: d }));
  renderDetailSections(d);
  if (typeof loadDetailMods === "function") loadDetailMods(d);
  if (d.shots) loadDetailShots(d.id);
  loadSaves(d);
  if (online || storePages.length) loadGameLinks(d);
  if (d.platform === "switch") loadSwitchContents(d);
  if (!pc) loadRA(d);
  if (GS.experience.detail === "modal" && !online && !d.hltb) loadHltb(d);
  GS.emit("gameOpened", d);
}

/* ---- HowLongToBeat: tessere con le ore; null = ancora in cerca, {} = nessun dato */
function hltbBlock(h) {
  if (!h) return `<span class="muted small d-hltb__state">Cerco la durata…</span>`;
  const rows = [["Storia", h.main], ["Storia + extra", h.extra], ["Completista", h.complete]].filter(([, v]) => v);
  if (!rows.length) return `<span class="muted small d-hltb__state">Durata non disponibile</span>`;
  const max = Math.max(...rows.map(([, v]) => v));
  return rows.map(([k, v]) => `<div class="d-hltb__tile"><span>${k}</span><b>${fmtHours(v)}</b>
      <i style="width:${Math.round(v / max * 100)}%"></i></div>`).join("")
    + (h.url ? `<a href="#" data-open="${esc(h.url)}" class="muted small">HowLongToBeat ↗</a>` : "");
}

async function loadHltb(d) {
  let h;
  try { h = await api(`/api/game/${d.id}/hltb`); } catch { h = { error: true }; }
  if (S.detail !== d) return;
  const box = $("#d-hltb");
  if (!box) return;
  if (h.error) return box.remove();
  box.innerHTML = hltbBlock(h);
}

/* ---- RetroAchievements: obiettivi sbloccati (solo se l'account e' collegato e la console e' supportata) */
async function loadRA(d, force = false) {
  let r;
  try { r = await api(`/api/game/${d.id}/ra${force ? "?force=1" : ""}`); } catch { return; }
  if (S.detail !== d || !r.configured || !r.supported) return;
  let box = $("#d-ra");
  if (!box) { $("#d-ext").insertAdjacentHTML("beforebegin", `<div id="d-ra"></div>`); box = $("#d-ra"); }
  if (r.error) { box.innerHTML = `<div class="d-h">🏆 RetroAchievements</div><p class="muted small">${esc(r.error)}</p>`; return; }
  if (!r.found) { box.innerHTML = `<div class="d-h">🏆 RetroAchievements</div><p class="muted small">Gioco non trovato su RetroAchievements (o senza obiettivi).</p>`; return; }
  const g = r.game, done = g.achievements.filter((a) => a.unlocked).length, tot = g.achievements.length || g.num_achievements;
  const pct = tot ? Math.round(done / tot * 100) : 0;
  box.innerHTML = `<div class="d-h">🏆 RetroAchievements <span class="muted small">${done}/${tot} · ${pct}%${g.highest_award_kind ? ` · ${esc(g.highest_award_kind)}` : ""}</span>
      <a href="#" data-open="${esc(r.url)}" class="muted small">apri ↗</a> <a href="#" id="ra-refresh" class="muted small">↻</a></div>
    <div class="ra-bar"><span style="width:${pct}%"></span></div>
    <div class="ra-list">${g.achievements.map((a) => `<div class="ra-a${a.unlocked ? " on" : ""}" title="${esc(a.description)}${a.date_earned ? " · " + esc(a.date_earned) : ""}">
      ${a.badge_url ? `<img loading="lazy" src="${remoteImg(a.unlocked ? a.badge_url : a.badge_locked_url)}" alt="" onerror="this.remove()">` : ""}
      <span><b>${esc(a.title)}</b> <span class="muted small">${a.points} pt${a.unlocked_hardcore ? " · hardcore" : ""}</span><br><span class="muted small">${esc(a.description)}</span></span></div>`).join("")}</div>`;
  box.onclick = (e) => {
    if (e.target.id === "ra-refresh") { e.preventDefault(); loadRA(d, true); }
    const o = e.target.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); }
  };
}

/* ---- Switch: aggiornamento installato e DLC presenti nella cartella del gioco */
async function loadSwitchContents(d) {
  let r;
  try { r = await api(`/api/game/${d.id}/switch`); } catch { return; }
  if (S.detail !== d || (!r.update && !r.dlc)) return;
  const grid = $("#detail .d-grid");
  if (grid) grid.insertAdjacentHTML("afterbegin", `<dt>Contenuti</dt><dd>${[r.update ? `<span class="tag">Aggiornamento ${esc(r.update)}</span>` : "",
    r.dlc ? `<span class="tag">${r.dlc} DLC</span>` : ""].join(" ")}</dd>`);
}

/* ---- link di download elencati nella pagina dello store (nxbrew, ziperto): gioco, update, DLC, provider, parti */
let DL_STATE = null; // ultimi link letti per il gioco aperto: { id, rows, kinds, labels, order }

/** Un link per tipo (gioco, aggiornamento, DLC), dalla stessa fonte: quella che ne ha di più. */
function dlPick(state) {
  const one = {};
  for (const row of state.rows) if (!one[row.kind]) one[row.kind] = row.items;
  const count = {};
  Object.values(one).forEach((items) => items.forEach((x) => { count[x.provider] = (count[x.provider] || 0) + 1; }));
  const best = Object.entries(count).sort((a, b) => b[1] - a[1])[0];
  const prov = best ? best[0] : "";
  return Object.values(one).map((items) => (items.find((x) => x.provider === prov) || items[0]).url);
}

async function loadGameLinks(d, force = false) {
  const box = $("#d-links");
  if (!box) return;
  box.innerHTML = `<p class="muted small">Cerco i link di download…</p>`;
  let r;
  try { r = await api(`/api/game/${d.id}/links${force ? "?refresh=1" : ""}`); }
  catch (e) { box.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; return; }
  if (S.detail !== d) return;
  const links = (r.links || []).filter((x) => x.url);
  if (!links.length) {
    box.innerHTML = `<p class="muted small">Nessun link di download nella pagina dello store${r.error ? ` (${esc(r.error)})` : ""}.</p>`;
    return;
  }
  const KL = r.kind_labels || {}, KO = r.kind_order || [];
  const rows = []; // una riga per tipo di file: le parti e le versioni in altre lingue restano righe separate
  for (const x of links) {
    const key = `${x.kind}|${x.label}`;
    let row = rows.find((y) => y.key === key);
    if (!row) rows.push(row = { key, kind: x.kind, label: x.label, items: [] });
    row.items.push(x);
  }
  rows.sort((a, b) => KO.indexOf(a.kind) - KO.indexOf(b.kind));
  const kinds = [...new Set(rows.map((x) => x.kind))];
  DL_STATE = { id: d.id, rows, kinds, labels: KL, order: KO };
  const btn = (x) => `<button class="btn" data-dl="${esc(x.url)}"
    title="${esc(x.provider)} → ${esc(x.host)}${x.short ? " (la pubblicità viene saltata)" : ""}">${esc(x.provider)}</button>`;
  box.innerHTML = `<div class="d-h">⬇ Link di download <span class="muted small">${esc([...new Set(links.map((x) => x.site))].join(" · "))}</span>
      <a href="#" id="dl-refresh" class="muted small" title="Rileggi la pagina dello store">↻</a></div>
    ${kinds.length > 1 ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn primary" id="dl-all" title="Apre un link per tipo, dalla stessa fonte">⬇ Scarica ${esc(kinds.map((k) => (KL[k] || k).toLowerCase()).join(" + "))}</button>
      <span>niente pagine dello store: si aprono i file, la pubblicità si salta da sola</span></div>` : ""}
    ${rows.map((row) => `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0">
      <span class="muted small" style="min-width:180px">${esc(KL[row.kind] || row.kind)}${row.label ? " · " + esc(row.label) : ""}</span>
      ${row.items.map(btn).join("")}</div>`).join("")}`;
  box.onclick = async (e) => {
    e.preventDefault();
    if (e.target.id === "dl-refresh") return loadGameLinks(d, true);
    const one = e.target.closest("[data-dl]");
    if (one) return downloadLinks(d, [one.dataset.dl], box);
    if (e.target.id === "dl-all") return downloadLinks(d, dlPick(DL_STATE), box);
  };
}

async function downloadLinks(d, urls, box) {
  const btns = box ? [...box.querySelectorAll("button")] : [];
  btns.forEach((b) => { b.disabled = true; });
  box?.insertAdjacentHTML("afterbegin", `<p class="muted small" id="dl-state">Preparo i link: la prima volta la pagina con pubblicità si apre una volta sola…</p>`);
  try {
    const r = await api(`/api/game/${d.id}/download`, { body: { links: urls } });
    const skipped = r.opened.filter((x) => x.shortened).length;
    toast(`${r.opened.length} link apert${r.opened.length === 1 ? "o" : "i"}${skipped ? `, ${skipped} senza pubblicità` : ""}`
      + (r.failed.length ? ` · ${r.failed.length} non riusciti` : ""), r.failed.length > 0);
  } catch (e) { toast(e.message, true); }
  finally {
    $("#dl-state")?.remove();
    btns.forEach((b) => { b.disabled = false; });
  }
}

async function downloadMain(d) {
  if (!DL_STATE || DL_STATE.id !== d.id) {
    await loadGameLinks(d);
    if (!DL_STATE || DL_STATE.id !== d.id) return toast("Nessun link da aprire in questa pagina: usa «🌐 Pagina dello store»", true);
  }
  return downloadLinks(d, dlPick(DL_STATE), $("#d-links"));
}

/* ---- salvataggi del gioco: versioni prima e dopo ogni partita, rollback, percorsi manuali e rilevati */
const SV_REASON = { "prima-della-partita": "prima della partita", "dopo-partita": "dopo la partita", manuale: "manuale",
  "prima-del-ripristino": "prima del ripristino", ludusavi: "fatta da Ludusavi" };
async function loadSaves(d) {
  let r;
  try { r = await api(`/api/game/${d.id}/saves`); } catch { return; }
  const box = $("#d-saves");
  if (!box || S.detail !== d) return;
  const found = r.paths.length + r.shared.length + r.manual.length;
  const url = `/api/game/${d.id}/saves`;
  box.innerHTML = `<div class="d-h">💾 Salvataggi <span class="muted small">${r.paths.length ? `${r.paths.length} trovati con ${esc(r.emulator)}`
      : found ? "" : "nessuno trovato: aggiungi la cartella qui sotto"}</span></div>
    <div class="saves">
      <div class="sv-actions">${found ? `<button class="btn" id="sv-now">Copia adesso</button>` : ""}
        ${r.session ? `<button class="btn" id="sv-undo" title="Riporta i salvataggi a com'erano prima dell'ultima partita">↶ Annulla l'ultima partita</button>` : ""}</div>
      ${r.shared.length ? `<p class="muted small">⚠ ${r.shared.length} file condivisi con altri giochi (memory card): ripristinando torna indietro anche il loro salvataggio.</p>` : ""}
      ${r.suggested.map((p) => `<div class="sv-row sv-sug"><span>Cambiati nell'ultima partita</span><span class="small" title="${esc(p)}">${esc(p)}</span>`
        + `<button class="btn" data-sug="${esc(p)}" data-ok="1">Sono i salvataggi</button><button class="btn" data-sug="${esc(p)}">Ignora</button></div>`).join("")}
      ${r.items.map((b) => `<div class="sv-row" data-name="${esc(b.name)}"><span>${esc(fmtDate(b.time))}</span>`
        + `<span class="muted small">${esc(SV_REASON[b.reason] || b.reason)} · ${esc(fmtSize(b.size))}${b.note ? ` · <i>${esc(b.note)}</i>` : ""}</span>`
        + `<button class="btn sv-pin" title="${b.pinned ? "Fissata: non si cancella mai" : "Fissa: non verrà cancellata"}">${b.pinned ? "★" : "☆"}</button>`
        + `<button class="btn sv-note" title="Nota">✎</button><button class="btn sv-diff">Confronta</button>`
        + `<button class="btn sv-restore">Ripristina</button><button class="btn sv-del" title="Elimina">✕</button></div>`).join("")
      || `<p class="muted small">Ancora nessuna versione: se ne crea una prima e dopo ogni partita.</p>`}
      <details class="sv-paths"${r.paths.length ? "" : " open"}><summary class="small">Percorsi</summary>
        ${[...r.paths, ...r.shared].map((p) => `<div class="small muted" title="${esc(p)}">${esc(p)}</div>`).join("")}
        ${r.manual.map((p, i) => `<div class="sv-row small"><span class="muted">a mano</span><span title="${esc(p)}">${esc(p)}</span><button class="btn" data-unpath="${i}">✕</button></div>`).join("")}
        <div class="sv-row"><input id="sv-path" placeholder="Cartella o file dei salvataggi, es. %APPDATA%\Gioco\Saves"><button class="btn" id="sv-add">Aggiungi</button></div>
      </details></div>`;
  const restore = async (name, what) => {
    if (!confirm(`Ripristinare i salvataggi ${what}?\nQuelli attuali vengono prima copiati, quindi si può annullare.`
      + (r.shared.length ? "\nAttenzione: anche le memory card condivise tornano indietro." : ""))) return;
    try { const x = await api(`${url}/restore`, { body: { name } }); toast(`Salvataggi ripristinati (${x.written} file${x.removed ? `, ${x.removed} tolti` : ""})`); }
    catch (err) { return toast(err.message, true); }
    loadSaves(d);
  };
  const setPaths = async (paths) => {
    try { await api(`${url}/paths`, { body: { paths } }); } catch (err) { return toast(err.message, true); }
    loadSaves(d);
  };
  box.onclick = async (e) => {
    const t = e.target, row = t.closest(".sv-row[data-name]"), name = row?.dataset.name;
    try {
      if (t.id === "sv-now") {
        const x = await api(url, { body: {} });
        toast(x.unchanged ? "Nessuna modifica dall'ultima versione" : "Versione dei salvataggi creata");
      } else if (t.id === "sv-undo") return restore(r.session, "di prima dell'ultima partita");
      else if (t.id === "sv-add") { const v = $("#sv-path").value.trim(); if (v) return setPaths([...r.manual, v]); return; }
      else if (t.dataset.unpath) return setPaths(r.manual.filter((_, i) => i !== +t.dataset.unpath));
      else if (t.dataset.sug) await api(`${url}/suggest`, { body: { path: t.dataset.sug, accept: !!t.dataset.ok } });
      else if (!row) return;
      else if (t.classList.contains("sv-restore")) return restore(name, `del ${row.firstChild.textContent}`);
      else if (t.classList.contains("sv-pin")) await api(`${url}/meta`, { body: { name, pinned: t.textContent === "☆" } });
      else if (t.classList.contains("sv-note")) {
        const note = prompt("Nota per questa versione (es. «prima del boss»):", r.items.find((b) => b.name === name)?.note || "");
        if (note === null) return;
        await api(`${url}/meta`, { body: { name, note } });
      } else if (t.classList.contains("sv-del")) {
        if (!confirm(`Eliminare la versione del ${row.firstChild.textContent}?`)) return;
        await api(`${url}/delete`, { body: { name } });
      } else if (t.classList.contains("sv-diff")) {
        const x = await api(`${url}/diff?name=${encodeURIComponent(name)}`);
        const list = (k, label) => x[k].length ? `<div><b>${label} (${x[k].length})</b>${x[k].map((f) => `<div title="${esc(f)}">${esc(f)}</div>`).join("")}</div>` : "";
        row.nextElementSibling?.classList.contains("sv-diffbox") && row.nextElementSibling.remove();
        row.insertAdjacentHTML("afterend", `<div class="sv-diffbox small muted">${list("changed", "Diversi da adesso") + list("missing", "Non più sul disco")
          + list("extra", "Nuovi, verrebbero tolti") || `Identica ai salvataggi attuali (${x.same} file).`}</div>`);
        return;
      } else return;
    } catch (err) { return toast(err.message, true); }
    loadSaves(d);
  };
}

function ratingBlock(d) {
  if (d.rating == null && d.rating_critics == null) return "";
  const stars = d.rating != null ? "★".repeat(Math.round(d.rating * 5)) + "☆".repeat(5 - Math.round(d.rating * 5)) : "";
  const parts = (d.ratings || []).map((r) => `${esc(r.name)} ${(r.rating * 5).toFixed(1)}${r.count ? ` (${r.count.toLocaleString("it")})` : ""}`);
  return `<div class="d-rating">${d.rating != null ? `<span class="stars">${stars}</span><span class="big">${(d.rating * 5).toFixed(1)}</span>`
    + `<span class="muted">${d.rating_count ? d.rating_count.toLocaleString("it") + " voti" : ""}</span>` : ""}
    ${d.rating_critics != null ? `<span class="crit" title="Voto della critica (Metacritic / IGDB)">Critica ${Math.round(d.rating_critics * 100)}/100</span>` : ""}
    ${parts.length > 1 ? `<span class="muted small">${parts.join(" · ")}</span>` : ""}</div>`;
}

async function renderDetailSections(d) {
  const host = $("#d-ext");
  for (const sec of GS.ui.detailSections) {
    if (sec.when && !sec.when(d)) continue;
    const box = document.createElement("div");
    box.innerHTML = `<div class="d-h">${esc(sec.title || "")}</div><div class="d-ext-body muted">…</div>`;
    host.appendChild(box);
    try {
      const out = await sec.render(d, GS);
      const body = box.querySelector(".d-ext-body");
      body.classList.remove("muted");
      if (out instanceof Element) { body.innerHTML = ""; body.appendChild(out); } else body.innerHTML = out ?? "";
    } catch (e) {
      box.querySelector(".d-ext-body").textContent = "Errore: " + e.message;
    }
    if (S.detail !== d) return; // l'utente ha aperto un altro gioco
  }
}

function closeDetail() {
  S.openSeq++; // una risposta in arrivo non deve riaprire il pannello
  const detail = $("#detail");
  detail.classList.remove("open");
  detail.setAttribute("aria-hidden", "true");
  detail.removeAttribute("aria-modal");
  detail.removeAttribute("aria-labelledby");
  delete document.documentElement.dataset.detailModal;
  S.detail = null;
  if (S.detailFocus?.isConnected) S.detailFocus.focus();
  S.detailFocus = null;
}

async function setFlag(field, value) {
  const d = S.detail;
  try { await api(`/api/game/${d.id}/flag`, { body: { field, value } }); } catch (e) { return toast(e.message, true); }
  const g = S.byId.get(d.id);
  g.grp[field] = field === "status" ? value || "" : value ? 1 : 0;
  renderSidebar();
  refreshGrid(true);
  if (S.detail?.id === d.id) openDetail(d.id); // solo se il pannello mostra ancora questo gioco
}
