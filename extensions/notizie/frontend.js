// Notizie videogiochi: timeline stile social, filtro «i miei giochi», fonti configurabili.
// In arrivo: la pagina «Calendario uscite» (estensione calendario-uscite) resta separata, qui nessuna integrazione.
import { KINDS, relDate, safeUrl, validUrl, buildSets, matcher, upcoming } from "./logica.js";

const LS = "notizie.prefs";
const load = () => { try { return JSON.parse(localStorage.getItem(LS)) || {}; } catch { return {}; } };
const save = (p) => { try { localStorage.setItem(LS, JSON.stringify(p)); } catch { /* storage non disponibile */ } };

export default function (gs, ctx) {
  const prefs = load();   // {mine, casa, kind}
  let match = () => true;
  const refreshMine = () => { try { match = matcher(buildSets(gs.library())); } catch { match = () => true; } };
  gs.on("libraryLoaded", refreshMine);
  refreshMine();

  const fetchFeed = (p) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(p || {})) if (v) q.set(k, v);
    return gs.api(`/plugin-api/notizie/feed?${q}`);
  };
  const api = { fetchFeed, mine: () => match, esc: gs.esc };

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function card(it) {
    const c = el("article", "nz-card");
    const head = el("div", "nz-head");
    head.append(el("span", "nz-casa", it.casa || it.source),
      el("span", `nz-kind nz-k-${KINDS[it.kind] ? it.kind : "notizia"}`, KINDS[it.kind] || "Notizia"),
      el("span", "nz-date muted", relDate(it.published)));
    const url = safeUrl(it.link);
    const t = el("h3", "nz-title");
    if (url) {
      const a = el("a", "", it.title); a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.onclick = (e) => { e.preventDefault(); gs.api("/api/open", { body: { url } }).catch(() => window.open(url, "_blank", "noopener")); };
      t.append(a);
    } else t.textContent = it.title;
    c.append(head, t);
    if (it.summary) c.append(el("p", "nz-sum", it.summary));
    const img = safeUrl(it.image);
    if (img) { const i = el("img", "nz-img"); i.loading = "lazy"; i.alt = ""; i.referrerPolicy = "no-referrer"; i.src = img; i.onerror = () => i.remove(); c.append(i); }
    return c;
  }

  gs.addSidebarItem({ id: "notizie", label: "Notizie", icon: "📰", view: "notizie" });

  gs.registerView("notizie", {
    title: "Notizie",
    async render(root) {
      const st = { casa: prefs.casa || "", kind: prefs.kind || "", q: "", mine: !!prefs.mine, items: [], sources: [], busy: false, end: false };
      root.innerHTML = "";
      root.classList.add("nz");
      const bar = el("div", "nz-bar"), chips = el("div", "nz-chips"), kinds = el("div", "nz-chips");
      const search = el("input", "nz-search"); search.type = "search"; search.placeholder = "Cerca nelle notizie…"; search.setAttribute("aria-label", "Cerca");
      const mineLbl = el("label", "chk nz-mine"), mine = el("input"); mine.type = "checkbox"; mine.checked = st.mine;
      const mineCount = el("span", "muted"); mineLbl.append(mine, " Solo i miei giochi e console ", mineCount);
      bar.append(search, mineLbl);
      const soon = el("section", "nz-soon"), list = el("div", "nz-list"), errs = el("details", "nz-errs"), more = el("button", "btn nz-more", "Carica altri");
      root.append(bar, chips, kinds, soon, list, more, errs);
      more.hidden = true; errs.hidden = true;

      const chipRow = (row, opts, key) => {
        row.replaceChildren(...opts.map(([v, lab]) => {
          const b = el("button", "nz-chip" + (st[key] === v ? " on" : ""), lab); b.type = "button";
          b.onclick = () => { st[key] = v; prefs[key] = v; save(prefs); chipRow(row, opts, key); reload(); };
          return b;
        }));
      };
      const drawKinds = () => chipRow(kinds, [["", "Tutto"], ...Object.entries(KINDS)], "kind");
      const drawCase = () => {
        const cs = [...new Set(st.sources.map((s) => s.casa).filter(Boolean))].sort();
        chipRow(chips, [["", "Tutte le case"], ...cs.map((c) => [c, c])], "casa");
      };

      function draw() {
        const vis = st.mine ? st.items.filter(match) : st.items;
        mineCount.textContent = st.mine ? `(${vis.length} su ${st.items.length})` : "";
        const up = upcoming(vis).slice(0, 5);
        soon.replaceChildren();
        if (up.length) { soon.append(el("h2", "nz-h", "Annunci e prossime uscite")); const g = el("div", "nz-list"); up.forEach((i) => g.append(card(i))); soon.append(g); }
        list.replaceChildren(...vis.map(card));
        if (!vis.length && !st.busy) list.append(el("p", "muted", st.mine ? "Nessuna notizia sui tuoi giochi o console tra quelle caricate." : "Nessuna notizia trovata."));
        more.hidden = st.end || !st.items.length;
        const bad = st.sources.filter((s) => s.ok === false);
        errs.hidden = !bad.length;
        errs.replaceChildren(el("summary", "", `${bad.length} font${bad.length === 1 ? "e non raggiungibile" : "i non raggiungibili"}`),
          ...bad.map((s) => el("div", "muted", `${s.nome}: ${s.error || "errore"}`)));
      }

      let tok = 0;
      async function fetchMore(reset) {
        if (st.busy && !reset) return;
        st.busy = true; const my = ++tok;
        if (reset) { st.items = []; st.end = false; list.replaceChildren(); window.GSSkeleton?.show?.(list, 6); }
        more.disabled = true;
        try {
          const before = reset ? "" : st.items[st.items.length - 1]?.published;
          const d = await fetchFeed({ casa: st.casa, kind: st.kind, q: st.q, limit: 50, before });
          if (my !== tok) return;   // risposta superata da una ricerca più recente
          const got = d.items || [];
          st.items = st.items.concat(got);
          st.end = got.length < 50;
          if (d.sources?.length) { const first = !st.sources.length; st.sources = d.sources; if (first) drawCase(); }
        } catch (e) { if (my === tok) list.replaceChildren(el("p", "muted", `Notizie non disponibili: ${e.message}`)); }
        finally { if (my === tok) { window.GSSkeleton?.hide?.(list); st.busy = false; more.disabled = false; draw(); } }
      }
      const reload = () => fetchMore(true);

      let timer;
      search.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { st.q = search.value.trim(); reload(); }, 300); };
      mine.onchange = () => { st.mine = mine.checked; prefs.mine = st.mine; save(prefs); draw(); };
      more.onclick = () => fetchMore(false);
      drawKinds(); drawCase();
      await fetchMore(true);
    },
  });

  gs.addSettingsTab({
    id: "notizie", label: "Notizie",
    async render(root) {
      root.innerHTML = "";
      let srcs;
      const stato = new Map();
      try {
        srcs = (await gs.api("/plugin-api/notizie/sources")).sources || [];
        ((await fetchFeed({ limit: 1 }).catch(() => ({}))).sources || []).forEach((s) => stato.set(s.id, s));
      } catch (e) { root.textContent = e.message; return; }
      const disabled = new Set(srcs.filter((s) => !s.enabled).map((s) => s.id));
      const custom = srcs.filter((s) => s.custom).map(({ casa, nome, url }) => ({ casa, nome, url }));
      const msg = el("p", "muted");
      const persist = async () => {
        try { await gs.api("/plugin-api/notizie/sources", { body: { disabled_sources: [...disabled], custom_sources: custom } }); msg.textContent = "Salvato."; return true; }
        catch (e) { msg.textContent = `Errore: ${e.message}`; return false; }
      };
      root.append(el("h3", "", "Fonti delle notizie"));
      const byCasa = new Map();
      srcs.forEach((s) => byCasa.set(s.casa, [...(byCasa.get(s.casa) || []), s]));
      for (const [casa, ss] of byCasa) {
        const g = el("fieldset", "nz-grp"); g.append(el("legend", "", casa));
        for (const s of ss) {
          const l = el("label", "chk"), cb = el("input"); cb.type = "checkbox"; cb.checked = s.enabled;
          cb.onchange = () => { if (cb.checked) disabled.delete(s.id); else disabled.add(s.id); persist(); };
          const sx = stato.get(s.id), info = sx ? (sx.ok ? "ok" : `errore: ${sx.error || "?"}`) : "";
          l.append(cb, ` ${s.nome} `, el("span", "muted", info));
          g.append(l);
        }
        root.append(g);
      }
      const f = el("form", "nz-add");
      const mk = (ph) => { const i = el("input"); i.placeholder = ph; i.required = true; return i; };
      const c = mk("Casa"), n = mk("Nome"), u = mk("https://…/feed.xml"), b = el("button", "btn", "Aggiungi fonte"); b.type = "submit";
      f.append(c, n, u, b);
      f.onsubmit = async (e) => {
        e.preventDefault();
        if (!validUrl(u.value.trim())) { msg.textContent = "L’URL deve iniziare con http:// o https://"; return; }
        custom.push({ casa: c.value.trim(), nome: n.value.trim(), url: u.value.trim() });
        if (await persist()) { f.reset(); msg.textContent = "Fonte aggiunta. Riapri le impostazioni per vederla nell’elenco."; } else custom.pop();
      };
      root.append(el("h4", "", "Aggiungi fonte"), f, msg);
    },
  });

  // moduli opzionali scritti a parte: se mancano si prosegue
  for (const m of ["./segui.js", "./rassegna.js"]) {
    import(m).then((x) => x.default?.(gs, ctx, api)).catch(() => {});
  }
}
