/* Pannello «Il tuo gusto»: generi e decenni preferiti del profilo attivo (GET /api/taste).
   Se la rotta manca (404), fallisce o non c'e' ancora abbastanza storia, la sezione resta nascosta senza rumore. */
(function (root) {
  "use strict";
  const MAX = 8;

  function el(doc, tag, cls, text) {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function colonna(doc, titolo, voci, suffisso) {
    const sec = el(doc, "section", "taste-col");
    const id = "taste-" + titolo.toLowerCase();
    const h = el(doc, "h3", "taste-h", titolo);
    h.setAttribute("id", id);
    sec.appendChild(h);
    const ul = el(doc, "ul", "taste-list");
    ul.setAttribute("role", "list");
    ul.setAttribute("aria-labelledby", id);
    const top = Math.max(...voci.map((v) => v[1]), 0) || 1;
    for (const [nome, peso] of voci.slice(0, MAX)) {
      const li = el(doc, "li", "taste-row");
      const pct = Math.max(0, Math.min(1, peso / top));
      const testo = nome + (suffisso || "");
      li.setAttribute("aria-label", `${testo}: ${Math.round(pct * 100)}%`);
      li.appendChild(el(doc, "span", "taste-name", testo));
      const bar = el(doc, "span", "taste-bar");
      bar.setAttribute("aria-hidden", "true");
      const fill = el(doc, "span", "taste-fill");
      fill.style.transform = `scaleX(${pct.toFixed(3)})`;
      bar.appendChild(fill);
      li.appendChild(bar);
      ul.appendChild(li);
    }
    sec.appendChild(ul);
    return sec;
  }

  /** Riempie `host` e lo mostra; ritorna true se c'e' qualcosa da vedere. */
  async function mount(host, { fetch: f = root.fetch && root.fetch.bind(root), doc = root.document } = {}) {
    host.hidden = true;
    let d;
    try {
      const r = await f("/api/taste");
      if (!r.ok) return false;
      d = await r.json();
    } catch { return false; }
    const generi = (d && d.genres) || [], decenni = (d && d.decades) || [];
    if (!generi.length && !decenni.length) return false;
    host.textContent = "";
    host.classList && host.classList.add("taste");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", "Il tuo gusto");
    host.appendChild(el(doc, "h2", "taste-title", "Il tuo gusto"));
    if (generi.length) host.appendChild(colonna(doc, "Generi", generi));
    if (decenni.length) host.appendChild(colonna(doc, "Decenni", decenni, "s"));
    if (d.reliable === false) host.appendChild(el(doc, "p", "taste-note", "Ancora pochi giochi giocati: il gusto e' indicativo."));
    host.hidden = false;
    return true;
  }

  const api = { mount };
  root.PozzoTaste = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);