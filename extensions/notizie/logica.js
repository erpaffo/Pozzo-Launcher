// Helper puri di Notizie (senza DOM): data relativa, normalizzazione, filtro «miei giochi».

export const KINDS = { annuncio: "Annuncio", patch: "Patch", dlc: "DLC", uscita: "Uscita", notizia: "Notizia" };

export const fold = (s) => String(s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
  .replace(/[^a-z0-9]+/g, " ").trim();

export function relDate(iso, now = Date.now()) {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "adesso";
  const un = (n, a, b) => `${n} ${n === 1 ? a : b} fa`;
  if (s < 3600) return un(Math.floor(s / 60), "minuto", "minuti");
  if (s < 86400) return un(Math.floor(s / 3600), "ora", "ore");
  if (s < 86400 * 7) return un(Math.floor(s / 86400), "giorno", "giorni");
  return new Date(t).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });
}

export const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? String(u) : "");

export const validUrl = (u) => { try { return /^https?:$/.test(new URL(u).protocol); } catch { return false; } };

// Insiemi normalizzati dalla libreria: titoli (>=4 caratteri) e nomi piattaforma.
export function buildSets(lib) {
  const titles = new Set(), plats = new Set();
  for (const g of lib?.games || []) { const f = fold(g.title); if (f.length >= 4) titles.add(f); }
  for (const p of lib?.plats?.values?.() || []) { const f = fold(p.name); if (f.length >= 3) plats.add(f); }
  return { titles, plats };
}

// shortcut: scansione lineare titoli x notizie, ok per librerie di migliaia di giochi; indicizzare se rallenta.
export function matcher(sets) {
  return (item) => {
    const h = ` ${fold(`${item.title} ${item.summary}`)} `;
    for (const t of sets.titles) if (h.includes(` ${t} `)) return true;
    for (const p of sets.plats) if (h.includes(` ${p} `)) return true;
    return false;
  };
}

export const filterMine = (items, match) => items.filter(match);
export const upcoming = (items) => items.filter((i) => i.kind === "annuncio" || i.kind === "uscita");
