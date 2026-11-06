"use strict";
/* Pozzo Launcher - frontend: vista «Per te» e questionario. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ vista "Per te" (stile Netflix) */
function nfCard(g, why = "") {
  const tag = g.store ? (STORE_SHORT[g.store] || "PC") : (SHORT[g.platform] || g.platform.toUpperCase());
  const sc = g.critics != null ? `${t("h.top.critic", {p: Math.round(g.critics * 100)})}` : g.rating != null && g.votes ? `★ ${Math.round(g.rating * 100)}%` : "";
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
      <div class="nf-kicker">✨ ${t("h.home.forYou")}</div><h1 id="nf-h-title"></h1><p id="nf-h-meta" class="muted"></p><p id="nf-h-desc"></p>
      <div class="nf-hero-btns"><button class="btn primary" id="nf-quiz">🎲 ${t("h.home.quizBtn")}</button>
        <button class="btn" id="nf-h-open">${t("h.common.details")}</button></div></div></div>
    ${rows.length ? "" : `<p class="muted" style="padding:20px">${t("h.home.playHint")}</p>`}
    ${rows.map((r) => `<section class="nf-row"><h2>${esc(r.title)}${r.why ? ` <small>${esc(r.why)}</small>` : ""}</h2>
      <div class="nf-wrap"><button class="nf-arr l" aria-label="${t("h.common.back")}">‹</button><div class="nf-scroll">${r.items.map((g) => nfCard(g)).join("")}</div>
      <button class="nf-arr r" aria-label="${t("h.common.next")}">›</button></div></section>`).join("")}
    ${crows.length ? `<div class="nf-section"><h2 class="nf-sec-title">🗂 ${t("h.app.navCollections")}</h2><p class="muted small">${t("h.home.sagas")}</p></div>` : ""}
    ${crows.map((r) => `<section class="nf-row"><h2>${esc(r.title)}</h2>
      <div class="nf-wrap"><button class="nf-arr l" aria-label="${t("h.common.back")}">‹</button><div class="nf-scroll">${r.items.map((x) => collCard(x)).join("")}</div>
      <button class="nf-arr r" aria-label="${t("h.common.next")}">›</button></div></section>`).join("")}</div>`;
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

/* ---- Riprendi (home): testi puri, testati in tests/test_home_resume_ui.js */
function resumeLeftText(sec) {
  if (!(sec > 0)) return "";
  const m = Math.round(sec / 60);
  if (m < 60) return `circa ${Math.max(1, m)} min rimasti`;
  const h = Math.round(m / 60);
  return `circa ${h} h rimast${h === 1 ? "a" : "e"}`;
}
function resumeSaveText(save, now = Date.now() / 1000) {
  if (!save || !save.time) return "";
  const t = new Date(save.time * 1000), n = new Date(now * 1000);
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((day(n) - day(t)) / 86400000);
  const when = diff <= 0 ? "oggi" : diff === 1 ? "ieri" : `${diff} giorni fa`;
  const hm = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  return `salvataggio di ${when} ${hm}`;
}
/* items: risposta di GET /api/home/resume; il primo diventa la card grande, gli altri le righe piccole */
function resumeHtml(items) {
  const [top, ...rest] = items;
  const left = resumeLeftText(top.remaining_secs), save = resumeSaveText(top.save);
  return `<article class="resume-hero" style="--h:${hue(top.title)}">
      <div class="resume-cover"><img src="/img/${top.id}/cover?w=640" alt="" loading="lazy" onerror="this.remove()"></div>
      <div class="resume-body">
        <div class="shelves-kicker">Riprendi</div>
        <h3>${esc(top.title)}</h3>
        <p class="muted">${esc(platName(top.platform))}</p>
        ${left ? `<p>${esc(left)}</p>` : ""}
        ${save ? `<p class="muted">${esc(save)}</p>` : ""}
        <button class="btn primary" type="button" data-resume-play="${top.id}">▶ Riprendi</button>
      </div></article>
    ${rest.length ? `<section class="shelf-section resume-row"><h2>Continua a giocare</h2><div class="shelf-lane">
      ${rest.map((g) => `<div class="resume-mini">${shelfGame(g)}<button class="btn" type="button" data-resume-play="${g.id}" aria-label="Riprendi ${esc(g.title)}">▶ Riprendi</button></div>`).join("")}
    </div></section>` : ""}`;
}
async function loadResume(pv) {
  let items = [];
  try { items = (await api("/api/home/resume")).items || []; } catch { return; }
  const host = pv.querySelector(".resume-host");
  if (!host || !items.length || S.view.type !== "home") return;
  host.innerHTML = resumeHtml(items);
  // lo scaffale dei recenti non ripete i giochi gia' nella card Riprendi
  const shown = new Set(items.map((g) => String(g.id))), recent = pv.querySelector("[data-recent-shelf]");
  if (!recent) return;
  recent.querySelectorAll("[data-shelf-game]").forEach((b) => { if (shown.has(b.dataset.shelfGame)) b.remove(); });
  if (!recent.querySelector("[data-shelf-game]")) recent.remove();
  else recent.querySelector("h2").textContent = "Giocati di recente";
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
    { title: t("h.app.heroContinue"), items: recent.slice(0, 16), recent: true },
    ...recommendations.slice(0, 3).map((r) => ({ title: r.title, why: r.why, items: r.items.slice(0, 16) })),
    { title: t("h.home.favs"), items: favorites.slice(0, 16) },
    ...(recent.length || recommendations.length || favorites.length ? [] : [{ title: t("h.home.fromLib"), items: games.slice(0, 16) }]),
  ].filter((r) => r.items.length);
  pv.innerHTML = `<div class="resume-host"></div><section class="shelves-hero"${hero ? ` data-hero="${hero.id}"` : ""}>
      <img class="shelves-hero-art" alt="" hidden>
      <div class="shelves-hero-copy">
        <div class="shelves-kicker">${hero ? (recent.length ? t("h.home.welcome") : t("h.home.selection")) : t("h.app.heroCollection")}</div>
        <h2>${hero ? esc(hero.title) : t("h.home.libStart")}</h2>
        <p>${hero ? t("h.home.resumeHint") : t("h.home.addHint")}</p>
        <div class="shelves-actions">
          ${hero ? `<button class="btn primary" type="button" data-shelf-game="${hero.id}">${t("h.home.openGame")}</button>` : ""}
          <button class="btn" type="button" data-home-view="all">${t("h.home.goLib")}</button>
          ${!games.length ? `<button class="btn" type="button" data-home-scan>⟳ ${t("h.scan.newGames")}</button>` : ""}
        </div>
      </div>
    </section>
    ${!games.length && !recommendations.length ? `<section class="shelves-empty"><h2>${t("h.home.emptyTitle")}</h2>
      <p class="muted">${t("h.home.emptyHint")}</p>
      <button class="btn" type="button" data-home-view="all">${t("h.home.openLib")}</button></section>` : ""}
    ${sections.map((r) => `<section class="shelf-section"${r.recent ? " data-recent-shelf" : ""}><h2>${esc(r.title)}${r.why ? `<small>${esc(r.why)}</small>` : ""}</h2>
      <div class="shelf-lane">${r.items.map(shelfGame).join("")}</div></section>`).join("")}
    ${collectionRows.length ? `<section class="shelf-section"><h2>${t("h.app.navCollections")}</h2><div class="shelf-lane">
      ${collectionRows.flatMap((r) => r.items).slice(0, 12).map((x) => `<button class="shelf-collection" type="button" data-shelf-collection="${esc(x.coll.slug)}">
        <b>${esc(x.coll.name)}</b><span>${esc(x.why || t("h.srf.games", {n: x.games.length}))}</span></button>`).join("")}
    </div></section>` : ""}`;
  pv.onclick = (e) => {
    const game = e.target.closest("[data-shelf-game]");
    if (game) { openDetail(+game.dataset.shelfGame); return; }
    const resume = e.target.closest("[data-resume-play]");
    if (resume) { play(+resume.dataset.resumePlay); return; }
    const collection = e.target.closest("[data-shelf-collection]");
    if (collection) { setView({ type: "collection", id: collection.dataset.shelfCollection }); return; }
    if (e.target.closest("[data-home-view]")) { setView({ type: "all" }); return; }
    if (e.target.closest("[data-home-scan]")) $("#scan-btn").click();
  };
  loadResume(pv);
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
    element.textContent = t("h.home.unavailable");
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
  box.innerHTML = `<div class="qz-head"><span class="muted">${t("h.quiz.qOf", {a: QZ.step + 1, b: Q.length})}</span>
      <div class="qz-dots">${Q.map((_, i) => `<i class="${i <= QZ.step ? "on" : ""}"></i>`).join("")}</div>
      <button class="icon-btn" id="qz-x" title="${t("h.common.close")}">✕</button></div>
    <h2>${esc(q.title)}</h2>${q.sub ? `<p class="muted">${esc(q.sub)}</p>` : ""}
    <div class="qz-opts">${q.options.map((o) => `<button class="qz-opt${on(o.id) ? " on" : ""}" data-o="${esc(o.id)}">${esc(o.label)}</button>`).join("")}</div>
    <div class="row end"><button class="btn" id="qz-back"${QZ.step ? "" : " disabled"}>‹ ${t("h.common.back")}</button>
      <button class="btn" id="qz-skip">${t("h.quiz.skip")}</button>
      ${q.multi ? `<button class="btn primary" id="qz-next">${t("h.common.next")} ›</button>` : ""}</div>`;
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
  box.innerHTML = `<div class="qz-head"><b>🎮 ${t("h.quiz.playNow")}</b><span class="muted">${t("h.quiz.count", {n: res.length})}</span>
      <button class="icon-btn" id="qz-x" title="${t("h.common.close")}">✕</button></div>
    ${res.length ? `<div class="qz-res">${res.map((x) => nfCard(x.g, x.why)).join("")}</div>`
      : `<p class="muted">${t("h.quiz.noMatch")}</p>`}
    <div class="row end"><button class="btn" id="qz-again">↻ ${t("h.quiz.more")}</button>
      <button class="btn" id="qz-restart">${t("h.quiz.restart")}</button></div>`;
  box.onclick = (e) => {
    const c = e.target.closest(".nf-card");
    if (c) { $("#quiz").close(); openDetail(+c.dataset.id); return; }
    if (e.target.id === "qz-x") $("#quiz").close();
    if (e.target.id === "qz-again") renderQuizResults();
    if (e.target.id === "qz-restart") { QZ.step = 0; renderQuiz(); }
  };
  if (S.view.type === "foryou") renderForYou($("#plugin-view")); // i gusti aggiornati cambiano le righe
}

if (typeof module !== "undefined") module.exports = { resumeLeftText, resumeSaveText, resumeHtml };
