"use strict";
/* Pozzo Launcher - frontend: telefono e streaming. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ---- telefono e streaming */
let phoneTimer = 0;
const EMU_DSU = [
  ["Cemu (Wii U)", "i.remote.dsu.cemu"],
  ["Ryujinx (Switch)", "i.remote.dsu.ryujinx"],
  ["Dolphin (Wii)", "i.remote.dsu.dolphin"],
  ["Azahar / Citra (3DS)", "i.remote.dsu.azahar"],
];
async function loadRemote() {
  clearTimeout(phoneTimer);
  let ph, sun;
  try { [ph, sun] = await Promise.all([api("/api/phone"), api("/api/sunshine")]); } catch (e) { return toast(e.message, true); }
  $("#ph-on").checked = ph.enabled;
  const mins = ph.code_until ? Math.max(0, Math.round((ph.code_until - Date.now() / 1000) / 60)) : 0;
  $("#ph-box").innerHTML = !ph.enabled ? "" : ph.error ? `<p class="status-bad">${esc(ph.error)}</p>` : !ph.running ? `<p class="muted">${t("i.remote.starting")}</p>` : `
    <h4>🔒 ${t("i.remote.cert.title")}</h4>
    <p class="muted small">${t("i.remote.cert.intro")}</p>
    <div class="ph-pair"${ph.ca_installed ? " hidden" : ""}>
      <div class="ph-qr">${ph.qr_ca || ""}</div>
      <div class="ph-steps">
        <b>${t("i.remote.cert.install")}</b>
        <ol>
          <li>${t("i.remote.cert.s1", { url: esc(ph.ca_url || "") })}</li>
          <li>${t("i.remote.cert.android")}</li>
          <li>${t("i.remote.cert.ios")}</li>
          <li>${t("i.remote.cert.s4")}</li>
        </ol>
        <p class="muted small">${t("i.remote.cert.noteA")}<br>
          ${t("i.remote.cert.noteB1")}
          <a href="/api/phone/ca" download="PozzoLauncher-CA.crt">${t("i.remote.cert.link")}</a> ${t("i.remote.cert.noteB2")}</p>
      </div>
    </div>
    <label class="small"><input type="checkbox" id="ph-ca-ok"${ph.ca_installed ? " checked" : ""}>
      ${t("i.remote.cert.haveIt")}</label>
    <div class="ph-pair">
      <div class="ph-qr">${ph.qr}</div>
      <div class="ph-steps">
        <b>${t("i.remote.pair.title")}</b>
        <ol>
          <li>${t("i.remote.pair.s1")}</li>
          <li>${t("i.remote.pair.s2", { url: esc(ph.urls[0] || "") })}
            <span class="ph-code">${esc(ph.code || "")}</span> <span class="muted small">(${t("i.remote.pair.valid", { m: mins })}, <a href="#" id="ph-newcode">${t("i.remote.pair.newCode")}</a>)</span></li>
          <li>${t("i.remote.pair.s3")}</li>
        </ol>
        <p class="muted small">${t("i.remote.pair.firewall")}</p>
      </div>
    </div>
    <h4>${t("i.remote.devices.title")}</h4>
    ${ph.devices.length ? `<table class="emu">${ph.devices.map((d) => `<tr><td>📱 ${esc(d.name)}</td>
      <td class="muted small">${t("i.remote.devices.paired", { d: new Date(d.created * 1000).toLocaleDateString(GSI18n.lang), l: new Date(d.last * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" }) })}</td>
      <td><button class="btn" data-revoke="${esc(d.id)}">${t("i.remote.revoke")}</button></td></tr>`).join("")}</table>` : `<p class="muted small">${t("i.remote.none")}</p>`}
    <h4>${t("i.remote.controllers.title")}</h4>
    <p class="small">${ph.vigem ? `✅ ${t("i.remote.vigem.ok")}` : `❌ ${esc(ph.vigem_error)} — <a href="#" data-open="https://github.com/nefarius/ViGEmBus/releases">${t("i.remote.vigem.download")}</a>`}<br>
      ${ph.dsu ? `✅ ${t("i.remote.dsu.ok")}` : `❌ ${esc(ph.dsu_error || t("i.remote.dsu.inactive"))}`}</p>
    ${ph.controllers.length ? `<div class="lobby small">${[0, 1, 2, 3].map((slot) => {
      const c = ph.controllers.find((x) => x.slot === slot);
      return `<div class="lb-seat" style="--pc:${c ? c.color : "#555"}"><b>${t("i.remote.lobby.player", { n: c ? c.player : slot + 1 })}</b>
        <span>${c ? `📱 ${esc(c.name)}${c.motion ? " · 🌀" : ""}` : `<i class="muted">${t("i.remote.lobby.free")}</i>`}</span>
        ${c ? `<select data-swap="${slot}"><option value="">${t("i.remote.lobby.move")}</option>${[0, 1, 2, 3].filter((s) => s !== slot)
          .map((s) => `<option value="${s}">${s + 1}</option>`).join("")}</select>` : ""}</div>`;
    }).join("")}</div>` : ""}
    <h4>${t("i.remote.spec.title")}</h4>
    <div class="row wrap small">
      <label class="chk"><input type="checkbox" id="ph-mouse" ${ph.mouse ? "checked" : ""}> ${t("i.remote.spec.mouse")}
        <span class="muted">${t("i.remote.spec.mouseHint")}</span></label>
      <label class="chk"><input type="checkbox" id="ph-touch" ${ph.touchscreen ? "checked" : ""}> ${t("i.remote.spec.touch")}
        <span class="muted">${t("i.remote.spec.touchHint")}</span></label>
      <label class="chk">${t("i.remote.spec.idle1")} <input class="field" id="ph-touch-idle" type="number" min="5" max="600" step="5" value="${ph.screen_idle || 30}" style="width:70px"> ${t("i.remote.spec.idle2")}
        <span class="muted">${t("i.remote.spec.idleHint")}</span></label>
    </div>
    <div class="row wrap small">
      <label>${t("i.remote.mic.label")}
        <select class="field" id="ph-mic"><option value="">${t("i.remote.mic.auto")}</option>
          ${ph.mic_devices.map((d) => `<option ${d === ph.mic_device ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></label>
      ${ph.mic_devices.some((d) => /CABLE|VB-Audio/i.test(d)) ? "" : `<span class="muted">${t("i.remote.mic.noCable")} <a href="#" data-open="https://vb-audio.com/Cable/">${t("i.remote.mic.install")}</a> ${t("i.remote.mic.then")}</span>`}
    </div>
    <div class="row wrap small emusetup">
      <label>${t("i.remote.emu.phones")} <input class="field" id="es-n" type="number" min="1" max="4" value="${Math.max(1, ph.controllers.length)}" style="width:60px"></label>
      <button class="btn" data-es="pcsx2_buzz">🔴 ${t("i.remote.emu.buzz")}</button>
      <button class="btn" data-es="pcsx2_guitar">🎸 ${t("i.remote.emu.guitar")}</button>
      <button class="btn" data-es="dolphin_wii">🎮 ${t("i.remote.emu.dolphin")}</button>
    </div>
    <p class="muted small">${t("i.remote.emu.note")}
      <a href="#" data-esundo="pcsx2_buzz">${t("i.remote.emu.undoPcsx2")}</a> · <a href="#" data-esundo="dolphin_wii">${t("i.remote.emu.undoDolphin")}</a></p>
    <details class="small"><summary>${t("i.remote.dsu.summary")}</summary>
      <ul>${EMU_DSU.map(([n, k]) => `<li><b>${n}</b>: ${t(k)}</li>`).join("")}</ul>
      <p class="muted">${t("i.remote.dsu.aim")}</p>
    </details>`;
  const s = sun;
  if (document.activeElement.id !== "ph-public") $("#ph-public").value = ph.public_url || "";
  if (document.activeElement.id !== "ph-video") $("#ph-video").value = ph.video_addr || "";
  const inv = ph.invite || {};
  const gmin = inv.until ? Math.max(0, Math.round((inv.until - Date.now() / 1000) / 60)) : 0;
  $("#guest-box").innerHTML = `<p class="small">${inv.code
    ? `${t("i.remote.guest.share", { link: esc(inv.link) })} <span class="ph-code">${esc(inv.code)}</span>
       <span class="muted small">(${t("i.remote.guest.valid", { m: gmin })})</span>`
    : `<span class="muted">${t("i.remote.guest.none")}</span>`}
    <button class="btn primary" id="ph-invite">${inv.code ? t("i.remote.guest.new") : t("i.remote.guest.create")}</button></p>
    <p class="muted small">${t("i.remote.guest.video")}</p>
    ${(ph.guests || []).length ? `<h4>${t("i.remote.guest.title")}</h4><table class="emu">${ph.guests.map((d) => `<tr><td>🙋 ${esc(d.name)}</td>
      <td class="muted small">${t("i.remote.guest.entered", { d: new Date(d.created * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" }) })}</td>
      <td><button class="btn" data-revoke="${esc(d.id)}">${t("i.remote.guest.remove")}</button></td></tr>`).join("")}</table>` : ""}`;
  $("#sun-box").innerHTML = !s.installed ? `<p>${t("i.remote.sun.notInstalled")} <a href="#" data-open="https://github.com/LizardByte/Sunshine/releases">${t("i.remote.sun.download")}</a>, ${t("i.remote.sun.reopen")}</p>`
    : `<p class="small">${s.service === "running"
      ? `✅ ${t("i.remote.sun.running")}${s.start_mode && s.start_mode !== "auto" ? ` · ⚠ ${t("i.remote.sun.notAuto")} <button class="btn" id="sun-start">${t("i.remote.sun.startAlways")}</button>` : ""}`
      : s.service === "stopped"
      ? `⏸ ${t("i.remote.sun.stopped")} <button class="btn primary" id="sun-start">▶ ${t("i.remote.sun.start")}</button> <span class="muted">${t("i.remote.sun.adminAsk")}</span>` : t("i.remote.sun.installed")}
      · <a href="#" data-open="${esc(s.web)}">${t("i.remote.sun.web")}</a> ${t("i.remote.sun.webHint")}</p>
    <div class="row wrap">
      <label>${t("i.remote.sun.user")} <input class="field" id="sun-user" value="${esc(s.user)}" autocomplete="off"></label>
      <label>${t("i.remote.sun.password")} <input class="field" id="sun-pass" type="password" placeholder="${s.has_password ? t("i.remote.sun.saved") : ""}" autocomplete="new-password"></label>
      <label>${t("i.remote.sun.count")} <input class="field" id="sun-count" type="number" min="0" max="100" value="${s.count}" style="width:80px"></label>
      <button class="btn primary" id="sun-pub">📡 ${t("i.remote.sun.publish")}</button>
    </div>
    ${s.error ? `<p class="status-bad small">${esc(s.error)}</p>` : ""}
    <p class="muted small">${t("i.remote.sun.publishes1")}
      ${t("i.remote.sun.publishes2")}
      ${s.preview.length ? t("i.remote.sun.previewGames", { n: s.preview.length, list: `${esc(s.preview.slice(0, 8).join(", "))}${s.preview.length > 8 ? "…" : ""}` }) : ""}.
      ${t("i.remote.sun.others")}</p>
    ${s.last ? `<p class="small">${t("i.remote.sun.last", { d: new Date(s.last.time * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" }), n: s.last.published })}</p>` : ""}
    ${s.apps ? `<p class="small muted">${t("i.remote.sun.now", { list: esc(s.apps.map((a) => a.name).join(" · ")) })}</p>` : ""}`;
  api("/api/stream/optimize").then((o) => {
    const ico = { ok: "✓", warn: "⚠", info: "ℹ" };
    $("#stream-opt").innerHTML = `<div class="health">` + o.checks.map((x) => `<div class="hl-row hl-${x.level === "info" ? "ok" : x.level}">`
      + `<span class="hl-ico">${ico[x.level] || "•"}</span><div class="hl-txt"><b>${esc(x.title)}</b>${x.detail ? `<div class="muted small">${esc(x.detail)}</div>` : ""}</div></div>`).join("") + `</div>`;
  }).catch(() => {});
  if (ph.enabled && (SET.tab === "controller" || SET.tab === "streaming") && settingsOpen()) phoneTimer = setTimeout(loadRemote, ph.running ? 5000 : 1000);
}
async function phoneSet(body) {
  try { await api("/api/phone", { body }); } catch (e) { toast(e.message, true); }
  loadRemote();
}
