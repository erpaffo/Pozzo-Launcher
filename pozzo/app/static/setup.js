"use strict";
/* Pozzo Launcher - configurazione guidata (primo avvio, riapribile da Impostazioni › Nuovi giochi).
 *
 * Passi: benvenuto, cartella delle ROM (con verifica delle console trovate), store PC, account delle
 * fonti online (facoltativi), riepilogo. "Inizia" salva tutto, importa gli store, crea la libreria e
 * avvia lo scraping dei giochi nuovi in sottofondo: l'app si apre appena la libreria e' pronta.
 */

const SETUP = (() => {
  const STEPS = ["b.setup.step.welcome", "b.onb.step.roms", "b.setup.step.stores", "b.setup.step.online", "b.setup.step.summary"];
  let st = null, step = 0, done = null;
  const v = { roms: "", romsOk: false, noRoms: false, platforms: [], stores: {}, acc: {}, scrape: true };
  const el = () => document.getElementById("setup");

  async function open(force = false) {
    st = await api("/api/setup");
    if (st.done && !force) return;
    v.roms = st.roms || "";
    v.romsOk = !!st.roms;
    v.stores = Object.fromEntries(st.stores.map((s) => [s.id, s.detected && s.enabled]));
    step = 0;
    el().hidden = false;
    if (v.roms) checkRoms(true);
    render();
    return new Promise((resolve) => { done = resolve; });
  }

  function close() {
    el().hidden = true;
    if (done) { done(); done = null; }
  }

  async function pick() {
    const a = window.pywebview && window.pywebview.api;
    if (!a) { el().querySelector("#su-roms").focus(); return toast(t("b.setup.pickNoBrowser")); }
    try {
      const p = await a.pick_folder();
      if (p) { v.roms = p; await checkRoms(); }
    } catch (e) { toast(String(e), true); }
  }

  async function checkRoms(quiet = false) {
    v.roms = (el().querySelector("#su-roms")?.value ?? v.roms).trim();
    if (!v.roms) { v.romsOk = false; v.platforms = []; return render(); }
    try {
      const r = await api("/api/setup/check-roms", { body: { path: v.roms } });
      v.roms = r.path; v.platforms = r.platforms; v.romsOk = true; v.noRoms = false;
    } catch (e) {
      v.romsOk = false; v.platforms = [];
      if (!quiet) toast(e.message, true);
    }
    render();
  }

  const canNext = () => (step === 1 ? v.romsOk || v.noRoms : true);

  function body() {
    const a = st.accounts;
    switch (step) {
      case 0: return `<div class="su-hero"><div class="su-logo">◆</div><h1>${t("b.tour.welcome.title")}</h1>
        <p>${t("b.setup.hero.text")}</p>
        <p class="muted small">${t("b.setup.hero.dataDir")} <code>${esc(st.data_dir)}</code></p></div>`;
      case 1: return `<h2>${t("b.setup.roms.title")}</h2>
        <p class="muted">${t("b.setup.roms.help")}</p>
        <div class="row"><input class="field grow" id="su-roms" placeholder="es. D:\\ROM" value="${esc(v.roms)}">
          <button class="btn" id="su-pick">📁 ${t("b.common.pick")}</button><button class="btn" id="su-check">${t("b.common.check")}</button></div>
        ${v.romsOk ? (v.platforms.length
          ? `<p class="su-ok">✓ ${v.platforms.length} ${v.platforms.length === 1 ? t("b.setup.roms.foundOne") : t("b.setup.roms.foundMany")}</p>
             <div class="su-plats">${v.platforms.map((p) => `<span class="su-chip"><img src="/icons/platform/${encodeURIComponent(p.id)}" alt="" onerror="this.remove()">${esc(p.name)}</span>`).join("")}</div>`
          : `<p class="su-warn">⚠ ${t("b.setup.roms.none")}</p>`) : ""}
        <label class="chk su-skip"><input type="checkbox" id="su-noroms"${v.noRoms ? " checked" : ""}> ${t("b.setup.roms.noRoms")}</label>`;
      case 2: return `<h2>${t("b.setup.stores.title")}</h2>
        <p class="muted">${t("b.setup.stores.help")}</p>
        <div class="su-stores">${st.stores.map((s) => `<label class="su-store${s.detected ? "" : " off"}">
          <input type="checkbox" data-store="${esc(s.id)}"${v.stores[s.id] ? " checked" : ""}${s.detected ? "" : " disabled"}>
          <img src="/icons/store/${esc(s.id)}" alt="" onerror="this.remove()"><span><b>${esc(s.name)}</b>
          <small class="muted">${s.detected ? t("b.setup.stores.found") : t("b.onb.stores.notFound")}</small></span></label>`).join("")}</div>`;
      case 3: return `<h2>${t("b.setup.step.online")} <span class="muted small">${t("b.setup.online.optional")}</span></h2>
        <p class="muted">${t("b.setup.online.help")}</p>
        <div class="su-acc">
          <fieldset><legend>ScreenScraper <a href="#" data-open="https://www.screenscraper.fr/membreinscription.php">${t("b.setup.online.createAccount")}</a></legend>
            <input class="field" id="su-ss-user" placeholder="${t("b.setup.online.user")}" value="${esc(v.acc.ss_user ?? a.ss_user)}" autocomplete="off">
            <input class="field" id="su-ss-pass" type="password" placeholder="${a.ss_password ? t("b.setup.online.savedPass") : t("b.setup.online.pass")}" autocomplete="new-password"></fieldset>
          <fieldset><legend>IGDB (Twitch) <a href="#" data-open="https://api-docs.igdb.com/#account-creation">${t("b.setup.online.howTo")}</a></legend>
            <input class="field" id="su-igdb-id" placeholder="Client ID" value="${esc(v.acc.igdb_id ?? a.igdb_id)}" autocomplete="off">
            <input class="field" id="su-igdb-secret" type="password" placeholder="${a.igdb_secret ? t("b.setup.online.savedSecret") : "Client Secret"}" autocomplete="new-password"></fieldset>
          <fieldset><legend>RAWG <a href="#" data-open="https://rawg.io/apidocs">${t("b.setup.online.freeKey")}</a></legend>
            <input class="field" id="su-rawg" placeholder="${a.rawg ? t("b.setup.online.savedKey") : t("b.setup.online.keyMeta")}" autocomplete="off"></fieldset>
          <fieldset><legend>TheGamesDB <a href="#" data-open="https://forums.thegamesdb.net/">${t("b.setup.online.apiKey")}</a></legend>
            <input class="field" id="su-tgdb" placeholder="${a.tgdb ? t("b.setup.online.savedKey") : t("b.setup.online.keyOptional")}" autocomplete="off"></fieldset>
        </div>`;
      default: {
        const stores = st.stores.filter((s) => v.stores[s.id]).map((s) => s.name);
        const accs = [["ScreenScraper", v.acc.ss_user || st.accounts.ss_user], ["IGDB", v.acc.igdb_id || st.accounts.igdb_id],
          ["RAWG", v.acc.rawg || st.accounts.rawg], ["TheGamesDB", v.acc.tgdb || st.accounts.tgdb]].filter(([, x]) => x).map(([n]) => n);
        return `<h2>${t("b.setup.sum.title")}</h2>
          <ul class="su-sum">
            <li><b>${t("b.setup.sum.roms")}</b> ${v.romsOk ? `${esc(v.roms)} · ${t("b.setup.sum.consoles", {n: v.platforms.length})}` : t("b.setup.sum.noRoms")}</li>
            <li><b>${t("b.setup.sum.stores")}</b> ${stores.length ? esc(stores.join(", ")) : t("b.setup.sum.none")}</li>
            <li><b>${t("b.setup.sum.online")}</b> ${accs.length ? esc(accs.join(", ")) : t("b.setup.sum.noOnline")}</li>
          </ul>
          ${v.romsOk ? `<label class="chk"><input type="checkbox" id="su-scrape"${v.scrape ? " checked" : ""}> ${t("b.setup.sum.scrape")}
            <span class="muted small">${t("b.setup.sum.background")}</span></label>` : ""}
          <div id="su-progress"></div>`;
      }
    }
  }

  function render() {
    el().innerHTML = `<div class="su-box">
      <div class="su-steps">${STEPS.map((s, i) => `<span class="${i === step ? "on" : i < step ? "ok" : ""}">${i < step ? "✓" : i + 1} ${esc(t(s))}</span>`).join("")}</div>
      <div class="su-body">${body()}</div>
      <div class="su-foot">
        ${step ? `<button class="btn" id="su-back">‹ ${t("b.common.back")}</button>` : `<span></span>`}
        ${step < STEPS.length - 1 ? `<button class="btn primary" id="su-next"${canNext() ? "" : " disabled"}>${step === 0 ? t("b.setup.start") : step === 3 ? t("b.setup.nextSkip") : t("b.setup.next")}</button>`
          : `<button class="btn primary" id="su-go">🚀 ${t("b.setup.go")}</button>`}
      </div></div>`;
  }

  function readFields() {
    const q = (id) => el().querySelector(id);
    if (step === 3) {
      v.acc = { ss_user: q("#su-ss-user").value, ss_password: q("#su-ss-pass").value, igdb_id: q("#su-igdb-id").value,
        igdb_secret: q("#su-igdb-secret").value, rawg: q("#su-rawg").value, tgdb: q("#su-tgdb").value };
    }
    if (step === 4 && q("#su-scrape")) v.scrape = q("#su-scrape").checked;
  }

  async function go() {
    readFields();
    const btn = el().querySelector("#su-go");
    btn.disabled = true;
    btn.textContent = t("b.common.starting");
    try {
      await api("/api/setup", { body: { roms: v.romsOk ? v.roms : "", stores: v.stores, accounts: v.acc, start: true, scrape: v.scrape } });
    } catch (e) { btn.disabled = false; btn.textContent = "🚀 " + t("b.setup.go"); return toast(e.message, true); }
    for (;;) {
      const s = (await api("/api/setup")).state;
      const box = el().querySelector("#su-progress");
      if (box) box.innerHTML = `<div class="su-phase">${s.status === "done" ? "✓" : "⏳"} ${esc(s.phase || "")}</div><pre class="log">${esc((s.log || []).slice(-6).join("\n"))}</pre>`;
      if (s.status === "done") break;
      if (s.status === "error") { btn.disabled = false; btn.textContent = t("b.common.retry"); return toast(s.phase, true); }
      await new Promise((r) => setTimeout(r, 800));
    }
    close();
  }

  document.addEventListener("click", (e) => {
    if (!el() || el().hidden || !el().contains(e.target)) return;
    const t = e.target;
    const o = t.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    if (t.id === "su-next" && canNext()) { readFields(); step++; render(); }
    else if (t.id === "su-back") { readFields(); step--; render(); }
    else if (t.id === "su-pick") pick();
    else if (t.id === "su-check") checkRoms();
    else if (t.id === "su-go") go();
  });
  document.addEventListener("change", (e) => {
    if (!el() || el().hidden || !el().contains(e.target)) return;
    if (e.target.id === "su-noroms") { v.noRoms = e.target.checked; render(); }
    if (e.target.dataset.store) v.stores[e.target.dataset.store] = e.target.checked;
    if (e.target.id === "su-roms") checkRoms();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.id === "su-roms") checkRoms();
  });

  return { open };
})();
