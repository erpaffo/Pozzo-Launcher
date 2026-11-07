"use strict";
/* Pozzo Launcher - frontend: scheda del gioco: HLTB, obiettivi, DLC, download, salvataggi. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ dettaglio */
function fmtTime(sec) {
  if (!sec) return "—";
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString(GSI18n.lang, { dateStyle: "medium", timeStyle: "short" }) : "—"; }

/** Copertina condivisa tessera <-> scheda via View Transitions (solo motion "normal"); altrimenti, o su qualsiasi errore, esegue update() come prima. Un solo elemento alla volta porta il nome. */
async function coverTransition(from, update, to) {
  const root = document.documentElement;
  if (!from?.isConnected || !document.startViewTransition || root.dataset.motion !== "normal") return update();
  const tile = from.closest?.(".tile") || to()?.closest?.(".tile");
  const clear = () => { from.style.viewTransitionName = ""; const t = to(); if (t) t.style.viewTransitionName = ""; root.classList.remove("vt-cover"); tile?.classList.remove("vt-hold"); };
  let tr;
  try {
    from.style.viewTransitionName = "cover"; root.classList.add("vt-cover"); tile?.classList.add("vt-hold");
    tr = document.startViewTransition(() => { from.style.viewTransitionName = ""; update(); const t = to(); if (t) t.style.viewTransitionName = "cover"; });
  } catch { clear(); return update(); }
  tr.finished.then(clear, clear);
  await tr.updateCallbackDone;
}
const tileCover = (id) => S.nodes.get(id)?.querySelector(".cover");

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
    detail.setAttribute("role", mode === "panel" ? "complementary" : "region"); // panel non e' modale: nessun dialog
    detail.removeAttribute("aria-modal");
    delete document.documentElement.dataset.detailModal;
  }
  if (mode !== "panel") $("#detail-close").focus();
  detail.scrollTop = 0;
}

/** "#rrggbb" oppure null: qualsiasi altro valore del server non diventa mai CSS. */
function safeAccent(v) { return typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v.toLowerCase() : null; }

/** Colore del gioco sulla scheda (--game-accent, mai --accent del tema); nullo o non valido = lo toglie. */
function paintGameAccent(color) {
  const detail = $("#detail"), c = safeAccent(color);
  if (c) { detail.style.setProperty("--game-accent", c); detail.dataset.gameAccent = "1"; }
  else { detail.style.removeProperty("--game-accent"); delete detail.dataset.gameAccent; }
}

const gameAccents = new Map(); // id -> promessa del colore (null se assente o in errore)
const coverAccentOn = () => GSUi.prefs(GSUi.saved()).coverAccent; // Aspetto > Colore della copertina, predefinito attivo
function gameAccentOf(id) {
  if (!gameAccents.has(id)) gameAccents.set(id, api(`/api/game/${id}/cover-accent`).then((r) => safeAccent(r?.accent)).catch(() => { gameAccents.delete(id); return null; }));
  return gameAccents.get(id);
}
/** Applica (o toglie, se l'opzione e' spenta) il colore del gioco aperto; una risposta tardiva per un altro gioco si ignora. */
async function syncGameAccent(id, my) {
  if (!coverAccentOn()) return paintGameAccent(null);
  const c = await gameAccentOf(id);
  if (my === S.openSeq && coverAccentOn()) paintGameAccent(c);
}
if (typeof window !== "undefined") window.addEventListener("gs-ui-change", () => { if (S.detail) syncGameAccent(S.detail.id, S.openSeq); });

