"use strict";
/* Pozzo Launcher - frontend: barra laterale, intestazione, collezioni intelligenti. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ sidebar e intestazione */
function counts() {
  const c = { all: 0, fav: 0, recent: 0, missing: 0, hidden: 0, apps: 0,
    plat: new Map(), coll: new Map(), store: new Map(), favPlat: new Map() };
  for (const g of S.games) {
    const grp = g.grp;
    if (S.oneVersion && g.id !== grp.primary) continue;
    if (g.store === "online") continue; // disponibili online: non sono giochi posseduti
    if (grp.hidden) { c.hidden++; continue; }
    c.all++;
    if (isApp(g)) c.apps++;
    if (grp.favorite) {
      c.fav++;
      c.favPlat.set(g.platform, (c.favPlat.get(g.platform) || 0) + 1);
    }
    if (grp.last) c.recent++;
    if (!g.found) c.missing++;
    if (g.store) {
      const x = c.store.get(g.store) || { total: 0, inst: 0 };
      x.total++; if (g.installed) x.inst++;
      c.store.set(g.store, x);
    }
    c.plat.set(g.platform, (c.plat.get(g.platform) || 0) + 1);
    for (const i of grp.colls) c.coll.set(i, (c.coll.get(i) || 0) + 1);
  }
  return c;
}

