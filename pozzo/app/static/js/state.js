"use strict";
/* Pozzo Launcher - frontend: stato della libreria, caricamento, filtri e ordinamenti. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */


const S = {
  games: [], groups: [], byId: new Map(), plats: new Map(), colls: [], collBySlug: new Map(),
  view: store.get("view", { type: "all" }),
  search: "", sort: store.get("sort", "title"), group: store.get("group", ""),
  oneVersion: store.get("oneVersion", true), zoom: store.get("zoom", 170),
  collSort: store.get("collSort", "name"), collFilter: "",
  items: [], rows: [], total: 0, cols: 1, tw: 170, th: 260, gap: 18, pad: 22,
  nodes: new Map(), selected: null, detail: null, running: null, openSeq: 0,
  instFilter: store.get("instFilter", "all"), stores: [],
  allLocal: store.get("allLocal", false), // Tutti i giochi: solo quelli presenti sul PC, divisi per console
  langFilter: store.get("language", ""),
  disc: store.get("disc", { preset: "", genre: "", decade: "" }),
  shopF: store.get("shopF", { src: "", plat: "", size: "", hideDlc: false }), shop: [], shopIds: new Set(),
};
const usesDrawer = () => GS.experience?.nav !== "sidebar"; // top e none aprono la navigazione come cassetto

// prima i giochi posseduti (pochi, subito), poi in sottofondo il catalogo degli store online
let onlineSeq = 0;
async function loadLibrary() {
  const seq = ++onlineSeq;
  const lib = await api("/api/library?part=owned");
  // stessa libreria (stessi id): il catalogo gia' caricato resta visibile finche' arriva quello nuovo
  const prev = lib.built_at === S.builtAt ? S.games.slice(S.nOwned?.[0] ?? S.games.length) : [];
  Object.assign(S, decodeLibrary(lib));
  S.nOwned = [S.games.length, S.groups.length];
  addOnline(prev);
  S.skipDup = lib.skip_duplicates !== false;
  S.hideDlc = new Set(lib.hide_dlc || []);
  S.userRev = lib.user_rev;
  S.metaRev = lib.meta_rev;
  S.catalogs = lib.catalogs || {};
  S.iconsCredit = lib.icons_credit || "";
  RECO.setPlatName(platName);
  S.smart = S.smart || [];
  libraryChanged();
  loadOnline(seq);
  return lib.games.rows.length > 0;
}

// store online cambiati (editor, Minerva, Link -> Store): rilegge solo {catalogs} e ridisegna barra e vista, senza riavvio
async function refreshCatalogs() {
  try { S.catalogs = (await api("/api/catalogs")).catalogs || {}; } catch { return; }
  renderSidebar();
  if (S.view.type === "platform") updateHeader();
}
window.addEventListener("pz-catalogs-changed", refreshCatalogs);

function libraryChanged() {
  renderLanguageFilter();
  S.shop = shopGames(S.games);
  renderDiscTools();
  S.shopIds = new Set(S.shop.map((g) => g.id));
  S.hasOnline = new Set(S.games.filter((g) => g.store === "online").map((g) => g.platform));
  GS.emit("libraryLoaded", S);
}

// accoda i giochi del catalogo dopo quelli posseduti, rinumerando i gruppi (gi) senza collisioni
function addOnline(games) {
  const gi = new Map();
  for (const g of games) {
    if (!gi.has(g.gi)) { gi.set(g.gi, S.groups.length); S.groups.push(g.grp); }
    g.gi = gi.get(g.gi);
    S.byId.set(g.id, g);
    S.games.push(g);
  }
}

async function loadOnline(seq) {
  if (S.games.length === S.nOwned[0]) loading(t("h.state.loadingStores"));
  try {
    const d = decodeLibrary(await api("/api/library?part=online"));
    if (seq !== onlineSeq) return; // nel frattempo la libreria e' stata ricaricata
    for (const g of S.games.slice(S.nOwned[0])) S.byId.delete(g.id);
    S.games.length = S.nOwned[0];
    S.groups.length = S.nOwned[1];
    addOnline(d.games);
    libraryChanged();
    renderSidebar();
    refreshGrid(true);
    if (S.view.type === "home") renderExperienceHome($("#plugin-view"));
  } catch (e) {
    if (seq === onlineSeq) toast(t("h.state.storesErr", {msg: e.message}), true);
  } finally {
    if (seq === onlineSeq) loading(null);
  }
}

