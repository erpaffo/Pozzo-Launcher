"use strict";
/* Pozzo Launcher - frontend: vista «Strumenti» (conversioni, patch, verifica, dump) e adozione del file prodotto.
 * Script classico (ambito globale condiviso, ordine in index.html). Le funzioni pure (TLU) sono provate con node
 * da tests/test_tools_ui.js. Il backend e' pozzo/app/routes/tools.py. */

const tt = (k, it, p) => {
  const s = typeof window !== "undefined" && window.t ? window.t(k, p) : k;
  return s !== k ? s : it.replace(/\{(\w+)\}/g, (m, n) => (p && n in p ? p[n] : m));
};

const TLU = (() => {
  /** gli strumenti che producono un file nuovo: solo questi offrono l'adozione */
  const PRODUCES = new Set(["nup", "chd", "rvz", "cso", "patch"]);
  const UNITS = ["B", "KB", "MB", "GB", "TB"];
  function bytes(n) {
    if (n == null || !isFinite(n) || n < 0) return "";
    let i = 0;
    while (n >= 1024 && i < UNITS.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n.toFixed(0) : n < 10 ? n.toFixed(2) : n.toFixed(1)).replace(".", ",") + " " + UNITS[i];
  }
  const num = (v) => (typeof v === "number" && isFinite(v) && v >= 0 ? v : null);
  /** dimensioni prima/dopo, solo se il server le manda (null altrimenti) */
  const sizes = (job) => ({
    before: num(job?.size_src ?? job?.result?.size_src ?? job?.size_before),
    after: num(job?.size_out ?? job?.result?.size_out ?? job?.size_after),
  });
  const adoptable = (job) => !!job && job.status === "done" && PRODUCES.has(job.tool) && !!job.out && !job.adopted;
  /** le tre scelte a fine lavoro; la prima e' quella predefinita (originale nel Cestino, mai cancellato) */
  const actions = (job) => adoptable(job)
    ? [{ id: "trash", move_old: true, primary: true }, { id: "keep", move_old: false }, { id: "skip" }] : [];
  /** manca qualcosa prima di avviare? (chiave dell'opzione mancante, o "") */
  function missing(tool, game, o) {
    if (tool.needs_game && !game) return "game";
    if (tool.id === "patch" && !o.patch) return "patch";
    if (tool.id === "dump") return !o.drive ? "drive" : !o.dst ? "dst" : "";
    return "";
  }
  /** corpo di POST /api/tools/run */
  function request(tool, game, o) {
    const body = { tool: tool.id, platform: game?.platform || "" };
    if (tool.needs_game) body.path = game.files[0];
    const opts = {};
    if (tool.id === "nup") opts.format = o.format === "nsp" ? "nsp" : "nup";
    if (tool.id === "patch") opts.patch = o.patch;
    if (tool.id === "dump") { opts.drive = o.drive; body.dst = o.dst; }
    if (Object.keys(opts).length) body.options = opts;
    return body;
  }
  /** i giochi scegliibili: solo quelli con file locali (niente store/online) che corrispondono alla ricerca */
  function pickGames(games, q, fold, limit = 12) {
    q = fold(q || "").trim();
    return games.filter((g) => !g.store && (!q || fold(g.title).includes(q))).slice(0, limit);
  }
  return { PRODUCES, bytes, sizes, adoptable, actions, missing, request, pickGames };
})();

if (typeof module !== "undefined") module.exports = TLU;

