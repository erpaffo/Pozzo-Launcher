// Rassegna: cosa è successo nel mondo console nella settimana. Prima i tuoi giochi, poi una sezione per casa.

const ETICHETTA = { patch: "Patch", dlc: "DLC" };
const CHIP = "font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--accent);white-space:nowrap";

// Solo link http/https: qualunque altro schema viene scartato.
export function safeHref(u) {
  try { const x = new URL(String(u || "")); return /^https?:$/.test(x.protocol) ? x.href : ""; } catch { return ""; }
}

// Conteggi per il riepilogo: notizie per casa, notizie per i tuoi giochi, case con almeno una notizia.
export function riepilogo(digest) {
  const casa = Object.values(digest?.per_casa || {});
  return {
    notizie: casa.reduce((n, items) => n + (items?.length || 0), 0),
    mine: digest?.mine?.length || 0,
    case: casa.filter((items) => items?.length).length,
  };
}

// Sezioni per casa con al massimo `max` notizie, senza le case vuote.
export function sezioniCase(perCasa, max = 3) {
  return Object.entries(perCasa || {})
    .filter(([, items]) => items?.length)
    .map(([casa, items]) => [casa, items.slice(0, max)]);
}

export default function (gs) {
  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "text") n.textContent = v; else n.setAttribute(k, v);
    }
    n.append(...kids.filter((k) => k != null).map((k) => (typeof k === "string" ? document.createTextNode(k) : k)));
    return n;
  };
  const fade = (node) => {
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches)
      node.animate?.([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "none" }], { duration: 180, easing: "ease-out" });
    return node;
  };
  const giorno = (s, opt = { day: "numeric", month: "short" }) => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleDateString("it", opt); };
  const intervallo = (a, b) => (a && b ? `${giorno(a)} – ${giorno(b, { day: "numeric", month: "short", year: "numeric" })}` : "");

  const lista = (items) => el("ul", { style: "list-style:none;padding:0;margin:4px 0" }, ...items.map((it) => {
    const href = safeHref(it.link);
    const titolo = href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, it.title || "(senza titolo)") : it.title || "(senza titolo)";
    return el("li", { style: "display:flex;gap:8px;align-items:baseline;padding:4px 0;flex-wrap:wrap" },
      ETICHETTA[it.kind] ? el("span", { style: CHIP, text: ETICHETTA[it.kind] }) : null,
      el("span", {}, titolo),
      el("span", { class: "muted small", text: giorno(it.published) }));
  }));

  const sezione = (titolo, body) => el("section", { style: "margin-bottom:16px" }, el("h3", { style: "margin:0 0 4px", text: titolo }), body);

  gs.addSidebarItem({ id: "rassegna", label: "Rassegna", icon: "🗞", view: "rassegna" });

  gs.registerView("rassegna", {
    title: "Cosa è successo nel mondo console",
    async render(root) {
      root.replaceChildren(el("p", { class: "muted", text: "Carico la settimana…" }));
      let d;
      try { d = await gs.api("/plugin-api/notizie/digest"); } catch (e) {
        return root.replaceChildren(el("p", { class: "status-bad", text: e.message || "Impossibile caricare la rassegna." }));
      }
      const r = riepilogo(d);
      const head = el("header", {},
        el("h2", { style: "margin:0", text: "Cosa è successo nel mondo console" }),
        el("p", { class: "muted small", text: intervallo(d.week_start, d.week_end) }),
        el("p", { class: "small", text: `${r.notizie} notizie da ${r.case} ${r.case === 1 ? "casa" : "case"} · ${r.mine} per i tuoi giochi` }));
      if (!r.notizie && !r.mine) {
        return root.replaceChildren(head, fade(el("p", { class: "muted", text: "Nessuna notizia questa settimana. Le notizie arrivano dai feed attivi: puoi controllarli nella pagina Notizie, alla voce Fonti." })));
      }
      const parti = [head];
      if (r.mine) parti.push(sezione("Per i tuoi giochi", lista(d.mine)));
      for (const [casa, items] of sezioniCase(d.per_casa, 3)) parti.push(sezione(casa, lista(items)));
      root.replaceChildren(...parti.map((p) => fade(p)));
    },
  });
}
