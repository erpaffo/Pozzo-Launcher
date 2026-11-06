"use strict";
/* Pozzo Launcher - frontend: emulatori. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ---- emulatori */
async function loadEmu() {
  try { SET.emu = await api("/api/emulators"); } catch (e) { return toast(e.message, true); }
  renderEmu(SET.emu);
  renderEmuInstall();
  api("/api/app/launch").then((l) => {
    $("#ln-before").value = l.before || ""; $("#ln-after").value = l.after || ""; $("#ln-close").checked = !!l.close_launcher;
  }).catch(() => {});
}

function collectEmu() {
  const emulators = {};
  document.querySelectorAll(".emu-path").forEach((i) => { emulators[i.dataset.emu] = i.value.trim(); });
  const platforms = {};
  document.querySelectorAll("#emu-table tr[data-p]").forEach((tr) => {
    platforms[tr.dataset.p] = { emulator: $(".emu-sel", tr).value.replace("__new", ""), core: $(".emu-core", tr).value, args: $(".emu-args", tr).value };
  });
  return { emulators, platforms, retroarch_cores: $("#ra-cores") ? $("#ra-cores").value : undefined };
}

function renderEmu(d, draft) {
  // draft = modifiche non ancora salvate da conservare quando si ridisegna
  const paths = { ...d.emulators, ...(draft ? draft.emulators : {}) };
  $("#emu-saved-to").textContent = t("i.emu.savedTo", { p: d.settings });
  const used = new Set(SET.extraEmus);
  d.platforms.forEach((p) => { p.candidates.forEach((c) => used.add(c.split(" ")[0])); if (p.emulator) used.add(p.emulator); });
  Object.keys(paths).forEach((k) => used.add(k));
  const names = [...used].sort();
  $("#emu-paths").innerHTML = `<table class="emu"><tr><th style="width:130px">${t("i.emu.col.emulator")}</th><th>${t("i.emu.col.exePath")}</th><th style="width:96px"></th></tr>`
    + names.map((n) => `<tr><td>${esc(n)}</td><td><input class="field emu-path" data-emu="${esc(n)}" value="${esc(paths[n] || "")}" placeholder="${t("i.emu.notConfigured")}"></td>`
      + `<td><button class="btn emu-pick" data-emu="${esc(n)}">${t("i.emu.browse")}</button></td></tr>`).join("")
    + `<tr><td class="muted">${t("i.emu.core")}</td><td><input class="field" id="ra-cores" value="${esc(draft && draft.retroarch_cores !== undefined ? draft.retroarch_cores : d.retroarch_cores || "")}" `
    + `placeholder="${t("i.emu.cores.placeholder")}"></td><td></td></tr></table>`;
  const known = [...new Set([...d.known, ...names])].sort();
  $("#emu-table").innerHTML = `<table class="emu"><tr><th>${t("i.emu.col.console")}</th><th style="width:160px">${t("i.emu.col.emulator")}</th><th style="width:150px">${t("i.emu.col.core")}</th><th>${t("i.emu.col.args")}</th><th style="width:180px">${t("i.emu.col.status")}</th></tr>`
    + d.platforms.map((p) => {
      const dp = draft && draft.platforms[p.platform] ? draft.platforms[p.platform] : { emulator: p.emulator, core: p.core, args: p.args };
      const rec = new Set(p.candidates.map((c) => c.split(" ")[0]));
      const opts = [`<option value="">${t("i.emu.auto")}</option>`,
        ...known.map((k) => `<option value="${esc(k)}" ${k === dp.emulator ? "selected" : ""}>${esc(k)}${rec.has(k) ? " ★" : ""}</option>`),
        `<option value="__new">${t("i.emu.other")}</option>`].join("");
      const status = p.effective ? `<span class="status-ok">✓ ${esc(p.effective)}</span>` : `<span class="status-bad">${esc(p.problem || t("i.emu.notConfigured"))}</span>`;
      return `<tr data-p="${esc(p.platform)}"><td>${esc(p.name)}<div class="muted small">consigliati: ${esc(p.candidates.join(", ") || "—")}</div></td>`
        + `<td><select class="field emu-sel">${opts}</select></td>`
        + `<td><input class="field emu-core" value="${esc(dp.core)}" placeholder="${esc(p.default_core)}"></td>`
        + `<td><input class="field emu-args" value="${esc(dp.args)}" placeholder="${esc(p.default_args)}"></td><td>${status}</td></tr>`;
    }).join("") + `</table>`;
}

