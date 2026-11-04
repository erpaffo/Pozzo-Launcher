// Sconti e bundle: lista desideri in saldo, bundle (IsThereAnyDeal) e giochi gratis ora.
import { countdown, fmtDate, fmtPercent, fmtPrice, gameNames, isHttpUrl, sortBundles, sortDeals, tierText } from "./logica.js";

const TABS = [
  { id: "deals", label: "Lista desideri", path: "/plugin-api/sconti/deals" },
  { id: "bundles", label: "Bundle", path: "/plugin-api/sconti/bundles" },
  { id: "free", label: "Gratis ora", path: "/plugin-api/sconti/free" },
];

export default function (gs) {
  gs.addSidebarItem({ id: "sconti", label: "Sconti", icon: "🏷️", view: "sconti" });

  const arr = (x) => (Array.isArray(x) ? x : []);
  // risposta {"deals": [...]} / {"bundles": [...]} / {"games": [...]}; accetta anche un array nudo
  const listOf = (x, key) => (Array.isArray(x) ? x : arr(x?.[key]));
  const card = (inner, cls = "") => `<article class="sc-card ${cls}">${inner}</article>`;
  const openBtn = (url) => (isHttpUrl(url) ? `<button type="button" class="sc-open" data-url="${gs.esc(url)}">Apri</button>` : "");
  const empty = (txt) => `<p class="muted">${gs.esc(txt)}</p>`;
  const drmLabel = (d) => (d === "none" ? "Senza DRM" : String(d).charAt(0).toUpperCase() + String(d).slice(1));

  const renderers = {
    deals(data) {
      const list = listOf(data, "deals");
      if (!list.length) return empty("Nessuno sconto sui giochi della tua lista desideri in questo momento.");
      return `<div class="sc-grid">${sortDeals(list).map((d) => {
        const pct = fmtPercent(d.cut_percent);
        const strike = d.price != null && d.regular != null && Number(d.regular) > Number(d.price);
        return card(`
          <div class="sc-top">${pct ? `<span class="sc-badge">${gs.esc(pct)}</span>` : ""}${d.historical_low ? `<span class="sc-chip">Minimo storico</span>` : ""}</div>
          <h4 class="sc-title">${gs.esc(d.title)}</h4>
          <div class="sc-price"><b>${gs.esc(fmtPrice(d.price))}</b>${strike ? ` <s class="muted">${gs.esc(fmtPrice(d.regular))}</s>` : ""}</div>
          ${d.store ? `<div class="sc-meta muted small">${gs.esc(d.store)}</div>` : ""}
          ${openBtn(d.url)}`);
      }).join("")}</div>`;
    },
    bundles(data) {
      const note = data?.need_key ? `<p class="sc-msg">Serve la chiave IsThereAnyDeal nelle impostazioni</p>` : "";
      const list = sortBundles(listOf(data, "bundles"));
      if (!list.length) return note + (data?.need_key ? "" : empty("Nessun bundle in questo momento."));
      return note + `<div class="sc-grid">${list.map((b) => {
        const left = countdown(b.expiry);
        const tiers = arr(b.tiers).map(tierText).filter(Boolean);
        const games = gameNames(b.games);
        return card(`
          ${b.mine ? `<span class="sc-chip sc-chip-mine">Per te</span>` : ""}
          <h4 class="sc-title">${gs.esc(b.title)}</h4>
          <div class="sc-meta muted small">${gs.esc(b.store || "")}${left ? `${b.store ? " · " : ""}${gs.esc(left)}` : ""}</div>
          ${tiers.length ? `<ul class="sc-tiers">${tiers.map((t) => `<li>${gs.esc(t)}</li>`).join("")}</ul>` : ""}
          ${games ? `<p class="small sc-games">${gs.esc(games)}</p>` : ""}
          ${openBtn(b.url)}`, `${b.mine ? "sc-mine " : ""}${left === "scaduto" ? "sc-expired" : ""}`);
      }).join("")}</div>`;
    },
    free(data) {
      const list = listOf(data, "games");
      if (!list.length) return empty("Nessun gioco gratis in questo momento.");
      return `<div class="sc-grid">${list.map((f) => {
        const until = fmtDate(f.end);
        const left = countdown(f.end);
        const when = until ? `fino al ${until}${left ? ` · ${left}` : ""}` : "";
        const meta = [f.kind, when].filter(Boolean).join(" · ");
        return card(`
          <div class="sc-top"><span class="sc-chip sc-chip-free">Gratis</span>${f.drm ? `<span class="sc-chip">${gs.esc(drmLabel(f.drm))}</span>` : ""}</div>
          <h4 class="sc-title">${gs.esc(f.title)}</h4>
          ${meta ? `<div class="sc-meta muted small">${gs.esc(meta)}</div>` : ""}
          ${f.worth ? `<div class="sc-meta muted small">Valore ${gs.esc(f.worth)}</div>` : ""}
          ${openBtn(f.url)}`);
      }).join("")}</div>`;
    },
  };

  gs.registerView("sconti", {
    title: "Sconti e bundle",
    render(el) {
      el.innerHTML = `<div class="sc-tabs" role="tablist">${TABS.map((t) =>
        `<button type="button" role="tab" class="sc-tab" data-tab="${t.id}" aria-selected="false">${gs.esc(t.label)}</button>`).join("")}</div>
        <div class="sc-panel" role="tabpanel" aria-live="polite"></div>`;
      const panel = el.querySelector(".sc-panel");
      let current = null, seq = 0;

      const bindOpen = () => panel.querySelectorAll("[data-url]").forEach((b) => b.addEventListener("click", () => {
        const url = b.dataset.url;
        if (isHttpUrl(url)) gs.api("/api/open", { body: { url } }).catch((err) => gs.toast(err.message, true));
      }));

      const show = async (id) => {
        current = id;
        const my = ++seq;
        el.querySelectorAll("[data-tab]").forEach((b) => {
          const on = b.dataset.tab === id;
          b.setAttribute("aria-selected", String(on));
          b.tabIndex = on ? 0 : -1;
        });
        panel.innerHTML = "";
        if (globalThis.GSSkeleton) GSSkeleton.show(panel, 6);
        else panel.innerHTML = `<p class="muted">Caricamento…</p>`;
        let data;
        try { data = await gs.api(TABS.find((t) => t.id === id).path); }
        catch (e) {
          if (my === seq) panel.innerHTML = `<p class="status-bad">Impossibile caricare gli sconti: ${gs.esc(e.message)}</p>`;
          return;
        }
        if (my !== seq) return;
        // errore del backend: si avvisa, ma gli elementi in cache restano visibili
        const note = data?.error ? `<p class="sc-msg">Dati non aggiornati: ${gs.esc(data.error)}</p>` : "";
        panel.innerHTML = note + renderers[id](data);
        bindOpen();
      };

      el.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => {
        if (b.dataset.tab !== current) show(b.dataset.tab);
      }));
      show("deals");
    },
  });
}
