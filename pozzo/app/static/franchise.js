/* Blocco «Ordine di gioco» del dettaglio: la serie del gioco in ordine, con i capitoli posseduti e quelli mancanti
   (GET /api/franchise/{id}). 404, errori o gioco senza serie: sezione nascosta. */
(function (root) {
  "use strict";

  function el(doc, tag, cls, text) {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /** onOpen(id): chiamata quando si sceglie un capitolo posseduto (apre il suo dettaglio). */
  async function mount(host, gid, { fetch: f = root.fetch && root.fetch.bind(root), doc = root.document, onOpen } = {}) {
    host.hidden = true;
    let d;
    try {
      const r = await f(`/api/franchise/${encodeURIComponent(gid)}`);
      if (!r.ok) return false;
      d = await r.json();
    } catch { return false; }
    const order = (d && d.order) || [], missing = (d && d.missing) || [];
    if (!d || !d.series || order.length + missing.length < 2) return false;
    const owned = new Set(d.owned || []), titles = d.titles || {};
    host.textContent = "";
    host.classList && host.classList.add("fr");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", "Ordine di gioco");
    host.appendChild(el(doc, "h3", "fr-title", `Ordine di gioco: ${d.series}`));
    const ol = el(doc, "ol", "fr-list");
    for (const id of order) {
      const li = el(doc, "li", "fr-item");
      const nome = titles[id] || `#${id}`;
      const corrente = String(id) === String(gid);
      if (corrente) {
        li.className += " fr-current";
        li.setAttribute("aria-current", "true");
      }
      if (onOpen && owned.has(id) && !corrente) {
        const b = el(doc, "button", "fr-open", nome);
        b.setAttribute("type", "button");
        b.addEventListener("click", () => onOpen(id));
        li.appendChild(b);
      } else li.appendChild(el(doc, "span", "fr-name", nome));
      li.appendChild(el(doc, "span", "fr-tag " + (owned.has(id) ? "fr-own" : "fr-miss"), owned.has(id) ? "Posseduto" : "Non posseduto"));
      ol.appendChild(li);
    }
    host.appendChild(ol);
    if (missing.length) {
      const m = el(doc, "div", "fr-missing");
      m.appendChild(el(doc, "h4", "fr-sub", "Ti mancano"));
      const ul = el(doc, "ul", "fr-miss-list");
      for (const t of missing) ul.appendChild(el(doc, "li", "fr-miss-item", t));
      m.appendChild(ul);
      host.appendChild(m);
    }
    host.hidden = false;
    return true;
  }

  const api = { mount };
  root.PozzoFranchise = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);