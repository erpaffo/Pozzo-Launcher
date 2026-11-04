// Seguiti: segui un gioco, badge di novità sulle tessere, sezione «Novità sul gioco» e vista «Seguiti».

const API = "/plugin-api/notizie";
const ETICHETTA = { patch: "Patch", dlc: "DLC" };
const CHIP = "font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--accent);white-space:nowrap";

// Solo link http/https: qualunque altro schema (javascript:, data:) viene scartato.
export function safeHref(u) {
  try { const x = new URL(String(u || "")); return /^https?:$/.test(x.protocol) ? x.href : ""; } catch { return ""; }
}

// Totale delle notizie non lette su tutti i giochi seguiti.
export function contaNonLetti(games) {
  let n = 0;
  for (const g of games || []) n += Math.max(0, +g.unread || 0);
  return n;
}

// id gioco -> notizie non lette (solo i giochi che ne hanno).
export function nonLettiPerGioco(games) {
  const m = new Map();
  for (const g of games || []) if (+g.unread > 0) m.set(String(g.id), +g.unread); // il backend salva gli id come stringhe
  return m;
}

export default function (gs) {
  let games = [];                       // ultima risposta di follows/news
  let unread = new Map();               // id -> non letti, per le tessere
  const followed = (id) => games.some((g) => String(g.id) === String(id));
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "text") n.textContent = v;
      else if (typeof v === "function") n.addEventListener(k.replace(/^on/, ""), v);
      else n.setAttribute(k, v);
    }
    n.append(...kids.filter((k) => k != null).map((k) => (typeof k === "string" ? document.createTextNode(k) : k)));
    return n;
  };
  const fade = (node) => {
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches)
      node.animate?.([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 180, easing: "ease-out" });
    return node;
  };
  const data = (s) => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleDateString("it", { day: "numeric", month: "short", year: "numeric" }); };

  // Ricarica i seguiti e aggiorna badge e voce della barra laterale (anche se la richiesta fallisce).
  // Ritorna i giochi, o null se la richiesta fallisce.
  async function refresh() {
    let ok = true;
    try { games = (await gs.api(`${API}/follows/news`)).games || []; } catch { ok = false; }
    unread = nonLettiPerGioco(games);
    const n = contaNonLetti(games);
    gs.addSidebarItem({ id: "seguiti", label: "Seguiti" + (n ? ` · ${n}` : ""), icon: "🔔", view: "seguiti" });
    return ok ? games : null;
  }

  // Elenco di notizie: etichetta Patch/DLC, titolo con link esterno, data.
  const lista = (items) => el("ul", { style: "list-style:none;padding:0;margin:4px 0" }, ...items.map((it) => {
    const href = safeHref(it.link);
    const titolo = href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, it.title || "(senza titolo)") : it.title || "(senza titolo)";
    return el("li", { style: "display:flex;gap:8px;align-items:baseline;padding:4px 0;flex-wrap:wrap" },
      ETICHETTA[it.kind] ? el("span", { style: CHIP, text: ETICHETTA[it.kind] }) : null,
      el("span", {}, titolo),
      it.unread ? el("b", { style: "color:var(--accent)", text: "nuovo" }) : null,
      el("span", { class: "muted small", text: data(it.published) }));
  }));

  async function toggle(g, on) {
    try {
      // il dettaglio gioco non ha steam_appid: si ricava da key/pagina Steam (come fa recensioni), cosi' arrivano le news Steam
      const appid = g.steam_appid || (/(?:steam:|steampowered\.com\/app\/)(\d+)/.exec(`${g.key || ""} ${g.page || ""}`) || [])[1];
      if (on) await gs.api(`${API}/follow`, { body: { id: g.id, title: g.title, steam_appid: appid } });
      else await gs.api(`${API}/unfollow`, { body: { id: g.id } });
    } catch (e) { return gs.toast(e.message, true); }
    await refresh();
    gs.toast(on ? `Ora segui ${g.title}` : `Non segui più ${g.title}`);
    if (String(gs.currentGame()?.id) === String(g.id)) gs.openGame(Number(g.id)); // ridisegna il dettaglio con il pulsante giusto
  }

  // Due voci con «when» complementari: il pulsante cambia in base allo stato già noto.
  gs.addGameAction({ id: "segui", label: "Segui", icon: "🔔", when: (g) => !followed(g.id), run: (g) => toggle(g, true) });
  gs.addGameAction({ id: "smetti-di-seguire", label: "Smetti di seguire", icon: "🔕", when: (g) => followed(g.id), run: (g) => toggle(g, false) });

  gs.addTileBadge({ id: "segui-novita", render: (g) => (unread.get(String(g.id)) ? `📰 ${unread.get(String(g.id))}` : null) });

  gs.addDetailSection({
    id: "novita-gioco",
    title: "Novità sul gioco",
    async render(g) {
      const all = await refresh();
      if (all === null) return el("p", { class: "muted small", text: "Novità non disponibili al momento." });
      const f = all.find((x) => String(x.id) === String(g.id));
      if (!f) return el("p", { class: "muted small", text: "Segui il gioco per ricevere patch e DLC." });
      if (!f.items.length) return el("p", { class: "muted small", text: "Nessuna novità per ora." });
      if (f.unread > 0) gs.api(`${API}/follows/seen`, { body: { id: g.id } }).then(refresh).catch(() => {}); // aperta = letta
      return fade(lista(f.items));
    },
  });

  gs.registerView("seguiti", {
    title: "Seguiti",
    async render(root) {
      root.replaceChildren(el("p", { class: "muted", text: "Carico…" }));
      const all = await refresh();
      if (all === null) return root.replaceChildren(el("p", { class: "status-bad", text: "Impossibile caricare i giochi seguiti." }));
      if (!all.length) return root.replaceChildren(el("p", { class: "muted", text: "Non segui ancora nessun gioco. Apri il dettaglio di un gioco e premi «Segui» per ricevere qui le sue patch e i suoi DLC." }));
      root.replaceChildren(...all.map((g) => fade(el("section", { style: "margin-bottom:16px" },
        el("div", { style: "display:flex;gap:10px;align-items:center" },
          el("h3", { style: "margin:0", text: g.title }),
          g.unread ? el("span", { class: "badge ext", text: `${g.unread} nuove` }) : null,
          el("button", { class: "btn", type: "button", text: "Apri", onclick: () => gs.openGame(Number(g.id)) })),
        g.items.length ? lista(g.items.slice(0, 5)) : el("p", { class: "muted small", text: "Nessuna novità per ora." })))));
    },
  });

  refresh();
  gs.on("gameOpened", () => refresh());
}
