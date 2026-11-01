"use strict";
/* Pozzo Launcher - frontend: vista «Per te» e questionario. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ vista "Per te" (stile Netflix) */
function nfCard(g, why = "") {
  const tag = g.store ? (STORE_SHORT[g.store] || "PC") : (SHORT[g.platform] || g.platform.toUpperCase());
  const sc = g.critics != null ? `Critica ${Math.round(g.critics * 100)}` : g.rating != null && g.votes ? `★ ${Math.round(g.rating * 100)}%` : "";
  return `<div class="nf-card${g.store && !g.installed ? " notinst" : ""}" data-id="${g.id}" title="${esc(g.title)}">`
    + `<div class="nf-cv" style="--h:${hue(g.title)}"><span class="nf-ph">${esc(g.title)}</span>`
    + (g.cover ? `<img loading="lazy" src="/img/${g.id}/cover?w=300" alt="" onerror="this.remove()">` : "")
    + `<span class="nf-tag">${esc(tag)}</span>${g.players >= 2 ? `<span class="nf-pl">👥 ${g.players}</span>` : ""}</div>`
    + `<div class="nf-info"><b>${esc(g.title)}</b><span>${esc([g.year, why || sc].filter(Boolean).join(" · "))}</span></div></div>`;
}

async function renderForYou(pv) {
  const rows = RECO.rows(S.games, RECO.tastes());
  const crows = RECO.collectionRows(S.games, S.colls, RECO.tastes());
  const heroG = rows.find((r) => r.id === "foryou")?.items[0] || rows[0]?.items[0];
  pv.innerHTML = `<div class="nf">
    <div class="nf-hero" id="nf-hero"><div class="nf-hero-txt">
      <div class="nf-kicker">✨ Scelto per te</div><h1 id="nf-h-title"></h1><p id="nf-h-meta" class="muted"></p><p id="nf-h-desc"></p>
      <div class="nf-hero-btns"><button class="btn primary" id="nf-quiz">🎲 A cosa vuoi giocare?</button>
        <button class="btn" id="nf-h-open">Dettagli</button></div></div></div>
    ${rows.length ? "" : `<p class="muted" style="padding:20px">Gioca qualche partita o rispondi al questionario per ricevere consigli.</p>`}
    ${rows.map((r) => `<section class="nf-row"><h2>${esc(r.title)}${r.why ? ` <small>${esc(r.why)}</small>` : ""}</h2>
      <div class="nf-wrap"><button class="nf-arr l" aria-label="Indietro">‹</button><div class="nf-scroll">${r.items.map((g) => nfCard(g)).join("")}</div>
      <button class="nf-arr r" aria-label="Avanti">›</button></div></section>`).join("")}
    ${crows.length ? `<div class="nf-section"><h2 class="nf-sec-title">🗂 Collezioni</h2><p class="muted small">Saghe e franchise della tua libreria</p></div>` : ""}
    ${crows.map((r) => `<section class="nf-row"><h2>${esc(r.title)}</h2>
      <div class="nf-wrap"><button class="nf-arr l" aria-label="Indietro">‹</button><div class="nf-scroll">${r.items.map((x) => collCard(x)).join("")}</div>
      <button class="nf-arr r" aria-label="Avanti">›</button></div></section>`).join("")}</div>`;
  pv.querySelectorAll(".nf-wrap").forEach((w) => {
    const sc = w.querySelector(".nf-scroll");
    w.querySelector(".l").onclick = () => sc.scrollBy({ left: -sc.clientWidth * 0.85, behavior: "smooth" });
    w.querySelector(".r").onclick = () => sc.scrollBy({ left: sc.clientWidth * 0.85, behavior: "smooth" });
  });
  pv.onclick = (e) => {
    const k = e.target.closest(".nf-coll");
    if (k) { setView({ type: "collection", id: k.dataset.slug }); return; }
    const c = e.target.closest(".nf-card");
    if (c) openDetail(+c.dataset.id);
  };
  pv.onmouseover = (e) => { const c = e.target.closest(".nf-card"); if (c && c.dataset.id !== pv.dataset.hero) setHero(+c.dataset.id); };
  $("#nf-quiz").onclick = openQuiz;
  $("#nf-h-open").onclick = () => pv.dataset.hero && openDetail(+pv.dataset.hero);
  let tmr = 0;
  async function setHero(id) {
    clearTimeout(tmr);
    tmr = setTimeout(async () => {
      pv.dataset.hero = id;
      const g = S.byId.get(id);
      if (!g) return;
      $("#nf-h-title").textContent = g.title;
      $("#nf-h-meta").textContent = [g.store ? STORE_SHORT[g.store] : platName(g.platform), g.year, g.dev, g.genres].filter(Boolean).join(" · ");
      let d;
      try { d = await api(`/api/game/${id}`); } catch { return; }
      if (+pv.dataset.hero !== id) return;
      const bg = d.media.hero || d.media.fanart || d.media.screenshot || d.media.header || d.media.cover;
      $("#nf-hero").style.backgroundImage = bg ? `url("${bg}?w=1280")` : "none";
      $("#nf-h-desc").textContent = (d.description || "").slice(0, 260) + ((d.description || "").length > 260 ? "…" : "");
      if (d.players_local) $("#nf-h-meta").textContent += " · " + d.players_local;
    }, 120);
  }
  if (heroG) setHero(heroG.id);
}