async function openDetail(id) {
  const my = ++S.openSeq; // un fetch lento non deve sovrascrivere il gioco aperto dopo
  if (!S.detail) S.detailFocus = document.activeElement;
  S.selected = id;
  try {
    const s = JSON.parse(localStorage.getItem("gs.last_session") || "{}");
    s.gameId = id;
    s.timestamp = Date.now();
    if (!s.view && S.view) s.view = S.view;
    localStorage.setItem("gs.last_session", JSON.stringify(s));
  } catch {}
  document.querySelectorAll(".tile.selected").forEach((t) => t.classList.remove("selected"));
  S.nodes.get(id)?.classList.add("selected");
  let d;
  try { d = await api(`/api/game/${id}`); } catch (e) { if (my === S.openSeq) { syncLibrary(); toast(e.message, true); } return; }
  if (my !== S.openSeq) return; // nel frattempo e' stato aperto (o chiuso) un altro gioco
  S.detail = d;
  paintGameAccent(null); // quello del gioco precedente non resta
  syncGameAccent(id, my);
  const hero = d.media.hero || d.media.screenshot || d.media.title || d.media.header || d.media.cover;
  $("#detail .hero-bg").style.backgroundImage = hero ? `url("${hero}?w=1280")` : "none";
  const u = d.user;
  const dl = [
    [t("f.dl.developer"), d.developer], [t("f.dl.publisher"), d.publisher], [t("f.dl.release"), d.release_date || d.year],
    [t("f.dl.languages"), GSLanguages.labels(d.title).join(", ")],
    [t("f.dl.genres"), (d.genres || []).join(", ")], [t("f.dl.players"), d.players_local],
    [t("f.dl.region"), d.region], [t("f.dl.size"), fmtSize(d.size)],
    [t("f.dl.playtime"), u.playtime ? fmtTime(u.playtime) : ""], [t("f.dl.last_played"), u.last_played ? fmtDate(u.last_played) : ""],
    [t("f.dl.launches"), u.play_count || ""],
    [t("f.dl.playtime_on", {store: d.store_name || "store"}), d.store_playtime ? fmtTime(d.store_playtime) : ""],
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
    ? (minerva ? "" : `<button class="btn primary" id="d-download" title="${t("f.btn.download_title")}">⬇ ${t("f.btn.download")}</button>`)
      // Minerva: la pagina web offre solo il torrent del set intero, il download vero e' il torrent del singolo file
      + (oneFile ? `<button class="btn${minerva && dlBase.length <= 1 ? " primary" : ""}" id="d-torrent" title="${t("f.btn.torrent_title")}">`
        + `${minerva && dlBase.length <= 1 ? "⬇ " + t("f.btn.download") : "🧲 Torrent"} ${t("f.btn.only_this")}</button>` : "")
    : pc && !d.installed
    ? `<button class="btn primary" id="d-install" ${d.can_install ? "" : "disabled"}>⬇ ${t("f.btn.install")}</button>`
    : `<button class="btn primary" id="d-play" ${d.emulator ? "" : "disabled"}>▶ ${t("f.btn.play")}</button>`
      // stesse condizioni di d-play: copia su SSD, avvio e cancellazione della copia lato backend (flag fast)
      + `<button class="btn" id="d-play-fast" ${d.emulator ? "" : "disabled"} title="${t("f.btn.play_fast_title")}">⚡ ${t("f.btn.play_fast")}</button>`
      + `<button class="btn" id="d-diagnose" title="${t("f.btn.diagnose_title")}">❔ ${t("f.btn.diagnose")}</button>`
      + (d.emulator ? `<button class="btn" id="d-party" ${["retroarch", "eden"].includes(d.emulator) ? "" : "disabled"} title="${["retroarch", "eden"].includes(d.emulator) ? t("f.party.invite_title") : t("f.party.unavailable_title")}">👥 ${t("f.party.button")}</button>` : "");
  const actions = GS.ui.gameActions.filter((a) => { try { return !a.when || a.when(d); } catch { return false; } });
  const bodyHtml = `
    <div class="d-top">
      <div class="d-cover">${d.media.cover ? `<img src="${d.media.cover}?w=450" alt="">` : ""}</div>
      <div class="d-title"><h2 id="detail-title">${esc(d.title)}</h2><div class="muted">${esc(d.platform_name)}${d.year ? " · " + d.year : ""}</div></div>
    </div>
    <div class="d-actions">
      ${mainBtn}
      <button class="btn ${u.favorite ? "on" : ""}" id="d-fav">${u.favorite ? "★ " + t("f.btn.favorite") : "☆ " + t("f.btn.favorite")}</button>
      ${pc && d.page ? `<button class="btn" id="d-page">🛒 ${t("f.btn.store_page")}</button>` : ""}
      ${!pc || (d.installed && d.files.length) ? `<button class="btn" id="d-folder">📁 ${t("f.btn.folder")}</button>` : ""}
      <button class="btn" id="d-hide">${u.hidden ? t("f.btn.show") : t("f.btn.hide")}</button>
      ${d.store === "manual" ? `<button class="btn" id="d-manual-del">🗑 ${t("f.btn.remove")}</button>` : ""}
      ${d.store === "ports" ? `<button class="btn" data-port="${esc(d.key.split(":").slice(1).join(":"))}">🕹 ${t("f.btn.manage_port")}</button>` : ""}
      ${(d.ports || []).map((p) => `<button class="btn" data-port="${esc(p.slug)}" title="${t("f.port.native_title", {name: esc(p.name)})}">🕹 ${t("f.port.available")}</button>`).join("")}
      ${actions.map((a) => `<button class="btn" data-ga="${esc(a.id)}">${esc((a.icon ? a.icon + " " : "") + a.label)}</button>`).join("")}
    </div>
    ${d.missing && d.missing.length ? `<div class="d-missing"><span>${t("f.missing.label")} ${esc(d.missing.join(", "))}</span>`
      + `<button class="btn" id="d-scrape" title="${t("f.missing.retry_title")}">⟳ ${t("f.missing.search")}</button></div>` : ""}
    ${online && d.magnet && !oneFile ? `<div class="d-note">${t("f.magnet.whole_set", {file: esc(d.file_name || d.title)})}</div>` : ""}
    <div class="d-emu muted">${online ? `${d.page_url ? `<img class="sico" src="/icons/site?url=${encodeURIComponent(d.page_url)}" alt="">` : "🌐"} ${t("f.emu.online")}${d.kind === "repack" ? " · 📦 " + t("f.emu.repack") : d.kind === "direct" ? " · ⬇ " + t("f.emu.direct") : ""}${dlBase.length > 1 ? ` · ${t("f.emu.sources", {n: dlBase.length, list: dlBase.map((s) => esc(s.site)).join(", ")})}` : ""} · ${esc(d.file_name || "")}`
      : pc ? `${esc(d.store_name)} · ${d.installed ? t("f.emu.installed") : t("f.emu.not_installed")}`
      : d.emulator ? t("f.emu.emulator") + ": " + esc(d.emulator) + (d.profile ? ` <span class="tag" title="${t("f.emu.profile_tag_title")}">${t("f.emu.profile")}</span>` : "")
      : `${t("f.emu.none", {platform: esc(d.platform_name)})} <a href="#" id="d-emu-cfg">${t("f.emu.settings")}</a>`}
      ${!online ? `<a href="#" id="d-profile" title="${pc ? t("f.profile.pc_title") : t("f.profile.emu_title")}">⚙ ${t("f.profile.label")}</a>
      · <a href="#" id="d-shortcut" title="${t("f.shortcut.title")}">🖥 ${t("f.shortcut.label")}</a>` : ""}
      ${online ? "" : "·"} <a href="#" id="d-media" title="${t("f.media.title")}">🖼 ${t("f.media.label")}</a></div>
    ${storePages.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>🌐 ${t("f.store.pages")}</span>
      ${storePages.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="${t("f.store.open_title", {site: esc(s.site || t("f.store.this_site"))})}">⬇ ${esc((s.site || "sito").replace(/^www\./, ""))}</button>`).join("")}
      </div>` : ""}
    ${updates.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>⬆ ${t("f.upd.label", {n: updates.length})}</span>
      ${updates.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="${esc(s.name || t("f.upd.title_default"))}">⬆ ${s.version ? "v" + esc(s.version) : t("f.upd.default")}${s.size ? " · " + fmtSize(s.size) : ""}</button>`).join("")}
      </div>` : ""}
    ${online && dlBase.length ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span>🌐 ${t("f.store.page")}</span>
      ${dlBase.map((s) => `<button class="btn" data-open="${esc(s.url)}"
        title="${t("f.store.open_title", {site: esc(s.site || t("f.store.this_site"))})}">${esc((s.site || "sito").replace(/^www\./, ""))} ↗</button>`).join("")}
      </div>` : ""}
    ${online || storePages.length ? `<div id="d-links"></div>` : ""}
    ${ratingBlock(d)}
    ${online ? "" : `<div class="d-status">${Object.entries(STATUS).map(([k, s]) =>
      `<button class="btn st-btn${u.status === k ? " on st-" + k : ""}" data-status="${k}">${s.icon} ${s.label}</button>`).join("")}</div>`}
    <div class="d-mine"><span class="muted small">${t("f.rate.mine")}</span><span class="d-stars">${[1, 2, 3, 4, 5].map((n) =>
      `<button class="star${n <= (u.my_rating || 0) ? " on" : ""}" data-myrate="${n}" title="${n}/5" aria-label="${t("f.rate.aria", {n})}" aria-pressed="${n <= (u.my_rating || 0)}">★</button>`).join("")}</span></div>
    <textarea class="field d-note" id="d-note" rows="2" placeholder="${t("f.notes.placeholder")}">${esc(u.note || "")}</textarea>
    ${GS.experience.detail === "modal" && !online ? `<div class="d-hltb" id="d-hltb" title="${t("f.hltb.title")}">${hltbBlock(d.hltb)}</div>` : ""}
    <div class="d-h">${t("f.coll.heading")}</div>
    <div class="chips">${d.collections.map((c) => `<span class="chip" data-slug="${esc(c.slug)}">${esc(c.name)}<button class="x" title="${t("f.coll.remove_title")}" aria-label="${t("f.coll.remove_aria", {name: esc(c.name)})}">✕</button></span>`).join("")}
      <span class="chip add" id="d-add-coll">＋ ${t("f.btn.add")}</span></div>
    <dl class="d-grid">${dl.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    ${d.description ? `<div class="d-h">${t("f.desc.heading")}</div><div class="d-desc">${esc(d.description)}</div>` : ""}
    ${d.shots ? `<div class="d-h">📷 ${t("f.shots.mine", {n: d.shots})} <a href="#" id="d-shots-all" class="muted small">${t("f.shots.see_all")}</a></div>
      <div class="my-shots" id="d-myshots"></div>` : ""}
    ${shots.length ? `<div class="d-h">${t("f.media.label")}</div><div class="shots">${shots.map((k) => `<img loading="lazy" src="${d.media[k]}?w=700" alt="${k}">`).join("")}</div>` : ""}
    ${d.versions.length > 1 ? `<div class="d-h">${t("f.versions.heading", {n: d.versions.length})}</div><div class="versions">${d.versions.map((v) =>
      `<div class="version ${v.primary ? "primary" : ""}"><span class="f" title="${esc(v.file)}">${esc(v.file)}</span>`
      + (v.store ? `<span class="muted">${v.installed ? t("f.emu.installed") : t("f.emu.not_installed")}</span>` : "")
      + (v.primary ? `<span class="muted">${t("f.versions.primary")}</span>` : `<button class="btn" data-pref="${v.id}">${t("f.versions.use")}</button>`)
      + (v.store && !v.installed ? `<button class="btn" data-install="${v.id}">⬇</button>`
        : `<button class="btn" data-play="${v.id}" ${d.emulator ? "" : "disabled"}>▶</button>`) + `</div>`).join("")}</div>` : ""}
    <div id="d-saves"></div>
    <div id="d-ext"></div>
    <div class="d-h">${t("f.files.heading")}</div>
    <div class="files">${d.files.map(esc).join("<br>")}${d.crc ? `<br>CRC ${esc(d.crc)}` : ""}
      ${Object.keys(d.sources).length ? `<br>${t("f.files.sources")}: ${esc([...new Set(Object.values(d.sources))].join(", "))}` : ""}</div>`;
  const wasOpen = $("#detail").classList.contains("open"); // già aperta (cambio gioco/riapertura): niente volo
  await coverTransition(wasOpen ? null : tileCover(id), () => { $("#detail-body").innerHTML = bodyHtml; presentDetail(); }, () => $("#detail .d-cover"));
  if (my !== S.openSeq) return;
  window.dispatchEvent(new CustomEvent("pozzo:detail-open", { detail: d }));
  renderDetailSections(d);
  if (typeof loadDetailMods === "function") loadDetailMods(d);
  if (typeof loadDetailNoclient === "function") loadDetailNoclient(d);
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
  if (!h) return `<span class="muted small d-hltb__state">${t("f.hltb.searching")}</span>`;
  const rows = [[t("f.hltb.main"), h.main], [t("f.hltb.extra"), h.extra], [t("f.hltb.complete"), h.complete]].filter(([, v]) => v);
  if (!rows.length) return `<span class="muted small d-hltb__state">${t("f.hltb.unavailable")}</span>`;
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

/** Un link per tipo (gioco, aggiornamento, DLC), dalla stessa fonte possibile.
 *  Per i repack PC prende le parti dirette della fonte più affidabile (FuckingFast, poi DataNodes…);
 *  il torrent non c'entra: ha il suo pulsante accanto a «Scarica». */
const DL_HOST_RANK = { "krakenfiles.com": 0, "megaup.net": 0, "1fichier.com": 1, "datanodes.to": 3 };
function dlPick(state, only = null) {
  const out = [];
  for (const kind of [...new Set(state.rows.map((r) => r.kind))].filter((k) => !only || k === only)) {
    const items = state.rows.filter((r) => r.kind === kind).flatMap((r) => r.items);
    const directRows = state.rows.filter((r) => r.kind === kind && r.items.some((x) => x.role === "direct"));
    if (directRows.length) { // la riga della fonte migliore: le parti si estraggono da sole quando ci sono tutte
      const row = directRows.reduce((a, b) => (dlRowRank(a) <= dlRowRank(b) ? a : b));
      const files = row.items.filter((x) => x.role === "direct");
      const best = Math.min(...files.map(dlRank));
      out.push(...files.filter((x) => dlRank(x) === best).map((x) => x.url));
      continue;
    }
    // MultiUp mai in automatico: si sceglie il provider a mano (tipi con solo MultiUp restano fuori)
    const it = items.filter((x) => (x.role || "download") === "download" && !DLU.isMultiup(x));
    if (!it.length) continue;
    const count = {}, hostOf = {};
    for (const x of it) {
      count[x.provider] = (count[x.provider] || 0) + 1;
      hostOf[x.provider] = hostOf[x.provider] || x.host;
    }
    const rank = (p) => (DL_HOST_RANK[hostOf[p]] ?? 2);
    const best = Object.entries(count).sort((a, b) => (rank(a[0]) - rank(b[0])) || (b[1] - a[1]))[0][0];
    out.push((it.find((x) => x.provider === best) || it[0]).url);
  }
  if (!out.length && !only) { // solo il torrent: allora è quello
    const mag = dlMagnetOf(state.rows);
    if (mag) out.push(mag);
  }
  return out;
}

/** il magnet elencato nella pagina del gioco ("" se non c'è) */
function dlMagnetOf(rows) {
  const mag = (rows || []).flatMap((r) => r.items).find((x) => (x.role || "download") === "magnet");
  return mag ? mag.url : "";
}

function dlMagnetUrl() {
  if (!DL_STATE || !S.detail || DL_STATE.id !== S.detail.id) return "";
  const game = DL_STATE.rows.filter((r) => r.kind === "game");
  return dlMagnetOf(game) || dlMagnetOf(DL_STATE.rows);
}

/* I paste dei filehoster (fitgirl e simili) si leggono al clic: un paste contiene decine di link */
const DL_PASTE = new Map(); // url del paste -> { links: [url], magnet }
const DL_PARTS = []; // elenchi di file da mettere in coda assieme (le parti di un archivio)
const dlParts = (urls) => { DL_PARTS.push(urls); return `data-dparts="${DL_PARTS.length - 1}"`; };

/** righe del pannello link: un gruppo per tipo+etichetta (le parti restano nella loro riga), ruolo normalizzato */
function dlRows(links) {
  const rows = [];
  for (const x of links || []) {
    const key = `${x.kind}|${x.label}`;
    let row = rows.find((y) => y.key === key);
    if (!row) rows.push(row = { key, kind: x.kind, label: x.label, items: [] });
    row.items.push({ ...x, role: x.role || "download" });
  }
  return rows;
}

/* Ordine delle fonti di un repack: il torrent per primo (è l'unica che funziona quasi sempre), poi FuckingFast,
 * DataNodes, FileKeeper e infine le pagine da aprire. */
const DL_HOST_ORDER = ["fuckingfast.co", "datanodes.to", "filekeeper.net"];
function dlRank(x) {
  if ((x.role || "download") === "magnet") return 0;
  const h = (x.host || "").toLowerCase(), p = (x.provider || "").toLowerCase().split(".")[0];
  // un paste ha l'host del paste: l'ordine lo dice il nome del servizio («FileKeeper», «DataNodes»)
  const i = DL_HOST_ORDER.findIndex((k) => k === h || (p && k.startsWith(p)));
  return i < 0 ? 9 : i + 1;
}
const dlRowRank = (row) => Math.min(...row.items.map(dlRank));

/** righe nell'ordine delle fonti (prima la più affidabile), poi per tipo di file */
function dlSortRows(rows, kinds) {
  return [...rows].sort((a, b) => (dlRowRank(a) - dlRowRank(b)) || (kinds.indexOf(a.kind) - kinds.indexOf(b.kind)));
}

async function loadGameLinks(d, force = false) {
  const box = $("#d-links");
  if (!box) return;
  if (!DL_STATE || DL_STATE.id !== d.id) { DL_PASTE.clear(); DL_PARTS.length = 0; }
  box.innerHTML = `<p class="muted small">${t("f.links.searching")}</p>`;
  let r;
  try { r = await api(`/api/game/${d.id}/links${force ? "?refresh=1" : ""}`); }
  catch (e) { box.innerHTML = `<p class="muted small">${esc(e.message)}</p>`; return; }
  if (S.detail !== d) return;
  const links = (r.links || []).filter((x) => x.url);
  if (!links.length) {
    box.innerHTML = `<p class="muted small">${t("f.links.none")}${r.error ? ` (${esc(r.error)})` : ""}.</p>`;
    return;
  }
  const KL = r.kind_labels || {}, KO = r.kind_order || [];
  const rows = dlSortRows(dlRows(links), KO); // una riga per tipo di file: le parti e le versioni in altre lingue restano righe separate
  const kinds = [...new Set(rows.map((x) => x.kind))];
  DL_STATE = { id: d.id, rows, kinds, labels: KL, order: KO };
  // un solo gruppo «MultiUp» per riga (più accorciatori verso lo stesso file non servono): i provider si caricano al clic
  const group = (x) => `<span class="mu-grp"><button class="btn" data-mu="${esc(x.url)}" aria-expanded="false"
      title="${t("f.mu.list_title")}">${esc(DLU.muTitle())}</button>
      <span class="mu-list" role="group" aria-label="${t("f.mu.aria")}" hidden></span></span>`;
  const btn = (x) => DLU.isMultiup(x) ? "" : `<button class="btn" data-dl="${esc(x.url)}"
    title="${esc(x.provider)} → ${esc(x.host)}${x.short ? " (" + t("f.dl.ads_skipped") + ")" : ""}">${esc(x.provider)}</button>`;
  /* I ruoli: magnet = torrent, page = una pagina da aprire, paste = un elenco da leggere, direct = i file veri.
   * Il primo pulsante (in ordine di affidabilità) è quello consigliato: pieno, gli altri secondari. */
  const rowButtons = (row, primaryRow) => {
    const out = [];
    for (const x of row.items) {
      if (x.role === "download") {
        const h = btn(x) || group(x);
        if (h) out.push({ rank: dlRank(x), make: () => h });
      } else if (x.role === "magnet") {
        out.push({ rank: 0, make: (p) => `<button class="btn${p}" data-dl="${esc(x.url)}"
          title="${t("f.dl.torrent_title")}">🧲 Torrent</button>` });
      } else if (x.role === "page") {
        out.push({ rank: 9, make: () => `<button class="btn" data-open="${esc(x.url)}"
          title="${t("f.dl.open_page_title", {host: esc(x.host)})}">↗ ${esc(x.provider || x.host)}</button>` });
      } else if (x.role === "paste") {
        out.push({ rank: dlRank(x), make: () => `<span class="pst-grp"><button class="btn" data-paste="${esc(x.url)}"
          aria-expanded="false" title="${t("f.dl.read_list_title", {host: esc(x.host)})}">📄 ${esc(x.provider || x.host)}</button>
          <span class="pst-list" role="group" aria-label="File del paste" hidden></span></span>` });
      }
    }
    const byHost = new Map(); // le parti dello stesso host sono un pulsante solo
    for (const x of row.items) if (x.role === "direct") byHost.set(x.host, [...(byHost.get(x.host) || []), x]);
    for (const [h, files] of byHost) {
      out.push({ rank: dlRank(files[0]), make: (p) => `<button class="btn${p}" ${dlParts(files.map((x) => x.url))}
        title="${t("f.dl.queue_parts_title")}">⬇ ${t("f.btn.download")} ${files.length === 1 ? t("f.dl.the_file") : t("f.dl.the_parts", {n: files.length})}${byHost.size > 1 ? ` · ${esc(h)}` : ""}</button>` });
    }
    out.sort((a, b) => a.rank - b.rank);
    const first = primaryRow ? out.findIndex((x) => x.rank < 9) : -1; // la fonte consigliata: la migliore della prima riga
    return out.map((x, i) => x.make(i === first ? " primary" : "")).join("");
  };
  box.innerHTML = `<div class="d-h">⬇ ${t("f.dl.links_heading")} <span class="muted small">${esc([...new Set(links.map((x) => x.site))].join(" · "))}</span>
      <a href="#" id="dl-refresh" class="muted small" title="${t("f.dl.refresh_title")}">↻</a></div>
    ${kinds.length > 1 ? `<div class="d-emu muted" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn primary" id="dl-all" title="${t("f.dl.one_per_type_title")}">⬇ ${t("f.btn.download")} ${esc(kinds.map((k) => (KL[k] || k).toLowerCase()).join(" + "))}</button>
      <span>${t("f.dl.no_pages_note")}</span></div>` : ""}
    ${rows.map((row, i) => `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0">
      <span class="muted small" style="min-width:180px">${esc(KL[row.kind] || row.kind)}${row.label ? " · " + esc(row.label) : ""}</span>
      ${rowButtons(row, i === 0)}</div>`).join("")}`;
  dlMagnetButton(d);
  box.onclick = async (e) => {
    e.preventDefault();
    if (e.target.id === "dl-refresh") return loadGameLinks(d, true);
    const mu = e.target.closest("[data-mu]"), retry = e.target.closest("[data-mu-retry]");
    if (mu || retry) return muToggle((mu || retry).closest(".mu-grp"), !!retry);
    const open = e.target.closest("[data-open]");
    if (open) return api("/api/open", { body: { url: open.dataset.open } }).catch((err) => toast(err.message, true));
    const pst = e.target.closest("[data-paste]");
    if (pst) return pasteToggle(d, pst.closest(".pst-grp"), pst.dataset.paste);
    const direct = e.target.closest("[data-dparts]");
    if (direct) return downloadLinks(d, DL_PARTS[Number(direct.dataset.dparts)] || [], box);
    const one = e.target.closest("[data-dl]");
    if (one) return downloadLinks(d, [one.dataset.dl], box);
    if (e.target.id === "dl-all") return downloadLinks(d, dlPick(DL_STATE), box);
  };
}

/** il torrent accanto a «Scarica»: la pagina lo elenca tra i link, quindi il pulsante compare dopo la lettura */
function dlMagnetButton(d) {
  const acts = $("#detail .d-actions"), mag = dlMagnetUrl();
  if (!acts || !mag || d.platform !== "pc" || $("#d-magnet") || !$("#d-download")) return;
  const b = document.createElement("button");
  b.className = "btn";
  b.id = "d-magnet";
  b.textContent = "🧲 Torrent";
  b.title = t("f.dl.magnet_title");
  $("#d-download").after(b);
}

/** apre l'elenco dei file di un paste dei filehoster; la seconda volta resta in memoria */
async function pasteToggle(d, grp, url) {
  const btn = grp.querySelector("[data-paste]"), list = grp.querySelector(".pst-list");
  const open = btn.getAttribute("aria-expanded") === "true";
  if (open) { btn.setAttribute("aria-expanded", "false"); list.hidden = true; return; }
  btn.setAttribute("aria-expanded", "true");
  list.hidden = false;
  const data = DL_PASTE.get(url);
  const show = (x) => {
    const files = x.links || [];
    const parts = files.length > 1 ? ` <span class="muted small">(${t("f.dl.parts", {n: files.length})})</span>` : "";
    list.innerHTML = (x.magnet ? `<button class="btn primary" data-dl="${esc(x.magnet)}">🧲 Torrent</button>` : "")
      + (files.length ? `<button class="btn primary" ${dlParts(files.map((f) => f.url))}>⬇ ${t("f.btn.download")} ${files.length === 1 ? t("f.dl.the_file") : t("f.dl.the_parts", {n: files.length})}</button>${parts}` : "")
      + (!x.magnet && !files.length ? `<span class="muted small">${t("f.dl.paste_empty")}</span>` : "");
  };
  if (data) { show(data); return; }
  skelInline(list, 2, `<span class="muted small"><span class="mu-spin" aria-hidden="true"></span> ${t("f.dl.reading")}</span>`);
  try {
    const r = await api(`/api/game/${d.id}/paste?url=${encodeURIComponent(url)}`);
    if (!grp.isConnected) return;
    DL_PASTE.set(url, r);
    show(r);
  } catch (e) {
    if (!grp.isConnected) return;
    list.innerHTML = `<span class="small err" role="alert">${esc(e.message)}</span>
      <button class="btn" data-open="${esc(url)}">↗ ${t("f.dl.open_paste")}</button>`;
  }
}

/** apre o chiude l'elenco dei provider di un link MultiUp; `fresh` (Riprova) rilegge dal server invece che dalla memoria */
async function muToggle(grp, fresh = false) {
  const btn = grp.querySelector("[data-mu]"), list = grp.querySelector(".mu-list");
  const open = btn.getAttribute("aria-expanded") === "true";
  if (open && !fresh) { btn.setAttribute("aria-expanded", "false"); list.hidden = true; return; }
  btn.setAttribute("aria-expanded", "true");
  list.hidden = false;
  list.setAttribute("aria-busy", "true");
  skelInline(list, 2, `<span class="muted small"><span class="mu-spin" aria-hidden="true"></span> ${t("f.mu.searching")}</span>`);
  try {
    const r = await muFetch(btn.dataset.mu, fresh);
    if (!grp.isConnected) return;
    btn.textContent = DLU.muTitle(r.mirrors.length);
    list.innerHTML = r.mirrors.map((m) => {
      const v = DLU.mirrorView(m);
      return `<button class="btn" ${v.dead ? "disabled data-dead=\"1\"" : `data-dl="${esc(m.url)}"`} title="${esc(v.title)}">${esc(v.label)}${v.note ? ` <span class="muted small">${esc(v.note)}</span>` : ""}</button>`;
    }).join("");
  } catch (e) {
    if (!grp.isConnected) return;
    list.innerHTML = `<span class="small err" role="alert">${esc(e.message)}</span> <button class="btn" data-mu-retry="1">${t("f.btn.retry")}</button>`;
  } finally { list.removeAttribute("aria-busy"); }
  if (grp.isConnected && document.activeElement === document.body) btn.focus(); // il clic su Riprova ha tolto il pulsante: il focus non si perde
}

async function downloadLinks(d, urls, box) {
  if (!urls.length) return toast(t("f.dl.no_direct"), true);
  const btns = box ? [...box.querySelectorAll("button")] : [];
  btns.forEach((b) => { b.disabled = true; });
  box?.insertAdjacentHTML("afterbegin", `<p class="muted small" id="dl-state">${t("f.dl.queueing")}</p>`);
  try {
    const r = await api(`/api/game/${d.id}/download`, { body: { links: urls } });
    const n = r.tasks.length;
    toast((n === 1 ? t("f.dl.queued_one", {n}) : t("f.dl.queued_many", {n}))
      + (r.failed.length ? " · " + t("f.dl.failed", {n: r.failed.length}) : ""), r.failed.length > 0);
  } catch (e) { toast(e.message, true); }
  finally {
    $("#dl-state")?.remove();
    btns.forEach((b) => { b.disabled = b.dataset.dead === "1"; }); // i mirror offline restano spenti
  }
}

async function downloadMain(d) {
  if (!DL_STATE || DL_STATE.id !== d.id) {
    await loadGameLinks(d);
    if (!DL_STATE || DL_STATE.id !== d.id) return toast(t("f.dl.nothing"), true);
  }
  // «Scarica» prende il gioco; gli aggiornamenti hanno la loro riga (e il pulsante «gioco + aggiornamento»)
  const game = dlPick(DL_STATE, "game");
  return downloadLinks(d, game.length ? game : dlPick(DL_STATE), $("#d-links"));
}

/* ---- salvataggi del gioco: versioni prima e dopo ogni partita, rollback, percorsi manuali e rilevati */
const SV_REASON = { "prima-della-partita": "f.sv.reason_before_play", "dopo-partita": "f.sv.reason_after_play", manuale: "f.sv.reason_manual",
  "prima-del-ripristino": "f.sv.reason_before_restore", ludusavi: "f.sv.reason_ludusavi" };
async function loadSaves(d) {
  let r;
  try { r = await api(`/api/game/${d.id}/saves`); } catch { return; }
  const box = $("#d-saves");
  if (!box || S.detail !== d) return;
  const found = r.paths.length + r.shared.length + r.manual.length;
  const url = `/api/game/${d.id}/saves`;
  box.innerHTML = `<div class="d-h">💾 ${t("f.sv.heading")} <span class="muted small">${r.paths.length ? t("f.sv.found", {n: r.paths.length, emu: esc(r.emulator)})
      : found ? "" : t("f.sv.none_found")}</span></div>
    <div class="saves">
      <div class="sv-actions">${found ? `<button class="btn" id="sv-now">${t("f.sv.copy_now")}</button>` : ""}
        ${r.session ? `<button class="btn" id="sv-undo" title="${t("f.sv.undo_title")}">↶ ${t("f.sv.undo")}</button>` : ""}</div>
      ${r.shared.length ? `<p class="muted small">⚠ ${t("f.sv.shared", {n: r.shared.length})}</p>` : ""}
      ${r.suggested.map((p) => `<div class="sv-row sv-sug"><span>${t("f.sv.changed_last")}</span><span class="small" title="${esc(p)}">${esc(p)}</span>`
        + `<button class="btn" data-sug="${esc(p)}" data-ok="1">${t("f.sv.is_saves")}</button><button class="btn" data-sug="${esc(p)}">${t("f.btn.ignore")}</button></div>`).join("")}
      ${r.items.map((b) => `<div class="sv-row" data-name="${esc(b.name)}"><span>${esc(fmtDate(b.time))}</span>`
        + `<span class="muted small">${esc(SV_REASON[b.reason] ? t(SV_REASON[b.reason]) : b.reason)} · ${esc(fmtSize(b.size))}${b.note ? ` · <i>${esc(b.note)}</i>` : ""}</span>`
        + `<button class="btn sv-pin" title="${b.pinned ? t("f.sv.pinned_title") : t("f.sv.pin_title")}">${b.pinned ? "★" : "☆"}</button>`
        + `<button class="btn sv-note" title="${t("f.sv.note_title")}">✎</button><button class="btn sv-diff">${t("f.sv.diff")}</button>`
        + `<button class="btn sv-restore">${t("f.sv.restore")}</button><button class="btn sv-del" title="${t("f.sv.delete_title")}">✕</button></div>`).join("")
      || `<p class="muted small">${t("f.sv.none_yet")}</p>`}
      <details class="sv-paths"${r.paths.length ? "" : " open"}><summary class="small">${t("f.sv.paths")}</summary>
        ${[...r.paths, ...r.shared].map((p) => `<div class="small muted" title="${esc(p)}">${esc(p)}</div>`).join("")}
        ${r.manual.map((p, i) => `<div class="sv-row small"><span class="muted">${t("f.sv.manual")}</span><span title="${esc(p)}">${esc(p)}</span><button class="btn" data-unpath="${i}">✕</button></div>`).join("")}
        <div class="sv-row"><input id="sv-path" placeholder="${t("f.sv.path_placeholder")}"><button class="btn" id="sv-add">${t("f.btn.add")}</button></div>
      </details></div>`;
  const restore = async (name, what) => {
    if (!confirm(t("f.sv.restore_confirm", {what}) + (r.shared.length ? t("f.sv.shared_warn") : ""))) return;
    try { const x = await api(`${url}/restore`, { body: { name } }); toast(x.removed ? t("f.sv.restored_removed", {written: x.written, removed: x.removed}) : t("f.sv.restored", {written: x.written})); }
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
        toast(x.unchanged ? window.t("f.sv.unchanged") : window.t("f.sv.created"));
      } else if (t.id === "sv-undo") return restore(r.session, window.t("f.sv.what_before_last"));
      else if (t.id === "sv-add") { const v = $("#sv-path").value.trim(); if (v) return setPaths([...r.manual, v]); return; }
      else if (t.dataset.unpath) return setPaths(r.manual.filter((_, i) => i !== +t.dataset.unpath));
      else if (t.dataset.sug) await api(`${url}/suggest`, { body: { path: t.dataset.sug, accept: !!t.dataset.ok } });
      else if (!row) return;
      else if (t.classList.contains("sv-restore")) return restore(name, window.t("f.sv.what_date", {date: row.firstChild.textContent}));
      else if (t.classList.contains("sv-pin")) await api(`${url}/meta`, { body: { name, pinned: t.textContent === "☆" } });
      else if (t.classList.contains("sv-note")) {
        const note = prompt(window.t("f.sv.note_prompt"), r.items.find((b) => b.name === name)?.note || "");
        if (note === null) return;
        await api(`${url}/meta`, { body: { name, note } });
      } else if (t.classList.contains("sv-del")) {
        if (!confirm(window.t("f.sv.delete_confirm", {date: row.firstChild.textContent}))) return;
        await api(`${url}/delete`, { body: { name } });
      } else if (t.classList.contains("sv-diff")) {
        const x = await api(`${url}/diff?name=${encodeURIComponent(name)}`);
        const list = (k, label) => x[k].length ? `<div><b>${label} (${x[k].length})</b>${x[k].map((f) => `<div title="${esc(f)}">${esc(f)}</div>`).join("")}</div>` : "";
        row.nextElementSibling?.classList.contains("sv-diffbox") && row.nextElementSibling.remove();
        row.insertAdjacentHTML("afterend", `<div class="sv-diffbox small muted">${list("changed", window.t("f.sv.changed")) + list("missing", window.t("f.sv.missing"))
          + list("extra", window.t("f.sv.extra")) || window.t("f.sv.identical", {n: x.same})}</div>`);
        return;
      } else return;
    } catch (err) { return toast(err.message, true); }
    loadSaves(d);
  };
}

function ratingBlock(d) {
  if (d.rating == null && d.rating_critics == null) return "";
  const stars = d.rating != null ? "★".repeat(Math.round(d.rating * 5)) + "☆".repeat(5 - Math.round(d.rating * 5)) : "";
  const parts = (d.ratings || []).map((r) => `${esc(r.name)} ${(r.rating * 5).toFixed(1)}${r.count ? ` (${r.count.toLocaleString(GSI18n.lang)})` : ""}`);
  return `<div class="d-rating">${d.rating != null ? `<span class="stars">${stars}</span><span class="big">${(d.rating * 5).toFixed(1)}</span>`
    + `<span class="muted">${d.rating_count ? d.rating_count.toLocaleString(GSI18n.lang) + " " + t("f.rate.votes") : ""}</span>` : ""}
    ${d.rating_critics != null ? `<span class="crit" title="${t("f.rate.critic_title")}">${t("f.rate.critic")} ${Math.round(d.rating_critics * 100)}/100</span>` : ""}
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
      box.querySelector(".d-ext-body").textContent = t("f.err.generic", {msg: e.message});
    }
    if (S.detail !== d) return; // l'utente ha aperto un altro gioco
  }
}

