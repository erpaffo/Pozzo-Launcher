"use strict";

/* Epic, GOG, Amazon senza il client ufficiale: legendary / gogdl / nile, scaricati da Pozzo (vedi pozzo/noclient.py) */
async function noclientRun(id, action, nc, extra = {}) {
  try {
    if (!nc.tool_installed) {
      toast(t("f.nc.toolDownloading", { tool: nc.tool }));
      await api(`/api/noclient/${nc.store}/tool`, { body: {} });
      nc.tool_installed = true;
    }
    if (!nc.account) return toast(t("f.nc.login"), true);
    await api(`/api/game/${id}/noclient/${action}`, { body: { path: nc.path, ...extra } });
  } catch (e) { return toast(e.message, true); }
  toast(action === "uninstall" ? t("f.nc.done") : t("f.nc.queued"));
}

async function loadDetailNoclient(d) {
  const body = document.querySelector("#detail-body");
  if (!body || !d?.id) return;
  body.querySelector("#d-noclient")?.remove();
  if (!["epic", "gog", "amazon"].includes(d.store)) return;
  let nc;
  try { nc = await api(`/api/game/${d.id}/noclient`); } catch { return; }
  if (!nc.supported || (typeof S !== "undefined" && S.detail !== d)) return;
  const own = nc.by_pozzo;
  const b = (act, label, extra = "") => `<button class="btn" data-nc="${act}" ${extra}>${label}</button>`;
  const section = document.createElement("section");
  section.id = "d-noclient";
  section.innerHTML = `<div class="d-h">🔧 ${t("f.nc.heading")}</div>
    <p class="muted small">${t(nc.official ? "f.nc.official" : "f.nc.intro", { tool: esc(nc.tool), store: esc(d.store_name) })}</p>
    <div class="d-mod-sources">
      ${!d.installed ? b("install", "⬇ " + t("f.nc.install", { tool: esc(nc.tool) })) : ""}
      ${own ? b("update", "⬆ " + t("f.nc.update")) + b("verify", "✔ " + t("f.nc.verify")) + b("uninstall", "🗑 " + t("f.nc.uninstall")) : ""}
      ${own && nc.dlc ? b("dlc", "🧩 " + t("f.nc.dlcShow")) : ""}
      ${own && nc.cloud ? b("sync", "☁ " + t("f.nc.cloudSync")) + b("download", "⇣ " + t("f.nc.cloudDown")) + b("upload", "⇡ " + t("f.nc.cloudUp")) : ""}
    </div><div id="d-nc-dlc"></div>`;
  body.append(section);
  section.onclick = async (event) => {
    const el = event.target.closest("[data-nc], [data-nc-dlc]");
    if (!el) return;
    el.disabled = true;
    try {
      if (el.dataset.ncDlc) await noclientRun(d.id, "install", nc, { dlcs: [el.dataset.ncDlc] });
      else if (["sync", "download", "upload"].includes(el.dataset.nc)) {
        const r = await api(`/api/game/${d.id}/noclient/saves`, { body: { direction: el.dataset.nc } });
        toast(r.message || t("f.nc.done"));
      } else if (el.dataset.nc === "dlc") {
        const r = await api(`/api/game/${d.id}/noclient/dlc`);
        section.querySelector("#d-nc-dlc").innerHTML = r.dlc.length
          ? r.dlc.map((x) => `<div class="d-mod-row"><div><strong>${esc(x.title)}</strong></div><button class="btn" data-nc-dlc="${esc(x.id)}">${t("f.btn.install")}</button></div>`).join("")
          : `<p class="muted small">${t("f.nc.dlcNone")}</p>`;
      } else if (el.dataset.nc === "uninstall") {
        if (confirm(t("f.nc.uninstallConfirm", { title: d.title }))) { await noclientRun(d.id, "uninstall", nc); }
      } else await noclientRun(d.id, el.dataset.nc, nc);
    } catch (e) { toast(e.message, true); }
    finally { el.disabled = false; }
  };
}