function collCard(x) {
  const slug = encodeURIComponent(x.coll.slug);
  return `<div class="nf-coll" data-slug="${esc(x.coll.slug)}" title="${esc(x.coll.name)}">
    <div class="nfc-bg" style="--h:${hue(x.coll.name)};background-image:url('/coll-img/${slug}/cover?w=640')"></div>
    <img class="nfc-icon" src="/coll-img/${slug}/icon?w=256" alt="" loading="lazy" onerror="this.remove()">
    <div class="nfc-txt"><b>${esc(x.coll.name)}</b><span>${esc(x.why || "")}</span></div>
    ${x.played ? `<div class="nfc-prog"><i style="width:${Math.round((100 * x.played) / x.games.length)}%"></i></div>` : ""}</div>`;
}

function shelfGame(g) {
  const meta = [g.year, g.store ? (STORE_SHORT[g.store] || "PC") : platName(g.platform)].filter(Boolean).join(" · ");
  return `<button class="shelf-game" type="button" data-shelf-game="${g.id}" aria-label="Apri ${esc(g.title)}">
    <span class="shelf-cover" style="--h:${hue(g.title)}"><img src="/img/${g.id}/cover?w=300" alt="" loading="lazy"><span>${esc(g.title)}</span></span>
    <span class="shelf-game-title">${esc(g.title)}</span><span class="shelf-game-meta">${esc(meta)}</span></button>`;
}

