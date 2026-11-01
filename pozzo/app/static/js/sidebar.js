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

function openPlatCtx(e, id) {
  closeCtx();
  const m = document.createElement("div");
  m.id = "ctxmenu";
  m.innerHTML = `<div class="ci">${favPlat(id) ? "★ Togli dalle console preferite" : "☆ Aggiungi alle console preferite"}</div>`
    + `<div class="ci" data-scan>⟳ Cerca nuovi giochi</div>`;
  document.body.appendChild(m);
  m.style.left = Math.max(6, Math.min(e.clientX, innerWidth - m.offsetWidth - 8)) + "px";
  m.style.top = Math.max(6, Math.min(e.clientY, innerHeight - m.offsetHeight - 8)) + "px";
  m.onclick = async (ev) => {
    const it = ev.target.closest(".ci");
    if (!it) return;
    closeCtx();
    if (!("scan" in it.dataset)) return toggleFavPlat(id);
    try { await api("/api/scan", { body: { platforms: [id], mode: "new" } }); } catch (err) { return toast(err.message, true); }
    toast("Cerco i giochi nuovi: compaiono subito, i dati arrivano dopo");
    SET.lastStatus = "running"; setScanRunning(true); pollScan();
  };
}

function renderSidebar() {
  const c = counts();
  $("#cnt-all").textContent = c.all.toLocaleString("it");
  $("#cnt-fav").textContent = c.fav || "";
  $("#cnt-recent").textContent = c.recent || "";
  $("#cnt-apps").textContent = c.apps || "";
  $('[data-view="apps"]').hidden = !c.apps;
  // preferiti per console: una sotto-voce per le console che ne hanno almeno uno
  const favPlats = [...c.favPlat.entries()].sort((a, b) => collator.compare(platName(a[0]), platName(b[0])));
  $("#fav-plat-list").innerHTML = favPlats.map(([p, n]) =>
    `<a class="nav-item" data-view="favorites" data-plat="${esc(p)}" style="padding-left:28px" title="Preferiti · ${esc(platName(p))}">`
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
    + `<span class="lbl">${favPlat(p.id) ? "★ " : ""}${esc(p.name)}</span><span class="cnt">${c.plat.get(p.id)?.toLocaleString("it") || ""}</span></a>`).join("");
  S.collCounts = c.coll;
  // PC: tutti + uno per store (installati / posseduti)
  const st = c.store;
  const pcTotal = [...st.values()].reduce((a, x) => a + x.total, 0);
  const pcInst = [...st.values()].reduce((a, x) => a + x.inst, 0);
  $("#store-list").innerHTML = (pcTotal ? `<a class="nav-item" data-view="store" data-id="all"><span class="ico">${platIcon("windows")}</span>`
    + `<span class="lbl">Tutti i giochi PC</span><span class="cnt" title="installati / totali">${pcInst} / ${pcTotal}</span></a>` : "")
    + S.stores.filter((x) => st.get(x.id)?.total).map((x) => `<a class="nav-item" data-view="store" data-id="${esc(x.id)}">`
      + `<span class="ico"><img class="pico" src="/icons/store/${esc(x.id)}" alt="" loading="lazy" onerror="this.replaceWith(document.createTextNode('${STORE_ICON[x.id] || "•"}'))"></span><span class="lbl">${esc(x.name)}</span>`
      + `<span class="cnt" title="installati / totali">${st.get(x.id).inst} / ${st.get(x.id).total}</span></a>`).join("")
    || `<div class="muted small" style="padding:6px 8px">Nessuno store collegato: vedi Impostazioni › Account</div>`;
  $("#plugin-nav").innerHTML = GS.ui.sidebarItems.map((x) => `<a class="nav-item" data-plugin-item="${esc(x.id)}"`
    + (x.view ? ` data-view="plugin" data-id="${esc(x.view)}"` : "") + `><span class="ico">${esc(x.icon || "✦")}</span>`
    + `<span class="lbl">${esc(x.label)}</span></a>`).join("");
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
    || `<div class="muted" style="padding:2px 8px 6px;font-size:12px">Regole salvate che si aggiornano da sole</div>`;
  markActive();
}

