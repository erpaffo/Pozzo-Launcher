// Pulizia libreria: funzioni pure (niente DOM), cosi' si provano da sole con node.

const DAY = 86400;
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** Una versione per gioco, posseduto e visibile. */
export function owned(games) {
  return games.filter((g) => g.id === g.grp.primary && !g.grp.hidden && g.store !== "online");
}

/** Gruppi di giochi con lo stesso titolo (senza maiuscole e punteggiatura) sulla stessa console: [[g, g, ...], ...]. */
export function duplicates(games) {
  const by = new Map();
  for (const g of owned(games)) {
    const k = `${g.store || g.platform}|${fold(g.title)}`;
    if (!fold(g.title)) continue;
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(g);
  }
  return [...by.values()].filter((l) => l.length > 1);
}

/** Mai avviati: nessuna partita, nessun tempo di gioco (nemmeno quello registrato dallo store). */
export function neverPlayed(games) {
  return owned(games).filter((g) => !g.grp.last && !g.grp.playtime && !g.splay && g.grp.status !== "done");
}

/** Fermi da `years` anni: giocati almeno una volta ma non da allora. */
export function stale(games, years, now = Date.now() / 1000) {
  return owned(games).filter((g) => g.grp.last && g.grp.last < now - years * 365 * DAY && g.grp.status !== "done")
    .sort((a, b) => a.grp.last - b.grp.last);
}

/** Che dati mancano: copertina, anno, genere, trovato dalle fonti. */
export function missing(g) {
  const out = [];
  if (!g.found) out.push("non trovato");
  if (!g.cover) out.push("copertina");
  if (!g.year) out.push("anno");
  if (!g.genres) out.push("genere");
  return out;
}

export function incomplete(games) {
  return owned(games).map((g) => [g, missing(g)]).filter(([, m]) => m.length).map(([g, m]) => ({ g, m }));
}

/** Byte leggibili, con la virgola come in italiano: 1536 -> "1,5 KB". */
export function fmtBytes(n) {
  if (n == null || isNaN(n)) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let v = +n, i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return i === 0 ? `${v} B` : `${v.toFixed(1).replace(".", ",")} ${u[i]}`;
}

/** Nome del file da un percorso (con / o \). */
export function baseName(p) {
  return String(p).split(/[\\/]/).pop();
}

/** Spazio liberato tenendo la copia `keep`: le copie gia' collegate (hardlink) non liberano nulla. */
export function freeable(group, keep = group.keep) {
  return group.files.reduce((s, f, j) => s + (j !== keep && !f.is_hardlink ? group.size : 0), 0);
}

export function freeableTotal(groups) {
  return groups.reduce((s, g) => s + freeable(g), 0);
}

/** Si puo' collegare ogni altra copia alla `keep`? Falso se una e' su un altro disco (non c'e' hardlink). */
export function linkable(group, keep = group.keep) {
  const f = group.files;
  // «dev» = volume del file (backend): confronto diretto con la copia scelta; senza, si ripiega sulla prima copia
  if (f.every((x) => x.dev != null)) return f.every((x) => x.dev === f[keep].dev);
  const sameVol = (j) => j === 0 || !!f[j].same_volume_as_first;   // la prima copia fa da riferimento
  return f.every((_, j) => j === keep || (sameVol(j) && sameVol(keep)));
}

/** Testo del confirm() per l'azione ("hardlink" | "delete") sulle copie diverse da `keep`. */
export function confirmText(action, group, keep = group.keep) {
  const others = group.files.filter((_, j) => j !== keep).map((f) => `  • ${f.path}`);
  const tieni = `Si tiene:\n  ${group.files[keep].path}`;
  if (action === "delete")
    return [`Eliminare definitivamente ${others.length} ${others.length === 1 ? "copia" : "copie"}:`, ...others, tieni, "Non si puo' annullare."].join("\n");
  return [`Sostituire con collegamenti (hardlink) ${others.length} ${others.length === 1 ? "copia" : "copie"}:`, ...others, tieni].join("\n");
}

/** Gruppo dopo `dup-apply`: `results` = [{path, ok}]. Ritorna il gruppo aggiornato, o null se ne restano meno di due. */
export function afterApply(group, action, results) {
  const done = new Set(results.filter((r) => r.ok).map((r) => r.path));
  const keepPath = group.files[group.keep].path;
  let files = group.files.filter((f) => f.path === keepPath || !done.has(f.path) || action !== "delete");
  if (action === "hardlink") files = files.map((f) => (done.has(f.path) && f.path !== keepPath ? { ...f, is_hardlink: true } : f));
  if (files.length < 2) return null;
  return { ...group, files, keep: files.findIndex((f) => f.path === keepPath) };
}