function closeDetail() {
  S.openSeq++; // una risposta in arrivo non deve riaprire il pannello
  S.selected = null;
  try {
    const s = JSON.parse(localStorage.getItem("gs.last_session") || "{}");
    s.gameId = null;
    s.timestamp = Date.now();
    localStorage.setItem("gs.last_session", JSON.stringify(s));
  } catch {}
  const detail = $("#detail"), gid = S.detail?.id, seq = S.openSeq;
  const hide = () => {
    if (seq !== S.openSeq && S.detail) return; // la transizione chiude in ritardo: nel frattempo e' stato aperto un altro gioco
    detail.classList.remove("open");
    detail.setAttribute("aria-hidden", "true");
    detail.removeAttribute("aria-modal");
    detail.removeAttribute("aria-labelledby");
    delete document.documentElement.dataset.detailModal;
  };
  const dc = detail.classList.contains("open") ? detail.querySelector(".d-cover") : null;
  if (dc && gid != null) coverTransition(dc, hide, () => tileCover(gid)).catch(hide); else hide();
  paintGameAccent(null);
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

/* ------------------------------------------------------------------ gioco scaricato ed estratto
   /api/status porta l'ultimo evento game_downloaded {seq, game_id, from_id, title}. Dopo il ricaricamento della libreria:
   avviso e, se la scheda aperta era la voce online (from_id; i numeri cambiano a ogni ricostruzione), si apre il gioco posseduto. */
function downloadedPlan(ev, seen, openId) {
  if (!ev || !(ev.seq > (seen || 0))) return null;
  return { seq: ev.seq, toast: t("f.dl.done", {title: ev.title}),
    open: ev.game_id != null && openId != null && openId === ev.from_id ? ev.game_id : null };
}
function onGameDownloaded(ev) {
  if (S.dlSeen === undefined) { S.dlSeen = ev?.seq || 0; return; } // primo controllo: gli eventi vecchi non si annunciano
  const plan = downloadedPlan(ev, S.dlSeen, S.detail?.id);
  if (!plan) return;
  S.dlSeen = plan.seq;
  toast(plan.toast);
  if (plan.open != null) openDetail(plan.open);
}
if (typeof module !== "undefined") module.exports = { coverTransition, safeAccent, downloadedPlan, dlRows, dlPick, linkUrlsOf, DL_PARTS, dlRank, dlSortRows, dlMagnetOf };

/* Tasto destro su un link di download (giochi di ogni console): copia l'indirizzo per aprirlo a mano nel browser.
   I magnet non c'entrano: si copiano dal torrent. Vale per i pulsanti con data-dl / data-dparts / data-mu / data-open / data-paste. */
function linkUrlsOf(el) {
  const d = el.dataset;
  return DLU.copyable(d.dparts != null ? DL_PARTS[Number(d.dparts)] : [d.dl || d.mu || d.open || d.paste]);
}

function openLinkMenu(e) {
  const el = e.target.closest("[data-dl], [data-dparts], [data-mu], [data-open], [data-paste]");
  const urls = el ? linkUrlsOf(el) : [];
  if (!urls.length) return false;
  closeCtx();
  const many = urls.length > 1, r = el.getBoundingClientRect();
  const pt = e.clientX || e.clientY ? { x: e.clientX, y: e.clientY } : { x: r.left, y: r.bottom }; // tasto Menu: sotto il pulsante
  const acts = [
    ["📋 " + (many ? t("f.lm.copy_many", {n: urls.length}) : t("f.lm.copy")), () => navigator.clipboard.writeText(urls.join("\n"))
      .then(() => toast(many ? t("f.lm.copied_many") : t("f.lm.copied")), () => toast(t("f.lm.copy_fail"), true))],
    ["↗ " + (many ? t("f.lm.open_first") : t("f.lm.open")), () => api("/api/open", { body: { url: urls[0] } })],
  ];
  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.setAttribute("role", "menu");
  m.setAttribute("aria-label", t("f.dl.links_heading"));
  m.innerHTML = acts.map(([l], i) => `<div class="ci" role="menuitem" tabindex="-1" data-i="${i}">${esc(l)}</div>`).join("")
    + (many ? "" : `<div class="ch" style="text-transform:none;letter-spacing:0;white-space:normal;word-break:break-all">${esc(urls[0].length > 90 ? urls[0].slice(0, 90) + "…" : urls[0])}</div>`);
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(pt.x, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(pt.y, innerHeight - m.offsetHeight - 8)) + "px";
  const items = [...m.querySelectorAll(".ci")];
  items[0].focus();
  m.addEventListener("keydown", (ev) => {
    const i = items.indexOf(document.activeElement);
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") items[(i + (ev.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
    else if (ev.key === "Enter" || ev.key === " ") document.activeElement.click();
    else if (ev.key === "Escape" || ev.key === "Tab") { closeCtx(); el.focus(); }
    else return;
    ev.preventDefault();
    ev.stopPropagation();
  });
  m.onclick = async (ev) => {
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    try { await acts[+it.dataset.i][1](); } catch (err) { toast(err.message, true); }
  };
  return true;
}

// in cattura: i gestori della griglia (menu del gioco) non devono rubare il clic destro su un link
if (typeof document !== "undefined") document.addEventListener("contextmenu", (e) => {
  if (e.target instanceof Element && openLinkMenu(e)) { e.preventDefault(); e.stopPropagation(); }
}, true);

/* ------------------------------------------------------------------ gioca con un amico (netplay) */
/* Come api() ma conserva detail.error (il server risponde {detail:{error}} o {detail:"testo"}). */
async function partyApi(path, body) {
  const r = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch { /* non JSON */ }
  if (!r.ok) { const dt = j && j.detail; const e = new Error(typeof dt === "string" ? dt : (dt && dt.error) || r.statusText); e.detail = dt; throw e; }
  return j;
}
const PARTY_ERR = { "core-mismatch": "f.party.err_core", "emulator-mismatch": "f.party.err_emulator" };
const partyMsg = (e) => {
  const d = e.detail;
  if (d && typeof d === "object" && d.error === "core-mismatch" && "local" in d && "remote" in d)
    return t("f.party.core_mismatch", {local: d.local || t("f.party.none"), remote: d.remote});
  if (d && typeof d === "object" && d.error === "cgnat") return t("f.party.err_cgnat", {ip: d.ip});
  return PARTY_ERR[d && d.error] ? t(PARTY_ERR[d && d.error]) : e.message;
};

async function openParty(d) {
  const dlg = $("#party-dlg"), body = $("#party-body");
  body.innerHTML = `<p class="muted">${t("f.party.loading")}</p>`;
  dlg.showModal();
  let cfg = {};
  try { cfg = await partyApi("/api/party"); } catch { /* campi vuoti */ }
  const hosts = cfg.hosts || [];
  body.innerHTML = `
    <label class="lbl-field">${t("f.party.nick")}<input id="pt-nick" class="field" value="${esc(cfg.nick || "")}"></label>
    <fieldset class="lbl-field"><legend>${t("f.party.where")}</legend>
      <label><input type="radio" name="pt-where" value="lan"> ${t("f.party.where_lan")}</label>
      <label><input type="radio" name="pt-where" value="internet" checked> ${t("f.party.where_internet")}</label>
      <label><input type="radio" name="pt-where" value="vpn"> ${t("f.party.where_vpn")}</label>
    </fieldset>
    <details><summary>${t("f.party.advanced")}</summary>
      <label class="lbl-field">${t("f.party.ip")}<input id="pt-host" class="field" list="pt-hosts" value="${esc(cfg.host || hosts[0] || "")}"></label>
      <datalist id="pt-hosts">${hosts.map((h) => `<option value="${esc(h)}">`).join("")}</datalist>
      <button class="btn" id="pt-detect" type="button">${t("f.party.detect_ip")}</button> <span id="pt-ipmsg" class="muted small" aria-live="polite"></span>
    </details>
    <label class="lbl-field">${t("f.party.port")}<input id="pt-port" class="field" type="number" value="${esc(d.emulator === "eden" ? (cfg.eden_port || 24872) : (cfg.port || 55435))}"></label>
    <p id="pt-out" aria-live="polite"></p>
    <div class="row end"><button class="btn primary" id="pt-go" type="button">${t("f.party.create")}</button></div>`;
  const ipOfKind = (k) => Object.keys(cfg.kinds || {}).find((ip) => cfg.kinds[ip] && cfg.kinds[ip].kind === k);
  body.querySelectorAll('input[name="pt-where"]').forEach((radio) => radio.onchange = () => {
    const ip = radio.value === "lan" ? ipOfKind("lan") : radio.value === "vpn" ? ipOfKind("shared") : null;
    if (ip) $("#pt-host").value = ip;
  });
  $("#pt-detect").onclick = async () => {
    try {
      const r = await partyApi("/api/party/public-ip", {});
      if (r.ip) $("#pt-host").value = r.ip;
      $("#pt-ipmsg").textContent = r.ip ? (r.tip || "") : (r.error || "");
    } catch (e) { toast(e.message, true); }
  };
  $("#pt-go").onclick = async () => {
    const out = $("#pt-out"), port = +$("#pt-port").value;
    try {
      const r = await partyApi("/api/party/invite", { key: d.key, nick: $("#pt-nick").value.trim(), host: $("#pt-host").value.trim(), port, where: (body.querySelector('input[name="pt-where"]:checked') || {}).value });
      out.innerHTML = `<label class="lbl-field">${t("f.party.code_label")}
        <span class="row tight"><input id="pt-code" class="field grow" readonly value="${esc(r.code)}"><button class="btn" id="pt-copy" type="button">${t("f.btn.copy")}</button><button class="btn" id="pt-copymsg" type="button">${t("f.party.copy_invite")}</button></span></label>
        <span class="muted small">${r.upnp ? t("f.party.upnp_ok", {port: esc(r.port || port)}) : (r.upnp === false ? t("f.party.upnp_fail") + " " : "") + (r.emulator === "eden" ? t("f.party.note_eden") : t("f.party.note_retro")) + " " + esc(r.port || port) + " " + t("f.party.router_tail")}</span>
        ${r.steps ? `<p class="muted small" id="pt-steps">${esc(r.steps)}</p><button class="btn" id="pt-close" type="button">${t("f.party.close_room")}</button>` : ""}`;
      if (r.steps) $("#pt-close").onclick = async () => { try { await partyApi("/api/party/close", {}); $("#pt-close").remove(); toast(t("f.party.room_closed")); } catch (e) { toast(e.message, true); } };
      $("#pt-copy").onclick = () => navigator.clipboard.writeText(r.code).then(() => toast(t("f.party.code_copied")), () => { $("#pt-code").select(); toast(t("f.party.copy_manual"), true); });
      $("#pt-copymsg").onclick = () => navigator.clipboard.writeText(r.message).then(() => toast(t("f.party.invite_copied")), () => toast(t("f.party.copy_fail"), true));
      $("#pt-code").select();
    } catch (e) {
      out.textContent = e.detail && e.detail.error === "no-netplay"
        ? t("f.party.only_retro_eden", {emu: e.detail.emulator || d.emulator || t("f.party.this_emu")})
        : partyMsg(e);
    }
  };
}

function openJoin() {
  $("#join-code").value = ""; $("#join-msg").textContent = "";
  const go = $("#join-go"); go.textContent = t("f.party.check_invite"); go.onclick = joinPreview;
  $("#join-dlg").showModal(); $("#join-code").focus();
}
function openJoinWith(code) {
  openJoin();
  $("#join-code").value = String(code).trim();
  joinPreview();
}
if (typeof window !== "undefined") window.openJoinWith = openJoinWith;
async function joinPreview() {
  const code = $("#join-code").value.trim(), msg = $("#join-msg"), go = $("#join-go");
  if (!code) return;
  try {
    const p = await partyApi("/api/party/preview", { code });
    if (!p.have) { msg.textContent = t("f.party.not_have", {title: p.title}); return; }
    msg.textContent = t("f.party.join_confirm", {nick: p.nick, title: p.title});
    go.textContent = t("f.party.enter");
    go.onclick = async () => {
      try {
        const r = await partyApi("/api/party/join", { code });
        if (r.prefilled === false) { msg.textContent = t("f.party.eden_manual"); return; }
        $("#join-dlg").close(); toast(r.steps ? t("f.party.started") + " · " + r.steps : t("f.party.started"));
      }
      catch (e) { msg.textContent = partyMsg(e); }
    };
  } catch (e) { msg.textContent = partyMsg(e); }
}

/* ------------------------------------------------------------------ perché non parte? */
/** riga segnaposto al posto dello spinner: GSSkeleton se caricato, altrimenti il testo di fallback */
function skelInline(el, count, fallbackHtml) {
  el.innerHTML = "";
  const layer = typeof window !== "undefined" && window.GSSkeleton && window.GSSkeleton.show(el, count);
  if (layer) layer.classList.add("dg-skel-line");
  else el.innerHTML = fallbackHtml;
}

/** HTML del pannello: la causa più probabile in cima, poi la checklist (✓ ok, ✗ con causa e rimedio); tutti i testi escapati */
function diagHtml(r) {
  const checks = Array.isArray(r.checks) ? r.checks : [];
  const p = Number.isInteger(r.probabile) && checks[r.probabile] ? checks[r.probabile] : null;
  const detail = (c) => `<div class="dg-causa">${esc(c.causa || "")}</div>${c.rimedio ? `<div class="dg-rimedio"><b>${t("f.diag.how_fix")}</b> ${esc(c.rimedio)}</div>` : ""}`;
  return (p ? `<section class="dg-probable"><h3>${t("f.diag.probable")}</h3><b>${esc(p.nome)}</b>${detail(p)}</section>` : "")
    + (r.ok ? `<p class="dg-ok">${t("f.diag.none")}</p>` : "")
    + `<ul class="dg-checks">${checks.map((c) => `<li class="dg-check ${c.ok ? "ok" : "ko"}">`
      + `<span class="dg-mark" aria-hidden="true">${c.ok ? "✓" : "✗"}</span>`
      + `<div><b>${esc(c.nome)}</b><span class="dg-sr">${c.ok ? " " + t("f.diag.ok") : " " + t("f.diag.problem")}</span>${c.ok ? "" : detail(c)}</div></li>`).join("")}</ul>`;
}

let diagSeq = 0;
/** apre il pannello «Perché non parte?» per il gioco `id` e ne carica la diagnosi */
async function openDiagnose(id) {
  let dlg = document.getElementById("diag-dlg");
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.id = "diag-dlg";
    dlg.className = "small-dlg";
    dlg.setAttribute("aria-labelledby", "diag-title");
    dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2 id="diag-title">${t("f.btn.diagnose")}</h2><button class="icon-btn" aria-label="${t("f.btn.close")}">✕</button></form><div class="dlg-body" id="diag-body" aria-live="polite"></div>`;
    document.body.appendChild(dlg);
  }
  const body = dlg.querySelector("#diag-body"), seq = ++diagSeq;
  if (!dlg.open) dlg.showModal();
  skelInline(body, 4, `<span class="muted small">${t("f.diag.checking")}</span>`);
  try {
    const r = await api(`/api/game/${id}/diagnose`);
    if (seq === diagSeq) body.innerHTML = diagHtml(r);
  } catch (e) {
    if (seq === diagSeq) body.innerHTML = `<p class="err" role="alert">${esc(e.message)}</p>`;
  }
}
if (typeof window !== "undefined") window.openDiagnose = openDiagnose;

// in node (test) il file si carica senza DOM
if (typeof document !== "undefined") document.addEventListener("click", (e) => {
  const t = e.target.closest && e.target.closest("#d-party, #join-btn, #d-play-fast, #d-diagnose");
  if (!t) return;
  if (t.id === "join-btn") openJoin();
  else if (t.id === "d-play-fast") { if (S.detail) play(S.detail.id, { fast: true }); } // stesso flusso di d-play (events.js)
  else if (t.id === "d-diagnose") { if (S.detail) openDiagnose(S.detail.id); }
  else if (S.detail) openParty(S.detail);
});

// all'apertura: se c'e' un invito in sospeso (incoming), propone di entrare
if (typeof document !== "undefined") { const pending = () => partyApi("/api/party").then((c) => { const code = c && c.incoming && c.incoming.code; if (code && typeof window.openJoinWith === "function") window.openJoinWith(code); }).catch(() => {}); if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", pending); else pending(); }
