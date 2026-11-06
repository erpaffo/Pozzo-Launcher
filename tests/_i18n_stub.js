// Per i test Node: t() e GSI18n come nel browser, con il catalogo italiano.
// require("./_i18n_stub") installa i globali; per i contesti vm usare inject(ctx).
const fs = require("fs"), path = require("path");
const strings = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "pozzo", "data", "locales", "it.json"), "utf8"));
const t = (key, p) => {
  const s = strings[key] ?? key;
  return p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? p[k] : m)) : s;
};
const GSI18n = { t, lang: "it", applyDom() {}, init() {}, set() {} };
function inject(ctx) {
  ctx.t = t; ctx.GSI18n = GSI18n;
  if (ctx.window && typeof ctx.window === "object") { ctx.window.t = t; ctx.window.GSI18n = GSI18n; }
  return ctx;
}
globalThis.t = t; globalThis.GSI18n = GSI18n;
module.exports = { t, GSI18n, inject, strings };
