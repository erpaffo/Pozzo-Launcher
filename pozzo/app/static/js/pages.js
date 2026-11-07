"use strict";
/* Pozzo Launcher - frontend: pagine: lista dei desideri, statistiche, top, schermate, profilo di avvio. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* Segnaposto mentre la pagina aspetta i dati (GSSkeleton, motion-settings.js): forma e numero per pagina.
   Se la pagina e' gia' a schermo (refresh dopo un'azione) il contenuto resta finche' arrivano i dati, senza sfarfallio. */
const PAGE_SKEL = {
  wishlist: { n: 6, cols: "1fr", gap: 6, h: "84px" },
  stats: { n: 6, cols: "repeat(auto-fill, minmax(180px, 1fr))", h: "78px" },
  top: { n: 10, cols: "1fr", gap: 4, h: "44px" },
  shots: { n: 12, cols: "repeat(auto-fill, minmax(240px, 1fr))", ratio: "16 / 9" },
};
function pageSkeleton(pv, key) {
  if (!window.GSSkeleton || pv.firstElementChild?.dataset.view === key) return;
  const c = PAGE_SKEL[key];
  pv.innerHTML = `<div class="page" data-view="${key}" style="position:relative;min-height:60vh"></div>`;
  const layer = window.GSSkeleton.show(pv.firstElementChild, c.n);
  layer.style.gridTemplateColumns = c.cols;
  if (c.gap) layer.style.gap = c.gap + "px";
  for (const it of layer.children) { it.style.aspectRatio = c.ratio || "auto"; if (c.h) it.style.height = c.h; }
}

