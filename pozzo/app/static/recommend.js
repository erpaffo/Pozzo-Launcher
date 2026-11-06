/* Consigli («perche' proprio questo») e classifica delle ROM per console.
   /api/recommend -> {items:[{id,title,score,reasons:[{kind,text}]}]}; /api/top/roms?console= -> {items:[{id,title,score,source}]}.
   Rotte assenti (404) o in errore: la sezione resta nascosta. Le liste lunghe passano da `vlist` (js/grid.js). */
(function (root) {
  "use strict";
  const SOGLIA_VLIST = 60;

  function el(doc, tag, cls, text) {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function leggi(f, url) {
    try {
      const r = await f(url);
      return r.ok ? await r.json() : null;
    } catch { return null; }
  }

  /** onOpen(id): apre il dettaglio del gioco consigliato. */
  async function mount(host, { fetch: f = root.fetch && root.fetch.bind(root), doc = root.document, onOpen, limit = 12 } = {}) {
    host.hidden = true;
    const d = await leggi(f, `/api/recommend?limit=${limit}`);
    const items = (d && d.items) || [];
    if (!items.length) return false;
    host.textContent = "";
    host.classList && host.classList.add("reco");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", t("i.reco.title"));
    host.appendChild(el(doc, "h2", "reco-title", t("i.reco.title")));
    const ul = el(doc, "ul", "reco-list");
    ul.setAttribute("role", "list");
    for (const it of items) {
      const li = el(doc, "li", "reco-item");
      const b = el(doc, "button", "reco-open", it.title);
      b.setAttribute("type", "button");
      if (onOpen) b.addEventListener("click", () => onOpen(it.id));
      li.appendChild(b);
      const why = el(doc, "ul", "reco-why");
      for (const m of it.reasons || []) why.appendChild(el(doc, "li", "reco-reason", m.text));
      li.appendChild(why);
      ul.appendChild(li);
    }
    host.appendChild(ul);
    host.hidden = false;
    return true;
  }

  /** Classifica ROM: `console` e' l'id piattaforma ("all" = tutte). box = contenitore che scorre (per vlist). */
  async function mountRanking(host, { fetch: f = root.fetch && root.fetch.bind(root), doc = root.document, console: pid = "all",
    onOpen, box, vlist = root.vlist, limit = 100 } = {}) {
    host.hidden = true;
    const d = await leggi(f, `/api/top/roms?console=${encodeURIComponent(pid)}&limit=${limit}`);
    const items = (d && d.items) || [];
    if (!items.length) return false;
    host.textContent = "";
    host.classList && host.classList.add("reco");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", t("i.reco.rank"));
    host.appendChild(el(doc, "h2", "reco-title", t("i.reco.rank")));
    const lista = el(doc, "div", "rank-list");
    lista.setAttribute("role", "list");
    host.appendChild(lista);
    items.forEach((it, i) => { it.pos = i + 1; });
    const cella = (it) => `<div class="rank-row" role="listitem"><span class="rank-pos">${it.pos}</span>` +
      `<button type="button" class="rank-open" data-id="${esc(it.id)}">${esc(it.title)}</button>` +
      `<span class="rank-score">${esc(it.score)}</span></div>`;
    if (items.length > SOGLIA_VLIST && typeof vlist === "function" && box) vlist(box, lista, items, cella);
    else lista.innerHTML = items.map(cella).join("");
    // un solo ascoltatore: le righe di vlist si ricreano scorrendo
    lista.addEventListener("click", (e) => {
      const b = e.target && e.target.closest ? e.target.closest("[data-id]") : null;
      if (b && onOpen) onOpen(Number(b.getAttribute("data-id")));
    });
    host.hidden = false;
    return true;
  }

  const api = { mount, mountRanking };
  root.PozzoRecommend = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);