async function renderEmuInstall() {
  let d;
  try { d = await api("/api/emulators/catalog"); } catch (e) { return toast(e.message, true); }
  const cores = d.cores.length ? `<div class="row"><span class="muted small grow">${t("i.emu.coresMissing", { list: esc(d.cores.join(", ")) })}</span>`
    + `<button class="btn" data-emu-cores ${d.retroarch ? "" : "disabled title=\"" + t("i.emu.installRetroarchFirst") + "\""}>⬇ ${t("i.emu.downloadCores")}</button></div>` : "";
  $("#emu-inst").innerHTML = `<table class="emu"><tr><th style="width:130px">${t("i.emu.col.emulator")}</th><th>${t("i.emu.col.console")}</th><th style="width:120px">${t("i.common.installed")}</th><th style="width:120px"></th></tr>`
    + d.items.map((x) => `<tr><td><a href="#" data-open="${esc(x.home)}">${esc(x.id)} ↗</a><div class="muted small">${esc(x.repo)}</div></td>`
      + `<td class="small">${esc(x.consoles.join(", ") || "—")}</td><td class="small">${x.version ? esc(x.version) : x.configured ? `<span class="muted">${t("i.emu.alreadySet")}</span>` : "—"}</td>`
      + `<td><button class="btn" data-emu-inst="${esc(x.id)}">${x.version ? "↻ " + t("i.common.update") : "⬇ " + t("i.common.install")}</button></td></tr>`).join("")
    + `</table>${cores}<p class="muted small">${t("i.emu.defaultDir", { dir: esc(d.dir) })}</p>`;
}

async function followEmuJob() {
  let j;
  do {
    try { j = await api("/api/emulators/job"); } catch { return; }
    const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
    $("#emu-inst-job").innerHTML = `<p class="small">${j.status === "running" ? `⏳ ${j.total ? `${pct}% · ${t("i.common.ofSize", { a: fmtSize(j.done), b: fmtSize(j.total) })}` : j.done ? fmtSize(j.done) : ""}` : ""}</p>
      <pre class="log">${esc(j.log.slice(-6).join("\n"))}</pre>`;
    if (j.status === "running") await new Promise((r) => setTimeout(r, 1000));
  } while (j.status === "running");
  if (j.status === "error") toast(j.log[j.log.length - 1] || t("i.common.installFailed"), true);
  else toast(j.log[j.log.length - 1] || t("i.common.done"));
  loadEmu();
}

async function saveEmu(body) {
  try {
    SET.emu = await api("/api/emulators", { body: body || collectEmu() });
    SET.extraEmus = [];
    renderEmu(SET.emu);
    toast(t("i.emu.saved"));
    if (S.detail) openDetail(S.detail.id);
  } catch (e) { toast(e.message, true); }
}

function showStatus(st) {
  const n = S.games.length;
  $("#lib-info").textContent = t("i.emu.libInfo", { v: n.toLocaleString(GSI18n.lang), g: S.groups.length.toLocaleString(GSI18n.lang), c: S.colls.length });
  $("#build-log").textContent = (st.build_log || []).join("\n");
  $("#rebuild-btn").disabled = st.building;
  $("#rebuild-btn").textContent = st.building ? t("i.emu.rebuilding") : "↻ " + t("i.emu.refreshLibrary");
  $("#thumbs-info").textContent = st.thumbs_total ? t("i.emu.thumbs", { done: st.thumbs_done.toLocaleString(GSI18n.lang), total: st.thumbs_total.toLocaleString(GSI18n.lang) }) : "";
}

async function rebuild() {
  await api("/api/rebuild", { body: {} });
  const tick = async () => {
    const st = await api("/api/status");
    showStatus(st);
    if (st.building) setTimeout(tick, 1000);
    else { await reload(true); toast(t("i.emu.libUpdated")); }
  };
  tick();
}

async function waitFirstBuild() {
  $("#splash").hidden = false;
  for (;;) {
    const st = await api("/api/status");
    $("#splash-log").textContent = (st.build_log || []).join("\n");
    if (st.has_library && !st.building) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  $("#splash").hidden = true;
}

async function reload(keepScroll) {
  await loadLibrary();
  if (S.view.type === "collection" && !S.collBySlug.has(S.view.id)) S.view = { type: "all" };
  renderSidebar();
  refreshGrid(keepScroll);
}
