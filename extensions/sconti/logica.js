// Sconti e bundle: funzioni pure (niente DOM), provate con node in tests/test_sconti_ui.js.

const MIN = 60000, HOUR = 60 * MIN, DAY = 24 * HOUR;

/** Prezzo in euro con la virgola; 0 = «Gratis»; mancante o non numerico = trattino. */
export function fmtPrice(v) {
  const n = Number(v);
  if (v == null || v === "" || !Number.isFinite(n)) return "—";
  if (n === 0) return "Gratis";
  return `${n.toFixed(2).replace(".", ",")} €`;
}

/** «-37%» oppure null se lo sconto non c'e' (o non e' un numero). */
export function fmtPercent(p) {
  const n = Math.round(Number(p));
  return p != null && Number.isFinite(n) && n > 0 ? `-${Math.min(100, n)}%` : null;
}

/** Data in millisecondi da secondi, millisecondi, stringa ISO o «AAAA-MM-GG» (mezzanotte locale). NaN se non valida. */
export function toMs(v) {
  if (typeof v === "number") return v < 1e12 ? v * 1000 : v;
  if (typeof v !== "string") return NaN;
  const s = v.trim().replace(/^(\d{4}-\d{2}-\d{2}) /, "$1T"); // «AAAA-MM-GG HH:MM» (fonte gratis) come ISO
  if (/^\d+$/.test(s)) return toMs(Number(s));
  return Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T00:00:00` : s);
}

/** «scade tra 3 giorni», «scade tra 5 h», «scaduto»; null se la scadenza manca. */
export function countdown(expiry, now = Date.now()) {
  const end = toMs(expiry);
  if (!Number.isFinite(end)) return null;
  const left = end - now;
  if (left <= 0) return "scaduto";
  const d = Math.floor(left / DAY), h = Math.floor(left / HOUR), m = Math.max(1, Math.floor(left / MIN));
  if (d >= 2) return `scade tra ${d} giorni`;
  if (d === 1) return "scade tra 1 giorno";
  if (h >= 1) return `scade tra ${h} h`;
  return `scade tra ${m} min`;
}

/** Data leggibile in italiano («10 novembre 2026»); null se non valida. */
export function fmtDate(v) {
  const ms = toMs(v);
  return Number.isFinite(ms) ? new Date(ms).toLocaleDateString("it", { day: "numeric", month: "long", year: "numeric" }) : null;
}

/** Solo link web: il resto (javascript:, file:, ...) non diventa mai un pulsante «Apri». */
export function isHttpUrl(u) {
  try { return /^https?:$/.test(new URL(String(u)).protocol); } catch { return false; }
}

const num = (x) => (x == null || x === "" || !Number.isFinite(Number(x)) ? null : Number(x));

/** Sconti: per percentuale (default, dal piu' alto) o per prezzo (dal piu' basso). Valori mancanti in fondo. */
export function sortDeals(list, by = "cut") {
  return [...list].sort((a, b) => {
    const [x, y] = by === "price" ? [num(a.price), num(b.price)] : [num(b.cut_percent), num(a.cut_percent)];
    if (x == null || y == null) return (y == null) - (x == null);
    return x - y || String(a.title).localeCompare(String(b.title), "it");
  });
}

/** Bundle: prima quelli «per te», poi in scadenza (piu' vicina prima), gli scaduti in fondo. */
export function sortBundles(list, now = Date.now()) {
  const group = (b) => { const e = toMs(b.expiry); return !Number.isFinite(e) ? 1 : e <= now ? 2 : 0; };
  return [...list].sort((a, b) =>
    (!!b.mine - !!a.mine) || (group(a) - group(b)) || ((toMs(a.expiry) || 0) - (toMs(b.expiry) || 0)));
}

/** Una fascia di prezzo di un bundle: testo semplice o oggetto {price, addon, name?}. */
export function tierText(t) {
  if (t == null) return "";
  if (typeof t !== "object") return String(t);
  return [t.name || t.title || (t.addon ? "Add-on" : ""), t.price != null ? fmtPrice(t.price) : ""].filter(Boolean).join(" · ");
}

/** Titoli dei giochi di un bundle, separati da virgola (stringhe o oggetti con title). */
export function gameNames(games) {
  return (Array.isArray(games) ? games : [])
    .map((g) => String((g && typeof g === "object" ? g.title : g) ?? ""))
    .filter(Boolean).join(", ");
}
