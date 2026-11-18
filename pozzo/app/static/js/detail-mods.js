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

/* giochi PC della libreria: mod Thunderstore (cerca, installa con anteprima, attiva/rimuovi) */
async function loadGameMods(d) {
  const body = document.querySelector("#detail-body");
  if (!body || !d?.id) return;
  body.querySelector("#d-gmods")?.remove();
  const base = `/api/game/${d.id}/mods`;
  let data;
  try { data = await api(base); } catch { return loadModSites(d); }
  if (typeof S !== "undefined" && S.detail !== d) return;
  if (!data.supported) return loadModSites(d);
  body.querySelector("#d-mod-sites")?.remove();
  const section = document.createElement("section");
  section.id = "d-gmods";
  section.innerHTML = `<div class="d-h">🧩 ${t("f.mods.heading")}</div>
    ${data.game_installed ? "" : `<p class="muted small">${t("s.mods.gameNotInstalled")}</p>`}
    <div class="d-gm-installed"></div>
    <input type="search" class="d-gm-q" placeholder="${esc(t("f.mods.g.search"))}">
    <div class="d-gm-list"></div><div class="d-gm-job muted small"></div>`;
  body.append(section);
  const $q = (sel) => section.querySelector(sel);
  const alive = () => typeof S === "undefined" || S.detail === d;
  let busy = false;

  const draw = () => {
    const inst = data.installed || {};
    const rows = Object.entries(inst).map(([id, m]) => {
      const need = (m.required_by || []).join(", ");
      const dis = busy || !data.game_installed;
      return `<div class="d-mod-row"><div><strong>${esc(m.name || id)}</strong> <span class="muted small">${esc(m.version || "")}${m.auto ? " · " + esc(t("f.mods.g.auto")) : ""}</span>
        ${need ? `<p class="muted small">${esc(t("f.mods.g.neededBy", { mods: need }))}</p>` : ""}</div>
        <button class="btn" data-gm-en="${esc(id)}" data-enabled="${m.enabled === false ? "true" : "false"}"${dis ? " disabled" : ""}>${m.enabled === false ? t("f.mods.enable") : t("f.mods.disable")}</button>
        <button class="btn" data-gm-rm="${esc(id)}"${dis || need ? " disabled" : ""}>${t("f.btn.remove")}</button></div>`;
    }).join("");
    $q(".d-gm-installed").innerHTML = rows ? `<div class="d-h">${t("f.mods.g.installedHeading")}</div>${rows}` : "";
    const list = (data.items || []).filter((x) => !inst[x.id]).map((x) => {
      const ok = x.installable && data.game_installed && !busy;
      return `<div class="d-mod-row">${x.icon ? `<img class="d-gm-ic" src="${esc(x.icon)}" alt="" loading="lazy" data-onerr="remove">` : ""}
        <div><strong>${esc(x.name || x.id)}</strong> <span class="muted small">${esc(x.owner || "")} · ${esc(x.version || "")} · ${esc(t("f.mods.g.downloads", { n: x.downloads || 0 }))}</span>${x.nsfw ? ` <span class="badge">${t("f.mods.g.nsfw")}</span>` : ""}
          ${x.description ? `<p class="muted small">${esc(x.description)}</p>` : ""}</div>
        <button class="btn" data-gm-add="${esc(x.id)}"${ok ? "" : " disabled"}${x.installable ? "" : ` title="${esc(t("s.mods.unsupportedLoader"))}"`}>${t("f.btn.install")}</button></div>`;
    }).join("");
    $q(".d-gm-list").innerHTML = list || `<p class="muted small">${t("f.mods.g.empty")}</p>`;
  };
  const reload = async () => {
    try { data = await api(`${base}?q=${encodeURIComponent($q(".d-gm-q").value.trim())}`); } catch (e) { toast(e.message, true); }
    if (alive()) draw();
  };

  const install = async (id, name) => {
    busy = true; draw();
    const job = $q(".d-gm-job");
    try {
      job.textContent = t("f.mods.g.preparing");
      const pv = await api(`${base}/preview`, { body: { id } });
      const extra = (pv.install || []).filter((x) => x.id !== id).map((x) => x.name).join(", ");
      const files = pv.overwrite || [];
      const msg = [t("f.mods.g.confirm", { name }),
        extra && t("f.mods.g.confirmDeps", { mods: extra }),
        files.length && t("f.mods.g.confirmOverwrite", { n: files.length, files: files.slice(0, 5).join(", ") })].filter(Boolean).join("\n\n");
      if (!confirm(msg)) return;
      let j = await api(`${base}/install`, { body: { id } });
      while (j.status === "running" && alive()) {
        job.textContent = `${t("f.mods.g.installing")} ${j.total ? Math.round(100 * j.done / j.total) + "%" : ""} ${(j.log || []).slice(-1)[0] || ""}`;
        await new Promise((r) => setTimeout(r, 700));
        j = await api(`${base}/job`);
      }
      if (j.status === "error") toast(j.error, true); else toast(t("f.mods.installed"));
    } catch (e) { toast(e.message, true); }
    finally { busy = false; job.textContent = ""; await reload(); }
  };

  let timer;
  $q(".d-gm-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(reload, 350); });
  section.addEventListener("click", async (event) => {
    const b = event.target.closest("[data-gm-add], [data-gm-en], [data-gm-rm]");
    if (!b || b.disabled) return;
    if (b.dataset.gmAdd) return install(b.dataset.gmAdd, b.closest(".d-mod-row").querySelector("strong").textContent);
    const id = encodeURIComponent(b.dataset.gmEn || b.dataset.gmRm);
    try {
      if (b.dataset.gmEn) {
        data.installed = await api(`${base}/${id}/enabled`, { body: { enabled: b.dataset.enabled === "true" } });
        toast(b.dataset.enabled === "true" ? t("f.mods.enabled") : t("f.mods.disabled"));
      } else {
        if (!confirm(t("f.mods.remove_confirm"))) return;
        data.installed = await api(`${base}/${id}`, { method: "DELETE" });
        toast(t("f.mods.removed"));
      }
    } catch (e) { toast(e.message, true); }
    draw();
  });
  draw();
}

async function loadDetailMods(d) {
  const body = document.querySelector("#detail-body");
  if (!body || !d) return;
  body.querySelector("#d-mods")?.remove();
  loadGameMods(d);

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
