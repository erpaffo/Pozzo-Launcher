// Speedrun: sezione nel dettaglio gioco con i record del mondo e il link a speedrun.com.

export default function (gs) {
  gs.addDetailSection({
    id: "speedrun",
    title: "⏱️ Speedrun",
    async render(game) {
      let r;
      try { r = await gs.api(`/plugin-api/speedrun/record?id=${encodeURIComponent(game.id)}`); }
      catch (e) { return `<p class="muted">Record non disponibili: ${gs.esc(e.message)}</p>`; }
      const righe = r.categorie.map((c) => `<li><b>${gs.esc(c.nome)}</b>: ${gs.esc(c.tempo)} di ${gs.esc(c.giocatore)}`
        + (c.link ? ` · <a href="${gs.esc(c.link)}" target="_blank" rel="noopener">run</a>` : "") + "</li>").join("");
      const pagina = r.link ? `<p><a href="${gs.esc(r.link)}" target="_blank" rel="noopener">Pagina su speedrun.com</a></p>` : "";
      return (righe ? `<ul>${righe}</ul>` : `<p class="muted">Nessun record in classifica.</p>`)
        + pagina + (r.errore ? `<p class="muted">Dati non aggiornati (${gs.esc(r.errore)})</p>` : "");
    },
  });
}