function loading(text) {
  $("#loadbar").hidden = !text;
  $("#loadbar-text").textContent = text || "";
  if ($("#grid-scroll")) layout(); // segnaposto e messaggio "vuoto" seguono lo stato di caricamento
}

/* ------------------------------------------------------------------ filtri e ordinamento */
const platName = (id) => S.plats.get(id)?.name || id;
const gameLanguages = (g) => g.languageCodes || (g.languageCodes = GSLanguages.codes(g.title));

function renderLanguageFilter() {
  const select = $("#language-filter");
  if (!select) return;
  const languages = new Set();
  for (const game of S.games) for (const code of gameLanguages(game)) languages.add(code);
  if (typeof S.langFilter === "string" && S.langFilter) languages.add(S.langFilter);
  const options = [...languages].sort((a, b) => collator.compare(GSLanguages.label(a), GSLanguages.label(b)));
  select.innerHTML = `<option value="">${t("h.state.allLangs")}</option>${options.map((code) =>
    `<option value="${esc(code)}">${esc(GSLanguages.label(code))}</option>`).join("")}`;
  select.value = S.langFilter;
  if (!select.dataset.bound) {
    select.onchange = (event) => {
      S.langFilter = event.target.value;
      store.set("language", S.langFilter);
      refreshGrid();
    };
    select.dataset.bound = "true";
  }
}

// le applicazioni aggiunte a mano hanno questo genere (vedi build.py: APP_GENRE)
const APP_GENRE = "Applicazione";
const isApp = (g) => g.store === "manual" && String(g.genres || "").split(", ").includes(APP_GENRE);

// Giochi degli store (non posseduti) che appartengono a una collezione, per TITOLO: stesso titolo di un membro
// oppure titolo che inizia col nome della collezione (stessa euristica di build.compute_collections).
// shortcut: solo prefisso/titolo esatto (niente dati franchise per le voci online), da affinare se servono piu' match.
function collStoreIds(c) {
  if (S.collStoreFor !== S.shop) { S.collStoreFor = S.shop; S.collStore = new Map(); } // cache invalidata a ogni libraryChanged
  let ids = S.collStore.get(c.idx);
  if (!ids) {
    const name = fold(c.name), titles = new Set();
    for (const g of S.games) if (g.grp.colls.includes(c.idx)) titles.add(fold(g.title));
    ids = new Set();
    const seen = new Set();
    for (const g of S.shop) {
      if (g.grp.colls.includes(c.idx) || g.content === "dlc" || g.content === "extra" || seen.has(g.gi)) continue;
      const t = fold(g.title);
      if (titles.has(t) || (name.length >= 4 && (t === name || t.startsWith(name + " ")))) { ids.add(g.id); seen.add(g.gi); }
    }
    S.collStore.set(c.idx, ids);
  }
  return ids;
}

function inView(g, v) {
  const grp = g.grp;
  if (v.type === "shop") return S.shopIds.has(g.id);
  if (v.type === "collection" && g.store === "online") { const c = S.collBySlug.get(v.id); return !!c && collStoreIds(c).has(g.id); }
  if (g.store === "online" && v.type !== "platform") return false;
  if (v.type === "dups") return g.id !== grp.primary && !grp.hidden;
  if (S.oneVersion && g.id !== grp.primary && !(v.type === "store" && v.id !== "all")) return false;
  if (v.type !== "hidden" && grp.hidden) return false;
  switch (v.type) {
    case "favorites": return !!grp.favorite && (!v.plat || g.platform === v.plat);
    case "apps": return isApp(g);
    case "recent": return grp.last > 0;
    case "multi": return g.players >= 2;
    case "status": return (grp.status || "") === v.id;
    case "smart": { const sc = S.smart.find((x) => x.id === v.id); return !!sc && g.id === grp.primary && smartMatch(g, sc.rules); }
    case "platform": if (g.platform !== v.id) return false; break;
    case "store": if (g.platform !== "windows" || (v.id !== "all" && g.store !== v.id)) return false; break;
    case "collection": { const c = S.collBySlug.get(v.id); return !!c && (grp.colls.includes(c.idx) || (S.shopIds.has(g.id) && collStoreIds(c).has(g.id))); }
    case "missing": return !g.found;
    case "hidden": return !!grp.hidden;
    case "all": if (S.allLocal && g.store && !g.installed) return false; break; // le ROM sono sempre sul disco
    default: break;
  }
  if ((g.platform === "windows" || S.hasOnline?.has(g.platform)) && S.instFilter !== "all" && (v.type === "store" || v.type === "platform")) {
    return S.instFilter === "installed" ? !!g.installed : !g.installed;
  }
  return true;
}