function renderShelvesHome(pv) {
  if (!pv || S.view.type !== "home") return;
  const games = S.games.filter((g) => g.id === g.grp.primary && !g.grp.hidden);
  const recent = games.filter((g) => g.grp.last > 0).sort((a, b) => b.grp.last - a.grp.last);
  const favorites = games.filter((g) => g.grp.favorite);
  let recommendations = [], collectionRows = [];
  try {
    const tastes = RECO.tastes();
    recommendations = RECO.rows(S.games, tastes).filter((r) => r.items?.length);
    collectionRows = RECO.collectionRows(S.games, S.colls, tastes).filter((r) => r.items?.length);
  } catch (e) { console.warn("Suggerimenti non disponibili", e); }
  const hero = recent[0] || recommendations[0]?.items?.[0] || games[0];
  const sections = [
    { title: "Continua a giocare", items: recent.slice(0, 16) },
    ...recommendations.slice(0, 3).map((r) => ({ title: r.title, why: r.why, items: r.items.slice(0, 16) })),
    { title: "I tuoi preferiti", items: favorites.slice(0, 16) },
    ...(recent.length || recommendations.length || favorites.length ? [] : [{ title: "Dalla tua libreria", items: games.slice(0, 16) }]),
  ].filter((r) => r.items.length);
  pv.innerHTML = `<section class="shelves-hero"${hero ? ` data-hero="${hero.id}"` : ""}>
      <img class="shelves-hero-art" alt="" hidden>
      <div class="shelves-hero-copy">
        <div class="shelves-kicker">${hero ? (recent.length ? "Bentornato" : "Una selezione per te") : "La tua raccolta"}</div>
        <h2>${hero ? esc(hero.title) : "La libreria inizia da qui"}</h2>
        <p>${hero ? "Apri la scheda per riprendere da dove eri rimasto o scoprire altri dettagli." : "Aggiungi o importa i tuoi giochi: li organizzeremo qui per piattaforma, attività e collezione."}</p>
        <div class="shelves-actions">
          ${hero ? `<button class="btn primary" type="button" data-shelf-game="${hero.id}">Apri gioco</button>` : ""}
          <button class="btn" type="button" data-home-view="all">Vai alla libreria</button>
          ${!games.length ? `<button class="btn" type="button" data-home-scan>⟳ Cerca nuovi giochi</button>` : ""}
        </div>
      </div>
    </section>
    ${!games.length && !recommendations.length ? `<section class="shelves-empty"><h2>Ancora nessun gioco da mostrare</h2>
      <p class="muted">Puoi collegare uno store, aggiungere un gioco o avviare una scansione dalle impostazioni.</p>
      <button class="btn" type="button" data-home-view="all">Apri la libreria</button></section>` : ""}
    ${sections.map((r) => `<section class="shelf-section"><h2>${esc(r.title)}${r.why ? `<small>${esc(r.why)}</small>` : ""}</h2>
      <div class="shelf-lane">${r.items.map(shelfGame).join("")}</div></section>`).join("")}
    ${collectionRows.length ? `<section class="shelf-section"><h2>Collezioni</h2><div class="shelf-lane">
      ${collectionRows.flatMap((r) => r.items).slice(0, 12).map((x) => `<button class="shelf-collection" type="button" data-shelf-collection="${esc(x.coll.slug)}">
        <b>${esc(x.coll.name)}</b><span>${esc(x.why || `${x.games.length} giochi`)}</span></button>`).join("")}
    </div></section>` : ""}`;
  pv.onclick = (e) => {
    const game = e.target.closest("[data-shelf-game]");
    if (game) { openDetail(+game.dataset.shelfGame); return; }
    const collection = e.target.closest("[data-shelf-collection]");
    if (collection) { setView({ type: "collection", id: collection.dataset.shelfCollection }); return; }
    if (e.target.closest("[data-home-view]")) { setView({ type: "all" }); return; }
    if (e.target.closest("[data-home-scan]")) $("#scan-btn").click();
  };
  if (hero) {
    const id = hero.id, target = pv.querySelector(".shelves-hero");
    api(`/api/game/${id}`).then((d) => {
      if (S.view.type !== "home" || target.dataset.hero !== String(id)) return;
      const art = d.media?.hero || d.media?.fanart || d.media?.screenshot || d.media?.header || d.media?.cover;
      const image = target.querySelector(".shelves-hero-art");
      if (art) {
        image.onload = () => { target.classList.add("has-art"); image.hidden = false; };
        image.onerror = () => { image.hidden = true; target.classList.remove("has-art"); };
        image.src = art;
      }
      const description = (d.description || "").trim();
      if (description) target.querySelector("p").textContent = description.slice(0, 260) + (description.length > 260 ? "…" : "");
    }).catch(() => {});
  }
}

function renderExperienceHome(element) {
  if (typeof GS.experience?.home !== "function") return;
  try { GS.experience.home(element, { renderShelvesHome, state: S, setView }); }
  catch (e) {
    console.error(`Home esperienza ${GS.experience.id}:`, e);
    element.textContent = "Home non disponibile.";
  }
}

