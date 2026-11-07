// Eventi e fiere: pagina con il calendario degli eventi e i giorni che mancano.

const data = (iso) => new Date(iso + "T00:00").toLocaleDateString("it", { day: "numeric", month: "long", year: "numeric" });

export default function (gs) {
  gs.addSidebarItem({ id: "eventi-fiere", label: "Eventi e fiere", icon: "🎮", view: "eventi-fiere" });
  gs.registerView("eventi-fiere", {
    title: "Eventi e fiere",
    async render(el) {
      let d;
      try { d = await gs.api("/plugin-api/eventi-fiere/eventi"); } catch (e) { el.innerHTML = `<p class="muted">${gs.esc(e.message)}</p>`; return; }
      const righe = d.eventi.map((e) => {
        const quando = e.giorni > 0 ? `tra ${e.giorni} giorni` : e.giorni === 0 ? "oggi" : "in corso";
        const nome = e.url ? `<a href="${gs.esc(e.url)}" target="_blank" rel="noopener">${gs.esc(e.nome)}</a>` : gs.esc(e.nome);
        return `<li><b>${nome}</b> <span class="muted">${data(e.inizio)}${e.fine !== e.inizio ? " – " + data(e.fine) : ""}${e.luogo ? " · " + gs.esc(e.luogo) : ""} · ${quando}</span></li>`;
      }).join("");
      el.innerHTML = `<h2>Eventi e fiere</h2>`
        + (righe ? `<ul class="an-list">${righe}</ul>` : `<p class="muted">Nessun evento in elenco. Aggiungili in eventi.json.</p>`);
    },
  });
}
