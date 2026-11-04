// Recensioni e punteggi: sezione nel dettaglio gioco e chiave OpenCritic nelle impostazioni.

const colore = (p) => (p >= 75 ? "rc-good" : p >= 50 ? "rc-warn" : "rc-bad");

export default function (gs) {
  gs.addDetailSection({
    id: "recensioni",
    title: "⭐ Recensioni",
    async render(game) {
      const box = document.createElement("div");
      box.className = "rc-box";
      let d;
      try { d = await gs.api(`/plugin-api/recensioni/scores/${game.id}`); } catch (e) { box.textContent = e.message; return box; }
      const chips = [], links = [];
      if (d.metacritic) {
        chips.push(`<div class="rc-chip ${colore(d.metacritic.score)}"><span>Metacritic</span><b>${d.metacritic.score}</b></div>`);
        links.push(["Apri su Metacritic", d.metacritic.url]);
      }
      if (d.opencritic) {
        const o = d.opencritic;
        const extra = [o.tier && gs.esc(o.tier), o.recommended != null && `${o.recommended}% consiglia`].filter(Boolean).join(" · ");
        chips.push(`<div class="rc-chip ${colore(o.score)}"><span>OpenCritic</span><b>${o.score}</b><small>${extra}</small></div>`);
        links.push(["Apri su OpenCritic", o.url]);
      }
      if (d.steam) {
        const s = d.steam;
        chips.push(`<div class="rc-chip ${colore(s.percent)}"><span>Steam</span><b>${s.percent}%</b>
          <small>${gs.esc(s.desc)} (${s.total.toLocaleString("it")})</small></div>`);
        links.push(["Apri su Steam", s.url]);
      }
      if (!chips.length) {
        box.innerHTML = `<p class="muted small">Nessuna recensione trovata per questo gioco.</p>`;
        return box;
      }
      box.innerHTML = `<div class="rc-chips">${chips.join("")}</div>
        <p class="rc-links">${links.map(([t, u]) => `<a href="#" data-url="${gs.esc(u)}">${gs.esc(t)}</a>`).join(" · ")}</p>`;
      box.addEventListener("click", (e) => {
        const a = e.target.closest("a[data-url]");
        if (!a) return;
        e.preventDefault();
        gs.api("/api/open", { body: { url: a.dataset.url } }).catch((err) => gs.toast(err.message, true));
      });
      return box;
    },
  });

  async function draw(el) {
    let d;
    try { d = await gs.api("/plugin-api/recensioni/stato"); } catch (e) { el.textContent = e.message; return; }
    el.innerHTML = `<h3>Recensioni e punteggi</h3>
      <p class="muted">Metacritic e le recensioni Steam non richiedono nulla. OpenCritic richiede una chiave gratuita di RapidAPI:
        iscriviti su <a href="#" data-url="https://rapidapi.com/">rapidapi.com</a>, cerca «OpenCritic» nel catalogo, scegli il piano gratuito
        e copia la chiave <b>X-RapidAPI-Key</b> dalla pagina dell'API.</p>
      <p>${d.opencritic ? "✔ Chiave impostata." : "Nessuna chiave: OpenCritic è disattivato."}</p>
      <p><input type="password" id="rc-k" placeholder="Incolla la chiave RapidAPI" autocomplete="off" style="width:320px">
        <button class="btn primary" id="rc-save">Salva</button>
        ${d.opencritic ? `<button class="btn" id="rc-del">Rimuovi</button>` : ""}</p>`;
    el.querySelector("a[data-url]").onclick = (e) => { e.preventDefault(); gs.api("/api/open", { body: { url: e.target.dataset.url } }); };
    const set = async (opencritic_key) => {
      try { await gs.api("/plugin-api/recensioni/chiave", { body: { opencritic_key } }); gs.toast("Salvato"); } catch (e) { return gs.toast(e.message, true); }
      draw(el);
    };
    el.querySelector("#rc-save").onclick = () => set(el.querySelector("#rc-k").value);
    el.querySelector("#rc-del")?.addEventListener("click", () => set(""));
  }
  gs.addSettingsTab({ id: "recensioni", label: "Recensioni", render: draw });
}
