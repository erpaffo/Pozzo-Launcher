/* Impostazioni › Controller: «Condividi la libreria» (il PC fa da server per famiglia e amici). Gestione solo dal PC. */
"use strict";
let LS_NEW = null; // invito appena creato: codice e link si vedono solo una volta

async function loadLibShare() {
  const box = document.getElementById("ls-box");
  if (!box) return;
  let d;
  try { d = await api("/api/libshare"); } catch (e) { return toast(e.message, true); }
  const when = (ts) => new Date(ts * 1000).toLocaleString(GSI18n.lang, { dateStyle: "short", timeStyle: "short" });
  const plats = d.platform_list.map((p) => `<label class="chk"><input type="checkbox" data-ls-plat="${esc(p.id)}"${d.platforms.includes(p.id) ? " checked" : ""}>
    ${esc(p.name)} <span class="muted small">(${p.n})</span></label>`).join(" ");
  const inv = d.invites.map((i) => `<tr><td>🙋 ${esc(i.name)}</td>
    <td class="muted small">${i.expired ? t("j.ls.state.expired") : i.used ? t("j.ls.state.used") : t("j.ls.state.waiting")} · ${t("j.ls.expires", { d: when(i.exp) })}${i.last ? " · " + t("j.ls.last", { d: when(i.last) }) : ""}</td>
    <td><button class="btn" data-ls-revoke="${esc(i.id)}">${t("j.ls.revoke")}</button></td></tr>`).join("");
  const n = LS_NEW;
  box.innerHTML = `
    <p class="small">${d.count ? t("j.ls.count", { n: d.count }) : `<span class="muted">${t("j.ls.nothing")}</span>`}</p>
    <h4>${t("j.ls.platforms")}</h4>
    <div class="row wrap small">${plats || `<span class="muted">${t("j.ls.nothing")}</span>`}</div>
    <h4>${t("j.ls.games")}</h4>
    <input class="field" id="ls-search" placeholder="${t("j.ls.search")}" autocomplete="off">
    <div id="ls-games" class="small"></div>
    <h4>${t("j.ls.invites")}</h4>
    <div class="row wrap">
      <input class="field" id="ls-name" maxlength="40" placeholder="${t("j.ls.name")}" autocomplete="off">
      <label class="small">${t("j.ls.days")} <input class="field" id="ls-days" type="number" min="1" max="365" value="30" style="width:80px"></label>
      <button class="btn primary" id="ls-create">${t("j.ls.create")}</button>
    </div>
    ${n ? `<div class="ph-pair"><div class="ph-qr">${n.qr || ""}</div><div class="ph-steps"><p>${t("j.ls.newcode")}</p>
      <p><span class="ph-code">${esc(n.code)}</span></p><p class="small"><code>${esc(n.link)}</code></p></div></div>` : ""}
    ${inv ? `<table class="emu">${inv}</table>` : `<p class="muted small">${t("j.ls.none")}</p>`}
    <p class="muted small">${t("j.ls.zipNote")}</p>
    <label class="chk"><input type="checkbox" id="ls-net"${d.upnp_on ? " checked" : ""}> ${t("j.ls.net")}</label>
    <p class="muted small">${t("j.ls.netHint")}${d.external ? " " + t("j.ls.netOk", { addr: esc(d.external) }) : ""}</p>
    ${d.running && d.urls[0] ? `<p class="muted small">${t("j.ls.urlHint", { url: esc(d.urls[0]) })}</p>` : ""}`;
  lsGames(d);
}

async function lsGames(d) {
  const el = document.getElementById("ls-games");
  if (!el) return;
  const q = document.getElementById("ls-search").value;
  let g;
  try { g = (await api("/api/libshare/games?q=" + encodeURIComponent(q))).games; } catch { return; }
  el.innerHTML = g.map((x) => `<label class="chk"><input type="checkbox" data-ls-game="${esc(x.key)}"${x.on ? " checked" : ""}>
    ${esc(x.title)} <span class="muted">${esc(x.platform)}</span></label>`).join("<br>");
}

document.addEventListener("input", (e) => {
  if (e.target.id === "ls-search") { clearTimeout(window._lsT); window._lsT = setTimeout(() => lsGames(), 250); }
});
document.addEventListener("change", async (e) => {
  const t_ = e.target;
  try {
    if (t_.dataset.lsPlat !== undefined || t_.dataset.lsGame !== undefined) {
      const d = await api("/api/libshare");
      const set = (arr, v, on) => (on ? [...new Set([...arr, v])] : arr.filter((x) => x !== v));
      const body = t_.dataset.lsPlat !== undefined ? { platforms: set(d.platforms, t_.dataset.lsPlat, t_.checked) }
        : { games: set(d.games, t_.dataset.lsGame, t_.checked) };
      await api("/api/libshare", { body });
      loadLibShare();
    } else if (t_.id === "ls-net") {
      const r = await api("/api/libshare/internet", { body: { on: t_.checked } });
      if (t_.checked && !r.upnp_on) toast(t("j.ls.netFail"), true);
      loadLibShare();
    }
  } catch (err) { toast(err.message, true); loadLibShare(); }
});
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  try {
    if (b.id === "ls-create") {
      b.disabled = true;
      const r = await api("/api/libshare/invite", { body: { name: document.getElementById("ls-name").value, days: +document.getElementById("ls-days").value || 30 } });
      LS_NEW = r.new;
      loadLibShare();
    } else if (b.dataset.lsRevoke) {
      if (!confirm(t("j.ls.revokeConfirm"))) return;
      if (LS_NEW && LS_NEW.id === b.dataset.lsRevoke) LS_NEW = null;
      await api("/api/libshare/invites/" + b.dataset.lsRevoke, { method: "DELETE" });
      loadLibShare();
    }
  } catch (err) { b.disabled = false; toast(err.message, true); }
});

/* Librerie remote (client): i pulsanti stanno nella riga «Pozzo remoto» di Impostazioni › Store (js/stores.js). */
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-pr-add],[data-pr-remove],[data-pr-dest]");
  if (b) prAction(b);
});
