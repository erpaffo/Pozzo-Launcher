/* Barra dei menu in alto (File, Strumenti, Visualizza, Impostazioni): scorciatoie per le funzioni e le
   impostazioni piu' usate. Usa le funzioni di app.js (script classico, stesso ambito globale); le
   impostazioni complete restano nella finestra Impostazioni. */
(() => {
  const click = (sel) => document.querySelector(sel)?.click();
  const setSelect = (sel, v) => { const el = document.querySelector(sel); el.value = v; el.dispatchEvent(new Event("change")); };
  const scan = async (mode) => {
    try { await api("/api/scan", { body: { mode } }); } catch (e) { return toast(e.message, true); }
    toast(mode === "all" ? t("b.menu.toast.scanAll") : t("b.menu.toast.scanNew"));
    SET.lastStatus = "running";
    pollScan();
  };
  const theme = async (id) => { await api("/api/app/theme", { body: { theme: id } }); await loadExtensions(); };
  window.GSMenu = { scan, theme }; // usati anche dalle scorciatoie (shortcuts.js)
  const sorts = () => [["title", t("b.core.shop.sort.title")], ["-year", t("b.menu.sort.year")], ["-last", t("b.menu.sort.lastPlayed")], ["-playtime", t("b.menu.sort.playtime")], ["-rating", t("b.common.rating")]];
  const groups = () => [["", t("b.menu.group.none")], ["platform", t("b.menu.group.platform")], ["year", t("b.menu.group.year")], ["letter", t("b.menu.group.letter")]];

  // "-" = separatore, {h} = titolo di gruppo, chk() = segno di spunta (puo' essere asincrono)
  const MENUS = {
    File: () => [
      { l: "👥 " + t("b.menu.file.switchUser"), a: "profile", f: () => GSProfilePicker.open({ onChange: applyProfile, toast }) },
      "-",
      { l: "＋ " + t("b.menu.file.addGame"), f: () => openAddGame("game") },
      { l: "🧩 " + t("b.menu.file.addApp"), f: () => openAddGame("app") },
      "-",
      { l: t("b.menu.file.exportBackup"), f: async () => { const r = await api("/api/backups", { body: {} }); toast(t("b.menu.toast.backupCreated", {nome: r.name})); } },
      { l: t("b.menu.file.importBackup"), f: () => openSettings("lib") },
      "-",
      { l: "↻ " + t("b.menu.file.reload"), f: () => reload(true) },
      { l: t("b.menu.file.refreshStores"), f: async () => { await api("/api/stores/refresh", { body: {} }); toast(t("b.menu.toast.storesRefresh")); } },
      "-",
      { l: t("b.menu.file.quit"), f: async () => { if (confirm(t("b.menu.confirm.quit"))) { try { await api("/api/app/quit", { body: {} }); } catch { /* il server si chiude */ } window.close(); } } },
    ],
    Strumenti: () => [
      { l: "⟳ " + t("b.menu.tools.scanNew"), a: "scanNew", f: () => scan("new") },
      { l: t("b.menu.tools.scanAll"), f: () => confirm(t("b.menu.confirm.scanAll")) && scan("all") },
      { l: t("b.menu.tools.scanMissing"), f: () => scan("missing") },
      "-",
      { l: t("b.menu.tools.clearCache"), f: async () => { const r = await api("/api/cache/thumbs/clear", { body: {} }); toast(t("b.menu.toast.thumbsRemoved", {n: r.removed})); } },
      { l: t("b.menu.tools.relink"), f: () => openSettings("scan") },
      { l: t("b.menu.tools.dedupe"), f: async () => { if (!confirm(t("b.menu.confirm.dedupe"))) return; const r = await api("/api/manual/dedupe", { body: {} }); toast(t("b.menu.toast.dupesRemoved", {n: r.removed})); await reload(true); } },
    ],
    Visualizza: () => [
      { h: t("b.menu.group.sortBy") },
      ...sorts().map(([v, l]) => ({ l, chk: () => S.sort === v, f: () => setSelect("#sort", v) })),
      { h: t("b.menu.group.groupBy") },
      ...groups().map(([v, l]) => ({ l, chk: () => ($("#group").value || "") === v, f: () => setSelect("#group", v) })),
      "-",
      { l: t("b.menu.view.hideDupes"), chk: () => $("#one-version").checked, f: () => click("#one-version") },
      { l: t("b.menu.view.zoomIn"), f: () => { const z = $("#zoom"); z.value = Math.min(+z.max, +z.value + 30); z.dispatchEvent(new Event("input")); } },
      { l: t("b.menu.view.zoomOut"), f: () => { const z = $("#zoom"); z.value = Math.max(+z.min, +z.value - 30); z.dispatchEvent(new Event("input")); } },
      "-",
      { l: t("b.menu.view.lightTheme"), chk: async () => (await api("/api/extensions")).active_theme === "chiaro",
        f: async () => theme((await api("/api/extensions")).active_theme === "chiaro" ? "default" : "chiaro") },
      { l: "🎮 Big Picture", a: "bigPicture", f: () => enterBigPicture() },
    ],
    Impostazioni: () => [
      { l: "⚙ " + t("b.menu.settings.all"), a: "settings", f: () => openSettings() },
      { l: "⌨ " + t("b.menu.settings.shortcuts"), a: "help", f: () => window.PozzoShortcuts?.openPanel() },
      { l: "🧭 " + t("b.menu.settings.tour"), f: () => window.GS?.tour?.start({ manual: true }) },
      "-",
      { l: t("b.menu.settings.folders"), f: () => openSettings("scan") },
      { l: t("b.menu.settings.accounts"), f: () => openSettings("acc") },
      { l: t("b.menu.settings.emulators"), f: () => openSettings("emu") },
      { l: t("b.menu.settings.look"), f: () => openSettings("look") },
      "-",
      { l: t("b.menu.settings.notify"), chk: async () => (await api("/api/app/notify")).enabled,
        f: async () => { const on = (await api("/api/app/notify")).enabled; await api("/api/app/notify", { body: { enabled: !on } }); toast(on ? t("b.menu.toast.notifyOff") : t("b.menu.toast.notifyOn")); } },
    ],
  };

  const TOP_KEY = {File: "b.menu.top.file", Strumenti: "b.menu.top.tools", Visualizza: "b.menu.top.view", Impostazioni: "b.common.settings"};
  const bar = document.createElement("nav");
  bar.id = "menubar";
  bar.innerHTML = Object.keys(MENUS).map((k) => `<button type="button" class="mb-top" data-m="${k}" data-i18n="${TOP_KEY[k]}">${k}</button>`).join("");
  document.getElementById("app").before(bar); // in cima alla finestra, sopra ogni esperienza
  document.documentElement.style.setProperty("--mb-h", `${bar.offsetHeight}px`);

  // Amici: pannello gestito da js/friends.js (si aggancia a questo pulsante); sta a destra, prima di profilo e attivita'
  bar.insertAdjacentHTML("beforeend", `<button type="button" id="mb-friends" title="Amici e presenze online" aria-haspopup="dialog" aria-expanded="false">`
    + `<span aria-hidden="true">👥</span><span>Amici</span><span id="friends-badge" hidden>0</span></button>`);

  // Utente attivo: il menu del profilo (cambia utente, nuovo profilo, icona e PIN), uguale a quello della barra laterale
  bar.insertAdjacentHTML("beforeend", `<button type="button" id="mb-profile" title="Utente attivo: clicca per cambiare" data-i18n-title="b.menu.profile.title" aria-haspopup="menu">`
    + `<span id="mb-profile-ico">👤</span><span id="mb-profile-name" data-i18n="b.menu.profile.default">Principale</span><span class="muted">▾</span></button>`);
  document.getElementById("mb-profile").onclick = (e) => { e.stopPropagation(); profileMenu(e.currentTarget); };
  if (typeof paintProfile === "function" && S?.profiles) paintProfile(); // i profili possono essere gia' arrivati

  // Attivita': tutte le operazioni in sottofondo (pannello qui sotto o finestra separata)
  bar.insertAdjacentHTML("beforeend", `<button type="button" id="mb-act" title="Operazioni in corso" data-i18n-title="b.menu.activity.title">⚙ <span data-i18n="b.menu.activity">Attività</span> <span id="mb-act-n"></span></button>`);
  const actBtn = document.getElementById("mb-act");
  const popOut = () => (window.pywebview?.api?.open_activity ? window.pywebview.api.open_activity()
    : window.open("/activity", "pozzo-activity", "popup,width=520,height=640"));
  actBtn.onclick = () => {
    const pan = document.getElementById("act-pop");
    if (pan) return pan.remove();
    document.body.insertAdjacentHTML("beforeend", `<div id="act-pop">
      <div class="ah"><b>${t("b.menu.activity")}</b><span><button type="button" id="act-out" title="${t("b.menu.activity.openWindow")}">⧉ ${t("b.menu.activity.window")}</button>
      <button type="button" id="act-x" title="${t("b.common.close")}">✕</button></span></div><iframe src="/activity"></iframe></div>`);
    document.getElementById("act-out").onclick = () => { document.getElementById("act-pop").remove(); popOut(); };
    document.getElementById("act-x").onclick = () => document.getElementById("act-pop").remove();
  };
  document.addEventListener("mousedown", (e) => { if (!e.target.closest("#act-pop, #mb-act")) document.getElementById("act-pop")?.remove(); });
  const count = async () => {
    try {
      const n = (await api("/api/activity")).jobs.filter((j) => j.status === "running").length;
      document.getElementById("mb-act-n").textContent = n || "";
      actBtn.classList.toggle("busy", n > 0);
    } catch { /* riprova al prossimo giro */ }
  };
  count();
  setInterval(count, 3000);

  let open = null;
  const close = () => { document.getElementById("mb-drop")?.remove(); bar.querySelectorAll(".on").forEach((b) => b.classList.remove("on")); open = null; };

  async function show(btn) {
    close();
    open = btn.dataset.m;
    btn.classList.add("on");
    const rows = MENUS[open]();
    const marks = await Promise.all(rows.map((r) => (r.chk ? Promise.resolve().then(r.chk).catch(() => false) : false)));
    if (open !== btn.dataset.m) return; // nel frattempo si e' aperto un altro menu
    const d = document.createElement("div");
    d.id = "mb-drop";
    d.innerHTML = rows.map((r, i) => r === "-" ? "<hr>" : r.h ? `<div class="ch">${esc(r.h)}</div>`
      : `<div class="ci" data-i="${i}"><span class="mk">${marks[i] ? "✓" : ""}</span>${esc(r.l)}${r.a && window.PozzoShortcuts?.keyLabel(r.a) ? `<span class="ac">${esc(window.PozzoShortcuts.keyLabel(r.a))}</span>` : ""}</div>`).join("");
    document.body.appendChild(d);
    const b = btn.getBoundingClientRect();
    d.style.left = Math.max(4, Math.min(b.left, innerWidth - d.offsetWidth - 8)) + "px";
    d.style.top = b.bottom + "px";
    d.onclick = async (ev) => {
      const it = ev.target.closest(".ci");
      if (!it) return;
      const f = rows[+it.dataset.i].f;
      close();
      try { await f(); } catch (e) { toast(e.message, true); }
    };
  }

  bar.addEventListener("click", (e) => {
    const b = e.target.closest(".mb-top");
    if (b) open === b.dataset.m ? close() : show(b);
  });
  bar.addEventListener("mouseover", (e) => {  // con un menu aperto basta passare sopra un altro per aprirlo
    const b = e.target.closest(".mb-top");
    if (b && open && open !== b.dataset.m) show(b);
  });
  document.addEventListener("mousedown", (e) => { if (open && !e.target.closest("#menubar, #mb-drop")) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open) close(); });
})();
