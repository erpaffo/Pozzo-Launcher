"use strict";
/* Big Picture · modalita' Media: film e serie sfogliati col pad e riprodotti dal lettore dell'estensione «Media locale».
 * Una sola global (BPMedia). Parte pura (righe, serie/stagioni, pad -> comando) separata e testata da tests/test_bigpicture_media.js;
 * la parte DOM sta in screen(ctx), che restituisce una schermata di Big Picture (render/move/ok/hints...).
 * Contratto col lettore: import("/plugins/media-locale/player.js").play(gs, item, onClose, {episodes}) e window.__pmCtl. */
(() => {
  const PLAYER = "/plugins/media-locale/player.js";
  const SOURCES = [["locale", "/plugin-api/media-locale/list?limit=1000"], ["ricette", "/plugin-api/ricette-web/list?limit=1000"],
    ["server", "/plugin-api/media-server/list"]];

  /* ------------------------------------------------------------ logica pura */
  const items = (r) => (Array.isArray(r) ? r : Array.isArray(r?.items) ? r.items : []);
  const norm = (s) => String(s || "").trim().toLowerCase();
  const isAnime = (it) => /anim/i.test([it.genre, it.genres, it.category].filter(Boolean).join(" "));
  const isEpisode = (it) => it.kind === "episodio" || (!!it.series && it.kind !== "serie" && it.kind !== "film" && (it.season != null || it.episode != null));
  const isVideo = (it) => !!it && it.kind !== "brano";
  const pct = (it) => (it.resume_pos > 0 && it.duration > 0 ? Math.min(99, Math.round((it.resume_pos / it.duration) * 100)) : 0);
  const epTag = (it) => `S${it.season ?? 1}E${it.episode ?? 1}`;
  const epCmp = (a, b) => (a.season ?? 0) - (b.season ?? 0) || (a.episode ?? 1e6) - (b.episode ?? 1e6) || String(a.title).localeCompare(String(b.title));

  /** Elenchi grezzi delle sorgenti (null = sorgente assente) -> solo video, senza doppioni source:id. */
  function mergeSources(lists) {
    const seen = new Set(), out = [];
    for (const l of lists) for (const it of items(l)) {
      const k = `${it.source || "media-locale"}:${it.id ?? it.title}`;
      if (isVideo(it) && !seen.has(k)) { seen.add(k); out.push(it); }
    }
    return out;
  }

  /** Episodi -> serie {key,title,poster,seasons:[{season,episodes}],count}. count e' null se qualche riga non e' di Media locale: un catalogo non ha episodi veri. */
  function groupSeries(list) {
    const m = new Map();
    for (const it of list) {
      if (!isEpisode(it) || !norm(it.series)) continue;
      const k = norm(it.series);
      const s = m.get(k) || { key: k, title: String(it.series).trim(), poster: "", eps: [], real: true };
      s.eps.push(it);
      s.poster = s.poster || it.poster || "";
      if ((it.source || "media-locale") !== "media-locale") s.real = false;
      m.set(k, s);
    }
    return [...m.values()].map((s) => {
      const eps = s.eps.sort(epCmp), by = new Map();
      for (const e of eps) { const n = e.season ?? 1; (by.get(n) || by.set(n, []).get(n)).push(e); }
      return { key: s.key, title: s.title, poster: s.poster, count: s.real ? eps.length : null,
        seasons: [...by].sort((a, b) => a[0] - b[0]).map(([season, episodes]) => ({ season, episodes })), episodes: eps };
    }).sort((a, b) => a.title.localeCompare(b.title));
  }

  /** «Continua a guardare»: iniziati e non visti, i piu' recenti prima (se il dato c'e'). */
  function continueItems(list, max = 30) {
    const when = (it) => Number(it.last_played || it.updated_at || 0) || 0;
    return list.filter((it) => it.resume_pos > 0 && !it.seen).sort((a, b) => when(b) - when(a)).slice(0, max);
  }

  const itemCard = (it) => ({ type: "item", key: `${it.source || "l"}:${it.id}`, item: it, poster: it.poster || "", pct: pct(it), seen: !!it.seen,
    label: isEpisode(it) && it.series ? it.series : it.title || "", sub: isEpisode(it) ? `${epTag(it)}${it.title ? " · " + it.title : ""}` : it.kind === "serie" ? "Serie" : it.year ? String(it.year) : "" });
  const seriesCard = (s) => ({ type: "series", key: "s:" + s.key, series: s, poster: s.poster, pct: 0, seen: false, label: s.title,
    sub: s.count != null ? `${s.count} ${s.count === 1 ? "episodio" : "episodi"}` : "Serie" });
  const cardsFor = (list) => groupSeries(list).map(seriesCard).concat(list.filter((it) => !isEpisode(it)).sort((a, b) => String(a.title).localeCompare(String(b.title))).map(itemCard));

  /** Righe della schermata. wl = voci della watchlist. Le righe vuote non esistono. */
  function buildRows(list, wl = []) {
    const anime = list.filter(isAnime), rest = list.filter((it) => !isAnime(it));
    const rows = [
      { id: "continue", title: "Continua a guardare", cards: continueItems(list).map(itemCard) },
      { id: "film", title: "Film", cards: rest.filter((it) => !isEpisode(it) && it.kind !== "serie").sort((a, b) => String(a.title).localeCompare(String(b.title))).map(itemCard) },
      { id: "serie", title: "Serie TV", cards: groupSeries(rest).map(seriesCard).concat(rest.filter((it) => it.kind === "serie").map(itemCard)) },
      { id: "anime", title: "Anime", cards: cardsFor(anime) },
      { id: "watchlist", title: "Watchlist", cards: items(wl).map((w) => ({ type: "wl", key: `w:${w.source || ""}:${w.item_id || w.title}`, wl: w, poster: w.poster || "",
        pct: 0, seen: false, label: w.title || "", sub: [w.year, w.kind].filter(Boolean).join(" · ") })) },
    ];
    return rows.filter((r) => r.cards.length);
  }

  /** Voce della watchlist -> elemento della libreria da riprodurre (null se non e' tra i file noti). */
  const matchWatch = (w, list) => list.find((it) => String(it.id) === String(w.item_id) && (!w.source || (it.source || "media-locale") === w.source))
    || list.find((it) => !isEpisode(it) && norm(it.title) === norm(w.title)) || null;

  const epState = (it) => (it.seen ? "Visto" : pct(it) ? `${pct(it)}%` : "");

  /** Pulsante del pad -> comando del lettore (o null). st = getState(), hold = tenuto premuto (ripetizione). */
  function padCommand(action, st = {}, hold = false) {
    switch (action) {
      case "a": return { name: "toggle" };
      case "b": return { name: "close" };
      case "left": return { name: "jump", arg: hold ? -30 : -10 };
      case "right": return { name: "jump", arg: hold ? 30 : 10 };
      case "up": return { name: "volume", arg: Math.min(1, Math.round(((st.volume ?? 1) + 0.05) * 100) / 100) };
      case "down": return { name: "volume", arg: Math.max(0, Math.round(((st.volume ?? 1) - 0.05) * 100) / 100) };
      case "lb": return st.hasPrev === false ? null : { name: "prev" };
      case "rb": return st.hasNext === false ? null : { name: "next" };
      case "y": return { name: "episodes" };
      case "x": return { name: "skip" };
      case "start": return { name: "fullscreen" };
      default: return null;
    }
  }

  /* ------------------------------------------------------------ pad mentre il lettore e' aperto */
  let openedAt = 0, lastDir = { a: "", t: 0 };
  const ctl = () => (typeof window !== "undefined" ? window.__pmCtl : null) || null;
  const active = () => { const c = ctl(); if (!c) return false; try { return c.getState?.().active !== false; } catch { return true; } };

  /** Da chiamare per ogni azione del pad di Big Picture: true = il lettore l'ha presa, la schermata non deve muoversi. */
  function handlePad(action, now = Date.now()) {
    if (!active() || now - openedAt < 400) return active(); // il tasto che ha avviato il video non deve arrivare al lettore
    const dir = action === "left" || action === "right";
    const hold = dir && lastDir.a === action && now - lastDir.t < 700; // la ripetizione parte a ~380 ms
    if (dir) lastDir = { a: action, t: now };
    let st = {};
    try { st = ctl().getState() || {}; } catch { /* stato non disponibile */ }
    const c = padCommand(action, st, hold);
    if (c) try { ctl().command(c.name, c.arg); } catch { /* lettore in chiusura */ }
    return true;
  }

  /* ------------------------------------------------------------ disponibilita' e lettore */
  /** L'estensione Media locale e' installata e abilitata? (risposta di /api/extensions; qualsiasi errore = no) */
  const isAvailable = (ext) => !!(ext?.plugins || []).find((p) => p.id === "media-locale" && p.enabled && !p.error);
  async function available(api) { try { return isAvailable(await api("/api/extensions")); } catch { return false; } }

  async function loadAll(api) {
    const res = await Promise.all(SOURCES.map(([, u]) => api(u).catch(() => null)));
    const wl = await api("/plugin-api/media-locale/watchlist").catch(() => null);
    return { list: mergeSources(res), wl: items(wl), anySource: res.some((r) => r != null) };
  }

  /* ------------------------------------------------------------ schermate */
  const hue = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; };
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") || String(u || "").startsWith("/") ? u : "");

  /** ctx: {api, toast, esc, push, cur(), main(), renderNav, openTab, tabIndex(), tabsCount(), beep, importPlayer?}. */
  function screen(ctx) {
    const esc = ctx.esc;
    const imp = ctx.importPlayer || (() => import(PLAYER));
    const gs = { api: ctx.api, toast: ctx.toast, esc };
    const D = { list: [], wl: [], rows: [], loading: true, anySource: false };
    const cardHtml = (c, r, i) => {
      const img = safeUrl(c.poster);
      return `<div class="bpm-card${c.seen ? " seen" : ""}" data-r="${r}" data-i="${i}" style="--h:${hue(c.label)}"><div class="bpm-cv"><div class="bpm-ph">${esc(c.label)}</div>`
        + (img ? `<img loading="lazy" decoding="async" src="${esc(img)}" alt="" onerror="this.remove()">` : "")
        + (c.pct ? `<span class="bpm-bar"><i style="width:${c.pct}%"></i></span>` : "") + `</div><div class="bpm-lbl">${esc(c.label)}</div>`
        + (c.sub ? `<div class="bpm-sub">${esc(c.sub)}</div>` : "") + `</div>`;
    };
    async function play(item, episodes, back = () => scr.refresh()) {
      let mod;
      try { mod = await imp(); } catch { ctx.beep?.("err"); return ctx.toast("Lettore Media non disponibile: controlla che «Media locale» sia attiva.", true); }
      openedAt = Date.now();
      try { await mod.play(gs, item, () => { openedAt = Date.now(); back(); }, { episodes }); } catch (e) { ctx.toast(e.message || "Impossibile avviare il video", true); }
    }
    const scr = {
      tab: "videos", title: "Media", row: 0, cols: [], navFocus: null,
      hints: [["a", "Riproduci"], ["b", "Indietro"]],
      async refresh() { // dopo il lettore: posizioni di ripresa aggiornate, fuoco dove era
        try { Object.assign(D, await loadAll(ctx.api), { loading: false }); D.rows = buildRows(D.list, D.wl); } catch { /* resta com'e' */ }
        if (ctx.cur() === scr) { scr.render(ctx.main()); }
      },
      render(el) {
        const body = D.loading ? `<p class="bpm-msg">Caricamento…</p>` : !D.rows.length
          ? `<div class="bpm-empty"><h2>Nessun contenuto da guardare</h2><p>${D.anySource ? "La libreria è vuota." : "Non si riesce a leggere la libreria Media."}</p>`
            + `<p>Aggiungi le cartelle di film e serie da <b>Impostazioni › Estensioni › Media locale</b> e avvia la scansione; poi torna qui.</p></div>`
          : D.rows.map((r, ri) => `<section class="bpm-row" data-r="${ri}"><h2>${esc(r.title)}</h2><div class="bpm-strip">${r.cards.map((c, i) => cardHtml(c, ri, i)).join("")}</div></section>`).join("");
        el.innerHTML = `<div class="bpm">${body}</div>`;
        this.cols = D.rows.map((_, i) => Math.min(this.cols[i] || 0, D.rows[i].cards.length - 1));
        this.row = Math.min(this.row, Math.max(0, D.rows.length - 1));
        if (D.loading) loadAll(ctx.api).then((d) => { Object.assign(D, d, { loading: false }); D.rows = buildRows(D.list, D.wl); if (ctx.cur() === scr) scr.render(ctx.main()); });
        this.update(true);
      },
      update(instant) {
        ctx.renderNav();
        document.querySelectorAll(".bpm-card.focus").forEach((e) => e.classList.remove("focus"));
        if (this.navFocus !== null) return;
        const el = document.querySelector(`.bpm-card[data-r="${this.row}"][data-i="${this.cols[this.row] || 0}"]`);
        if (!el) return;
        el.classList.add("focus");
        el.scrollIntoView({ block: "center", inline: "center", behavior: instant ? "auto" : "smooth" });
      },
      move(dx, dy) {
        const n = ctx.tabsCount();
        if (this.navFocus !== null) {
          if (dy > 0) { this.navFocus = null; this.update(); return true; }
          const k = this.navFocus + dx;
          if (k < 0 || k >= n) return false;
          this.navFocus = k; ctx.renderNav(); return true;
        }
        if (!D.rows.length) { if (dy < 0) { this.navFocus = ctx.tabIndex(); this.update(); return true; } return false; }
        if (dx) {
          const k = (this.cols[this.row] || 0) + dx;
          if (k < 0 || k >= D.rows[this.row].cards.length) return false;
          this.cols[this.row] = k; this.update(); return true;
        }
        const r = this.row + dy;
        if (r < 0) { this.navFocus = ctx.tabIndex(); this.update(); return true; }
        if (r >= D.rows.length) return false;
        this.row = r; this.update(); return true;
      },
      ok() {
        if (this.navFocus !== null) return ctx.openTab(this.navFocus);
        const c = D.rows[this.row]?.cards[this.cols[this.row] || 0];
        if (!c) return;
        if (c.type === "series") return ctx.push(seriesScreen(c.series));
        if (c.type === "wl") {
          const it = matchWatch(c.wl, D.list);
          return it ? (isEpisode(it) ? ctx.push(seriesScreen(groupSeries(D.list).find((s) => s.key === norm(it.series)))) : play(it)) : ctx.toast("Non c'è un file da riprodurre per questa voce della watchlist.", true);
        }
        play(c.item);
      },
    };

    /* serie -> schede stagione (LB/RB) + elenco episodi (su/giu', A avvia) */
    function seriesScreen(s) {
      let si = 0, ei = 0;
      if (!s) return scr;
      const first = s.seasons.findIndex((x) => x.episodes.some((e) => !e.seen)); // si parte dal primo da vedere
      if (first > 0) si = first;
      const eps = () => s.seasons[si].episodes;
      if (first >= 0) ei = Math.max(0, eps().findIndex((e) => !e.seen));
      const sc = {
        tab: "videos", title: s.title, navFocus: null, hints: [["a", "Riproduci"], ["b", "Indietro"], ["lb", "Stagione"], ["rb", "Stagione"]],
        render(el) {
          const img = safeUrl(s.poster);
          el.innerHTML = `<div class="bpm bpm-series"><div class="bpm-side">${img ? `<img src="${esc(img)}" alt="" onerror="this.remove()">` : ""}<h1>${esc(s.title)}</h1>`
            + `<p>${s.count != null ? s.count + " episodi" : "Serie"}</p></div><div class="bpm-main"><div class="bpm-seasons">`
            + s.seasons.map((x, i) => `<span class="bpm-season${i === si ? " on" : ""}">Stagione ${x.season}</span>`).join("")
            + `</div><div class="bpm-eps">` + eps().map((e, i) => `<div class="bpm-ep${e.seen ? " seen" : ""}" data-i="${i}"><b>${e.episode ?? i + 1}</b><span class="t">${esc(e.title || epTag(e))}</span>`
              + `<span class="st">${esc(epState(e))}</span>${pct(e) ? `<span class="bpm-bar"><i style="width:${pct(e)}%"></i></span>` : ""}</div>`).join("") + `</div></div></div>`;
          this.update(true);
        },
        update(instant) {
          ctx.renderNav();
          const el = document.querySelector(`.bpm-ep[data-i="${ei}"]`);
          document.querySelectorAll(".bpm-ep.focus").forEach((e) => e.classList.remove("focus"));
          if (el) { el.classList.add("focus"); el.scrollIntoView({ block: "center", behavior: instant ? "auto" : "smooth" }); }
        },
        move(dx, dy) {
          const k = ei + dy;
          if (!dy || k < 0 || k >= eps().length) return false;
          ei = k; this.update(); return true;
        },
        season(d) {
          const k = si + d;
          if (k < 0 || k >= s.seasons.length) return;
          si = k; ei = Math.max(0, eps().findIndex((e) => !e.seen)); this.render(ctx.main()); ctx.beep?.("move");
        },
        lb() { this.season(-1); }, rb() { this.season(1); },
        ok() { const e = eps()[ei]; if (e) play(e, s.episodes, () => sc.refresh()); },
        async refresh() { // aggiorna visto/avanzamento dopo il lettore
          try { Object.assign(D, await loadAll(ctx.api), { loading: false }); D.rows = buildRows(D.list, D.wl); } catch { return; }
          const n = groupSeries(D.list).find((x) => x.key === s.key);
          if (n) { s = n; si = Math.min(si, s.seasons.length - 1); }
          if (ctx.cur() === sc) sc.render(ctx.main());
        },
      };
      return sc;
    }
    return scr;
  }

  const api = { screen, available, isAvailable, handlePad, active, padCommand, buildRows, groupSeries, continueItems, mergeSources, matchWatch, epState, isAnime, isEpisode, pct };
  if (typeof window !== "undefined") window.BPMedia = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