if (typeof window !== "undefined") {
  /* stato della vista: sopravvive al cambio pagina, cosi' un lavoro in corso non si perde */
  const TS = { game: null, tools: [], busy: false, o: { format: "nup", patch: "", drive: "", dst: "" }, drives: null,
    job: null, err: "", note: "", timer: null, q: "", seq: 0 };
  const toolName = (x) => tt(`t.tools.${x.id}.name`, x.name);

  /** il gioco con i suoi file (la lista non li ha) */
  async function toolsLoadGame(g) {
    const d = g.files ? g : await api(`/api/game/${g.id}`);
    return { id: d.id, title: d.title, platform: d.platform, files: d.files || [] };
  }
  /** gli strumenti compatibili con un gioco; [] se non ha file o il server non risponde */
  async function toolsFor(game) {
    if (!game?.files?.length) return [];
    try {
      const r = await api(`/api/tools?platform=${encodeURIComponent(game.platform)}&path=${encodeURIComponent(game.files[0])}`);
      return r.tools.filter((x) => x.needs_game);
    } catch { return []; }
  }
  const COMPAT = new Map();
  /** per dettaglio e menu: gli strumenti del gioco (in cache), con il gioco gia' caricato */
  async function toolsCompat(g) {
    if (g.store) return null;
    if (!COMPAT.has(g.id)) COMPAT.set(g.id, toolsLoadGame(g).then(async (gg) => ({ game: gg, tools: await toolsFor(gg) })).catch(() => ({ game: null, tools: [] })));
    const c = await COMPAT.get(g.id);
    return c.tools.length ? c : null;
  }
  /** apre la vista Strumenti gia' sul gioco */
  function openTools(c) {
    TS.game = c.game; TS.tools = []; TS.err = ""; TS.note = "";
    if (typeof closeDetail === "function") closeDetail();
    setView({ type: "tools" });
  }

  async function toolsRefresh() {
    const my = ++TS.seq;
    try {
      // con platform+path il server filtra i compatibili e tiene quelli senza gioco (dump)
      const q = TS.game?.files?.length ? `?platform=${encodeURIComponent(TS.game.platform)}&path=${encodeURIComponent(TS.game.files[0])}` : "";
      const r = await api("/api/tools" + q);
      if (my !== TS.seq) return;
      TS.busy = r.busy;
      TS.tools = r.tools;
    } catch (e) { TS.err = e.message; }
    if (TS.tools.some((x) => x.id === "dump") && !TS.drives) {
      TS.drives = [];
      api("/api/tools/drives").then((r) => { TS.drives = r.drives || []; if (!TS.o.drive && TS.drives[0]) TS.o.drive = TS.drives[0].id; paintCards(); }).catch(() => {});
    }
    paintCards();
  }

  function paintGame() {
    const box = document.getElementById("tl-game");
    if (!box) return;
    const res = document.getElementById("tl-res");
    const list = TLU.pickGames(S.games, TS.q, fold);
    res.innerHTML = TS.q.trim() ? (list.length ? list.map((g) => `<button class="btn tl-pick" type="button" data-tl="game" data-id="${g.id}">${esc(g.title)} <span class="muted small">${esc(platName(g.platform))}</span></button>`).join("")
      : `<p class="muted small">${esc(tt("t.tools.noMatch", "Nessun gioco trovato."))}</p>`) : "";
    box.innerHTML = TS.game
      ? `<p class="tl-sel"><b>${esc(TS.game.title)}</b> <span class="muted small">${esc(platName(TS.game.platform))}</span> <button class="btn" type="button" data-tl="clear">${esc(tt("t.tools.clear", "Cambia gioco"))}</button></p>`
      : `<p class="muted small">${esc(tt("t.tools.pickHint", "Scegli un gioco per vedere gli strumenti adatti."))}</p>`;
  }

  function optsHtml(x) {
    if (x.id === "nup") return `<label class="small">${esc(tt("t.tools.format", "Formato"))} <select class="field" data-tl-opt="format"><option value="nup"${TS.o.format === "nup" ? " selected" : ""}>NUP</option><option value="nsp"${TS.o.format === "nsp" ? " selected" : ""}>NSP</option></select></label>`;
    if (x.id === "patch") return `<button class="btn" type="button" data-tl="pickpatch">${esc(tt("t.tools.pickPatch", "Scegli la patch (.ips / .bps)"))}</button> <span class="small muted">${esc(TS.o.patch || tt("t.tools.noPatch", "Nessuna patch scelta"))}</span>`;
    if (x.id === "dump") {
      const dr = TS.drives || [];
      return (dr.length ? `<label class="small">${esc(tt("t.tools.drive", "Lettore"))} <select class="field" data-tl-opt="drive">${dr.map((d) => `<option value="${esc(d.id)}"${TS.o.drive === d.id ? " selected" : ""}>${esc(d.label)}</option>`).join("")}</select></label>`
        : `<span class="small muted">${esc(tt("t.tools.noDrives", "Nessun lettore ottico trovato."))}</span>`)
        + ` <button class="btn" type="button" data-tl="pickdst">${esc(tt("t.tools.pickDst", "Cartella di destinazione"))}</button> <span class="small muted">${esc(TS.o.dst || "")}</span>`;
    }
    return "";
  }

  function paintCards() {
    const box = document.getElementById("tl-cards");
    if (!box) return;
    const running = TS.job?.status === "running";
    box.innerHTML = TS.tools.map((x) => {
      const miss = TLU.missing(x, TS.game, TS.o), off = running || TS.busy || !!miss;
      const why = miss === "game" ? tt("t.tools.needGame", "Scegli prima un gioco.") : "";
      return `<article class="tl-card" aria-labelledby="tl-h-${x.id}"><h3 id="tl-h-${x.id}">${esc(toolName(x))}${x.binary && !x.binary_ready ? ` <span class="pill">${esc(tt("t.tools.willDownload", "verrà scaricato"))}</span>` : ""}</h3>
        <p class="small muted">${esc(tt(`t.tools.${x.id}.desc`, ""))}</p>
        <div class="tl-opts">${optsHtml(x)}</div>
        <div class="tl-run"><button class="btn primary" type="button" data-tl="run" data-tool="${x.id}"${off ? " disabled" : ""}>${esc(tt("t.tools.run", "Avvia"))}</button>${why ? ` <span class="small muted">${esc(why)}</span>` : ""}</div></article>`;
    }).join("") || `<p class="muted">${esc(tt("t.tools.none", "Nessuno strumento per questo gioco."))}</p>`;
  }

  function resultHtml(j) {
    const r = j.result || {};
    if (j.tool === "verify") {
      const st = { ok: tt("t.tools.verify.ok", "Il file coincide con il dump di riferimento."), mismatch: tt("t.tools.verify.mismatch", "Il file NON coincide con il dump di riferimento."), unknown: tt("t.tools.verify.unknown", "Nessun riferimento trovato per questo file.") }[r.status] || "";
      const h = Object.entries(r.hashes || {}).map(([k, v]) => `<li><b>${esc(k)}</b> <code>${esc(v)}</code></li>`).join("");
      return `<p><b>${esc(st)}</b>${r.name ? ` ${esc(r.name)}` : ""}</p>${h ? `<ul class="small">${h}</ul>` : ""}`;
    }
    if (j.tool === "m3u") return `<p>${esc(tt("t.tools.m3u.done", "Playlist creata ({n} dischi): {m3u}", { n: r.discs?.length ?? r.discs ?? 0, m3u: r.m3u || j.out || "" }))}</p>`;
    if (j.tool === "dump") return `<p>${esc(tt("t.tools.dump.done", "Dump creato: {out}. Il gioco comparirà alla prossima scansione.", { out: j.out || "" }))}</p><button class="btn" type="button" data-tl="scan">${esc(tt("t.tools.scan", "Cerca nuovi giochi"))}</button>`;
    return "";
  }

  function paintJob() {
    const box = document.getElementById("tl-job");
    if (!box) return;
    const j = TS.job, name = j ? toolName({ id: j.tool, name: j.tool }) : "";
    let h = TS.err ? `<p class="tl-err" role="alert">${esc(TS.err)}</p>` : "";
    if (j?.status === "running") {
      h += `<p>${esc(name)} · ${j.pct || 0}%</p><progress max="100" value="${j.pct || 0}" aria-label="${esc(name)}"></progress> <button class="btn" type="button" data-tl="cancel">${esc(tt("t.tools.cancel", "Annulla"))}</button>`;
    } else if (j?.status === "cancelled") h += `<p>${esc(tt("t.tools.cancelled", "Lavoro annullato."))}</p>`;
    else if (j?.status === "error") h += `<p class="tl-err" role="alert">${esc(j.error || "")}</p>`;
    else if (j?.status === "done") {
      h += `<div class="tl-done"><h3>${esc(name)}</h3>${resultHtml(j)}`;
      if (j.adopted) h += `<p>${esc(j.adopted === "trash" ? tt("t.tools.adopted.trash", "Fatto: il gioco usa il nuovo file e il vecchio è nel Cestino.") : tt("t.tools.adopted.keep", "Fatto: il gioco usa il nuovo file, il vecchio è rimasto dov'era."))}</p>`;
      else if (TLU.adoptable(j)) {
        const s = TLU.sizes(j);
        h += `<p class="small">${esc(j.out)}</p>`
          + (s.before != null && s.after != null ? `<p>${esc(tt("t.tools.sizes", "Prima {a} · Dopo {b}", { a: TLU.bytes(s.before), b: TLU.bytes(s.after) }))}</p>` : "")
          + `<div class="tl-actions">` + TLU.actions(j).map((a) => `<button class="btn${a.primary ? " primary" : ""}" type="button" data-tl="adopt" data-act="${a.id}">${esc(a.id === "trash" ? tt("t.tools.adoptTrash", "Usa il nuovo file e sposta il vecchio nel Cestino") : a.id === "keep" ? tt("t.tools.adoptKeep", "Usa il nuovo file, tieni il vecchio") : tt("t.tools.adoptNo", "Non usarlo"))}</button>`).join("") + `</div>`;
      }
      h += `</div>`;
    }
    box.innerHTML = h;
  }

  function poll() {
    clearTimeout(TS.timer);
    TS.timer = setTimeout(async () => {
      if (TS.job?.status !== "running") return;
      try { TS.job = { ...(await api(`/api/tools/job/${TS.job.id}`)), adopted: TS.job.adopted }; }
      catch (e) { TS.err = e.message; TS.job = null; paintJob(); paintCards(); return; }
      paintJob();
      if (TS.job.status === "running") poll(); else toolsRefresh();
    }, 700);
  }

  async function toolsClick(e) {
    const b = e.target.closest("[data-tl]");
    if (!b) return;
    const k = b.dataset.tl;
    TS.err = "";
    try {
      if (k === "game") {
        TS.game = await toolsLoadGame(S.byId.get(+b.dataset.id)); TS.q = ""; document.getElementById("tl-q").value = "";
        paintGame(); await toolsRefresh();
      } else if (k === "clear") { TS.game = null; paintGame(); await toolsRefresh(); }
      else if (k === "pickpatch") { const p = await pickPath("file"); if (p) { TS.o.patch = p; paintCards(); } }
      else if (k === "pickdst") { const p = await pickPath("folder"); if (p) { TS.o.dst = p; paintCards(); } }
      else if (k === "scan") { await api("/api/scan", { body: { mode: "new" } }); toast(tt("t.tools.scanning", "Scansione avviata.")); }
      else if (k === "cancel") { TS.job = { ...(await api(`/api/tools/job/${TS.job.id}/cancel`, { body: {} })) }; paintJob(); }
      else if (k === "run") {
        const x = TS.tools.find((y) => y.id === b.dataset.tool);
        try { TS.job = await api("/api/tools/run", { body: TLU.request(x, TS.game, TS.o) }); } catch (er) { TS.err = er.message; TS.job = null; }
        paintJob(); paintCards();
        if (TS.job) poll();
      } else if (k === "adopt") {
        const a = TLU.actions(TS.job).find((y) => y.id === b.dataset.act);
        if (a.id === "skip") TS.job = null;
        else {
          await api(`/api/tools/job/${TS.job.id}/adopt`, { body: { move_old: a.move_old } });
          TS.job.adopted = a.id;
          if (typeof reload === "function") await reload(true); // la libreria deve vedere il nuovo file
          COMPAT.clear();
          if (TS.game) TS.game = await toolsLoadGame({ id: TS.game.id }).catch(() => null); // i file sono cambiati
          paintGame(); toolsRefresh();
        }
        paintJob();
      }
    } catch (er) { TS.err = er.message; paintJob(); }
  }

  window.renderTools = async function renderTools(pv) {
    pv.innerHTML = `<div class="page tools-page" data-view="tools">
      <div class="page-head"><div><h2>🛠 ${esc(tt("h.title.tools", "Strumenti"))}</h2><p class="muted">${esc(tt("t.tools.intro", "Converti, applica patch, verifica e crea dump. Prima di ogni lavoro si controlla lo spazio libero."))}</p></div></div>
      <label class="small" for="tl-q">${esc(tt("t.tools.pickLabel", "Gioco"))}</label>
      <input class="field" type="search" id="tl-q" autocomplete="off" placeholder="${esc(tt("t.tools.search", "Cerca un gioco della libreria…"))}" value="${esc(TS.q)}">
      <div id="tl-res" class="tl-res"></div><div id="tl-game"></div>
      <div id="tl-job" class="tl-job" aria-live="polite"></div>
      <div id="tl-cards" class="tl-cards"></div></div>`;
    pv.onclick = toolsClick;
    pv.oninput = (e) => { if (e.target.id === "tl-q") { TS.q = e.target.value; paintGame(); } };
    pv.onchange = (e) => { const k = e.target.dataset.tlOpt; if (k) TS.o[k] = e.target.value; };
    paintGame(); paintJob();
    await toolsRefresh();
    if (TS.job?.status === "running") poll();
  };

  /* dettaglio gioco: pulsante «Strumenti» solo se c'e' qualcosa di compatibile (come dlMagnetButton, arriva dopo la rete) */
  window.toolsDetailButton = async function (d) {
    const acts = document.querySelector("#detail .d-actions");
    const c = acts && await toolsCompat(d);
    if (!c || !document.querySelector("#detail .d-actions") || document.getElementById("d-tools")) return;
    const b = document.createElement("button");
    b.className = "btn"; b.id = "d-tools"; b.type = "button";
    b.textContent = "🛠 " + tt("t.tools.btn", "Strumenti");
    b.onclick = () => openTools(c);
    acts.appendChild(b);
  };

  /* menu contestuale: la voce si aggiunge se il gioco ha strumenti compatibili */
  window.toolsCtxRow = async function (g, menu, rows) {
    const c = await toolsCompat(g);
    if (!c || !menu.isConnected) return;
    rows.push({ l: "🛠 " + tt("t.tools.btn", "Strumenti"), f: () => openTools(c) });
    const el = document.createElement("div");
    el.className = "ci"; el.dataset.i = rows.length - 1; el.textContent = rows[rows.length - 1].l;
    menu.appendChild(el);
  };
}