/* console preferite: salvate in questo browser/app (come zoom e ordinamento) */
const favPlat = (id) => (store.get("favPlats", []).includes(id) ? 1 : 0);
function toggleFavPlat(id) {
  const cur = store.get("favPlats", []);
  store.set("favPlats", cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  renderSidebar();
}

/* estensioni preferite: salvate in store ("favExts") */
const favExt = (id) => (store.get("favExts", []).includes(id) ? 1 : 0);
function toggleFavExt(id) {
  const cur = store.get("favExts", []);
  store.set("favExts", cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  renderSidebar();
}
window.favExt = favExt;
window.toggleFavExt = toggleFavExt;

function openExtCtx(e, id) {
  if (id === "estensioni") return;
  closeCtx();
  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.innerHTML = `<div class="ci">${favExt(id) ? "★ " + t("h.fav.removeExt") : "☆ " + t("h.fav.addExt")}</div>`;
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + "px";
  m.onclick = (ev) => {
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    toggleFavExt(id);
  };
}

function openPlatCtx(e, id) {
  closeCtx();
  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.innerHTML = `<div class="ci">${favPlat(id) ? "★ " + t("h.fav.removePlat") : "☆ " + t("h.fav.addPlat")}</div>`
    + `<div class="ci" data-scan>⟳ ${t("h.scan.newGames")}</div>`;
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + "px";
  m.onclick = async (ev) => {
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    if (!("scan" in it.dataset)) return toggleFavPlat(id);
    try { await api("/api/scan", { body: { platforms: [id], mode: "new" } }); } catch (err) { return toast(err.message, true); }
    toast(t("h.scan.started"));
    SET.lastStatus = "running"; setScanRunning(true); pollScan();
  };
}

function renderSidebar() {
  const c = counts();
  $("#cnt-all").textContent = c.all.toLocaleString(GSI18n.lang);
  $("#cnt-fav").textContent = c.fav || "";
  $("#cnt-recent").textContent = c.recent || "";
  $("#cnt-apps").textContent = c.apps || "";
  $('[data-view="apps"]').hidden = !c.apps;
  // preferiti per console: una sotto-voce per le console che ne hanno almeno uno
  const favPlats = [...c.favPlat.entries()].sort((a, b) => collator.compare(platName(a[0]), platName(b[0])));
  $("#fav-plat-list").innerHTML = favPlats.map(([p, n]) =>
    `<a class="nav-item" data-view="favorites" data-plat="${esc(p)}" style="padding-left:28px" title="${t("h.nav.favTitle", {p: esc(platName(p))})}">`
    + `<span class="ico">${platIcon(p)}</span><span class="lbl">${esc(platName(p))}</span><span class="cnt">${n}</span></a>`).join("");
  renderStatusList();
  renderSmartList();
  $("#cnt-multi").textContent = S.games.filter((g) => g.id === g.grp.primary && !g.grp.hidden && g.players >= 2 && g.store !== "online").length || "";
  $("#cnt-shop").textContent = new Set(S.shop.map((g) => g.gi)).size || "";
  $("#cnt-missing").textContent = c.missing || "";
  $("#cnt-hidden").textContent = c.hidden || "";
  $("#cnt-dups").textContent = S.games.filter((g) => g.store !== "online" && g.id !== g.grp.primary).length || "";
  const plats = [...S.plats.values()].filter((p) => (c.plat.get(p.id) || S.catalogs[p.id]?.length) && p.id !== "windows").sort((a, b) => (favPlat(b.id) - favPlat(a.id)) || collator.compare(a.name, b.name)); // prima le preferite, poi A–Z
  $("#platform-list").innerHTML = plats.map((p) =>
    `<a class="nav-item" data-view="platform" data-id="${esc(p.id)}"><span class="ico">${platIcon(p.id)}</span>`
    + `<span class="lbl">${favPlat(p.id) ? "★ " : ""}${esc(p.name)}</span><span class="cnt">${c.plat.get(p.id)?.toLocaleString(GSI18n.lang) || ""}</span></a>`).join("");
  S.collCounts = c.coll;
  // PC: tutti + uno per store (installati / posseduti)
  const st = c.store;
  const pcTotal = [...st.values()].reduce((a, x) => a + x.total, 0);
  const pcInst = [...st.values()].reduce((a, x) => a + x.inst, 0);
  $("#store-list").innerHTML = (pcTotal ? `<a class="nav-item" data-view="store" data-id="all"><span class="ico">${platIcon("windows")}</span>`
    + `<span class="lbl">${t("h.nav.allPc")}</span><span class="cnt" title="${t("h.nav.instTotal")}">${pcInst} / ${pcTotal}</span></a>` : "")
    + S.stores.filter((x) => st.get(x.id)?.total).map((x) => `<a class="nav-item" data-view="store" data-id="${esc(x.id)}">`
      + `<span class="ico"><img class="pico" src="/icons/store/${esc(x.id)}" alt="" loading="lazy" onerror="this.replaceWith(document.createTextNode('${STORE_ICON[x.id] || "•"}'))"></span><span class="lbl">${esc(x.name)}</span>`
      + `<span class="cnt" title="${t("h.nav.instTotal")}">${st.get(x.id).inst} / ${st.get(x.id).total}</span></a>`).join("")
    || `<div class="muted small" style="padding:6px 8px">${t("h.nav.noStore")}</div>`;
  // Store estensioni sempre in cima alla sezione e non considerato tra i plugin ordinabili/preferiti
  const storeExt = GS.ui.sidebarItems.find((x) => x.id === "estensioni");
  const otherExts = GS.ui.sidebarItems.filter((x) => x.id !== "estensioni")
    .sort((a, b) => (favExt(b.id) - favExt(a.id)) || collator.compare(a.label || a.id, b.label || b.id));

  const storeHtml = storeExt ? `<a class="nav-item store-nav-item" data-plugin-item="estensioni" data-view="plugin" data-id="${esc(storeExt.view || 'estensioni')}"><span class="ico">${esc(storeExt.icon || "🧩")}</span><span class="lbl">${esc(storeExt.label || t("h.nav.storeExt"))}</span></a>` : "";

  const extsHtml = otherExts.map((x) => `<a class="nav-item" data-plugin-item="${esc(x.id)}"`
    + (x.view ? ` data-view="plugin" data-id="${esc(x.view)}"` : "") + `><span class="ico">${esc(x.icon || "✦")}</span>`
    + `<span class="lbl">${esc(x.label)}</span>`
    + `<button type="button" class="fav-star ${favExt(x.id) ? "is-fav" : ""}" data-toggle-fav-ext="${esc(x.id)}" title="${favExt(x.id) ? t("h.fav.remove") : t("h.fav.add")}" aria-label="${favExt(x.id) ? t("h.fav.remove") : t("h.fav.add")}">${favExt(x.id) ? "★" : "☆"}</button></a>`).join("");

  $("#plugin-nav").innerHTML = storeHtml + extsHtml;
  $("#plugin-nav-section").hidden = !GS.ui.sidebarItems.length;
  renderCollList();
  markActive();
}

function renderStatusList() {
  const n = {};
  for (const g of S.games) if (g.id === g.grp.primary && g.grp.status && !g.grp.hidden) n[g.grp.status] = (n[g.grp.status] || 0) + 1;
  $("#status-list").innerHTML = Object.entries(STATUS).map(([id, s]) =>
    `<a class="nav-item" data-view="status" data-id="${id}"><span class="ico">${s.icon}</span><span class="lbl">${s.label}</span>`
    + `<span class="cnt">${n[id] || ""}</span></a>`).join("");
}

function renderSmartList() {
  $("#smart-list").innerHTML = S.smart.map((x) => `<a class="nav-item" data-view="smart" data-id="${esc(x.id)}">`
    + `<span class="ico">${esc(x.icon || "⚡")}</span><span class="lbl" title="${esc(x.name)}">${esc(x.name)}</span>`
    + `<span class="cnt">${smartGames(S.games, x.rules).length}</span></a>`).join("")
    || `<div class="muted" style="padding:2px 8px 6px;font-size:12px">${t("h.smart.help")}</div>`;
  markActive();
}

/* ---- editor delle collezioni intelligenti */
let smEdit = null;
function openSmart(id = null) {
  const sc = S.smart.find((x) => x.id === id) || { id: "", name: "", icon: "⚡", rules: {} };
  smEdit = JSON.parse(JSON.stringify(sc));
  const r = smEdit.rules;
  $("#sm-title").textContent = id ? t("h.smart.editTitle") : t("h.smart.newTitle");
  $("#sm-name").value = sc.name;
  $("#sm-icon").value = sc.icon || "⚡";
  $("#sm-delete").hidden = !id;
  const chips = (el, list, key) => {
    $(el).innerHTML = list.map((o) => `<span class="sm-chip${(r[key] || []).includes(o.id) ? " on" : ""}" data-k="${key}" data-v="${esc(o.id)}">${esc(o.label)}</span>`).join("");
  };
  const plats = [...S.plats.values()].filter((p) => p.id !== "windows").sort((a, b) => collator.compare(a.name, b.name))
    .map((p) => ({ id: p.id, label: p.name }));
  chips("#sm-plats", plats.concat([{ id: "windows", label: t("h.smart.pcAll") }]), "platforms");
  chips("#sm-genres", Object.entries(RECO.GENRE_LABEL).map(([id, label]) => ({ id, label }))
    .sort((a, b) => collator.compare(a.label, b.label)), "genres");
  chips("#sm-status", Object.entries(STATUS).map(([k, s]) => ({ id: k, label: `${s.icon} ${s.label}` })).concat([{ id: "none", label: t("h.smart.noStatus") }]), "status");
  for (const k of ["minRating", "minCritics", "minPlayers", "yearFrom", "yearTo", "maxHours", "minHours"]) $(`#sm-${k}`).value = r[k] ?? "";
  for (const k of ["installed", "favorites", "unplayed"]) $(`#sm-${k}`).checked = !!r[k];
  smCount();
  $("#smart-dlg").showModal();
}
function smRead() {
  const r = smEdit.rules;
  for (const k of ["minRating", "minCritics", "minPlayers", "yearFrom", "yearTo", "maxHours", "minHours"]) {
    const v = $(`#sm-${k}`).value;
    if (v === "") delete r[k]; else r[k] = +v;
  }
  for (const k of ["installed", "favorites", "unplayed"]) { if ($(`#sm-${k}`).checked) r[k] = true; else delete r[k]; }
  return r;
}
function smCount() { $("#sm-count").textContent = t("h.smart.count", {n: smartGames(S.games, smRead()).length.toLocaleString(GSI18n.lang)}); }
async function saveSmart(remove = false) {
  smRead();
  smEdit.name = $("#sm-name").value.trim();
  smEdit.icon = $("#sm-icon").value.trim() || "⚡";
  if (!remove && !smEdit.name) return toast(t("h.smart.nameReq"), true);
  let items = S.smart.filter((x) => x.id !== smEdit.id);
  if (!remove) {
    if (!smEdit.id) smEdit.id = "s" + Date.now().toString(36);
    items = S.smart.some((x) => x.id === smEdit.id) ? S.smart.map((x) => (x.id === smEdit.id ? smEdit : x)) : S.smart.concat([smEdit]);
  }
  try { S.smart = (await api("/api/smart", { body: { items } })).items; } catch (e) { return toast(e.message, true); }
  $("#smart-dlg").close();
  renderSmartList();
  if (remove) setView({ type: "all" }); else setView({ type: "smart", id: smEdit.id });
}

function collIcon(slug) {
  // icona della collezione (logo da Wikipedia o dei suoi giochi); se manca, il simbolo di prima
  return `<img class="pico coll-ico" src="/coll-img/${encodeURIComponent(slug)}/icon?w=64" alt="" loading="lazy" onerror="this.outerHTML='❖'">`;
}

function renderCollBanner() {
  const b = $("#coll-banner");
  const c = S.view.type === "collection" ? S.collBySlug.get(S.view.id) : null;
  b.hidden = !c;
  if (!c) return;
  const slug = encodeURIComponent(c.slug);
  b.innerHTML = `<div class="cb-bg" style="background-image:url('/coll-img/${slug}/cover?w=1600')"></div>
    <div class="cb-content"><img class="cb-icon" src="/coll-img/${slug}/icon?w=256" alt="" onerror="this.remove()">
      <div><div class="cb-kicker">${c.custom ? t("h.coll.yours") : t("h.coll.coll")}</div><h2>${esc(c.name)}</h2>
      <div class="muted">${S.items.length.toLocaleString(GSI18n.lang)} ${S.items.length === 1 ? t("h.game.one") : t("h.game.many")}</div></div></div>`;
}

function renderCollList() {
  const f = fold(S.collFilter);
  let list = S.colls.filter((x) => !x.hidden && (S.collCounts.get(x.idx) || x.custom) && (!f || fold(x.name).includes(f)));
  if (S.collSort === "count") list.sort((a, b) => (S.collCounts.get(b.idx) || 0) - (S.collCounts.get(a.idx) || 0) || collator.compare(a.name, b.name));
  else list.sort((a, b) => collator.compare(a.name, b.name));
  $("#coll-list").innerHTML = list.map((x) =>
    `<a class="nav-item" data-view="collection" data-id="${esc(x.slug)}"><span class="ico">${collIcon(x.slug)}</span><span class="lbl" title="${esc(x.name)}">${esc(x.name)}</span>`
    + (x.custom ? `<span class="tag">${t("h.coll.mine")}</span>` : "") + `<span class="cnt">${S.collCounts.get(x.idx) || 0}</span></a>`).join("")
    || `<div class="muted" style="padding:6px 8px;font-size:12px">${t("h.coll.none")}</div>`;
  markActive();
}

function markActive() {
  document.querySelectorAll("#nav .nav-item").forEach((a) => {
    const on = a.dataset.view === S.view.type && (a.dataset.id || null) === (S.view.id || null)
      && (a.dataset.plat || null) === (S.view.plat || null);
    a.tabIndex = 0;
    a.setAttribute("role", "button");
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  document.querySelectorAll("#experience-nav [data-view]").forEach((a) => {
    const on = a.dataset.view === S.view.type;
    a.classList.toggle("active", on);
    if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}

function setDrawer(open, restoreFocus = true) {
  if (!usesDrawer()) return;
  const aside = $("#sidebar"), toggle = $("#drawer-toggle");
  aside.classList.toggle("drawer-open", open);
  toggle.setAttribute("aria-expanded", String(open));
  $("#drawer-scrim").hidden = !open;
  if (open) $("#nav .nav-item:not([hidden])")?.focus();
  else if (restoreFocus) toggle.focus();
}

function renderDiscTools() {
  const f = S.disc, opt = (v, l, sel, t = "") => `<option value="${esc(v)}"${String(v) === String(sel) ? " selected" : ""}${t ? ` title="${esc(t)}"` : ""}>${esc(l)}</option>`;
  const nCrit = S.games.filter((g) => g.critics != null).length;
  $("#disc-preset").innerHTML = PRESETS.map((p) => opt(p.id, p.id === "critics" ? t("h.disc.withScore", {l: p.label, n: nCrit}) : p.label, f.preset, p.hint)).join("");
  $("#disc-genre").innerHTML = opt("", t("h.disc.allGenres"), f.genre) + genreList(S.games).map((x) => opt(x.id, x.label, f.genre)).join("");
  $("#disc-decade").innerHTML = opt("", t("h.disc.allYears"), f.decade) + decadeList(S.games).map((d) => opt(d, t("h.disc.decade", {y: String(d).slice(2), full: d}), f.decade)).join("");
  for (const k of ["preset", "genre", "decade"]) $(`#disc-${k}`).classList.toggle("on", !!f[k]);
  $("#disc-reset").hidden = !(f.preset || f.genre || f.decade);
}

function renderShopTools() {
  const on = S.view.type === "shop";
  $("#shop-tools").hidden = !on;
  $("#group").hidden = $("#one-version").parentElement.hidden = on;
  if (!on) return;
  const f = S.shopF, opt = (v, l, sel) => `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(l)}</option>`;
  $("#shop-src").innerHTML = opt("", t("h.shop.allStores"), f.src)
    + shopSources(S.shop, S.stores, platName).map((s) => opt(s.id, `${s.label} (${s.n})`, f.src)).join("");
  const pl = [...new Set(S.shop.map((g) => g.platform))].sort((a, b) => collator.compare(platName(a), platName(b)));
  $("#shop-plat").innerHTML = opt("", t("h.shop.allPlat"), f.plat) + pl.map((p) => opt(p, platName(p), f.plat)).join("");
  $("#shop-size").innerHTML = SHOP_SIZES.map((s) => opt(s.id, s.label, f.size)).join("");
}

function viewTitle() {
  const v = S.view;
  if (v.type === "favorites" && v.plat) return `★ ${t("h.app.navFavorites")} · ${platName(v.plat)}`;
  if (v.type === "apps") return "🧩 " + t("h.title.apps");
  return { shots: t("h.title.shots"), free: t("h.title.free"), ports: t("h.title.ports"), wishlist: t("h.wl.title"), stats: t("h.title.stats"), downloads: t("h.title.downloads"),
    top: !v.id || v.id === "all" ? "🏆 " + t("h.title.topBest") : `🏆 ${t("h.title.top100Of", {p: platName(v.id)})}`,
    status: `${STATUS[v.id]?.icon || ""} ${STATUS[v.id]?.label || ""}`,
    smart: `${S.smart.find((x) => x.id === v.id)?.icon || "⚡"} ${S.smart.find((x) => x.id === v.id)?.name || t("h.coll.coll")}`,
    home: t("h.app.navHome"), foryou: t("h.title.foryou"), multi: t("h.title.multi"), shop: t("h.title.shop"), all: t("h.app.navAllGames"), favorites: t("h.app.navFavorites"), recent: t("h.title.recent"), missing: t("h.title.noData"),
    hidden: t("h.title.hidden"), dups: t("h.title.dups"), platform: platName(v.id), collection: S.collBySlug.get(v.id)?.name || t("h.coll.coll"),
    store: v.id === "all" ? t("h.title.pcGames") : t("h.title.pcStore", {n: S.stores.find((x) => x.id === v.id)?.name || v.id}),
    plugin: GS.ui.views.get(v.id)?.title || t("h.title.plugin") }[v.type] || t("h.title.games");
}

function updateHeader() {
  $("#view-title").textContent = viewTitle();
  const n = S.items.length;
  let extra = "";
  if (S.view.type === "collection") {
    const plats = new Set(S.items.map((g) => g.platform)).size;
    extra = ` ${t("h.hdr.onPlatforms", {n: plats})}`;
  }
  $("#view-count").textContent = S.view.type === "plugin" ? "" : `${n.toLocaleString(GSI18n.lang)} ${n === 1 ? t("h.game.one") : t("h.game.many")}${extra}`;
  renderShopTools();
  $("#group").disabled = S.view.type === "all" && S.allLocal; // la vista «Sul PC» e' gia' divisa per console
  $("#inst-filter").hidden = !(S.view.type === "store" || (S.view.type === "platform" && (S.view.id === "windows" || S.hasOnline.has(S.view.id))));
  const c = S.view.type === "collection" ? S.collBySlug.get(S.view.id) : null;
  $("#view-actions").innerHTML = c
    ? `<button class="icon-btn" id="coll-rename" title="${t("h.coll.rename")}">✎ ${t("h.coll.rename")}</button>`
      + `<button class="icon-btn" id="coll-delete" title="${c.custom ? t("h.lb.delete") : t("h.coll.hide")}">${c.custom ? "🗑 " + t("h.lb.delete") : "⊘ " + t("h.coll.hide")}</button>`
    : S.view.type === "dups"
      ? `<button class="icon-btn" id="dup-toggle" title="${t("h.dups.help")}">`
        + `${S.skipDup ? "✓ " + t("h.dups.excluded") : "✗ " + t("h.dups.included")} ${t("h.dups.clickChange")}</button>`
    : S.view.type === "all"
      ? `<button class="icon-btn${S.allLocal ? " on" : ""}" id="all-local" title="${t("h.all.localHelp")}">`
        + `💾 ${t("h.all.localBtn")}${S.allLocal ? " ✓" : ""}</button>`
    : S.view.type === "smart"
      ? `<button class="icon-btn" id="smart-edit" title="${t("h.smart.editRules")}">✎ ${t("h.smart.rules")}</button>`
    : S.view.type === "store"
      ? `<button class="icon-btn" id="plat-scan" title="${t("h.scan.storeHelp", {w: S.view.id === "all" ? t("h.scan.pcStores") : t("h.scan.thisStore")})}">⟳ ${t("h.scan.newGames")}</button>`
    : S.view.type === "shop"
      ? `<button class="icon-btn${S.shopF.hideDlc ? " on" : ""}" id="shop-hide-dlc" title="${t("h.shop.excludeHelp")}">`
        + `${S.shopF.hideDlc ? "✓ " + t("h.shop.dlcOut") : "⊘ " + t("h.shop.excludeDlc")}</button>`
        + `<button class="btn smeta-btn" id="smeta-open" title="${t("h.shop.smetaHelp")}">📚 ${t("h.shop.smeta")} <span class="pill">${t("h.common.offline")}</span></button>`
    : S.view.type === "platform" && S.view.id !== "windows"
      ? `<label class="icon-btn" title="${t("h.plat.hideDlcHelp")}">`
        + `<input type="checkbox" id="hide-dlc"${S.hideDlc?.has(S.view.id) ? " checked" : ""}> ${t("h.plat.hideDlc")}</label>`
        + `<button class="icon-btn" id="plat-scan" title="${t("h.scan.consoleHelp")}">⟳ ${t("h.scan.newGames")}</button>`
        + `<button class="icon-btn" id="top-open" title="${t("h.plat.topHelp")}">🏆 Top 100</button>`
        + `<button class="icon-btn" id="cat-open" title="${t("h.plat.catHelp")}">`
        + ((S.catalogs[S.view.id] || []).map((u) => `<img class="sico" src="/icons/site?url=${encodeURIComponent(u)}" alt="">`).join("") || "🌐")
        + ` ${t("h.plat.onlineStore")}${(S.catalogs[S.view.id] || []).length ? ` (${S.catalogs[S.view.id].length})` : ""}</button>` : "";
}

function setView(v) {
  if (v.type === "home" && typeof GS.experience?.home !== "function") v = { type: "all" };
  const wasHome = S.view.type === "home", same = JSON.stringify(S.view) === JSON.stringify(v);
  S.view = v;
  setDrawer(false, false);
  // la finestra Media separata non deve sovrascrivere la vista da riaprire all'avvio della finestra principale
  if (!document.body.classList.contains("media-window")) {
    store.set("view", v);
    try { localStorage.setItem("gs.last_session", JSON.stringify({ view: v, gameId: S.selected || null, timestamp: Date.now() })); } catch {}
  }
  GS.emit("viewChanged", v);
  document.body.classList.toggle("experience-home-mode", v.type === "home");
  const pv = $("#plugin-view");
  if (v.type === "home") pv.className = "experience-home";
  else if (wasHome) pv.className = "";
  document.body.classList.toggle("foryou-mode", ["foryou", "free", "ports", "wishlist", "stats", "shots", "top", "downloads"].includes(v.type));
  if (v.type !== "collection") $("#coll-banner").hidden = true;
  if (!same) queueMicrotask(() => window.GSMotion?.enter(pv.hidden ? $("#grid-scroll") : pv));
  if (v.type === "home") {
    $("#grid-scroll").hidden = true;
    pv.hidden = false;
    markActive();
    updateHeader();
    $("#view-count").textContent = "";
    renderExperienceHome(pv);
    return;
  }
  if (["free", "ports", "wishlist", "stats", "shots", "top", "downloads"].includes(v.type)) {
    $("#grid-scroll").hidden = true;
    pv.hidden = false;
    markActive();
    updateHeader();
    $("#view-count").textContent = "";
    ({ free: renderFree, ports: renderPorts, wishlist: renderWishlist, stats: renderStats, shots: renderShots, top: renderTop, downloads: renderDownloads })[v.type](pv);
    return;
  }
  if (v.type === "foryou") {
    $("#grid-scroll").hidden = true;
    pv.hidden = false;
    markActive();
    updateHeader();
    $("#view-count").textContent = "";
    renderForYou(pv);
    return;
  }
  if (v.type === "plugin") {
    const view = GS.ui.views.get(v.id);
    $("#grid-scroll").hidden = true;
    pv.hidden = false;
    pv.innerHTML = "";
    markActive();
    updateHeader();
    Promise.resolve(view ? view.render(pv, GS) : (pv.textContent = t("h.view.unavailable")))
      .catch((e) => { pv.textContent = t("h.view.error", {msg: e.message}); });
    return;
  }
  $("#grid-scroll").hidden = false;
  pv.hidden = true;
  const def = { recent: "-last", collection: "year", shop: "title" }[v.type];
  setTimeout(renderCollBanner, 0);
  // l'ordine scelto dall'utente vale per tipo di vista; il default forzato (recenti, collezione, store) solo finché non sceglie
  S.sort = store.get("sorts", {})[v.type] || def || store.get("sort", "title");
  if (![...$("#sort").options].some((o) => o.value === S.sort)) S.sort = def || "title";
  $("#sort").value = S.sort;
  markActive();
  refreshGrid();
}