/* ---- pagina: lista dei desideri */
async function renderWishlist(pv) {
  pageSkeleton(pv, "wishlist");
  let d;
  try { d = await api("/api/wishlist"); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  const money = (v, cur = "EUR") => (v == null ? "—" : v === 0 ? t("h.wl.free") : v.toLocaleString(GSI18n.lang, { style: "currency", currency: cur || "EUR" }));
  // header.jpg esiste per ogni gioco Steam; senza codice Steam (o se manca) si usa la copertina salvata alla ricerca
  const steamImg = (w) => remoteImg(w.steam_appid ? `https://cdn.cloudflare.steamstatic.com/steam/apps/${w.steam_appid}/header.jpg` : w.cover);
  const imgTag = (w) => (steamImg(w) ? `<img src="${steamImg(w)}" alt="" data-fb="${w.steam_appid && w.cover ? remoteImg(w.cover) : ""}" onerror="if(this.dataset.fb){this.src=this.dataset.fb;this.dataset.fb=''}else this.remove()">` : "");
  const s = d.settings;
  pv.innerHTML = `<div class="page" data-view="wishlist">
    <div class="page-head"><div><h2>♡ ${t("h.wl.title")}</h2>
      <p class="muted small">${t("h.wl.officialPrices")}${s.has_key ? t("h.wl.itadAll") : t("h.wl.itadAdd")}.
        ${t("h.wl.keyShops")}
        ${t("h.wl.clickGame")}
        ${t("h.wl.alertHelp", {thr: s.threshold})}</p></div>
      <div class="row"><button class="btn" id="wl-import">⬇ ${t("h.common.importSteam")}</button><button class="btn" id="wl-check">↻ ${t("h.wl.checkPrices")}</button>
        <button class="btn" id="wl-settings">⚙</button></div></div>
    <div class="wl-settings" hidden>
      <label>${t("h.wl.itadKey")} <input class="field" id="wl-key" placeholder="${s.has_key ? t("h.wl.keyStored") : t("h.wl.optional")}">
        <a href="#" data-open="https://isthereanydeal.com/apps/my/">${t("h.wl.getKey")}</a></label>
      <label>${t("h.wl.ggKey")} <input class="field" id="wl-gg" placeholder="${s.has_gg ? t("h.wl.keyStored") : t("h.wl.optionalKeyPrices")}">
        <a href="#" data-open="https://gg.deals/api/">${t("h.wl.getKey")}</a></label>
      <label>${t("h.wl.country")} <input class="field" id="wl-country" value="${esc(s.country)}" maxlength="2" style="width:60px"></label>
      <label>${t("h.wl.alertFrom")} <input class="field" id="wl-thr" type="number" min="5" max="95" value="${s.threshold}" style="width:70px">%</label>
      <button class="btn primary" id="wl-save">${t("h.common.save")}</button></div>
    <div class="wl-add"><input class="field grow" id="wl-q" placeholder="${t("h.wl.searchPh")}" autocomplete="off"><div id="wl-res"></div></div>
    ${d.checking ? `<p class="muted small">${t("h.wl.checking")}</p>` : ""}
    ${!s.has_gg ? `<p class="muted small">🔑 Per i prezzi delle key aggiungi la chiave GG.deals in ⚙.</p>`
      : d.log.length ? `<p class="muted small">${t("h.wl.lastNotice", {msg: esc(d.log[d.log.length - 1])})}</p>` : ""}
    <div class="wl-list" id="wl-rows">${d.items.length ? "" : `<p class="muted">${t("h.wl.empty")}</p>`}</div></div>`;
  // una riga per volta, solo quelle visibili: la lista puo' avere migliaia di giochi
  if (d.items.length) vlist(pv, $("#wl-rows", pv), d.items, (w) => `<div class="wl-row${w.alert ? " has-alert" : ""}${w.alert && !w.seen ? " new" : ""}" data-wid="${esc(w.id)}" title="${t("h.wl.clickOffers")}">
      <div class="wl-img">${imgTag(w)}</div>
      <div class="wl-t"><b>${esc(w.title)}</b>${w.owned ? ` <span class="tag">${t("h.wl.inLibrary")}</span>` : ""}
        <span class="muted small">${w.checked ? `${esc(w.shop || "")} · ${t("h.wl.checkedOn", {d: new Date(w.checked * 1000).toLocaleDateString(GSI18n.lang)})}` : t("h.wl.notChecked")}
          ${w.low != null ? ` · ${t("h.wl.low", {p: money(w.low, w.currency)})}` : ""}</span>${priceSpark(w.history, money, w.currency)}</div>
      <div class="wl-price" title="${esc(w.steam ? "Steam" : w.shop || "")}">${(w.steam || w).cut ? `<span class="cut">-${(w.steam || w).cut}%</span><s class="muted">${money((w.steam || w).regular, w.currency)}</s>` : ""}<b>${money((w.steam || w).price, w.currency)}</b>
        ${w.key_price != null ? keyPrice(w, money, (w.steam || w).regular || (w.steam || w).price) : ""}</div>
      <div class="wl-alert">${w.alert ? `🔔 ${esc(w.alert)}` : ""}</div>
      <label class="wl-target" title="${t("h.wl.alertWhen")}">≤ <input class="field" type="number" step="0.5" min="0" data-target="${esc(w.id)}" value="${w.target ?? ""}" placeholder="€"></label>
      ${w.url ? `<button class="btn" data-open="${esc(w.url)}">${t("h.common.open")} ↗</button>` : ""}
      ${w.key_url ? `<button class="btn" data-open="${esc(w.key_url)}" title="${t("h.wl.keyCompare")}">🔑 ↗</button>` : ""}
      <button class="icon-btn" data-del="${esc(w.id)}" title="${t("h.wl.removeFromList")}">✕</button></div>`, { gap: 6 });
  if (d.unseen) { api("/api/wishlist/seen", { body: {} }).then(() => pollWishBadge()); }
  let tmr = 0;
  $("#wl-q").oninput = (e) => {
    clearTimeout(tmr);
    const q = e.target.value.trim();
    if (q.length < 2) { $("#wl-res").innerHTML = ""; return; }
    tmr = setTimeout(async () => {
      let r;
      try { r = await api("/api/wishlist/search", { body: { q } }); } catch (err) { return toast(err.message, true); }
      $("#wl-res").innerHTML = r.results.map((x, i) => `<div class="wl-hit" data-i="${i}">${x.cover ? `<img src="${remoteImg(x.cover)}" alt="" onerror="this.remove()">` : ""}<span>${esc(x.title)}</span><b>＋</b></div>`).join("")
        || `<div class="muted small" style="padding:8px">${t("h.wl.noResults")}</div>`;
      $("#wl-res").onclick = async (ev) => {
        const h = ev.target.closest(".wl-hit");
        if (!h) return;
        const x = r.results[+h.dataset.i];
        try { await api("/api/wishlist/add", { body: x }); } catch (err) { return toast(err.message, true); }
        toast(t("h.wl.added", {name: x.title}));
        renderWishlist(pv);
        setTimeout(() => S.view.type === "wishlist" && renderWishlist(pv), 4000);
      };
    }, 350);
  };
  pv.onclick = async (e) => {
    const t = e.target;
    const o = t.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    if (t.dataset.del) { await api(`/api/wishlist/item/${encodeURIComponent(t.dataset.del)}`, { method: "DELETE" }); renderWishlist(pv); pollWishBadge(); }
    else if (t.closest(".wl-row") && !t.closest("button, input, label, a")) openWishPrices(t.closest(".wl-row").dataset.wid);
    else if (t.id === "wl-settings") pv.querySelector(".wl-settings").hidden = !pv.querySelector(".wl-settings").hidden;
    else if (t.id === "wl-save") {
      const body = { country: $("#wl-country").value, threshold: $("#wl-thr").value };
      if ($("#wl-key").value.trim()) body.itad_key = $("#wl-key").value.trim();
      if ($("#wl-gg").value.trim()) body.gg_key = $("#wl-gg").value.trim();
      try { await api("/api/wishlist/settings", { body }); } catch (err) { return toast(err.message, true); }
      toast(window.t("h.wl.settingsSaved")); renderWishlist(pv);
    } else if (t.id === "wl-check") {
      await api("/api/wishlist/check", { body: { force: true } });
      toast(window.t("h.wl.checkStarted"));
      setTimeout(() => S.view.type === "wishlist" && renderWishlist(pv), 5000);
    } else if (t.id === "wl-import") {
      t.disabled = true;
      try { const r = await api("/api/wishlist/import-steam", { body: {} }); toast(window.t("h.wl.imported", {n: r.imported})); }
      catch (err) { toast(err.message, true); }
      renderWishlist(pv);
      setTimeout(() => S.view.type === "wishlist" && renderWishlist(pv), 6000);
    }
  };
  pv.onchange = async (e) => {
    const t = e.target;
    if (t.dataset.target === undefined) return;
    try { await api(`/api/wishlist/item/${encodeURIComponent(t.dataset.target)}`, { body: { target: t.value } }); } catch (err) { return toast(err.message, true); }
    toast(window.t("h.wl.targetSaved"));
  };
}

/** Grafico a gradini del prezzo nel tempo: pts = [[data, prezzo]], low = linea tratteggiata del minimo storico. */
function lineChart(pts, color, low, money) {
  if (pts.length < 2) return `<p class="muted small">${t("h.chart.notEnough")}</p>`;
  const W = 640, H = 170, L = 58, B = 20, T = 8;
  const ts = pts.map(([d]) => +new Date(d)), vs = pts.map(([, v]) => v).concat(low != null ? [low] : []);
  const t0 = ts[0], t1 = ts[ts.length - 1], lo = Math.min(...vs), hi = Math.max(...vs);
  const x = (t) => L + (t1 === t0 ? 0 : ((t - t0) / (t1 - t0)) * (W - L - 6));
  const y = (v) => T + (hi === lo ? (H - T - B) / 2 : (1 - (v - lo) / (hi - lo)) * (H - T - B));
  const path = pts.map(([, v], i) => (i ? `H${x(ts[i]).toFixed(1)}V${y(v).toFixed(1)}` : `M${x(t0).toFixed(1)},${y(v).toFixed(1)}`)).join("") + `H${x(t1).toFixed(1)}`;
  const day = (t) => new Date(t).toLocaleDateString(GSI18n.lang, { day: "2-digit", month: "short", year: "2-digit" });
  return `<svg class="wp-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">
    <text x="2" y="${T + 9}" class="ax">${money(hi)}</text><text x="2" y="${H - B}" class="ax">${money(lo)}</text>
    <text x="${L}" y="${H - 5}" class="ax">${day(t0)}</text><text x="${W - 4}" y="${H - 5}" class="ax" text-anchor="end">${day(t1)}</text>
    ${low != null ? `<line x1="${L}" x2="${W - 6}" y1="${y(low)}" y2="${y(low)}" stroke="${color}" stroke-dasharray="4 4" opacity=".5"><title>${t("h.chart.lowTitle", {p: money(low)})}</title></line>` : ""}
    <path d="${path}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}

/** Dettaglio dei prezzi di un gioco: Steam, key più economica (GG.deals), offerte degli store (IsThereAnyDeal), grafici. */
async function openWishPrices(wid) {
  const dlg = $("#wl-dlg"), box = $("#wl-dlg-body");
  let d;
  try { d = await api(`/api/wishlist/prices/${encodeURIComponent(wid)}`); } catch (e) { return toast(e.message, true); }
  const money = (v) => (v == null ? "—" : v.toLocaleString(GSI18n.lang, { style: "currency", currency: d.currency }));
  const a = d.detail || {}, steam = a.steam, key = a.key;
  const since = (days) => (days ? new Date(Date.now() - days * 864e5).toISOString().slice(0, 10) : "");
  // Steam: storico di ITAD + punti giornalieri registrati qui (questi vincono sullo stesso giorno)
  const byDay = new Map((a.hist || []).concat(d.history.filter((h) => h[1] != null).map((h) => [h[0], h[1]])));
  const steamPts = [...byDay].sort(([x], [y]) => (x < y ? -1 : 1));
  const keyPts = d.history.filter((h) => h[2] != null).map((h) => [h[0], h[2]]);
  const offers = a.offers || [];
  let range = 365;
  const draw = () => {
    const cut = (pts) => pts.filter(([day]) => day >= since(range));
    box.querySelector("#wp-charts").innerHTML = `
      <h4>Steam</h4>${lineChart(cut(steamPts), "#5b8cff", null, money)}
      <h4>${t("h.prices.cheapestKey")}</h4>${keyPts.length > 1 ? lineChart(cut(keyPts), "#9be3b5", d.key_low, money)
        : `<p class="muted small">${t("h.prices.keyBuild")}${d.key_low != null ? t("h.prices.keyLow", {p: money(d.key_low)}) : ""}.</p>`}`;
    box.querySelectorAll("[data-range]").forEach((b) => b.classList.toggle("primary", +b.dataset.range === range));
  };
  box.innerHTML = `<div class="row"><h3 class="grow">${esc(d.title)}</h3>
      ${steam?.url ? `<button class="btn" data-open="${esc(steam.url)}">Steam ↗</button>` : ""}
      ${d.key_url ? `<button class="btn" data-open="${esc(d.key_url)}">GG.deals ↗</button>` : ""}
      <button class="icon-btn" id="wp-close" title="${t("h.common.close")}">✕</button></div>
    <p class="muted small">${d.checked ? t("h.prices.checkedOn", {d: new Date(d.checked * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" })}) : t("h.prices.notChecked")}
      ${d.has_gg ? "" : " " + t("h.prices.addGg")}${d.has_itad ? "" : " " + t("h.prices.addItad")}</p>
    <div class="wp-cards">
      <div class="wp-card"><span class="muted small">Steam</span>
        <b>${steam ? money(steam.price) : "—"}</b>${steam?.cut ? ` <span class="cut">-${steam.cut}%</span> <span class="muted small">${t("h.prices.fullPrice")} <s>${money(steam.regular)}</s></span>` : ""}</div>
      <div class="wp-card key"><span class="muted small">${t("h.prices.cheapestKeyGg")}</span>
        <b>${key?.key != null ? money(key.key) : "—"}</b>
        <span class="muted small">${t("h.prices.lowLabel", {p: money(key?.key_low)})}</span></div>
      ${a.low != null ? `<div class="wp-card"><span class="muted small">${t("h.prices.lowStores")}</span><b>${money(a.low)}</b></div>` : ""}
    </div>
    ${offers.length ? `<h4>${t("h.prices.offers", {n: offers.length})}</h4><table class="wp-table"><thead><tr><th>${t("h.prices.shop")}</th><th class="num">${t("h.prices.fullPriceCap")}</th><th class="num">${t("h.prices.discount")}</th><th class="num">${t("h.prices.price")}</th><th></th></tr></thead>
      <tbody>${offers.map((o) => `<tr><td>${esc(o.shop)}</td><td class="num muted">${o.cut ? `<s>${money(o.regular)}</s>` : ""}</td>
        <td class="num">${o.cut ? `-${o.cut}%` : ""}</td><td class="num"><b>${money(o.price)}</b></td>
        <td>${o.url ? `<button class="btn" data-open="${esc(o.url)}">${t("h.common.open")} ↗</button>` : ""}</td></tr>`).join("")}</tbody></table>` : ""}
    <div class="row wp-range"><span class="muted small grow">${t("h.prices.trend")}</span>
      <button class="btn" data-range="30">${t("h.prices.days30")}</button><button class="btn" data-range="365">${t("h.prices.year1")}</button><button class="btn" data-range="0">${t("h.prices.all")}</button></div>
    <div id="wp-charts"></div>`;
  box.onclick = (e) => {
    const t = e.target, o = t.closest("[data-open]"), r = t.closest("[data-range]");
    if (o) api("/api/open", { body: { url: o.dataset.open } });
    else if (r) { range = +r.dataset.range; draw(); }
    else if (t.id === "wp-close") dlg.close();
  };
  draw();
  if (!dlg.open) dlg.showModal();
}

/* ---- pagina: statistiche */
const STATS_Y = { y: new Date().getFullYear() };
async function renderStats(pv) {
  pageSkeleton(pv, "stats");
  let d;
  try { d = await api(`/api/stats?year=${STATS_Y.y}`); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  const prim = S.games.filter((g) => g.id === g.grp.primary && !g.grp.hidden && g.store !== "online");
  const secs = (g) => (g.grp.playtime || 0) + (g.splay || 0) * 60;
  const played = prim.filter((g) => secs(g) > 0 || g.grp.last);
  const total = played.reduce((a, g) => a + secs(g), 0);
  const st = {};
  for (const g of prim) if (g.grp.status) st[g.grp.status] = (st[g.grp.status] || 0) + 1;
  const backlogH = prim.filter((g) => g.grp.status === "backlog" && g.hltb).reduce((a, g) => a + g.hltb, 0);
  const doneN = st.done || 0, startedN = doneN + (st.playing || 0) + (st.dropped || 0);
  const sum = (key) => {
    const m = new Map();
    for (const g of played) for (const k of key(g)) m.set(k, (m.get(k) || 0) + secs(g) / Math.max(1, key(g).length));
    return [...m.entries()].filter(([, v]) => v >= 60).sort((a, b) => b[1] - a[1]);
  };
  const perPlat = sum((g) => [g.store ? STORE_SHORT[g.store] || g.store : platName(g.platform)]).slice(0, 10);
  const perGenre = sum((g) => RECO.canonGenres(g.genres).map((x) => RECO.GENRE_LABEL[x])).slice(0, 8);
  const top = played.slice().sort((a, b) => secs(b) - secs(a)).slice(0, 10);
  const h = (s) => fmtTime(s);
  const bars = (rows) => {
    const max = Math.max(1, ...rows.map((r) => r[1]));
    return `<div class="sbars">${rows.map(([k, v]) => `<div class="sbar" title="${esc(k)}: ${h(v)}"><span class="k">${esc(k)}</span>
      <span class="trk"><span class="fill" style="width:${Math.max(1, (100 * v) / max)}%"></span></span><span class="v">${h(v)}</span></div>`).join("")}</div>`;
  };
  const mMax = Math.max(1, ...d.months);
  const MONTHS = Array.from({ length: 12 }, (_, i) => t("h.stats.m" + (i + 1)));
  const years = Object.keys(d.years).map(Number);
  if (!years.includes(STATS_Y.y)) years.push(STATS_Y.y);
  pv.innerHTML = `<div class="page stats" data-view="stats">
    <div class="tiles">
      <div class="tile-s"><b>${prim.length.toLocaleString(GSI18n.lang)}</b><span>${t("h.stats.inLibrary")}</span></div>
      <div class="tile-s"><b>${played.length.toLocaleString(GSI18n.lang)}</b><span>${t("h.stats.playedOnce")}</span></div>
      <div class="tile-s"><b>${h(total) || t("h.stats.zeroMin")}</b><span>${t("h.stats.totalTime")}</span></div>
      <div class="tile-s"><b>${doneN}</b><span>${t("h.stats.finished")}${startedN ? ` · ${t("h.stats.ofStarted", {p: Math.round((100 * doneN) / startedN)})}` : ""}</span></div>
      <div class="tile-s"><b>${st.playing || 0}</b><span>${t("h.stats.inProgress")}</span></div>
      <div class="tile-s"><b>${st.backlog || 0}</b><span>${t("h.stats.toPlay")}${backlogH ? `<br><small>${t("h.stats.needHours", {hrs: Math.round(backlogH)})}</small>` : ""}</span></div>
    </div>
    <div class="scard"><div class="scard-h"><h3>🏆 ${t("h.stats.yourYear", {y: d.year})}</h3>
      <select class="field" id="st-year">${years.sort().map((y) => `<option${y === STATS_Y.y ? " selected" : ""}>${y}</option>`).join("")}</select></div>
      <p class="muted small">${t("h.stats.hoursPerMonth")}</p>
      <div class="months">${d.months.map((v, i) => `<div class="mcol" title="${MONTHS[i]} ${d.year}: ${h(v) || t("h.stats.noSession")}">
        <span class="mbar" style="height:${v ? Math.max(3, (100 * v) / mMax) : 0}%"></span><span class="ml">${MONTHS[i]}</span></div>`).join("")}</div>
      ${d.top_year.length ? `<h4>${t("h.stats.yearRank")}</h4><ol class="toplist">${d.top_year.map((t) => `<li data-id="${t.id}"><b>${esc(t.title)}</b>
        <span class="muted">${esc(STORE_SHORT[t.platform] || platName(t.platform))} · ${h(t.seconds)}</span></li>`).join("")}</ol>`
        : `<p class="muted small">${t("h.stats.noYear", {y: d.year})}</p>`}</div>
    <div class="scols">
      <div class="scard"><h3>${t("h.stats.timePlatform")}</h3>${perPlat.length ? bars(perPlat) : `<p class="muted small">${t("h.stats.noData")}</p>`}</div>
      <div class="scard"><h3>${t("h.stats.timeGenre")}</h3>${perGenre.length ? bars(perGenre) : `<p class="muted small">${t("h.stats.noData")}</p>`}</div>
    </div>
    <div class="scard"><h3>${t("h.stats.mostPlayed")}</h3>${top.length ? `<ol class="toplist">${top.map((g) => `<li data-id="${g.id}"><b>${esc(g.title)}</b>
      <span class="muted">${esc(g.store ? STORE_SHORT[g.store] : platName(g.platform))} · ${h(secs(g))}${g.grp.status ? ` · ${STATUS[g.grp.status].icon} ${STATUS[g.grp.status].label}` : ""}</span></li>`).join("")}</ol>`
      : `<p class="muted small">${t("h.stats.noSessions")}</p>`}</div></div>`;
  $("#st-year").onchange = (e) => { STATS_Y.y = +e.target.value; renderStats(pv); };
  pv.onclick = (e) => { const li = e.target.closest("li[data-id]"); if (li) openDetail(+li.dataset.id); };
}

/* ---- migliori giochi: Top 100 per console e classifica globale (100/1000) */
const TOP_F = { limit: +store.get("topLimit", 100) || 100, own: "", plat: "" };
let topTimer = 0;
async function renderTop(pv) {
  clearTimeout(topTimer);
  pageSkeleton(pv, "top");
  const pid = S.view.id || "all", glob = pid === "all";
  let d;
  try { d = await api(`/api/top?pid=${encodeURIComponent(pid)}&limit=${glob ? TOP_F.limit : 100}`); }
  catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  if (S.view.type !== "top" || (S.view.id || "all") !== pid) return;
  const js = d.job, run = js.status === "running";
  const items = d.items.filter((t) => (!TOP_F.own || (TOP_F.own === "owned") === t.owned) && (!glob || !TOP_F.plat || t.platform === TOP_F.plat));
  const plats = [...new Set(d.items.map((t) => t.platform))].sort((a, b) => collator.compare(platName(a), platName(b)));
  const opt = (v, l, sel) => `<option value="${esc(v)}"${String(v) === String(sel) ? " selected" : ""}>${esc(l)}</option>`;
  const pct = (x) => Math.round(x * 100);
  const row = (t, i) => `<div class="top-row" data-id="${t.id}">
      <span class="top-n">${i + 1}</span>
      <span class="top-cv">${t.id ? `<img loading="lazy" src="/img/${t.id}/cover?w=120" alt="" onerror="this.remove()">` : ""}</span>
      <span class="top-t"><b>${esc(t.title)}</b>
        <span class="muted small">${[glob ? platName(t.platform) : "", t.year, t.also?.length ? window.t("h.top.alsoOn", {list: t.also.map(platName).join(", ")}) : ""].filter(Boolean).map(esc).join(" · ")}</span>
        <span class="muted small">${[t.critics != null ? window.t("h.top.critic", {p: pct(t.critics)}) : "", t.rating != null ? window.t("h.top.players", {p: pct(t.rating)}) + (t.votes ? window.t("h.top.votes", {n: t.votes.toLocaleString(GSI18n.lang)}) : "") : "", t.sources.join(", ")].filter(Boolean).map(esc).join(" · ")}</span></span>
      <span class="badge ${t.owned ? "inst" : ""}">${t.owned ? window.t("h.top.owned") : window.t("h.top.downloadable")}</span>
      <span class="top-s" title="${window.t("h.top.scoreTitle")}">${pct(glob ? t.best ?? t.score : t.score)}</span></div>`;
  pv.innerHTML = `<div class="page top" data-view="top">
    <p class="muted small">${t("h.top.help", {note: glob ? t("h.top.sameGame") : t("h.top.regional")})}</p>
    <div class="top-tools">
      ${glob ? `<select class="field" id="top-limit">${opt(100, "Top 100", TOP_F.limit)}${opt(1000, "Top 1000", TOP_F.limit)}</select>
        <select class="field" id="top-plat">${opt("", t("h.top.allConsoles"), TOP_F.plat)}${plats.map((p) => opt(p, platName(p), TOP_F.plat)).join("")}</select>` : ""}
      <select class="field" id="top-own">${opt("", t("h.top.ownedAndDl"), TOP_F.own)}${opt("owned", t("h.top.onlyOwned"), TOP_F.own)}${opt("net", t("h.top.onlyDl"), TOP_F.own)}</select>
      <button class="btn" id="top-fetch"${run ? " disabled" : ""} title="${t("h.top.fetchHelp", {all: glob ? t("h.top.ofAll") : ""})}">↻ ${t("h.top.updateVotes")}${glob ? " " + t("h.top.allParen") : ""}</button>
      <button class="btn" id="top-stop"${run ? "" : " hidden"}>■ ${t("h.common.stop")}</button>
    </div>
    <div id="top-job"></div>
    ${items.length ? `<div class="top-list" id="top-rows"></div>`
      : `<p class="muted">${t("h.top.none")}${TOP_F.own || TOP_F.plat ? " " + t("h.top.withFilters") : ""}. ${t("h.top.hint")}</p>`}</div>`;
  if (items.length) vlist(pv, $("#top-rows", pv), items, (t) => row(t, items.indexOf(t)), { gap: 4 });
  renderJobInto($("#top-job"), js);
  const re = () => renderTop(pv);
  $("#top-own").onchange = (e) => { TOP_F.own = e.target.value; re(); };
  if (glob) {
    $("#top-limit").onchange = (e) => { TOP_F.limit = +e.target.value; store.set("topLimit", TOP_F.limit); re(); };
    $("#top-plat").onchange = (e) => { TOP_F.plat = e.target.value; re(); };
  }
  $("#top-fetch").onclick = async () => {
    try { await api("/api/top/fetch", { body: { pid } }); } catch (e) { return toast(e.message, true); }
    re();
  };
  $("#top-stop").onclick = () => api("/api/top/cancel", { body: {} });
  pv.onclick = (e) => { const r = e.target.closest(".top-row[data-id]"); if (r && +r.dataset.id) openDetail(+r.dataset.id); };
  if (run) topTimer = setTimeout(async () => {
    const st = await api("/api/top/state").catch(() => null);
    if (st && st.status !== "running") { await reload(true); toast(st.phase, st.status === "error"); }
    if (S.view.type === "top") re();
  }, 2000);
}

/* ---- schermate dei giochi */
const SHOTS = { detail: [], page: [], hotkey: "Ctrl+Shift+S", pauseHotkey: "Ctrl+Shift+P" };

async function loadDetailShots(id) {
  let r;
  try { r = await api(`/api/game/${id}/shots`); } catch { return; }
  if (!S.detail || S.detail.id !== id) return;
  SHOTS.detail = r.shots;
  const box = $("#d-myshots");
  if (box) box.innerHTML = r.shots.slice(0, 12).map((s, i) => `<img loading="lazy" src="${s.url}?w=360" data-i="${i}" alt="" title="${esc(fmtDate(s.taken))} · ${esc(s.source)}">`).join("");
}

function openLightbox(list, i) {
  if (!list.length) return;
  const lb = $("#lightbox");
  const draw = () => {
    const s = list[i];
    lb.innerHTML = `<div class="lb-top"><b>${esc(s.title || "")}</b><span class="muted">${esc(fmtDate(s.taken))} · ${esc(s.source)} · ${i + 1}/${list.length}</span>
      <span class="grow"></span><button class="btn" data-lb="folder">📁 ${t("h.lb.showFolder")}</button><button class="btn" data-lb="del">🗑 ${t("h.lb.delete")}</button>
      <button class="icon-btn big" data-lb="close">✕</button></div>
      <button class="lb-arr l" data-lb="prev"${i ? "" : " disabled"}>‹</button><img class="lb-img" src="${s.url}" alt="">
      <button class="lb-arr r" data-lb="next"${i < list.length - 1 ? "" : " disabled"}>›</button>`;
  };
  const close = () => { lb.hidden = true; document.removeEventListener("keydown", keys, true); };
  const keys = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    else if (e.key === "ArrowLeft" && i > 0) { i--; draw(); }
    else if (e.key === "ArrowRight" && i < list.length - 1) { i++; draw(); }
  };
  lb.onclick = async (e) => {
    const a = e.target.closest("[data-lb]")?.dataset.lb;
    if (!a && e.target === lb) return close();
    if (a === "close") close();
    else if (a === "prev" && i > 0) { i--; draw(); }
    else if (a === "next" && i < list.length - 1) { i++; draw(); }
    else if (a === "folder") api("/api/shots/open", { body: { id: list[i].id } });
    else if (a === "del") {
      if (!confirm(t("h.shots.confirmDel"))) return;
      await api(`/api/shots/${list[i].id}`, { method: "DELETE" });
      list.splice(i, 1);
      if (!list.length) { close(); } else { i = Math.min(i, list.length - 1); draw(); }
      if (S.view.type === "shots") renderShots($("#plugin-view"));
      if (S.detail) openDetail(S.detail.id);
    }
  };
  document.addEventListener("keydown", keys, true);
  lb.hidden = false;
  draw();
}

async function renderShots(pv) {
  pageSkeleton(pv, "shots");
  let d;
  try { d = await api("/api/shots"); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  SHOTS.page = d.shots;
  const st = d.settings;
  SHOTS.hotkey = st.hotkey ? st.hotkey.split("+").map((k) => k[0].toUpperCase() + k.slice(1)).join("+") : "—";
  $("#cnt-shots").textContent = d.shots.length || "";
  const groups = new Map();
  d.shots.forEach((s, i) => { const k = s.game ?? s.key; if (!groups.has(k)) groups.set(k, { s, items: [] }); groups.get(k).items.push(i); });
  pv.innerHTML = `<div class="page" data-view="shots">
    <div class="page-head"><div><h2>📷 ${t("h.shots.title")}</h2>
      <p class="muted small">${t("h.shots.hint", {hk: esc(SHOTS.hotkey)})}</p></div>
      <div class="row"><button class="btn" id="sh-steam">⬇ ${t("h.common.importSteam")}</button><button class="btn" id="sh-folder">📁 ${t("h.shots.folder")}</button>
        <button class="btn" id="sh-set">⚙</button></div></div>
    <div class="wl-settings" id="sh-settings" hidden>
      <label>Scorciatoia da tastiera <input class="field" id="sh-hotkey" value="${esc(st.hotkey || "")}" placeholder="es. ctrl+shift+s, f10"></label>
      <label>${t("h.shots.pauseHotkey")} <input class="field" id="sh-pause-hotkey" value="${esc(st.pause_hotkey || "")}" placeholder="ctrl+shift+p"></label>
      <label class="chk"><input type="checkbox" id="sh-pad"${st.pad ? " checked" : ""}> ${t("h.shots.padLabel")}</label>
      <label class="chk"><input type="checkbox" id="sh-emu"${st.import_emulator ? " checked" : ""}> ${t("h.shots.emuLabel")}</label>
      <button class="btn primary" id="sh-save">${t("h.common.save")}</button></div>
    ${d.shots.length ? `<div id="sh-rows"></div>`
      : `<p class="muted">${t("h.shots.empty", {hk: esc(SHOTS.hotkey)})}</p>`}</div>`;
  // un gioco per riga (gruppo): si disegnano solo i gruppi visibili
  if (d.shots.length) vlist(pv, $("#sh-rows", pv), [...groups.values()], (g) => `<section class="sh-group"><h3>${g.s.game ? `<a href="#" data-game="${g.s.game}">${esc(g.s.title)}</a>` : esc(g.s.title)}
        <span class="muted small">${esc(STORE_SHORT[g.s.platform] || platName(g.s.platform) || "")} · ${g.items.length}</span></h3>
        <div class="sh-grid">${g.items.map((i) => `<img loading="lazy" src="${d.shots[i].url}?w=480" data-i="${i}" alt="" title="${esc(fmtDate(d.shots[i].taken))} · ${esc(d.shots[i].source)}">`).join("")}</div></section>`, { gap: 22 });
  pv.onclick = async (e) => {
    const t = e.target;
    if (t.matches(".sh-grid img")) return openLightbox(SHOTS.page, +t.dataset.i);
    if (t.dataset.game) { e.preventDefault(); return openDetail(+t.dataset.game); }
    if (t.id === "sh-folder") api("/api/shots/open", { body: {} });
    else if (t.id === "sh-set") $("#sh-settings").hidden = !$("#sh-settings").hidden;
    else if (t.id === "sh-steam") {
      t.disabled = true;
      try { const r = await api("/api/shots/import-steam", { body: {} }); toast(window.t("h.shots.imported", {n: r.imported})); renderShots(pv); }
      catch (err) { toast(err.message, true); t.disabled = false; }
    } else if (t.id === "sh-save") {
      try {
        await api("/api/shots/settings", { body: { hotkey: $("#sh-hotkey").value, pause_hotkey: $("#sh-pause-hotkey").value, pad: $("#sh-pad").checked, import_emulator: $("#sh-emu").checked } });
        toast(window.t("h.shots.settingsSaved"));
        renderShots(pv);
      } catch (err) { toast(err.message, true); }
    }
  };
}

/* ---- profilo di avvio per gioco */
let PF = null;
async function openProfile(d) {
  PF = null; // se la richiesta fallisce non si riusa il profilo del gioco aperto prima
  let data;
  try { data = await api(`/api/game/${d.id}/profile`); } catch (e) { return toast(e.message, true); }
  PF = data;
  PF.id = d.id;
  const p = PF.profile, def = PF.default;
  $("#pf-game").textContent = `— ${d.title} (${PF.platform})`;
  $("#pf-before").value = p.before || "";
  $("#pf-after").value = p.after || "";
  $("#pf-comp-exe").value = p.companion || "";
  $("#pf-comp-args").value = p.companion_args || "";
  $("#pf-comp-kill").checked = p.companion_close === "1";
  const au = p.auto || {};
  for (const w of ["b", "a"]) {
    const n = w === "b" ? "before" : "after";
    $(`#pf-au-${w}cmd`).value = au[`${n}_cmd`] || ""; $(`#pf-au-${w}cwd`).value = au[`${n}_cwd`] || "";
    $(`#pf-au-${w}wait`).checked = au[`${n}_wait`] ?? (w === "b");
  }
  $("#pf-au-res").value = au.res || ""; $("#pf-au-power").value = au.power || "";
  $("#pf-au-kill").value = (au.kill || []).join(", "); $("#pf-au-hdr").checked = !!au.hdr; $("#pf-au-magpie").value = au.magpie || "";
  $("#pf-emu-box").hidden = !!PF.pc; // giochi PC: solo gli script
  if (PF.pc) {  // niente emulatore: si azzerano i campi rimasti dal gioco aperto prima
    $("#pf-emu").innerHTML = ""; $("#pf-core").innerHTML = "";
    $("#pf-exe").value = ""; $("#pf-args").value = ""; $("#pf-extra").value = "";
    $("#pf-cmd").textContent = ""; $(".pf-preview").hidden = true;
    return $("#prof-dlg").showModal();
  }
  $(".pf-preview").hidden = false;
  const emus = PF.emulators.filter((e) => e.configured || e.id === p.emulator).sort((a, b) => (b.preset - a.preset) || a.id.localeCompare(b.id));
  $("#pf-emu").innerHTML = `<option value="">${t("h.prof.defaultConsole")}${def ? ` (${esc(def.emulator)}${def.core ? " · " + esc(def.core) : ""})` : ""}</option>`
    + emus.map((e) => `<option value="${esc(e.id)}"${p.emulator === e.id ? " selected" : ""}>${esc(e.id)}${e.preset ? "" : " " + t("h.prof.notPlanned")}</option>`).join("");
  $("#pf-core").innerHTML = `<option value="">${t("h.prof.default")}</option>` + PF.cores.map((c) => `<option${p.core === c ? " selected" : ""}>${esc(c)}</option>`).join("");
  $("#pf-exe").value = p.exe || "";
  $("#pf-args").value = p.args || "";
  $("#pf-extra").value = p.extra || "";
  pfRefresh();
  $("#prof-dlg").showModal();
}
function pfRefresh() {
  if (!PF || PF.pc) return; // giochi PC: nessun emulatore, l'anteprima del comando non serve
  const emu = $("#pf-emu").value || PF.default?.emulator || "";
  $("#pf-core-row").hidden = emu !== "retroarch";
  const sel = PF.emulators.find((e) => e.id === $("#pf-emu").value);
  const cur = PF.current && !PF.current.error && PF.current.emulator === (sel ? sel.id : PF.default?.emulator) ? PF.current : null;
  const base = sel ? (cur || { exe: sel.exe, args: sel.args }) : (PF.default || cur);
  $("#pf-args").placeholder = base ? base.args.join(" ") : "{rom}";
  const exe = $("#pf-exe").value || (base ? base.exe : "");
  const args = ($("#pf-args").value || (base ? base.args.join(" ") : "{rom}"));
  const extra = $("#pf-extra").value;
  $("#pf-cmd").textContent = `"${exe}" ${extra && args.includes("{rom}") ? args.replace("{rom}", extra + " {rom}") : args + (extra ? " " + extra : "")}`;
}
async function saveProfile(reset = false) {
  if (!PF) return toast(t("h.prof.notLoaded"), true);
  // app da avviare insieme al gioco (facoltativa), per giochi PC e console: tre campi nel profilo
  const comp = { companion: $("#pf-comp-exe").value.trim(), companion_args: $("#pf-comp-args").value.trim(),
    companion_close: $("#pf-comp-kill").checked ? "1" : "",
    auto: { before_cmd: $("#pf-au-bcmd").value, before_cwd: $("#pf-au-bcwd").value, before_wait: $("#pf-au-bwait").checked,
      after_cmd: $("#pf-au-acmd").value, after_cwd: $("#pf-au-acwd").value, after_wait: $("#pf-au-await").checked,
      res: $("#pf-au-res").value, power: $("#pf-au-power").value, kill: $("#pf-au-kill").value, hdr: $("#pf-au-hdr").checked, magpie: $("#pf-au-magpie").value } };
  try {
    PF = Object.assign(PF, reset ? await api(`/api/game/${PF.id}/profile`, { method: "DELETE" })
      : await api(`/api/game/${PF.id}/profile`, { body: PF.pc ? { before: $("#pf-before").value, after: $("#pf-after").value, ...comp }
        : { emulator: $("#pf-emu").value, core: $("#pf-emu").value === "retroarch" || !$("#pf-emu").value ? $("#pf-core").value : "",
          exe: $("#pf-exe").value, args: $("#pf-args").value, extra: $("#pf-extra").value, before: $("#pf-before").value, after: $("#pf-after").value, ...comp } }));
  } catch (e) { return toast(e.message, true); }
  $("#prof-dlg").close();
  toast(reset ? t("h.prof.removed") : t("h.prof.saved"));
  if (S.detail?.id === PF.id) openDetail(PF.id);
}

/* ---- obiettivi sbloccati: totali per store dai giochi gia' aperti (Steam, GOG, Epic) */
async function renderAchievements(pv) {
  let d;
  try { d = await api("/api/achievements"); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  if (S.view.type !== "achievements") return;
  const names = { steam: "Steam", gog: "GOG", epic: "Epic Games" }, ids = Object.keys(d.stores);
  const bar = (u, n) => `<div class="ra-bar"><span style="width:${n ? Math.round(u / n * 100) : 0}%"></span></div>`;
  pv.innerHTML = `<div class="page" data-view="achievements"><div class="page-head"><div><h2>🏆 ${t("h.title.achievements")}</h2>
    <p class="muted small">${t("h.ach.help")}</p></div></div>
    ${ids.length ? ids.map((k) => { const s = d.stores[k]; return `<div style="margin-bottom:12px"><b>${names[k] || esc(k)}</b>
      <span class="muted small">${t("h.ach.store", { u: s.unlocked, n: s.total, g: s.games, p: s.perfect })}</span>${bar(s.unlocked, s.total)}</div>`; }).join("")
      + `<div class="ra-list" style="max-height:none">${d.games.map((x) => `<div class="ra-a on"><span><b>${esc(x.title)}</b> <span class="muted small">${names[x.source] || ""} · ${x.unlocked}/${x.total}</span>${bar(x.unlocked, x.total)}</span></div>`).join("")}</div>`
      : `<p class="muted">${t("h.ach.empty")}</p>`}</div>`;
}