const SORTS = {
  title: (a, b) => collator.compare(a.sort, b.sort),
  year: (a, b) => (a.year || 9999) - (b.year || 9999) || collator.compare(a.sort, b.sort),
  "-year": (a, b) => (b.year || 0) - (a.year || 0) || collator.compare(a.sort, b.sort),
  platform: (a, b) => collator.compare(platName(a.platform), platName(b.platform)) || collator.compare(a.sort, b.sort),
  "-last": (a, b) => b.grp.last - a.grp.last || collator.compare(a.sort, b.sort),
  "-playtime": (a, b) => b.grp.playtime - a.grp.playtime || collator.compare(a.sort, b.sort),
  "-rating": (a, b) => (b.rating ?? -1) - (a.rating ?? -1) || collator.compare(a.sort, b.sort),
  "-size": (a, b) => (b.size || 0) - (a.size || 0) || collator.compare(a.sort, b.sort),
  hltb: (a, b) => (a.hltb ?? 9999) - (b.hltb ?? 9999) || collator.compare(a.sort, b.sort),
  "-hltb": (a, b) => (b.hltb ?? -1) - (a.hltb ?? -1) || collator.compare(a.sort, b.sort),
  size: (a, b) => (a.size || Infinity) - (b.size || Infinity) || collator.compare(a.sort, b.sort),
  store: (a, b) => collator.compare(shopSource(a), shopSource(b)) || collator.compare(a.sort, b.sort),
  language: (a, b) => collator.compare(gameLanguages(a).map(GSLanguages.label).join(", "),
    gameLanguages(b).map(GSLanguages.label).join(", ")) || collator.compare(a.sort, b.sort),
};

function computeItems() {
  let it = S.games.filter((g) => inView(g, S.view));
  // DLC nascoste per console (check box nella vista della console) e aggiornamenti: mai come riquadri,
  // stanno tra i download del gioco base (vedi build.py: _attach_updates)
  // «Nascondi DLC»: via anche gli extra (temi, avatar, colonne sonore), che non sono giochi nemmeno loro
  it = it.filter((g) => g.content !== "update" && !((g.content === "dlc" || g.content === "extra") && S.hideDlc?.has(g.platform)));
  if (S.view.type === "shop") it = shopFilter(it, S.shopF);
  if (S.langFilter) it = it.filter((g) => gameLanguages(g).includes(S.langFilter));
  const d = discover(it, S.disc);
  it = d.items;
  S.discScore = d.preset.score || null;
  if (S.search) {
    const toks = fold(S.search).split(/\s+/).filter(Boolean);
    it = it.filter((g) => toks.every((t) => g.q.includes(t)));
  }
  it.sort(d.cmp && S.view.type !== "shop" ? d.cmp : SORTS[S.sort] || SORTS.title);
  const byDisc = !!d.cmp && S.view.type !== "shop";
  $("#sort").disabled = byDisc;
  $("#sort").title = byDisc ? t("h.state.sortByDisc") : t("h.state.sortTitle");
  S.items = it;
}

function sections(items) {
  const group = S.view.type === "all" && S.allLocal ? "platform" : S.group;
  if (!group) return [{ label: null, items }];
  const keyOf = {
    platform: (g) => platName(g.platform),
    year: (g) => (g.year ? String(g.year) : t("h.state.unknownYear")),
    letter: (g) => { const c = (g.sort || "#")[0].toUpperCase(); return /[A-Z]/.test(c) ? c : "#"; },
  }[group];
  const m = new Map();
  for (const g of items) { const k = keyOf(g); if (!m.has(k)) m.set(k, []); m.get(k).push(g); }
  const keys = [...m.keys()].sort((a, b) => collator.compare(a, b));
  return keys.map((k) => ({ label: k, items: m.get(k) }));
}