/* ---- questionario "A cosa vuoi giocare?" */
const QZ = { step: 0, a: {} };
function openQuiz() {
  const t = RECO.tastes() || {};
  QZ.step = 0;
  QZ.a = { genres: t.genres || [], moods: [] };
  $("#quiz").showModal();
  renderQuiz();
}
function renderQuiz() {
  const Q = RECO.QUESTIONS, box = $("#quiz-body");
  if (QZ.step >= Q.length) return renderQuizResults();
  const q = Q[QZ.step], val = QZ.a[q.id];
  const on = (id) => (q.multi ? (val || []).includes(id) : val === id);
  box.innerHTML = `<div class="qz-head"><span class="muted">Domanda ${QZ.step + 1} di ${Q.length}</span>
      <div class="qz-dots">${Q.map((_, i) => `<i class="${i <= QZ.step ? "on" : ""}"></i>`).join("")}</div>
      <button class="icon-btn" id="qz-x" title="Chiudi">✕</button></div>
    <h2>${esc(q.title)}</h2>${q.sub ? `<p class="muted">${esc(q.sub)}</p>` : ""}
    <div class="qz-opts">${q.options.map((o) => `<button class="qz-opt${on(o.id) ? " on" : ""}" data-o="${esc(o.id)}">${esc(o.label)}</button>`).join("")}</div>
    <div class="row end"><button class="btn" id="qz-back"${QZ.step ? "" : " disabled"}>‹ Indietro</button>
      <button class="btn" id="qz-skip">Salta</button>
      ${q.multi ? `<button class="btn primary" id="qz-next">Avanti ›</button>` : ""}</div>`;
  box.onclick = (e) => {
    const o = e.target.closest(".qz-opt");
    if (o) {
      if (q.multi) {
        const s = new Set(QZ.a[q.id] || []);
        s.has(o.dataset.o) ? s.delete(o.dataset.o) : s.add(o.dataset.o);
        QZ.a[q.id] = [...s];
        o.classList.toggle("on");
      } else { QZ.a[q.id] = o.dataset.o; QZ.step++; renderQuiz(); }
      return;
    }
    const id = e.target.id;
    if (id === "qz-x") $("#quiz").close();
    else if (id === "qz-back") { QZ.step--; renderQuiz(); }
    else if (id === "qz-skip") { if (!q.multi) delete QZ.a[q.id]; QZ.step++; renderQuiz(); }
    else if (id === "qz-next") { QZ.step++; renderQuiz(); }
  };
}
function renderQuizResults() {
  RECO.saveTastes(QZ.a);
  const res = RECO.suggest(S.games, QZ.a, 12);
  const box = $("#quiz-body");
  box.innerHTML = `<div class="qz-head"><b>🎮 Da giocare adesso</b><span class="muted">${res.length} suggerimenti</span>
      <button class="icon-btn" id="qz-x" title="Chiudi">✕</button></div>
    ${res.length ? `<div class="qz-res">${res.map((x) => nfCard(x.g, x.why)).join("")}</div>`
      : `<p class="muted">Nessun gioco corrisponde a tutte le risposte: prova a cambiarne qualcuna.</p>`}
    <div class="row end"><button class="btn" id="qz-again">↻ Altri suggerimenti</button>
      <button class="btn" id="qz-restart">Rifai il questionario</button></div>`;
  box.onclick = (e) => {
    const c = e.target.closest(".nf-card");
    if (c) { $("#quiz").close(); openDetail(+c.dataset.id); return; }
    if (e.target.id === "qz-x") $("#quiz").close();
    if (e.target.id === "qz-again") renderQuizResults();
    if (e.target.id === "qz-restart") { QZ.step = 0; renderQuiz(); }
  };
  if (S.view.type === "foryou") renderForYou($("#plugin-view")); // i gusti aggiornati cambiano le righe
}
