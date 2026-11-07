"use strict";
/* Pozzo Launcher - frontend: eventi (bind). Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ eventi */
function bind() {
  // a11y: aprendo il dettaglio il focus va al titolo; closeDetail (detail.js) riporta il focus sull'elemento di partenza
  let detailWasOpen = false;
  new MutationObserver(() => {
    const open = $("#detail").classList.contains("open"), h = $("#detail-title");
    if (open && !detailWasOpen && h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
    detailWasOpen = open;
  }).observe($("#detail"), { attributes: true, attributeFilter: ["class"] });
  $("#feedback-btn").onclick = () => api("/api/open", {
    body: { url: "https://github.com/erpaffo/Pozzo-Launcher/issues/new/choose" },
  }).catch((e) => toast(e.message, true));
  // a11y: le voci create da sidebar.js (store, piattaforme, plugin) non hanno tabindex: le rendo raggiungibili da tastiera
  const focusableNav = () => document.querySelectorAll("#nav .nav-item:not([tabindex])").forEach((a) => {
    a.tabIndex = 0;
    a.setAttribute("role", "button");
  });
  focusableNav();
  new MutationObserver(focusableNav).observe($("#nav"), { childList: true, subtree: true });
  $("#nav").addEventListener("click", (e) => {
    const star = e.target.closest("[data-toggle-fav-ext]");
    if (star) {
      e.preventDefault();
      e.stopPropagation();
      toggleFavExt(star.dataset.toggleFavExt);
      return;
    }
    const a = e.target.closest(".nav-item");
    if (!a || a.dataset.otherPlats !== undefined) return; // il gruppo «Altre console» ha il suo gestore
    if (a.dataset.pluginItem && !a.dataset.view) {
      const it = GS.ui.sidebarItems.find((x) => x.id === a.dataset.pluginItem);
      try { it?.onClick?.(GS); } catch (err) { toast(err.message, true); }
      setDrawer(false, false);
      return;
    }
    if (a.dataset.view === "ports") PORTS_F.open = null; // dalla barra laterale: sempre il catalogo
    setView({ type: a.dataset.view, id: a.dataset.id || null, plat: a.dataset.plat || undefined });
    setDrawer(false, false);
  });
  $("#nav").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const star = e.target.closest("[data-toggle-fav-ext]");
    if (star) {
      e.preventDefault();
      e.stopPropagation();
      toggleFavExt(star.dataset.toggleFavExt);
      return;
    }
    const a = e.target.closest(".nav-item");
    if (!a) return;
    e.preventDefault();
    a.click();
  });
  $("#platform-list").addEventListener("click", (e) => {
    if (!e.target.closest("[data-other-plats]")) return;
    let open = false;
    try { open = localStorage.getItem("gs.otherPlatsOpen") === "1"; localStorage.setItem("gs.otherPlatsOpen", open ? "0" : "1"); } catch {}
    renderSidebar();
  });
  $("#drawer-toggle").onclick = () => setDrawer(!$("#sidebar").classList.contains("drawer-open"));
  $("#drawer-scrim").onclick = () => setDrawer(false);
  $("#experience-nav").addEventListener("click", (e) => {
    const a = e.target.closest("[data-view]");
    if (a) { setView({ type: a.dataset.view }); setDrawer(false, false); } // altrimenti il cassetto resta aperto sopra la libreria
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("#sidebar").classList.contains("drawer-open")) setDrawer(false);
  });
  $("#inst-filter").value = S.instFilter;
  // altri store PC: aggiunta, rimozione, categoria e filtro
  $("#pcst-add").onclick = () => {
    const url = $("#pcst-url").value.trim();
    if (!/^https?:\/\//i.test(url)) return toast(t("g.ev.url.invalid"), true);
    if (PCST.rows.some((r) => r.url === url)) return toast(t("g.ev.pcstore.exists"));
    savePcStores([...PCST.rows, { url, kind: $("#pcst-kind").value }], false);
    $("#pcst-url").value = "";
  };
  // anteprima: legge solo la prima pagina e dice quanti giochi/pagine ci sono
  $("#pcst-probe").onclick = async () => {
    const url = $("#pcst-url").value.trim();
    if (!/^https?:\/\//i.test(url)) return toast(t("g.ev.url.invalid"), true);
    const out = $("#pcst-probe-out");
    out.textContent = t("g.ev.probe.reading");
    let r;
    try { r = await api("/api/pc-stores/probe", { body: { url } }); } catch (e) { out.textContent = ""; return toast(e.message, true); }
    const many = r.pages > 1 ? t("g.ev.probe.pages", { n: r.pages.toLocaleString(GSI18n.lang) }) : t("g.ev.probe.single_page");
    const ex = r.samples.length ? ` ${t("g.ev.probe.examples", { list: r.samples.slice(0, 3).join(" · ") })}` : "";
    out.textContent = `${r.games ? "✅" : "⚠️"} ${t("g.ev.probe.result", { kind: r.kind, n: r.games.toLocaleString(GSI18n.lang), many })}${ex}`;
  };
  // aggiornamento di tutti gli store: modalità (avvio / orario / manuale), parallelismo, avvio a mano
  $("#srf-mode").onchange = () => { $("#srf-time").disabled = $("#srf-mode").value !== "daily"; };
  const saveStoreSchedule = async () => {
    const body = { mode: $("#srf-mode").value, time: $("#srf-time").value, workers: Number($("#srf-workers").value) || 4 };
    renderStoreRefresh(await api("/api/store-refresh", { body }));
  };
  for (const id of ["srf-mode", "srf-time", "srf-workers"]) autosaveControl($("#" + id), saveStoreSchedule);
  $("#srf-run").onclick = async () => {
    try { await api("/api/store-refresh/run", { body: {} }); } catch (e) { return toast(e.message, true); }
    pollStoreRefresh();
  };
  $("#srf-stop").onclick = async () => {
    try { await api("/api/store-refresh/stop", { body: {} }); } catch (e) { return toast(e.message, true); }
    pollStoreRefresh();
  };
  // log e aggiornamento del singolo store (row della lista)
  $("#srf-progress").addEventListener("click", async (e) => {
    const logBtn = e.target.closest("[data-srf-log]");
    if (logBtn) {
      if (!srfLast) return;
      const id = logBtn.dataset.srfLog;
      if (srfOpen.has(id)) srfOpen.delete(id); else srfOpen.add(id);
      renderStoreRefreshJob(srfLast.job || { status: "idle" }, srfLast.list);
      return;
    }
    const runBtn = e.target.closest("[data-srf-run]");
    if (!runBtn) return;
    try { await api("/api/store-refresh/run", { body: { ids: [runBtn.dataset.srfRun] } }); }
    catch (err) { return toast(err.message, true); }
    pollStoreRefresh();
  });
  // integrazioni: notifiche di Windows
  autosaveControl($("#nt-on"), (enabled) => api("/api/app/notify", { body: { enabled } }));
  autosaveControl($("#bp-start"), (enabled) => api("/api/app/start-bigpicture", { body: { enabled } }));
  autosaveControl($("#resume-session-start"), (enabled) => { store.set("resumeSession", enabled); });
  // a coda vuota: sospendi o spegni
  autosaveControl($("#pw-after"), (after_jobs) => api("/api/app/power", { body: { after_jobs } }).then(loadPower));
  $("#pw-abort").onclick = async () => {
    try { await api("/api/app/power/abort", { body: {} }); loadPower(); toast(t("g.ev.common.cancelled")); } catch (err) { toast(err.message, true); }
  };
  // integrazioni: presenza su Discord
  $("#dc-save").onclick = async () => {
    const body = { enabled: $("#dc-on").checked, client_id: $("#dc-id").value.trim(), show_time: $("#dc-time").checked };
    let d;
    try { d = await api("/api/integrations/discord", { body }); } catch (e) { return toast(e.message, true); }
    $("#dc-state").textContent = "";
    renderIntegrations({ discord: d.discord });
    toast(body.enabled ? t("g.ev.discord.updated") : t("g.ev.discord.off"));
  };
  autosaveControl($("#dc-on"), (enabled) => api("/api/integrations/discord", { body: { enabled } }));
  autosaveControl($("#dc-time"), (show_time) => api("/api/integrations/discord", { body: { show_time } }));
  $("#pcst-refresh").onclick = async () => {
    try { await api("/api/pc-stores/refresh", { body: {} }); } catch (e) { return toast(e.message, true); }
    pollStoreRefresh(); // la coda unica mostra l'avanzamento nel blocco «Aggiornamento degli store»
    pollPcStores();
  };
  $("#pcst-meta").onclick = async () => {
    try { await api("/api/catalogs/windows/netmeta", { body: {} }); } catch (e) { return toast(e.message, true); }
    toast(t("g.ev.pcstore.covers_running"));
  };
  $("#pcst-filter").addEventListener("click", (e) => {
    const b = e.target.closest("[data-pcst-filter]");
    if (!b) return;
    PCST.filter = b.dataset.pcstFilter;
    document.querySelectorAll("#pcst-filter .btn").forEach((x) => x.classList.toggle("on", x === b));
    renderPcStores(null);
  });
  $("#pcst-table").addEventListener("click", (e) => {
    const del = e.target.closest("[data-pcst-del]");
    if (del) savePcStores(PCST.rows.filter((r) => r.url !== del.dataset.pcstDel), true);
  });
  $("#pcst-table").addEventListener("change", (e) => {
    const s = e.target.closest("[data-pcst-kind]");
    if (!s) return;
    savePcStores(PCST.rows.map((r) => (r.url === s.dataset.pcstKind ? { ...r, kind: s.value } : r)), false);
  });
  $("#acc-table").addEventListener("click", (e) => {
    if (e.target.closest("[data-ports-open]")) { closeSettings(); setView({ type: "ports", id: null }); }
  });
  $("#inst-filter").onchange = (e) => { S.instFilter = e.target.value; store.set("instFilter", S.instFilter); refreshGrid(); };
  $("#pc-add").onclick = () => openAddGame();
  $("#bp-btn").onclick = () => enterBigPicture();
  $("#refresh-btn").onclick = async () => {
    try { await loadLibrary(); } catch (e) { toast(t("g.ev.library.reload_failed")); return; }
    refreshGrid(true);
    toast(t("g.ev.library.updated"));
  };
  $("#random-btn").onclick = () => {
    // tra quelli mostrati; meglio se si possono avviare subito (niente da scaricare o installare)
    const ready = S.items.filter((g) => !g.store || (g.store !== "online" && g.installed));
    const pool = ready.length ? ready : S.items;
    if (!pool.length) return toast(t("g.ev.random.empty"));
    openDetail(pool[Math.floor(Math.random() * pool.length)].id);
  };
  GS.on("uiChanged", () => { if (S.games.length) { renderSidebar(); } });
  layer.addEventListener("click", (e) => { const t = e.target.closest(".tile"); if (t) openDetail(+t.dataset.id); });
  layer.addEventListener("dblclick", (e) => { const t = e.target.closest(".tile"); if (t) play(+t.dataset.id); });
  layer.addEventListener("focusin", (e) => {
    const tile = e.target.closest(".tile[data-id]");
    const game = tile && S.byId.get(+tile.dataset.id);
    if (!game || typeof GS.experience?.onFocus !== "function") return;
    try { GS.experience.onFocus(game); }
    catch (err) { console.warn(`Focus esperienza ${GS.experience.id}:`, err); }
  });
  layer.addEventListener("keydown", (e) => {
    const tile = e.target.closest(".tile[data-id]");
    if (!tile || !["Enter", " "].includes(e.key)) return;
    e.preventDefault();
    openDetail(+tile.dataset.id);
  });
  $("#platform-list").addEventListener("contextmenu", (e) => {
    const a = e.target.closest("[data-view=platform]");
    if (!a) return;
    e.preventDefault();
    openPlatCtx(e, a.dataset.id);
  });
  $("#plugin-nav").addEventListener("contextmenu", (e) => {
    const a = e.target.closest("[data-plugin-item]");
    if (!a) return;
    e.preventDefault();
    openExtCtx(e, a.dataset.pluginItem);
  });
  document.addEventListener("contextmenu", (e) => {
    // dove serve (campi di testo, finestre aperte, il menu stesso) resta quello del browser
    if (e.target.closest("input, textarea, select, [contenteditable], dialog, #ctxmenu")) return;
    const g = gameFromEvent(e);
    if (!g) return;
    e.preventDefault();
    openCtx(e, g);
  });
  // Home, scaffali e le altre viste; lo scorrimento del menu stesso (ha un'altezza massima) non lo chiude
  document.addEventListener("scroll", (e) => { if (!(e.target instanceof Element && e.target.closest("#ctxmenu"))) closeCtx(); },
    { capture: true, passive: true });
  document.addEventListener("mousedown", (e) => { if (!e.target.closest("#ctxmenu")) closeCtx(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCtx(); });
  scroller.addEventListener("scroll", () => closeCtx(), { passive: true });
  window.addEventListener("blur", closeCtx);
  window.addEventListener("focus", syncLibrary);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) syncLibrary(); });
  setInterval(syncLibrary, 3000); // libreria ricostruita da un lavoro in sottofondo: compare entro 3 s
  scroller.addEventListener("scroll", scheduleRender, { passive: true });
  new ResizeObserver(() => { layout(); render(); }).observe(scroller);

  let st = 0;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(st);
    st = setTimeout(() => {
      S.search = e.target.value.trim();
      // dalla home di un tema o da una vista senza griglia la ricerca porta ai risultati
      if (S.search && (S.view.type === "home" || document.body.classList.contains("foryou-mode"))) return setView({ type: "all" });
      refreshGrid();
    }, 120);
  });
  $("#sort").value = S.sort;
  for (const k of ["preset", "genre", "decade"]) {
    $(`#disc-${k}`).onchange = (e) => { S.disc[k] = e.target.value; store.set("disc", S.disc); e.target.classList.toggle("on", !!e.target.value); $("#disc-reset").hidden = !(S.disc.preset || S.disc.genre || S.disc.decade); refreshGrid(); };
  }
  for (const k of ["src", "plat", "size"]) {
    $(`#shop-${k}`).onchange = (e) => { S.shopF[k] = e.target.value; store.set("shopF", S.shopF); refreshGrid(); };
  }
  $("#disc-reset").onclick = () => { S.disc.preset = S.disc.genre = S.disc.decade = ""; store.set("disc", S.disc); renderDiscTools(); refreshGrid(); };
  $("#sort").onchange = (e) => { S.sort = e.target.value; store.set("sorts", { ...store.get("sorts", {}), [S.view.type]: S.sort }); refreshGrid(); };
  $("#group").value = S.group;
  $("#group").onchange = (e) => { S.group = e.target.value; store.set("group", S.group); refreshGrid(); };
  $("#one-version").checked = S.oneVersion;
  $("#one-version").onchange = (e) => { S.oneVersion = e.target.checked; store.set("oneVersion", S.oneVersion); renderSidebar(); refreshGrid(); };
  $("#zoom").value = S.zoom;
  $("#zoom").oninput = (e) => {
    S.zoom = +e.target.value; store.set("zoom", S.zoom);
    const anchor = scroller.scrollTop / Math.max(1, S.total);
    for (const el of S.nodes.values()) el.remove();
    S.nodes.clear();
    layout(); scroller.scrollTop = anchor * S.total; render();
  };
  $("#coll-filter").addEventListener("input", (e) => { S.collFilter = e.target.value; renderCollList(); });
  $("#coll-sort").onclick = () => { S.collSort = S.collSort === "name" ? "count" : "name"; store.set("collSort", S.collSort); renderCollList();
    toast(S.collSort === "name" ? t("g.ev.coll.sort_name") : t("g.ev.coll.sort_count")); };
  $("#coll-new").onclick = async (e) => {
    const name = await askText(e.currentTarget, t("g.ev.coll.new_name"));
    if (!name) return;
    try { const r = await api("/api/collections", { body: { name } }); await reload(true); setView({ type: "collection", id: r.slug }); }
    catch (err) { toast(err.message, true); }
  };
  $("#view-actions").addEventListener("click", async (e) => {
    if (e.target.id === "cat-open") { openCatalog(S.view.id); return; }
    if (e.target.closest("#shop-hide-dlc")) {
      S.shopF.hideDlc = !S.shopF.hideDlc;
      store.set("shopF", S.shopF);
      updateHeader();
      refreshGrid();
      return;
    }
    if (e.target.id === "plat-scan") {
      try {
        if (S.view.type === "store") {
          await api("/api/stores/refresh", { body: { only: S.view.id === "all" ? null : [S.view.id] } });
          toast(t("g.ev.scan.searching_store"));
          pollStores(true);
        } else {
          await api("/api/scan", { body: { platforms: [S.view.id], mode: "new" } });
          toast(t("g.ev.scan.searching_plat"));
          SET.lastStatus = "running"; setScanRunning(true); pollScan();
        }
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (e.target.id === "top-open") { setView({ type: "top", id: S.view.id }); return; }
    if (e.target.id === "all-local") { S.allLocal = !S.allLocal; store.set("allLocal", S.allLocal); setView(S.view); return; }
    if (e.target.closest("#smart-edit")) { openSmart(S.view.id); return; }
    if (e.target.closest("#smeta-open")) { $("#smeta").showModal(); pollStoreMeta(); return; }
    if (e.target.id === "dup-toggle") {
      const r = await api("/api/app/duplicates", { body: { skip: !S.skipDup } });
      S.skipDup = r.skip_duplicates;
      updateHeader();
      toast(S.skipDup ? t("g.ev.dup.skip_on")
        : t("g.ev.dup.skip_off"));
      return;
    }
    const c = S.collBySlug.get(S.view.id);
    if (!c) return;
    if (e.target.id === "coll-rename") {
      const name = await askText(e.target, t("g.ev.common.new_name"), c.name);
      if (name) { await api(`/api/collections/${encodeURIComponent(c.slug)}`, { method: "PATCH", body: { name } }); await reload(true); }
    } else if (e.target.id === "coll-delete") {
      if (!confirm(c.custom ? t("g.ev.coll.delete_confirm", { name: c.name }) : t("g.ev.coll.hide_confirm", { name: c.name }))) return;
      await api(`/api/collections/${encodeURIComponent(c.slug)}`, { method: "DELETE" });
      S.view = { type: "all" }; await reload(false);
    }
  });

  $("#view-actions").addEventListener("change", async (e) => {
    if (e.target.id !== "hide-dlc") return;
    try {
      const r = await api("/api/app/hide-dlc", { body: { platform: S.view.id, hide: e.target.checked } });
      S.hideDlc = new Set(r.hide_dlc);
    } catch (err) { e.target.checked = !e.target.checked; return toast(err.message, true); }
    refreshGrid();
    toast(e.target.checked ? t("g.ev.dlc.hidden", { plat: platName(S.view.id) }) : t("g.ev.dlc.visible", { plat: platName(S.view.id) }));
  });

  $("#detail-close").onclick = closeDetail;
  $("#md-q").oninput = googleImages;
  $("#md-q").onkeydown = (e) => { if (e.key === "Enter") $("#md-google").click(); };
  $("#md-use").onclick = () => useMedia($("#md-url").value.trim());
  $("#md-tiles").onclick = (e) => { const t = e.target.closest(".md-tile"); if (t) renderMedia(t.dataset.kind); };
  $("#md-kind").onchange = (e) => renderMedia(e.target.value);
  $("#md-upload").onclick = () => $("#md-file").click();
  $("#md-file").onchange = (e) => { const f = e.target.files[0]; e.target.value = ""; uploadMedia(f); };
  $("#md-reset").onclick = resetMedia;
  $("#md-cands").onclick = (e) => { const b = e.target.closest("button[data-url]"); if (b) useMedia(b.dataset.url); };
  // trascinare un file nella finestra lo carica per il tipo scelto
  const mdDlg = $("#media-dlg");
  mdDlg.addEventListener("dragover", (e) => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); mdDlg.classList.add("drop"); } });
  mdDlg.addEventListener("dragleave", (e) => { if (!mdDlg.contains(e.relatedTarget)) mdDlg.classList.remove("drop"); });
  mdDlg.addEventListener("drop", (e) => { e.preventDefault(); mdDlg.classList.remove("drop"); uploadMedia(e.dataTransfer.files[0]); });
  $("#md-paste").onclick = async () => {
    let url = "";
    try { url = (await navigator.clipboard.readText() || "").trim(); } catch { /* permesso negato: si incolla a mano */ }
    if (url) $("#md-url").value = url;
    useMedia(url || $("#md-url").value.trim());
  };
  // la nota si salva quando si esce dal campo (change), senza ridisegnare la scheda
  $("#detail").addEventListener("change", async (e) => {
    const d = S.detail;
    if (e.target.id !== "d-note" || !d) return;
    const v = e.target.value.trim();
    try { await api(`/api/game/${d.id}/flag`, { body: { field: "note", value: v } }); } catch (err) { return toast(err.message, true); }
    d.user.note = v;
    toast(v ? t("g.ev.note.saved") : t("g.ev.note.deleted"));
  });
  $("#detail").addEventListener("click", async (e) => {
    const d = S.detail;
    if (!d) return;
    const t = e.target;
    if (t.id === "d-play") play(d.id);
    else if (t.id === "d-install") installGame(d.id);
    else if (t.id === "d-torrent") api(`/api/game/${d.id}/torrent`, { body: {} })
      .then((r) => r.internal ? toast(window.t("g.ev.torrent.started", { file: r.file, dest: r.dest })) : toast(r.single ? window.t("g.ev.torrent.single", { file: r.file })
        : window.t("g.ev.torrent.set", { file: r.file })))
      .catch((err) => toast(err.message, true));
    else if (t.dataset.install) installGame(+t.dataset.install);
    else if (t.dataset.port) { closeDetail(); PORTS_F.open = t.dataset.port; setView({ type: "ports" }); }
    else if (t.id === "d-page") api(`/api/game/${d.id}/store-page`, { body: {} }).catch((err) => toast(err.message, true));
    else if (t.id === "d-manual-del") {
      try { await removeManual(d); } catch (err) { toast(err.message, true); }
    } else if (t.dataset.ga) {
      const a = GS.ui.gameActions.find((x) => x.id === t.dataset.ga);
      try { await a.run(d, GS); } catch (err) { toast(err.message, true); }
    }
    else if (t.id === "d-fav") setFlag("favorite", !d.user.favorite);
    else if (t.dataset.status) setFlag("status", d.user.status === t.dataset.status ? "" : t.dataset.status);
    else if (t.dataset.myrate) {
      const n = +t.dataset.myrate === d.user.my_rating ? 0 : +t.dataset.myrate; // stessa stella = togli il voto
      try { await api(`/api/game/${d.id}/flag`, { body: { field: "my_rating", value: n } }); } catch (err) { return toast(err.message, true); }
      d.user.my_rating = n;
      document.querySelectorAll("#detail .star").forEach((b) => b.classList.toggle("on", +b.dataset.myrate <= n));
    }
    else if (t.dataset.open) { e.preventDefault(); api("/api/open", { body: { url: t.dataset.open } }); }
    else if (t.id === "d-download") downloadMain(d);
    else if (t.id === "d-magnet") {
      const mag = dlMagnetUrl();
      if (mag) downloadLinks(d, [mag]);
      else toast(window.t("g.ev.magnet.none"), true);
    }
    else if (t.id === "d-hide") setFlag("hidden", !d.user.hidden);
    else if (t.id === "d-folder") api(`/api/game/${d.id}/open-folder`, { body: {} }).catch((err) => toast(err.message, true));
    else if (t.id === "d-emu-cfg") { e.preventDefault(); openSettings("emu"); }
    else if (t.id === "d-profile") { e.preventDefault(); openProfile(d); }
    else if (t.id === "d-media") { e.preventDefault(); openMediaPick(d); }
    else if (t.id === "d-shortcut") {
      e.preventDefault();
      api(`/api/game/${d.id}/shortcut`, { body: {} }).then(() => toast(window.t("g.ev.shortcut.created", { title: d.title })), (err) => toast(err.message, true));
    }
    else if (t.id === "d-shots-all") { e.preventDefault(); openLightbox(SHOTS.detail, 0); }
    else if (t.closest("#d-myshots [data-i]")) { openLightbox(SHOTS.detail, +t.closest("#d-myshots [data-i]").dataset.i); }
    else if (t.id === "d-scrape") {
      try { await api("/api/scan", { body: { game: d.id, mode: "missing" } }); }
      catch (err) { return toast(err.message, true); }
      t.disabled = true;
      t.textContent = window.t("g.ev.scrape.running");
      toast(window.t("g.ev.scrape.searching", { title: d.title }));
      SET.lastStatus = "running";
      pollScan();
    }
    else if (t.id === "d-add-coll") pickCollection(t, d.id, d.collections.map((c) => c.slug));
    else if (t.classList.contains("x")) {
      const slug = t.closest(".chip").dataset.slug;
      try { await api(`/api/collections/${encodeURIComponent(slug)}/members`, { body: { game: d.id, action: "remove" } }); } catch (err) { return toast(err.message, true); }
      await reload(true); openDetail(d.id);
    } else if (t.closest(".chip[data-slug]")) { setView({ type: "collection", id: t.closest(".chip").dataset.slug }); }
    else if (t.dataset.play) play(+t.dataset.play);
    else if (t.dataset.pref) {
      await api(`/api/game/${t.dataset.pref}/preferred`, { body: {} });
      await reload(true); openDetail(+t.dataset.pref);
    }
  });

  $("#settings-btn").onclick = () => openSettings();
  $("#scan-btn").onclick = () => openSettings("scan");
  $("#rebuild-btn").onclick = rebuild;
  $("#backup-now").onclick = backupNow;
  $("#save-dir-pick").onclick = async () => { const p = await pickPath("folder"); if (p) $("#save-dir").value = p; };
  $("#save-dir-save").onclick = () => api("/api/app/save-dir", { body: { save_dir: $("#save-dir").value } })
    .then((r) => { loadSaveDir(r); toast(t("g.ev.saves.dir_saved")); }, (e) => toast(e.message, true));
  bindSync();
  $("#profile-btn").onclick = (e) => profileMenu(e.currentTarget);
  bindProfilesSettings();
  $("#ra-save").onclick = async () => {
    const body = { username: $("#ra-user").value };
    if ($("#ra-key").value.trim()) body.key = $("#ra-key").value.trim();
    try { await api("/api/ra", { body }); toast(t("g.ev.ra.linked")); $("#ra-key").value = ""; loadAccounts(); }
    catch (e) { toast(e.message, true); }
  };
  const sxRun = async (go, key, params) => {
    $("#sx-info").textContent = "";
    try {
      const r = await go();
      $("#sx-info").textContent = t(key, { n: r[params], a: r.art, k: r.kept });
    } catch (e) { toast(e.message, true); }
  };
  $("#sx-what").onchange = () => { $("#sx-plats").hidden = $("#sx-what").value !== "platforms"; };
  $("#sx-go").onclick = () => sxRun(() => api("/api/steam-export", { body: {
    account: $("#sx-user").value, what: $("#sx-what").value, platforms: [...$("#sx-plats").selectedOptions].map((o) => o.value) } }), "g.steamx.done", "added");
  $("#sx-rm").onclick = () => sxRun(() => api(`/api/steam-export?account=${encodeURIComponent($("#sx-user").value)}`, { method: "DELETE" }), "g.steamx.removed", "removed");
  $("#xf-pick").onclick = async () => { const p = window.pywebview?.api ? await pickPath("folder") : null; if (p) $("#xf-out").value = p; };
  // la pagina web ha un titolo proprio: il campo compare solo per quel formato
  $("#xf-format").onchange = () => { $("#xf-title-row").hidden = $("#xf-format").value !== "html"; };
  $("#xf-title-row").hidden = $("#xf-format").value !== "html";
  $("#xf-go").onclick = async (e) => {
    e.target.disabled = true;
    $("#xf-info").textContent = t("g.ev.export.running");
    try {
      const r = await api("/api/export/frontend", {
        body: { format: $("#xf-format").value, out_dir: $("#xf-out").value, title: $("#xf-title").value.trim() },
      });
      $("#xf-info").textContent = t("g.ev.export.done", { n: r.games.toLocaleString(GSI18n.lang), consoles: Object.keys(r.summary).length, dir: r.out_dir })
        + (r.index ? ` · ${t("g.ev.export.open", { index: r.index })}` : "");
    } catch (err) { $("#xf-info").textContent = ""; toast(err.message, true); }
    e.target.disabled = false;
  };
  $("#health-reload").onclick = loadHealth;
  $("#about-check").onclick = () => checkUpdate(true, true);
  $("#storage-go").onclick = () => loadStorage(true);
  $("#csrc-go").onclick = loadCacheSources;
  $("#csrc-clear-all").onclick = () => clearCacheSource("");
  $("#api-token-copy").onclick = async () => {
    try { await navigator.clipboard.writeText($("#api-token").value); toast(t("g.ev.token.copied")); }
    catch { toast(t("g.ev.token.copy_failed"), true); }
  };
  $("#api-token-new").onclick = async () => {
    if (!confirm(t("g.ev.token.change_confirm"))) return;
    try { const r = await api("/api/api-token", { body: {} }); $("#api-token").value = r.token; toast(t("g.ev.token.created")); }
    catch (e) { toast(e.message, true); }
  };
  checkUpdate(false, false); // subito all'avvio, in parallelo al caricamento dei giochi (la risposta resta in cache 2 ore)
  setInterval(() => checkUpdate(false, false), 30 * 60000); // app lasciata aperta per giorni
  document.addEventListener("visibilitychange", () => { if (!document.hidden) checkUpdate(false, false); });
  $("#health-list").addEventListener("click", (e) => { const b = e.target.closest(".hl-fix"); if (b) healthFix(SET.health[+b.dataset.i].fix); });
  $("#backup-list").addEventListener("click", (e) => { const b = e.target.closest(".bk-restore"); if (b) restoreBackup(b.dataset.name); });
  initSettingsLayout();

  // scraping
  $("#scan-start").onclick = startScan;
  $("#scan-cancel").onclick = () => api("/api/scan/cancel", { body: {} }).then(() => toast(t("g.ev.scan.stopping")));
  $("#scan-reload").onclick = loadScan;
  $("#scan-mode").onchange = applyScanMode;
  $("#scan-table").addEventListener("change", (e) => {
    if (e.target.id === "scan-all") document.querySelectorAll(".scan-sel").forEach((c) => { c.checked = e.target.checked; });
    if (e.target.id === "scan-all" || e.target.classList?.contains("scan-sel")) applyScanMode();
  });
  $("#scan-table").addEventListener("click", (e) => {
    const b = e.target.closest(".paste-dir");
    if (b) pasteFolder(b.dataset.platform);
  });
  $("#scan-unknown").addEventListener("change", async (e) => {
    const s = e.target.closest(".map-folder");
    if (!s || !s.value) return;
    try {
      const pv = await api("/api/folders", { body: { folder: s.dataset.folder, platform: s.value } });
      renderScan(pv, null);
      toast(t("g.ev.scan.mapped", { folder: s.dataset.folder }));
    } catch (err) { toast(err.message, true); }
  });

  // store online per console
  $("#cat-save").onclick = async () => {
    const urls = $("#cat-urls").value.split(/\s+/).filter(Boolean);
    try { renderCatalog(await api(`/api/catalogs/${SET.catPid}`, { body: { urls } })); } catch (e) { return toast(e.message, true); }
    refreshCatalogs();
    if (urls.length) pollCatalog(); else toast(t("g.ev.catalog.unlinked"));
  };
  $("#cat-refresh").onclick = async () => {
    try { await api(`/api/catalogs/${SET.catPid}/refresh`, { body: {} }); } catch (e) { return toast(e.message, true); }
    pollCatalog();
  };
  $("#cat-meta-btn").onclick = async () => {
    if (!SET.catPid) return;
    try {
      const running = SET.metaRunning;
      await api(`/api/catalogs/${SET.catPid}/netmeta${running ? "/stop" : ""}`, { body: {} });
    } catch (e) { return toast(e.message, true); }
    pollMeta();
  };
  // console personalizzate
  $("#console-add").onclick = () => { ["cn-name", "cn-id", "cn-exts", "cn-aliases", "cn-igdb"].forEach((i) => { $("#" + i).value = ""; }); $("#console-dlg").showModal(); };
  $("#cn-name").oninput = (e) => { $("#cn-id").placeholder = e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "") || "es. pc8801"; };
  $("#cn-save").onclick = async () => {
    const body = { name: $("#cn-name").value, id: $("#cn-id").value || $("#cn-id").placeholder.replace(/^es\. /, ""),
      exts: $("#cn-exts").value, aliases: $("#cn-aliases").value.split(","), cd: $("#cn-cd").checked,
      dir_games: $("#cn-dir").checked, igdb: $("#cn-igdb").value };
    try { await api("/api/platforms/custom", { body }); } catch (e) { return toast(e.message, true); }
    $("#console-dlg").close();
    SET.platforms = null;
    toast(t("g.ev.console.added", { name: body.name }));
    loadScan(); renderCustomConsoles();
  };
  $("#custom-consoles").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-cdel]");
    if (!b || !confirm(t("g.ev.console.remove_confirm"))) return;
    await api(`/api/platforms/custom/${b.dataset.cdel}`, { method: "DELETE" });
    SET.platforms = null;
    loadScan(); renderCustomConsoles();
  });

  // fonti dei dati
  $("#src-table").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mv]");
    if (!b) return;
    const tr = b.closest("tr"), dir = +b.dataset.mv;
    const sib = dir < 0 ? tr.previousElementSibling : tr.nextElementSibling;
    if (sib) { (dir < 0 ? sib.before(tr) : sib.after(tr)); scheduleSourceSave(); }
  });
  $("#src-table").addEventListener("change", (e) => {
    if (e.target.matches("[data-en]")) {
      e.target.closest("tr").classList.toggle("src-off", !e.target.checked);
      scheduleSourceSave();
    }
  });
  $("#src-table").addEventListener("input", (e) => {
    if (e.target.matches("[data-lim]")) scheduleSourceSave();
  });
  for (const id of ["sch-on", "sch-time", "sch-mode"]) $("#" + id).addEventListener("change", scheduleSourceSave);
  $("#rawg-save").onclick = async () => {
    if (!$("#rawg-key").value.trim()) return toast(t("g.ev.rawg.paste_first"), true);
    try { SET.sources = await api("/api/sources", { body: collectSources() }); } catch (e) { return toast(e.message, true); }
    $("#rawg-key").value = "";
    loadSources();
    toast(t("g.ev.rawg.saved"));
  };
  $("#bulk-list").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-bulk]");
    if (!b) return;
    try { await api(`/api/bulk/${b.dataset.bulk}/refresh`, { body: {} }); } catch (err) { return toast(err.message, true); }
    toast(t("g.ev.bulk.started"));
    pollBulk();
  });
  $("#scan-plan").onclick = showPlan;
  $("#setup-open").onclick = async () => { closeSettings(); await SETUP.open(true); await reload(true); };
  $("#roms-change").onclick = async () => {
    let p = window.pywebview?.api ? await pickPath("folder") : prompt(t("g.ev.roms.prompt"), $("#scan-root").textContent);
    if (!p) return;
    try { await api("/api/roms", { body: { path: p } }); } catch (e) { return toast(e.message, true); }
    toast(t("g.ev.roms.updated"));
    loadScan();
  };
  $("#scan-extra").addEventListener("click", async (e) => {
    const del = e.target.closest(".xr-del");
    if (del) { e.preventDefault(); return extraRoot("remove", del.dataset.path); }
    if (e.target.id === "xr-add") {
      const p = window.pywebview?.api ? await pickPath("folder") : prompt(t("g.ev.roms.extra_prompt"));
      extraRoot("add", p);
    }
    if (e.target.id === "xr-paste") pasteFolder("windows");
  });
  $("#collart-missing").onclick = () => startCollart("missing");
  $("#collart-all").onclick = () => startCollart("all");
  $("#collart-stop").onclick = () => api("/api/collart/cancel", { body: {} });
  $("#smeta-all").onclick = () => startStoreMeta(false);
  $("#ph-on").onchange = (e) => phoneSet({ enabled: e.target.checked });
  $("#pads-test-btn").onclick = (e) => {
    const box = $("#pads-test");
    box.hidden = !box.hidden;
    e.currentTarget.setAttribute("aria-expanded", String(!box.hidden));
    if (box.hidden) stopPadTest(); else startPadTest();
  };
  $("#settings-body").addEventListener("change", async (e) => {
    const t = e.target;
    if (t.id === "ph-mouse") phoneSet({ mouse: t.checked });
    if (t.id === "ph-ca-ok") phoneSet({ ca_installed: t.checked });
    if (t.id === "ph-touch") phoneSet({ touchscreen: t.checked });
    else if (t.id === "ph-public") phoneSet({ public_url: t.value });
    else if (t.id === "ph-video") phoneSet({ video_addr: t.value });
    else if (t.id === "ph-touch-idle") { const v = Math.min(600, Math.max(5, Number(t.value) || 30)); phoneSet({ screen_idle: v }); }
    else if (t.id === "ph-mic") phoneSet({ mic_device: t.value });
    else if (t.dataset.swap && t.value !== "") {
      try { await api("/api/phone/swap", { body: { a: +t.dataset.swap, b: +t.value } }); } catch (err) { toast(err.message, true); }
      loadRemote();
    }
  });
  $("#settings-body").addEventListener("click", async (e) => {
    const t = e.target;
    const rb = t.closest("[data-pad-rumble]");
    if (rb) {
      try {
        await api("/api/phone/pads/rumble", { body: { slot: +rb.dataset.padRumble } });
        toast("📳 " + window.t("g.ev.phone.rumble"));
      } catch (err) { toast(err.message, true); }
      return;
    }
    if (t.dataset.es) {
      t.disabled = true;
      try {
        const r = await api("/api/phone/emusetup", { body: { what: t.dataset.es, players: +$("#es-n").value || 1 } });
        toast(window.t("g.ev.phone.done", { note: r.note }));
      } catch (err) { toast(err.message, true); }
      t.disabled = false;
      return;
    }
    if (t.dataset.esundo) {
      e.preventDefault();
      if (!confirm(window.t("g.ev.emu.undo_confirm"))) return;
      try { await api("/api/phone/emusetup", { body: { what: t.dataset.esundo, restore: true } }); toast(window.t("g.ev.emu.restored")); } catch (err) { toast(err.message, true); }
      return;
    }
    if (t.id === "ph-newcode") { e.preventDefault(); await api("/api/phone/code", { body: {} }); loadRemote(); }
    else if (t.id === "ph-invite") {
      e.preventDefault();
      t.disabled = true;
      try { await api("/api/phone/invite", { body: {} }); } catch (err) { toast(err.message, true); }
      loadRemote();
    }
    else if (t.dataset.revoke) {
      if (!confirm(window.t("g.ev.phone.revoke_confirm"))) return;
      await api(`/api/phone/devices/${t.dataset.revoke}`, { method: "DELETE" }); loadRemote();
    } else if (t.id === "sun-start") {
      try { await api("/api/sunshine/start", { body: {} }); toast(window.t("g.ev.sun.starting")); setTimeout(loadRemote, 4000); } catch (err) { toast(err.message, true); }
    } else if (t.id === "sun-pub") {
      t.disabled = true; t.textContent = window.t("g.ev.sun.publishing");
      try {
        await api("/api/sunshine", { body: { user: $("#sun-user").value, password: $("#sun-pass").value, count: $("#sun-count").value, publish: true } });
        toast(window.t("g.ev.sun.published"));
      } catch (err) { toast(err.message, true); }
      loadRemote();
    }
  });
  $("#prof-dlg").addEventListener("input", pfRefresh);
  $("#prof-dlg").addEventListener("change", pfRefresh);
  $("#pf-cancel").onclick = () => $("#prof-dlg").close();
  $("#pf-save").onclick = () => saveProfile(false);
  $("#pf-reset").onclick = () => saveProfile(true);
  $("#pf-exe-pick").onclick = async () => { const p = await pickPath("file"); if (p) { $("#pf-exe").value = p; pfRefresh(); } };
  $("#pf-comp-pick").onclick = async () => { const p = await pickPath("file"); if (p) $("#pf-comp-exe").value = p; };
  $("#running").addEventListener("click", async (e) => {
    if (e.target.closest("#run-shot")) api("/api/running/screenshot", { body: {} });
    if (e.target.closest("#run-pause")) { await api(S.running?.paused ? "/api/running/resume" : "/api/running/pause", { body: {} }); return pollRunning(); }
    if (!e.target.closest("#run-stop")) return;
    if (!confirm(t("g.ev.running.close_confirm", { title: S.running?.title || t("g.ev.running.default_title") }))) return;
    try {
      const r = await api("/api/running/stop", { body: {} });
      toast(r.found ? t("g.ev.running.closed") : t("g.ev.running.not_found"), !r.found);
    } catch (err) { toast(err.message, true); }
    pollRunning();
  });
  api("/api/shots").then((d) => {
    $("#cnt-shots").textContent = d.shots.length || "";
    SHOTS.pauseHotkey = (d.settings.pause_hotkey || "—").split("+").map((k) => k[0].toUpperCase() + k.slice(1)).join("+");
    SHOTS.hotkey = d.settings.hotkey ? d.settings.hotkey.split("+").map((k) => k[0].toUpperCase() + k.slice(1)).join("+") : "—";
  }).catch(() => {});
  $("#smart-new").onclick = () => openSmart();
  $("#smart-dlg").addEventListener("click", (e) => {
    const c = e.target.closest(".sm-chip");
    if (!c) return;
    const list = new Set(smEdit.rules[c.dataset.k] || []);
    list.has(c.dataset.v) ? list.delete(c.dataset.v) : list.add(c.dataset.v);
    smEdit.rules[c.dataset.k] = [...list];
    if (!smEdit.rules[c.dataset.k].length) delete smEdit.rules[c.dataset.k];
    c.classList.toggle("on");
    smCount();
  });
  $("#smart-dlg").addEventListener("input", smCount);
  $("#sm-cancel").onclick = () => $("#smart-dlg").close();
  $("#sm-save").onclick = () => saveSmart(false);
  $("#sm-delete").onclick = () => { if (confirm(t("g.ev.smart.delete_confirm"))) saveSmart(true); };
  $("#hltb-missing").onclick = () => startHltb("missing");
  $("#hltb-all").onclick = () => startHltb("all");
  $("#hltb-stop").onclick = () => api("/api/hltb/cancel", { body: {} });
  pollWishBadge();
  // notifiche notizie e avvisi per giochi in wishlist
  function onWishlistAlert(data) {
    if (!data) return;
    const items = data.alerts || data.news || (data.title ? [data.title] : []);
    (Array.isArray(items) ? items : [items]).forEach((item) => {
      const title = typeof item === "string" ? item : (item && (item.title || item.name));
      if (title) toast(t("g.ev.wishlist.news", { title }));
    });
  }
  window.addEventListener("wishlist_alerts", (e) => onWishlistAlert(e.detail));
  window.addEventListener("wishlist_news", (e) => onWishlistAlert(e.detail));
  if (typeof window !== "undefined" && window.EventSource) {
    try {
      const es = window.gsEventSource || new EventSource("/api/v1/events");
      window.gsEventSource = es;
      es.addEventListener("wishlist_alerts", (e) => {
        try { onWishlistAlert(JSON.parse(e.data)); } catch {}
      });
      es.addEventListener("wishlist_news", (e) => {
        try { onWishlistAlert(JSON.parse(e.data)); } catch {}
      });
    } catch {}
  }
  setTimeout(() => api("/api/free").then((d) => { if (d.first) d.new = 0; freeBadge(d); }).catch(() => {}), 4000);
  $("#smeta-missing").onclick = () => startStoreMeta(true);
  $("#smeta-close").onclick = () => $("#smeta").close();
  $("#smeta-stop").onclick = () => api("/api/stores/metadata/cancel", { body: {} });

  // account degli store
  $("#acc-refresh").onclick = async () => {
    try { await api("/api/stores/refresh", { body: {} }); } catch (e) { return toast(e.message, true); }
    pollStores(true);
  };
  $("#acc-table").addEventListener("click", (e) => {
    const t = e.target.closest("[data-acc-login],[data-acc-logout],[data-acc-code],[data-acc-save],[data-acc-refresh]");
    if (!t) return;
    e.preventDefault();
    if (t.dataset.accRefresh) {
      api("/api/stores/refresh", { body: { only: [t.dataset.accRefresh] } }).then(() => pollStores(true)).catch((err) => toast(err.message, true));
    } else accountAction(t);
  });
  $("#acc-table").addEventListener("change", async (e) => {
    const c = e.target.closest("[data-acc-enable]");
    if (!c) return;
    const previous = !c.checked, id = c.dataset.accEnable;
    try {
      await api(`/api/accounts/${id}/enabled`, { body: { enabled: c.checked } });
      savedToast(async () => { await api(`/api/accounts/${id}/enabled`, { body: { enabled: previous } }); loadAccounts(); });
    } catch (err) { c.checked = previous; toast(err.message, true); }
  });
  // aspetto: temi e plugin
  $("#theme-list").addEventListener("change", async (e) => {
    if (e.target.name !== "theme") return;
    uiHoverOff();
    const next = e.target.value;
    const previous = SET.theme;
    try {
      await api("/api/app/theme", { body: { theme: next } });
      await loadExtensions();
      loadAppearance();
      savedToast(previous ? async () => {
        await api("/api/app/theme", { body: { theme: previous } });
        await loadExtensions();
        loadAppearance();
      } : null);
    } catch (err) { await loadAppearance(); toast(err.message, true); }
  });
  $("#experience-list").addEventListener("change", async (e) => {
    if (e.target.name !== "experience") return;
    document.querySelectorAll('#experience-list input[name="experience"]').forEach((input) => { input.disabled = true; });
    try {
      await api("/api/app/experience", { body: { experience: e.target.value } });
      store.set("view", GS.experiences.get(e.target.value)?.home ? { type: "home" } : { type: "all" });
      location.reload(); // riavvio pulito: struttura e vista partono dalla stessa esperienza
    } catch (err) {
      toast(err.message, true);
      loadAppearance();
    }
  });
  $("#plugin-list").addEventListener("click", (e) => {
    const star = e.target.closest("[data-toggle-fav-ext]");
    if (!star) return;
    e.preventDefault();
    toggleFavExt(star.dataset.toggleFavExt);
    loadAppearance();
  });
  $("#plugin-list").addEventListener("change", async (e) => {
    const c = e.target.closest("[data-plugin]");
    if (!c) return;
    const previous = !c.checked, id = c.dataset.plugin;
    try {
      await api("/api/app/plugin", { body: { id, enabled: c.checked } });
      savedToast(async () => { await api("/api/app/plugin", { body: { id, enabled: previous } }); loadAppearance(); },
        t("g.ev.plugin.saved_restart"));
    } catch (err) { c.checked = previous; toast(err.message, true); }
  });
  // aggiungi gioco PC
  $("#ag-pick").onclick = async () => {
    const p = await pickPath("file");
    if (p) {
      $("#ag-exe").value = p;
      agTitleFromExe();
    }
  };
  $("#ag-kind").onchange = agKindChanged;
  $("#ag-exe").onchange = agTitleFromExe;  // anche se il percorso viene incollato a mano
  $("#ag-title").oninput = () => { $("#ag-title").dataset.auto = ""; };
  $("#ag-save").onclick = saveAddGame;

  // emulatori
  $("#emu-save").onclick = () => saveEmu();
  $("#ln-save").onclick = () => api("/api/app/launch", { body: { before: $("#ln-before").value, after: $("#ln-after").value,
    close_launcher: $("#ln-close").checked, splash: $("#ln-splash").checked } }).then(() => toast(t("g.ev.launch.saved")), (e) => toast(e.message, true));
  $("#emu-folder-pick").onclick = async () => { const p = await pickPath("folder"); if (p) $("#emu-folder").value = p; };
  $("#emu-detect").onclick = async () => {
    const folder = $("#emu-folder").value.trim();
    if (!folder) return toast(t("g.ev.emu.folder_first"), true);
    try {
      const d = await api("/api/emulators/detect", { body: { folder } });
      SET.emu = d;
      renderEmu(d);
      const n = Object.keys(d.found).length;
      toast(n ? t("g.ev.emu.found", { list: Object.keys(d.found).join(", ") }) : t("g.ev.emu.none_found"), !n);
    } catch (err) { toast(err.message, true); }
  };
  $("#emu-inst").addEventListener("click", async (e) => {
    const o = e.target.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    const b = e.target.closest("[data-emu-inst], [data-emu-cores]");
    if (!b) return;
    try {
      if (b.dataset.emuInst) await api("/api/emulators/install", { body: { emu: b.dataset.emuInst, folder: $("#emu-folder").value.trim() } });
      else await api("/api/emulators/cores", { body: {} });
    } catch (err) { return toast(err.message, true); }
    followEmuJob();
  });
  $("#emu-add").onclick = async (e) => {
    const name = await askText(e.currentTarget, t("g.ev.emu.name_prompt"));
    if (!name) return;
    const draft = collectEmu();
    SET.extraEmus.push(name.toLowerCase());
    renderEmu(SET.emu, draft);
  };
  $("#emu-paths").addEventListener("click", async (e) => {
    const b = e.target.closest(".emu-pick");
    if (!b) return;
    const p = await pickPath("file");
    if (p) document.querySelector(`.emu-path[data-emu="${CSS.escape(b.dataset.emu)}"]`).value = p;
  });
  $("#emu-table").addEventListener("change", async (e) => {
    const s = e.target.closest(".emu-sel");
    if (!s || s.value !== "__new") return;
    const name = await askText(s, t("g.ev.emu.name_prompt"));
    const draft = collectEmu();
    if (name) {
      SET.extraEmus.push(name.toLowerCase());
      draft.platforms[s.closest("tr").dataset.p].emulator = name.toLowerCase();
    }
    renderEmu(SET.emu, draft);
  });
  document.addEventListener("mousedown", (e) => {
    if (!$("#popover").hidden && !e.target.closest("#popover") && !e.target.closest("#d-add-coll, #coll-new, #view-actions")) closePopover();
  });
  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (e.key === "Tab" && S.detail && $("#detail").dataset.presentation === "modal") {
      const focusable = [...$("#detail").querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) { e.preventDefault(); $("#detail-close").focus(); }
      else if (e.shiftKey && document.activeElement === focusable[0]) { e.preventDefault(); focusable[focusable.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === focusable[focusable.length - 1]) { e.preventDefault(); focusable[0].focus(); }
    }
    if (e.key === "/" && !typing) { e.preventDefault(); $("#search").focus(); }
    else if (e.key === "Escape") {
      if (!$("#popover").hidden) closePopover();
      else if (S.detail) closeDetail();
      else if (S.search) { $("#search").value = ""; S.search = ""; refreshGrid(); }
    } else if (e.key === "Enter" && S.detail && !typing) play(S.detail.id);
  });
}
