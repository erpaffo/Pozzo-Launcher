"use strict";

/* titoli famosi: link ai siti di mod (tabella curata sul server), per qualsiasi gioco della libreria */
async function loadModSites(d) {
  const body = document.querySelector("#detail-body");
  if (!body || !d?.id) return;
  body.querySelector("#d-mod-sites")?.remove();
  let sites = [];
  try { sites = (await api(`/api/game/${d.id}/mod-sites`)).sites || []; } catch { return; }
  if (!sites.length || (typeof S !== "undefined" && S.detail !== d)) return;
  const section = document.createElement("section");
  section.id = "d-mod-sites";
  section.innerHTML = `<div class="d-h">🧩 ${t("f.mods.heading")}</div><div class="d-mod-sources">${sites.map((s) =>
    `<a class="btn" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.name)} ↗</a>`).join("")}</div>
    <p class="muted small">${t("f.mods.search_hint")}</p>`;
  body.append(section);
}

async function loadDetailMods(d) {
  const body = document.querySelector("#detail-body");
  if (!body || !d) return;
  body.querySelector("#d-mods")?.remove();
  loadModSites(d);

  const slugs = [];
  if (d.store === "ports") slugs.push((d.key || "").split(":").slice(1).join(":"));
  for (const port of d.ports || []) if (port?.slug) slugs.push(port.slug);
  const unique = [...new Set(slugs.filter(Boolean))];
  if (!unique.length) return;

  const section = document.createElement("section");
  section.id = "d-mods";
  section.innerHTML = `<div class="d-h">🧩 Mod</div><p class="muted small">${t("f.mods.loading")}</p>`;
  body.append(section);

  const render = (slug, result) => {
    const installed = result.installed || {};
    const items = result.items || [];
    const links = result.links || [];
    return `<div class="d-mod-port"><div class="d-h">${esc(slug)}</div>
      ${links.length ? `<div class="d-mod-sources">${links.map((source) => {
        const url = source.url || "";
        const provider = source.provider || t("f.mods.source");
        const isNexus = provider.toLowerCase() === "nexus";
        return url && /^https:\/\//i.test(url)
          ? `<a class="btn" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(provider)}${isNexus ? " · " + t("f.mods.api_required") : ""}</a>`
          : `<span class="muted small">${esc(provider)}${isNexus ? " · " + t("f.mods.api_no_scrape") : ""}</span>`;
      }).join("")}</div>` : ""}
      ${items.length ? items.map((item) => {
        const id = item.id || "";
        const entry = installed[id];
        const isEnabled = !entry || entry.enabled !== false;
        return `<div class="d-mod-row">
          <div><strong>${esc(item.name || id)}</strong><span class="muted small">${esc(item.version || "")}</span>
            ${item.description ? `<p class="muted small">${esc(item.description)}</p>` : ""}
            ${item.page && /^https:\/\//i.test(item.page) ? `<a class="muted small" href="${esc(item.page)}" target="_blank" rel="noopener noreferrer">${t("f.mods.open_source")} ↗</a>` : ""}
          </div>
          ${entry ? `<button class="btn" data-mod-enabled="${esc(id)}" data-enabled="${isEnabled ? "false" : "true"}">${isEnabled ? t("f.mods.disable") : t("f.mods.enable")}</button>
            <button class="btn" data-mod-remove="${esc(id)}">${t("f.btn.remove")}</button>`
            : item.url ? `<button class="btn" data-mod-install="${esc(id)}">${t("f.btn.install")}</button>` : ""}
        </div>`;
      }).join("") : `<p class="muted small">${t("f.mods.no_auto")}</p>`}
    </div>`;
  };

  const loadPort = async (slug) => {
    const encoded = encodeURIComponent(slug);
    try {
      const result = await api(`/api/mods/${encoded}`);
      return render(slug, result);
    } catch (error) {
      return `<div class="d-mod-port"><div class="d-h">${esc(slug)}</div><p class="muted small">${esc(error.message)}</p></div>`;
    }
  };
  const results = await Promise.all(unique.map(loadPort));
  if (typeof S !== "undefined" && S.detail !== d) return;
  section.innerHTML = `<div class="d-h">🧩 ${t("f.mods.heading_sources")}</div>${results.join("")}`;
  section.onclick = async (event) => {
    const button = event.target.closest("[data-mod-install], [data-mod-enabled], [data-mod-remove]");
    if (!button) return;
    const port = button.closest(".d-mod-port")?.querySelector(".d-h")?.textContent || "";
    const encoded = encodeURIComponent(port);
    button.disabled = true;
    try {
      if (button.dataset.modInstall) {
        await api(`/api/mods/${encoded}/install`, { body: { id: button.dataset.modInstall } });
        toast(t("f.mods.installed"));
      } else if (button.dataset.modEnabled) {
        await api(`/api/mods/${encoded}/${encodeURIComponent(button.dataset.modEnabled)}/enabled`,
          { body: { enabled: button.dataset.enabled === "true" } });
        toast(button.dataset.enabled === "true" ? t("f.mods.enabled") : t("f.mods.disabled"));
      } else if (button.dataset.modRemove) {
        if (!confirm(t("f.mods.remove_confirm"))) return;
        await api(`/api/mods/${encoded}/${encodeURIComponent(button.dataset.modRemove)}`, { method: "DELETE" });
        toast(t("f.mods.removed"));
      }
      if (typeof S === "undefined" || S.detail === d) await loadDetailMods(d);
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  };
}