/* ---- editor delle collezioni intelligenti */
let smEdit = null;
function openSmart(id = null) {
  const sc = S.smart.find((x) => x.id === id) || { id: "", name: "", icon: "⚡", rules: {} };
  smEdit = JSON.parse(JSON.stringify(sc));
  const r = smEdit.rules;
  $("#sm-title").textContent = id ? "Modifica collezione intelligente" : "Nuova collezione intelligente";
  $("#sm-name").value = sc.name;
  $("#sm-icon").value = sc.icon || "⚡";
  $("#sm-delete").hidden = !id;
  const chips = (el, list, key) => {
    $(el).innerHTML = list.map((o) => `<span class="sm-chip${(r[key] || []).includes(o.id) ? " on" : ""}" data-k="${key}" data-v="${esc(o.id)}">${esc(o.label)}</span>`).join("");
  };
  const plats = [...S.plats.values()].filter((p) => p.id !== "windows").sort((a, b) => collator.compare(a.name, b.name))
    .map((p) => ({ id: p.id, label: p.name }));
  chips("#sm-plats", plats.concat([{ id: "windows", label: "PC (tutti gli store)" }]), "platforms");
  chips("#sm-genres", Object.entries(RECO.GENRE_LABEL).map(([id, label]) => ({ id, label }))
    .sort((a, b) => collator.compare(a.label, b.label)), "genres");
  chips("#sm-status", Object.entries(STATUS).map(([k, s]) => ({ id: k, label: `${s.icon} ${s.label}` })).concat([{ id: "none", label: "Senza stato" }]), "status");
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
function smCount() { $("#sm-count").textContent = `${smartGames(S.games, smRead()).length.toLocaleString("it")} giochi`; }
async function saveSmart(remove = false) {
  smRead();
  smEdit.name = $("#sm-name").value.trim();
  smEdit.icon = $("#sm-icon").value.trim() || "⚡";
  if (!remove && !smEdit.name) return toast("Dai un nome alla collezione", true);
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
      <div><div class="cb-kicker">${c.custom ? "La tua collezione" : "Collezione"}</div><h2>${esc(c.name)}</h2>
      <div class="muted">${S.items.length.toLocaleString("it")} ${S.items.length === 1 ? "gioco" : "giochi"}</div></div></div>`;
}

function renderCollList() {
  const f = fold(S.collFilter);
  let list = S.colls.filter((x) => !x.hidden && (S.collCounts.get(x.idx) || x.custom) && (!f || fold(x.name).includes(f)));
  if (S.collSort === "count") list.sort((a, b) => (S.collCounts.get(b.idx) || 0) - (S.collCounts.get(a.idx) || 0) || collator.compare(a.name, b.name));
  else list.sort((a, b) => collator.compare(a.name, b.name));
  $("#coll-list").innerHTML = list.map((x) =>
    `<a class="nav-item" data-view="collection" data-id="${esc(x.slug)}"><span class="ico">${collIcon(x.slug)}</span><span class="lbl" title="${esc(x.name)}">${esc(x.name)}</span>`
    + (x.custom ? `<span class="tag">mia</span>` : "") + `<span class="cnt">${S.collCounts.get(x.idx) || 0}</span></a>`).join("")
    || `<div class="muted" style="padding:6px 8px;font-size:12px">Nessuna collezione</div>`;
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
  $("#disc-preset").innerHTML = PRESETS.map((p) => opt(p.id, p.id === "critics" ? `${p.label} (${nCrit} con voto)` : p.label, f.preset, p.hint)).join("");
  $("#disc-genre").innerHTML = opt("", "Tutti i generi", f.genre) + genreList(S.games).map((x) => opt(x.id, x.label, f.genre)).join("");
  $("#disc-decade").innerHTML = opt("", "Tutti gli anni", f.decade) + decadeList(S.games).map((d) => opt(d, `Anni ${String(d).slice(2)} (${d})`, f.decade)).join("");
  for (const k of ["preset", "genre", "decade"]) $(`#disc-${k}`).classList.toggle("on", !!f[k]);
  $("#disc-reset").hidden = !(f.preset || f.genre || f.decade);
}

function renderShopTools() {
  const on = S.view.type === "shop";
  $("#shop-tools").hidden = !on;
  $("#group").hidden = $("#one-version").parentElement.hidden = on;
  if (!on) return;
  const f = S.shopF, opt = (v, l, sel) => `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(l)}</option>`;
  $("#shop-src").innerHTML = opt("", "Tutti gli store", f.src)
    + shopSources(S.shop, S.stores, platName).map((s) => opt(s.id, `${s.label} (${s.n})`, f.src)).join("");
  const pl = [...new Set(S.shop.map((g) => g.platform))].sort((a, b) => collator.compare(platName(a), platName(b)));
  $("#shop-plat").innerHTML = opt("", "Tutte le piattaforme", f.plat) + pl.map((p) => opt(p, platName(p), f.plat)).join("");
  $("#shop-size").innerHTML = SHOP_SIZES.map((s) => opt(s.id, s.label, f.size)).join("");
}

function viewTitle() {
  const v = S.view;
  if (v.type === "favorites" && v.plat) return `★ Preferiti · ${platName(v.plat)}`;
  if (v.type === "apps") return "🧩 Applicazioni";
  return { shots: "Schermate", free: "Giochi gratis", ports: "Port e app", wishlist: "Lista desideri", stats: "Statistiche",
    top: !v.id || v.id === "all" ? "🏆 Migliori giochi" : `🏆 Top 100 · ${platName(v.id)}`,
    status: `${STATUS[v.id]?.icon || ""} ${STATUS[v.id]?.label || ""}`,
    smart: `${S.smart.find((x) => x.id === v.id)?.icon || "⚡"} ${S.smart.find((x) => x.id === v.id)?.name || "Collezione"}`,
    home: "Home", foryou: "Per te", multi: "Multigiocatore in locale", shop: "Store · da installare", all: "Tutti i giochi", favorites: "Preferiti", recent: "Giocati di recente", missing: "Senza dati",
    hidden: "Nascosti", dups: "Duplicati", platform: platName(v.id), collection: S.collBySlug.get(v.id)?.name || "Collezione",
    store: v.id === "all" ? "Giochi PC" : `PC · ${S.stores.find((x) => x.id === v.id)?.name || v.id}`,
    plugin: GS.ui.views.get(v.id)?.title || "Estensione" }[v.type] || "Giochi";
}

function updateHeader() {
  $("#view-title").textContent = viewTitle();
  const n = S.items.length;
  let extra = "";
  if (S.view.type === "collection") {
    const plats = new Set(S.items.map((g) => g.platform)).size;
    extra = ` su ${plats} ${plats === 1 ? "console" : "console"}`;
  }
  $("#view-count").textContent = S.view.type === "plugin" ? "" : `${n.toLocaleString("it")} ${n === 1 ? "gioco" : "giochi"}${extra}`;
  renderShopTools();
  $("#group").disabled = S.view.type === "all" && S.allLocal; // la vista «Sul PC» e' gia' divisa per console
  $("#inst-filter").hidden = !(S.view.type === "store" || (S.view.type === "platform" && (S.view.id === "windows" || S.hasOnline.has(S.view.id))));
  const c = S.view.type === "collection" ? S.collBySlug.get(S.view.id) : null;
  $("#view-actions").innerHTML = c
    ? `<button class="icon-btn" id="coll-rename" title="Rinomina">✎ Rinomina</button>`
      + `<button class="icon-btn" id="coll-delete" title="${c.custom ? "Elimina" : "Nascondi"}">${c.custom ? "🗑 Elimina" : "⊘ Nascondi"}</button>`
    : S.view.type === "dups"
      ? `<button class="icon-btn" id="dup-toggle" title="Le versioni duplicate prendono i metadati dalla versione principale">`
        + `${S.skipDup ? "✓ Esclusi dallo scraping" : "✗ Inclusi nello scraping"} (clic per cambiare)</button>`
    : S.view.type === "all"
      ? `<button class="icon-btn${S.allLocal ? " on" : ""}" id="all-local" title="Solo i giochi scaricati sul PC (ROM e giochi PC installati), divisi per console">`
        + `💾 Sul PC · per console${S.allLocal ? " ✓" : ""}</button>`
    : S.view.type === "smart"
      ? `<button class="icon-btn" id="smart-edit" title="Modifica le regole">✎ Regole</button>`
    : S.view.type === "store"
      ? `<button class="icon-btn" id="plat-scan" title="Rilegge ${S.view.id === "all" ? "gli store PC" : "questo store"} e i giochi aggiunti a mano: i giochi nuovi compaiono subito">⟳ Cerca nuovi giochi</button>`
    : S.view.type === "shop"
      ? `<button class="icon-btn${S.shopF.hideDlc ? " on" : ""}" id="shop-hide-dlc" title="Esclude le voci classificate come DLC">`
        + `${S.shopF.hideDlc ? "✓ DLC escluse" : "⊘ Escludi DLC"}</button>`
        + `<button class="btn smeta-btn" id="smeta-open" title="Cerca descrizioni, generi, giocatori e valutazioni dei giochi degli store SOLO nei database offline (LaunchBox, TheGamesDB): nessuna richiesta online">📚 Scraping metadati store <span class="pill">offline</span></button>`
    : S.view.type === "platform" && S.view.id !== "windows"
      ? `<label class="icon-btn" title="Nascondi DLC, temi e avatar di questa console: le DLC restano comunque tra i download del gioco base">`
        + `<input type="checkbox" id="hide-dlc"${S.hideDlc?.has(S.view.id) ? " checked" : ""}> Nascondi DLC</label>`
        + `<button class="icon-btn" id="plat-scan" title="Cerca nuovi giochi nella cartella di questa console: compaiono subito, i dati arrivano dopo">⟳ Cerca nuovi giochi</button>`
        + `<button class="icon-btn" id="top-open" title="I 100 migliori giochi di questa console, posseduti e scaricabili">🏆 Top 100</button>`
        + `<button class="icon-btn" id="cat-open" title="Collega pagine web con i giochi di questa console">`
        + ((S.catalogs[S.view.id] || []).map((u) => `<img class="sico" src="/icons/site?url=${encodeURIComponent(u)}" alt="">`).join("") || "🌐")
        + ` Store online${(S.catalogs[S.view.id] || []).length ? ` (${S.catalogs[S.view.id].length})` : ""}</button>` : "";
}

function setView(v) {
  if (v.type === "home" && typeof GS.experience?.home !== "function") v = { type: "all" };
  const wasHome = S.view.type === "home", same = JSON.stringify(S.view) === JSON.stringify(v);
  S.view = v;
  setDrawer(false, false);
  store.set("view", v);
  GS.emit("viewChanged", v);
  document.body.classList.toggle("experience-home-mode", v.type === "home");
  const pv = $("#plugin-view");
  if (v.type === "home") pv.className = "experience-home";
  else if (wasHome) pv.className = "";
  document.body.classList.toggle("foryou-mode", ["foryou", "free", "ports", "wishlist", "stats", "shots", "top"].includes(v.type));
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
  if (["free", "ports", "wishlist", "stats", "shots", "top"].includes(v.type)) {
    $("#grid-scroll").hidden = true;
    pv.hidden = false;
    markActive();
    updateHeader();
    $("#view-count").textContent = "";
    ({ free: renderFree, ports: renderPorts, wishlist: renderWishlist, stats: renderStats, shots: renderShots, top: renderTop })[v.type](pv);
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
    Promise.resolve(view ? view.render(pv, GS) : (pv.textContent = "Vista non disponibile"))
      .catch((e) => { pv.textContent = "Errore nella vista: " + e.message; });
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
