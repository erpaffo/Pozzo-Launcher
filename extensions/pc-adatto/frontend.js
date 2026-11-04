// Il mio PC ce la fa?: sezione nel dettaglio gioco con il verdetto del backend (route check/<id>).

const VERDETTI = {
  ok: ["good", "Gira bene"],
  impostazioni: ["warn", "Gira con queste impostazioni"],
  insufficiente: ["bad", "Probabilmente troppo pesante"],
  sconosciuto: ["muted", "Non so dirlo"],
};

// Valore annidato -> testo leggibile ("CPU: Ryzen 5 · GPU: ...")
const fmt = (v) => {
  if (v == null || v === "") return "n.d.";
  if (Array.isArray(v)) return v.map(fmt).join(", ");
  if (typeof v === "object") return Object.entries(v).map(([k, x]) => `${k}: ${fmt(x)}`).join(" · ");
  return String(v);
};

export default function (gs) {
  const cache = new Map();   // id gioco -> Promise del verdetto (le aperture successive non ri-chiedono nulla)

  const lista = (voci) => voci?.length
    ? `<ul class="pa-list">${voci.map((v) => `<li>${gs.esc(fmt(v))}</li>`).join("")}</ul>`
    : "";

  const righe = (obj) => obj && typeof obj === "object" && Object.keys(obj).length
    ? Object.entries(obj).map(([k, v]) => `<div class="pa-row"><span class="muted">${gs.esc(k)}</span><span>${gs.esc(fmt(v))}</span></div>`).join("")
    : `<p class="muted">Dati non disponibili.</p>`;

  function carica(id) {
    if (!cache.has(id)) {
      const p = gs.api(`/plugin-api/pc-adatto/check/${encodeURIComponent(id)}`);
      p.catch(() => cache.delete(id));   // gli errori non restano in cache: al prossimo tentativo si riprova
      cache.set(id, p);
    }
    return cache.get(id);
  }

  gs.addDetailSection({
    id: "pc-adatto",
    title: "Il mio PC ce la fa?",
    async render(game) {
      let r;
      try { r = await carica(game.id); }
      catch (e) { return `<p class="muted">Impossibile calcolare il verdetto: ${gs.esc(e.message)}</p>`; }
      const [cls, etichetta] = Object.hasOwn(VERDETTI, r.verdict) ? VERDETTI[r.verdict] : VERDETTI.sconosciuto;
      return `<div class="pa-badge pa-${cls}">${gs.esc(etichetta)}</div>`
        + lista(r.reasons)
        + (r.suggestions?.length ? `<div class="pa-sub">Impostazioni consigliate</div>${lista(r.suggestions)}` : "")
        + `<details class="pa-box"><summary>Il tuo PC</summary>${righe(r.hw)}</details>`
        + `<details class="pa-box"><summary>Requisiti</summary>${righe(r.requirements)}</details>`;
    },
  });
}
