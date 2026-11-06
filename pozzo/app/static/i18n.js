// Traduzioni UI. t("chiave", {x: 1}) sostituisce {x}; data-i18n (testo) / data-i18n-html (con tag) / data-i18n-title / data-i18n-placeholder / data-i18n-aria nell'HTML.
// Lingua: localStorage "gs.lang" (se manca, quella del browser). Cataloghi da /api/i18n/<lingua>, ricaduta su it.
(() => {
  let strings = {}, lang = "it";
  const t = (key, p) => {
    const s = strings[key] ?? key;
    return p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? p[k] : m)) : s;
  };
  const applyDom = (root = document) => {
    for (const [attr, set] of [["i18n", (e, v) => (e.textContent = v)], ["i18nHtml", (e, v) => (e.innerHTML = v)], ["i18nTitle", (e, v) => (e.title = v)], ["i18nPlaceholder", (e, v) => (e.placeholder = v)], ["i18nAria", (e, v) => e.setAttribute("aria-label", v)]]) {
      const sel = "data-" + attr.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
      const hit = [...root.querySelectorAll(`[${sel}]`), ...(root.matches?.(`[${sel}]`) ? [root] : [])];
      hit.forEach((e) => set(e, t(e.getAttribute(sel))));
    }
  };
  const pick = async () => {
    const list = (await (await fetch("/api/i18n")).json()).languages;
    const want = localStorage.getItem("gs.lang") || navigator.language || "it";
    return [want, want.split("-")[0]].find((l) => list.includes(l)) || "it";
  };
  const init = async () => {
    try {
      lang = await pick();
      const r = await (await fetch("/api/i18n/" + lang)).json();
      strings = r.strings;
      document.cookie = `gs_lang=${localStorage.getItem("gs.lang") ? lang : ""}; path=/; max-age=31536000; samesite=lax`;  // il server risponde nella stessa lingua
      document.documentElement.lang = lang;
      document.documentElement.dir = r.dir;
      applyDom();
    } catch (e) { /* senza catalogo restano le chiavi/testi scritti nell'HTML */ }
  };
  // Selettore in Impostazioni > Generale: la pagina viene caricata dopo, quindi si riempie al primo uso.
  const fill = async (sel) => {
    const list = (await (await fetch("/api/i18n")).json()).languages;
    const cur = localStorage.getItem("gs.lang") || "";
    sel.innerHTML = `<option value="">${t("app.language.auto")}</option>` + list.map((l) => `<option value="${l}"${l === cur ? " selected" : ""}>${new Intl.DisplayNames([l], { type: "language" }).of(l)}</option>`).join("");
  };
  document.addEventListener("change", (e) => { if (e.target.id === "ui-language") GSI18n.set(e.target.value).then(() => location.reload()); });
  // Pannelli e schermate entrano nella pagina dopo l'avvio: si traducono man mano che arrivano.
  new MutationObserver((muts) => {
    for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1) applyDom(n);
    const s = document.getElementById("ui-language"); if (s && !s.options.length) fill(s);
  }).observe(document.documentElement, { childList: true, subtree: true });
  window.GSI18n = { t, applyDom, init, get lang() { return lang; }, set: (l) => { l ? localStorage.setItem("gs.lang", l) : localStorage.removeItem("gs.lang"); return init(); } };
  window.t = t;
  init();
})();
