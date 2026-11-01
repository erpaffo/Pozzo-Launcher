"use strict";
/* Pozzo Launcher - frontend: pagine: giochi gratis, port e app PC. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ---- pagina: giochi gratis */
const FREE_F = { console: store.get("freeConsole", ""), kind: "" };
const remoteImg = (u) => (u ? `/remote-img?u=${encodeURIComponent(u)}` : "");
async function renderFree(pv, force = false) {
  pv.innerHTML = `<div class="page"><p class="muted">Cerco i giochi gratis…</p></div>`;
  let d;
  try { d = await api(`/api/free${force ? "?force=1" : ""}`); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  if (d.first) d.items.forEach((i) => { i.new = false; }); // prima apertura: non sono tutti «nuovi»
  freeBadge(d);
  // prima quelli ancora da prendere, poi chi scade prima; senza scadenza in fondo
  const endOf = (i) => (i.end ? Date.parse(i.end.replace(" ", "T")) || Infinity : Infinity);
  d.items.sort((a, b) => (a.claimed || a.owned) - (b.claimed || b.owned) || endOf(a) - endOf(b));
  api("/api/free/mark", { body: { seen: true } }).catch(() => {}); // da ora non sono piu' nuovi (l'etichetta resta in questa pagina)
  const draw = () => {
    const items = d.items.filter((i) => (!FREE_F.console || i.console === FREE_F.console) && (!FREE_F.kind || i.kind === FREE_F.kind));
    const kinds = [...new Set(d.items.map((i) => i.kind))];
    const cons = [...new Set(d.items.map((i) => i.console))];
    const chip = (k, v, l) => `<button class="pchip${FREE_F[k] === v ? " on" : ""}" data-f="${k}" data-v="${esc(v)}">${esc(l)}</button>`;
    pv.innerHTML = `<div class="page">
      <div class="page-head"><div><h2>🎁 Giochi gratis adesso</h2>
        <p class="muted small">Da tenere, inclusi negli abbonamenti, weekend gratuiti e DLC gratis.
          Fonti: <a href="#" data-open="https://www.allkeyshop.com/blog/daily-game-deals/">allkeyshop.com</a> ·
          <a href="#" data-open="https://www.gamerpower.com/">GamerPower</a> ·
          <a href="#" data-open="https://store.steampowered.com/search/?specials=1&maxprice=free">Steam</a> ·
          <a href="#" data-open="https://github.com/eikowagenknecht/lootscraper">LootScraper</a> (Prime)${d.time ? ` · aggiornato ${new Date(d.time * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })}` : ""}</p>
        ${d.errors.length ? `<p class="warn small">⚠ ${d.errors.map((e) => esc(e.split(":")[0])).join(", ")} non ha risposto: ${d.stale ? "elenco dell'ultima volta" : "elenco parziale"}.</p>` : ""}</div>
        <button class="btn" id="free-refresh">↻ Aggiorna</button></div>
      <div class="pchips">${chip("console", "", "Tutte")}${cons.map((c) => chip("console", c, ({ pc: "🖥 PC", playstation: "PlayStation", xbox: "Xbox", switch: "Switch" })[c] || c)).join("")}
        <span class="sep"></span>${chip("kind", "", "Ogni offerta")}${kinds.map((k) => chip("kind", k, FREE_KIND[k] || k)).join("")}</div>
      <div class="free-grid" id="free-rows"></div></div>`;
    // schede come in .free-grid (minmax 170px, gap 16px): si disegnano solo quelle visibili
    vlist(pv, $("#free-rows", pv), items, (i) => `<div class="free-card${i.owned || i.claimed ? " owned" : ""}" data-n="${d.items.indexOf(i)}">
        <div class="fc-cover">${i.cover ? `<img loading="lazy" src="${remoteImg(i.cover)}" alt="" onerror="this.remove()">` : ""}
          <span class="fc-kind k-${fold(i.kind).replace(/[^a-z]+/g, "")}">${esc(FREE_KIND[i.kind] || i.kind)}</span>
          ${i.drm && i.drm !== "none" ? `<img class="fc-drm" src="/icons/store/${esc(({ amazon: "amazon", epic: "epic", steam: "steam", gog: "gog", battlenet: "battlenet" })[i.drm] || "manual")}" alt="" onerror="this.remove()">` : ""}
          ${i.owned ? `<span class="fc-owned">✓ Già tuo</span>` : i.claimed ? `<span class="fc-owned">✓ Riscattato</span>` : i.new ? `<span class="fc-new">Nuovo</span>` : ""}
          ${i.wished && !i.owned ? `<span class="fc-wish" title="Nella tua lista desideri">♡</span>` : ""}</div>
        <div class="fc-info"><b title="${esc(i.full_title || i.title)}">${esc(i.title)}</b>
          <span class="muted small">${esc([({ pc: "PC", playstation: "PlayStation", xbox: "Xbox" })[i.console] || i.console,
            i.end ? "fino al " + new Date(i.end.replace(" ", "T")).toLocaleDateString("it") : "", i.worth ? "valore " + i.worth : ""].filter(Boolean).join(" · "))}</span>
          <span class="fc-btns"><button class="btn primary fc-open" data-n="${d.items.indexOf(i)}">Apri ↗</button>
          ${i.owned ? "" : `<button class="btn fc-claim" data-n="${d.items.indexOf(i)}" title="Segna come preso (o togli il segno)">${i.claimed ? "↺" : "✓ Preso"}</button>`}</span></div></div>`, { cols: () => Math.max(1, Math.floor(($("#free-rows", pv).clientWidth + 16) / (170 + 16))), gap: 16, rowClass: "free-grid" });
    if (!items.length) $("#free-rows", pv).innerHTML = `<p class="muted">Nessun gioco gratis con questi filtri.</p>`;
  };
  draw();
  pv.onclick = (e) => {
    const f = e.target.closest("[data-f]");
    if (f) { FREE_F[f.dataset.f] = f.dataset.v; if (f.dataset.f === "console") store.set("freeConsole", f.dataset.v); draw(); return; }
    if (e.target.id === "free-refresh") { renderFree(pv, true); return; }
    const o = e.target.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    const cl = e.target.closest(".fc-claim");
    if (cl) {
      const it = d.items[+cl.dataset.n];
      api("/api/free/mark", { body: { claim: it.id, value: !it.claimed } }).then(() => { it.claimed = !it.claimed; it.new = false; freeBadge(d); draw(); })
        .catch((err) => toast(err.message, true));
      return;
    }
    const c = e.target.closest(".fc-open, .free-card");
    if (c) api("/api/open", { body: { url: d.items[+c.dataset.n].url } }).then(() => toast("Apro la pagina nel browser"));
  };
}
/** Numero nella barra laterale: le offerte nuove (🆕), altrimenti quante sono ancora da prendere. */
function freeBadge(d) {
  const todo = d.items.filter((i) => !i.upcoming && !i.owned && !i.claimed).length;
  $("#cnt-free").textContent = d.new ? `🆕 ${d.new}` : todo || "";
}
const FREE_KIND = { "Free to keep": "Da tenere", "Free with Prime": "Con Prime", "Free with PS+": "Con PS Plus", Gamepass: "Game Pass",
  "Free DLC": "DLC gratis", "Free weekend": "Weekend gratis", "Free to play": "Free to play", "Play for free": "Gioca gratis", "In arrivo": "In arrivo" };

/* ---- pagina: port e app PC (port, giochi ed emulatori dal catalogo di Quiver Launcher) */
const PORTS_F = { console: store.get("portsConsole", ""), type: store.get("portsType", ""), mine: "", q: "", open: null };
// tipi del catalogo Quiver: quasi tutte sono ricompilazioni (port) ma ci sono anche giochi ed emulatori
const WINDOW_MODES = { "": "Chiedi ogni volta", windowed: "🗗 Finestra", borderless: "▭ Senza bordi", fullscreen: "⛶ Schermo intero" };
const PORT_KIND = { port: "🕹 Port", game: "🎮 Gioco", emulator: "🖥 Emulatore", tool: "🔧 Strumento" };
/** Il catalogo si apre subito dalla copia salvata e si aggiorna in background: a fine aggiornamento la pagina si ridisegna. */
async function followPortsRefresh(pv) {
  if (PORTS_F.following) return;
  PORTS_F.following = true;
  try {
    let r;
    do { await new Promise((ok) => setTimeout(ok, 1500)); r = await api("/api/ports/refreshing"); } while (r.refreshing);
  } catch { return; } finally { PORTS_F.following = false; }
  if (S.view.type === "ports" && pv.isConnected && !PORTS_F.open) { S.ports = null; renderPorts(pv); }
}

async function renderPorts(pv, force = false) {
  if (PORTS_F.open) return renderPort(pv, PORTS_F.open);
  pv.innerHTML = `<div class="page"><p class="muted">Leggo il catalogo dei port…</p></div>`;
  let d;
  try { d = await api(`/api/ports${force ? "?force=1" : ""}`); } catch (e) { pv.innerHTML = `<div class="page"><p>${esc(e.message)}</p></div>`; return; }
  S.ports = d;
  portsBadge(d);
  if (d.refreshing) followPortsRefresh(pv);
  const rank = (i) => (i.installed?.update ? 0 : i.installed ? 1 : i.roms.length ? 2 : 3);
  d.items.sort((a, b) => rank(a) - rank(b) || b.recommended - a.recommended || collator.compare(a.name, b.name));
  const cons = Object.entries(d.consoles).map(([id, name]) => [id, name, d.items.filter((i) => i.consoles.includes(id)).length])
    .sort((a, b) => b[2] - a[2]);
  const kinds = Object.entries(PORT_KIND).map(([id, label]) => [id, label, d.items.filter((i) => (i.type || "port") === id).length])
    .filter((k) => k[2]);
  const upd = d.items.filter((i) => i.installed?.update).length;
  const chip = (k, v, l) => `<button class="pchip${PORTS_F[k] === v ? " on" : ""}" data-f="${k}" data-v="${esc(v)}">${esc(l)}</button>`;
  pv.innerHTML = `<div class="page">
    <div class="page-head"><div><h2>🕹 Port e app</h2>
      <p class="muted small">Giochi console ricompilati o ricostruiti per Windows senza emulatore, più i giochi e gli emulatori
        del catalogo che si distribuiscono con le release di GitHub/GitLab: li installa e li aggiorna il launcher, senza aprirne altri.
        Quasi tutti i port chiedono la tua ROM originale: quelli segnati «🎮 ROM» li hai già nella libreria. Catalogo:
        <a href="#" data-open="https://github.com/tgeorgiadis/quiver-launcher">Quiver Launcher</a>${d.time ? ` · aggiornato ${new Date(d.time * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })}` : ""}</p>
      ${d.error ? `<p class="warn small">⚠ Il catalogo non ha risposto (${esc(d.error)}): ${d.stale ? "elenco dell'ultima volta" : "nessun elenco salvato"}.</p>` : ""}</div>
      <span class="fc-btns pt-tools">${upd ? `<button class="btn primary" id="pt-update-all">⬆ Aggiorna tutto (${upd})</button>` : ""}<button class="btn" id="pt-add">＋ Aggiungi a mano</button><button class="btn" id="pt-set">⚙</button>
        <button class="btn" id="pt-refresh">↻ Aggiorna</button></span></div>
    <div id="pt-form"></div>
    <div class="pchips"><input id="pt-q" class="field" placeholder="Cerca…" value="${esc(PORTS_F.q)}" autocomplete="off">
      ${chip("mine", "", "Tutti")}${chip("mine", "rom", "🎮 Ho la ROM")}${chip("mine", "inst", "✓ Installati")}${chip("mine", "upd", "⬆ Da aggiornare")}
      ${kinds.length > 1 ? `<span class="sep"></span>${chip("type", "", "Ogni tipo")}${kinds.map(([id, label, n]) => chip("type", id, `${label} (${n})`)).join("")}` : ""}
      <span class="sep"></span>${chip("console", "", "Ogni console")}${cons.map(([id, name, n]) => chip("console", id, `${name} (${n})`)).join("")}</div>
    <div class="free-grid" id="pt-grid"></div></div>`;
  const draw = () => {
    const q = fold(PORTS_F.q);
    const items = d.items.filter((i) => (!PORTS_F.console || i.consoles.includes(PORTS_F.console))
      && (!PORTS_F.type || (i.type || "port") === PORTS_F.type)
      && (!PORTS_F.mine || (PORTS_F.mine === "rom" ? i.roms.length : PORTS_F.mine === "inst" ? i.installed : i.installed?.update))
      && (!q || fold(`${i.name} ${i.project} ${i.developer} ${i.tags.join(" ")}`).includes(q)));
    vlist(pv, $("#pt-grid", pv), items, (i) => `<div class="free-card" data-slug="${esc(i.slug)}">
      <div class="fc-cover">${i.cover ? `<img loading="lazy" src="${remoteImg(gridThumb(i.cover))}" data-full="${esc(remoteImg(i.cover))}" alt=""
          onerror="if (this.dataset.full && this.src.indexOf('thumb') > 0) { this.src = this.dataset.full; this.dataset.full = '' } else this.remove()">` : ""}
        <span class="fc-kind">${esc((i.type && i.type !== "port" ? [PORT_KIND[i.type] || i.type] : []).concat(i.consoles.map((c) => d.consoles[c] || c)).join(" · ") || PORT_KIND.port)}</span>
        ${i.installed?.update ? `<span class="fc-new">⬆ ${esc(i.installed.latest)}</span>` : i.installed ? `<span class="fc-owned">✓ Installato</span>` : ""}
        ${i.roms.length ? `<span class="fc-wish pt-rom" title="Hai la ROM: ${esc(i.roms.map((r) => r.title).join(", "))}">🎮 ROM</span>`
          : i.in_store?.length ? `<span class="fc-wish pt-rom" title="ROM non posseduta, scaricabile dagli store">🛒 ROM negli store</span>` : ""}</div>
      <div class="fc-info"><b title="${esc(i.name)}">${esc(i.name)}</b>
        <span class="muted small">${esc([i.project !== i.name ? i.project : "", i.developer, i.installed?.version || i.version].filter(Boolean).join(" · "))}</span></div></div>`, { cols: () => Math.max(1, Math.floor(($("#pt-grid", pv).clientWidth + 16) / (170 + 16))), gap: 16, rowClass: "free-grid" });
    if (!items.length) $("#pt-grid", pv).innerHTML = `<p class="muted">Nessun port con questi filtri.</p>`;
  };
  draw();
  $("#pt-q", pv).oninput = (e) => { PORTS_F.q = e.target.value; draw(); };
  pv.onclick = async (e) => {
    const f = e.target.closest("[data-f]");
    if (f) {
      PORTS_F[f.dataset.f] = f.dataset.v;
      if (f.dataset.f === "console") store.set("portsConsole", f.dataset.v);
      if (f.dataset.f === "type") store.set("portsType", f.dataset.v);
      pv.querySelectorAll(`[data-f="${f.dataset.f}"]`).forEach((b) => b.classList.toggle("on", b === f));
      return draw();
    }
    const o = e.target.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    if (e.target.id === "pt-update-all") {
      // un'installazione alla volta: il server ne accetta una sola, qui si aspetta la fine di ciascuna
      const todo = d.items.filter((i) => i.installed?.update);
      if (!todo.length) return;
      $("#pt-form", pv).innerHTML = `<div class="d-note"><p class="small" id="pt-all-msg"></p></div>`;
      e.target.disabled = true;
      for (let n = 0; n < todo.length; n++) {
        const msg = $("#pt-all-msg", pv);
        if (msg) msg.textContent = `Aggiorno ${n + 1}/${todo.length}: ${todo[n].name}…`;
        try { await api(`/api/ports/${encodeURIComponent(todo[n].slug)}/update`, { body: { slug: todo[n].slug } }); }
        catch (err) { toast(`${todo[n].name}: ${err.message}`, true); continue; }
        let j;
        do {
          await new Promise((ok) => setTimeout(ok, 1000));
          j = await api("/api/ports/job").catch(() => ({ status: "done" }));
        } while (j.status === "running");
        if (j.status === "error") toast(`${todo[n].name}: ${j.log.slice(-1)[0] || "aggiornamento non riuscito"}`, true);
      }
      toast("Aggiornamento finito");
      pollStores(true);
      S.ports = null;
      return renderPorts(pv);
    }
    if (e.target.id === "pt-refresh") return renderPorts(pv, true);
    if (e.target.id === "pt-set") {
      $("#pt-form", pv).innerHTML = `<div class="d-note"><p class="small">Cartella dei port (vuota = predefinita):</p>
        <input class="field" id="pt-dir" value="${esc(d.dir)}" style="width:100%">
        <p class="small">Token GitHub (facoltativo: senza, GitHub permette 60 richieste all'ora) ${d.token ? "· <b>impostato</b>" : ""}</p>
        <input class="field" id="pt-tok" type="password" placeholder="${d.token ? "lascia vuoto per non cambiarlo" : "ghp_…"}" style="width:100%">
        <p class="small">Cartella breve per i port che compilano sul posto (vuota = una scrivibile fra <code>C:\\PozzoPorts</code>,
          le altre unità e <code>Public</code>):</p>
        <input class="field" id="pt-short-dir" value="${esc(d.short_dir || "")}" placeholder="automatica" style="width:100%">
        <label class="small" style="display:flex;gap:6px;align-items:center;margin-top:8px">
          <input type="checkbox" id="pt-auto"${d.auto ? " checked" : ""}> Aggiorna da solo le app installate: la patch la mette il launcher,
          senza aprire quello del gioco</label>
        <p><button class="btn primary" id="pt-set-save">Salva</button></p></div>`;
      return;
    }
    if (e.target.id === "pt-set-save") {
      const body = { dir: $("#pt-dir", pv).value, auto: $("#pt-auto", pv).checked, short_dir: $("#pt-short-dir", pv).value };

      if ($("#pt-tok", pv).value) body.token = $("#pt-tok", pv).value;
      try { await api("/api/ports-settings", { body }); } catch (err) { return toast(err.message, true); }
      toast("Impostazioni dei port salvate");
      return renderPorts(pv);
    }
    if (e.target.id === "pt-add") {
      $("#pt-form", pv).innerHTML = `<div class="d-note"><p class="small">Un port o un'app che non sono nel catalogo: repository
        (<code>utente/progetto</code>, anche <code>gitlab:utente/progetto</code> o un indirizzo completo; si installa l'ultima release)
        <b>oppure</b> una cartella già scaricata con il suo .exe.</p>
        <input class="field" id="pt-repo" placeholder="utente/progetto" style="width:100%">
        <input class="field" id="pt-folder" placeholder="oppure: C:\\Giochi\\MioPort" style="width:100%">
        <input class="field" id="pt-name" placeholder="Nome (facoltativo)">
        <select class="field" id="pt-con"><option value="">Console originale…</option>${cons.map(([id, name]) => `<option value="${esc(id)}">${esc(name)}</option>`).join("")}</select>
        <p><button class="btn primary" id="pt-add-go">Aggiungi</button></p></div>`;
      return;
    }
    if (e.target.id === "pt-add-go") {
      const body = { repo: $("#pt-repo", pv).value, folder: $("#pt-folder", pv).value, name: $("#pt-name", pv).value, console: $("#pt-con", pv).value };
      let r;
      try { r = await api("/api/ports/manual", { body }); } catch (err) { return toast(err.message, true); }
      if (r.status === "running") { PORTS_F.open = null; return followPortJob(pv); }
      toast(`${r.name} aggiunto`);
      pollStores(true);
      return renderPorts(pv);
    }
    const c = e.target.closest(".free-card");
    if (c) { PORTS_F.open = c.dataset.slug; renderPort(pv, c.dataset.slug); }
  };
}

/** Copertine di SteamGridDB: la miniatura (~50 KB) invece del PNG originale (~700 KB). */
const gridThumb = (u) => u.replace(/^(https:\/\/cdn2\.steamgriddb\.com)\/grid\/(\w+)\.\w+$/, "$1/thumb/$2.jpg");

function portsBadge(d) {
  const n = d.items.filter((i) => i.installed?.update).length;
  $("#cnt-ports").textContent = n ? `⬆ ${n}` : "";
}

async function renderPort(pv, slug) {
  if (!S.ports) { try { S.ports = await api("/api/ports"); } catch (e) { return toast(e.message, true); } }
  const i = S.ports.items.find((x) => x.slug === slug);
  if (!i) { PORTS_F.open = null; return renderPorts(pv); }
  const inst = i.installed;
  let m = null;
  if (inst) { try { m = await api(`/api/ports/${encodeURIComponent(slug)}`); } catch { /* cartella sparita: si vede come non installato */ } }
  const cname = (c) => S.ports.consoles[c] || c;
  const romFile = (r) => r.file.split(/[\\/]/).pop();
  pv.innerHTML = `<div class="page port-page">
    <p><button class="btn" id="pt-back">← Port e app</button></p>
    ${i.hero ? `<div class="pt-hero"><img src="${remoteImg(i.hero)}" alt="" onerror="this.parentNode.remove()"></div>` : ""}
    <h2>${esc(i.name)}</h2>
    <p class="muted">${esc([i.type && i.type !== "port" ? PORT_KIND[i.type] : "", i.project !== i.name ? i.project : "", i.consoles.map(cname).join(", "), i.developer, inst ? `installato ${inst.version}${inst.sha256 ? " ✓ verificato" : ""}` : i.version ? `ultima versione ${i.version}` : ""].filter(Boolean).join(" · "))}</p>
    ${i.broken ? `<p class="warn small">⚠ ${i.broken} giocator${i.broken === 1 ? "e lo segnala" : "i lo segnalano"} come non funzionante.</p>` : ""}
    <p>${esc(i.description)}</p>
    <div class="d-actions">
      ${!inst ? `<button class="btn primary" id="pt-install">⬇ Installa</button>`
        : `<button class="btn primary" id="pt-play">▶ Gioca</button>${inst.game_id ? `<button class="btn" id="pt-lib">Scheda nella libreria</button>
             <button class="btn" id="pt-folder">📁 Cartella</button>` : ""}
           ${inst.update ? `<button class="btn primary" id="pt-update">⬆ Aggiorna a ${esc(inst.latest)}</button>
             <button class="btn" id="pt-skip" title="Non segnalare più questa versione">Salta questa versione</button>` : ""}
           ${inst.repository ? `<button class="btn" data-open="https://github.com/${esc(inst.repository)}">Progetto ↗</button>` : ""}
           <button class="btn" id="pt-remove">🗑 Disinstalla</button>`}
    </div>
    ${m && m.path ? `<div class="d-note"><p class="warn small">⚠ Percorso troppo lungo per questo port: ${m.path.length} caratteri,
      il massimo è ${m.path.limit}. Il launcher di questo port compila il gioco dentro la sua cartella, e oltre quel limite Windows
      non riesce ad aprire i file: il gioco non parte.</p>
      <p class="small">${m.path.short ? `Posso spostarlo in <code>${esc(m.path.short)}</code> (percorso più corto) copiando anche salvataggi
        e impostazioni; la cartella di adesso resta come copia di sicurezza.` : `Scegli una cartella dei port più corta (⚙ qui sopra):
        nemmeno la cartella breve automatica basta.`}</p>
      ${m.path.short ? `<p><button class="btn primary" id="pt-short">📦 Sposta in una cartella breve</button></p>` : ""}</div>` : ""}
    <div id="pt-job"></div>
    ${m && m.candidates.length > 1 ? `<div class="d-h">Eseguibile da avviare</div>
      <select class="field" id="pt-exe">${m.candidates.map((x) => `<option${x === m.exe ? " selected" : ""}>${esc(x)}</option>`).join("")}</select>` : ""}
    ${m ? `<div class="d-h">Finestra all'avvio</div>
      <select class="field" id="pt-window">${Object.entries(WINDOW_MODES).map(([k, l]) => `<option value="${k}"${k === (m.window || "") ? " selected" : ""}>${l}</option>`).join("")}</select>` : ""}
    ${i.type === "port" || i.roms.length || i.in_store?.length ? `<div class="d-h">ROM originale</div>
    ${i.roms.length ? i.roms.map((r) => `<div class="sv-row"><span>🎮 ${esc(r.title)}</span><span class="muted small" title="${esc(r.file)}">${esc(romFile(r))}</span>
        <button class="btn" data-game="${r.id}">Apri</button></div>`).join("")
      : i.in_store?.length ? `<p class="warn small">Non hai la ROM originale, ma è disponibile negli store: scaricala e poi torna qui.</p>`
        + i.in_store.map((r) => `<div class="sv-row"><span>🛒 ${esc(r.title)}</span><span class="muted small">${esc(platName(r.platform))}</span>
        <button class="btn primary" data-game="${r.id}">⬇ Scarica la ROM</button></div>`).join("")
      : `<p class="muted small">Non hai la ROM di questo gioco nella libreria. Il port ha bisogno della tua copia originale.</p>`}` : ""}
    ${m && m.setup.length ? m.setup.map((s) => `<div class="sv-row"><span>${esc(s.label)} <span class="muted small">→ ${esc(s.destination)}${s.accepted.filter(Boolean).length ? ` (${esc(s.accepted.filter(Boolean).join(", "))})` : ""}</span></span>
        ${s.present ? `<span class="muted small">✓ presente</span>` : ""}
        ${i.roms.length ? `<button class="btn" data-setup="${esc(s.id)}">${s.present ? "Ricopia" : "Copia dalla libreria"}</button>` : ""}</div>`).join("")
      : inst && i.roms.length ? `<p class="muted small">Il port chiede la ROM al primo avvio: scegli il file «${esc(romFile(i.roms[0]))}»
        (<a href="#" data-game-folder="${i.roms[0].id}">mostra nella cartella</a>).</p>` : ""}
    ${m ? `<p class="muted small">${m.user_files} file tuoi (salvataggi, configurazione, mod) nella cartella: restano negli aggiornamenti
      e si copiano con i salvataggi dalla scheda del gioco.</p>` : ""}
    ${m && m.mods ? `<div class="d-h">Mod</div><div id="pt-mods"><button class="btn" id="pt-mods-load">Mostra le mod</button></div>` : ""}
  </div>`;
  pv.onclick = async (e) => {
    const t = e.target, enc = encodeURIComponent(slug);
    const o = t.closest("[data-open]");
    if (o) { e.preventDefault(); api("/api/open", { body: { url: o.dataset.open } }); return; }
    if (t.id === "pt-back") { PORTS_F.open = null; return renderPorts(pv); }
    if (t.id === "pt-install" || t.id === "pt-update") {
      try { await api(t.id === "pt-install" ? "/api/ports/install" : `/api/ports/${enc}/update`, { body: { slug } }); } catch (err) { return toast(err.message, true); }
      return followPortJob(pv);
    }
    if (t.id === "pt-play") {
      if (inst.game_id) { await play(inst.game_id); return renderPort(pv, slug); }
      try {
        let r = await api(`/api/ports/${enc}/play`, { body: {} });
        if (r.ask) { const w = await askWindow(); if (!w) return; r = await api(`/api/ports/${enc}/play`, { body: w }); }
        pollRunning();
      } catch (err) { toast(err.message, true); }
      return renderPort(pv, slug); // «ricorda» cambia il menu della modalità
    }
    if (t.id === "pt-lib") return openDetail(inst.game_id);
    if (t.id === "pt-folder") return api(`/api/game/${inst.game_id}/open-folder`, { body: {} }).catch((err) => toast(err.message, true));
    if (t.id === "pt-skip") {
      await api(`/api/ports/${enc}/skip`, { body: { version: inst.latest } }).catch((err) => toast(err.message, true));
      S.ports = null;
      return renderPort(pv, slug);
    }
    if (t.id === "pt-short") {
      const p = m.path;
      if (!confirm(`Sposto «${i.name}» in:\n${p.short}\n\nPerché: questo port compila il gioco dentro la sua cartella, e Windows si ferma `
        + `oltre ${p.limit} caratteri di percorso (adesso sono ${p.length}), quindi il gioco non partirebbe. `
        + `Salvataggi e impostazioni vengono copiati; la cartella di adesso resta come copia di sicurezza.\n\nProcedo?`)) return;
      t.disabled = true;
      try { await api(`/api/ports/${enc}/short-path`, { body: {} }); } catch (err) { t.disabled = false; return toast(err.message, true); }
      return followPortJob(pv, "Port spostato nella cartella breve: ora il gioco si avvia");
    }
    if (t.id === "pt-remove") {
      if (!confirm(`Disinstallare «${i.name}»? La cartella va nel Cestino (salvataggi compresi: copiali prima se ti servono).`)) return;
      try { await api(`/api/ports/${enc}/uninstall`, { body: {} }); } catch (err) { return toast(err.message, true); }
      toast(`${i.name} disinstallato`);
      pollStores(true);
      S.ports = null;
      return renderPort(pv, slug);
    }
    if (t.dataset.game) return openDetail(+t.dataset.game);
    if (t.dataset.gameFolder) { e.preventDefault(); return api(`/api/game/${t.dataset.gameFolder}/open-folder`, { body: {} }).catch((err) => toast(err.message, true)); }
    if (t.dataset.setup) {
      t.disabled = true;
      try { const r = await api(`/api/ports/${enc}/rom`, { body: { id: t.dataset.setup } }); toast(`ROM copiata: ${r.path}`); }
      catch (err) { t.disabled = false; return toast(err.message, true); }
      return renderPort(pv, slug);
    }
    if (t.id === "pt-mods-load" || t.dataset.mod || t.dataset.modDel) return portMods(pv, slug, t);
  };
  pv.onchange = async (e) => {
    if (e.target.id === "pt-window") {
      try { await api(`/api/ports/${encodeURIComponent(slug)}/window`, { body: { window: e.target.value } }); } catch (err) { return toast(err.message, true); }
      return toast("Modalità di avvio salvata");
    }
    if (e.target.id !== "pt-exe") return;
    try { await api(`/api/ports/${encodeURIComponent(slug)}/exe`, { body: { exe: e.target.value } }); } catch (err) { return toast(err.message, true); }
    toast("Eseguibile salvato");
    pollStores(true);
  };
  const j = await api("/api/ports/job").catch(() => null);
  if (j && j.status === "running" && j.slug === slug) followPortJob(pv);
}

async function portMods(pv, slug, t) {
  const enc = encodeURIComponent(slug), box = $("#pt-mods", pv);
  try {
    if (t.dataset.mod) { t.disabled = true; await api(`/api/ports/${enc}/mods`, { body: { id: t.dataset.mod } }); toast("Mod installata"); }
    if (t.dataset.modDel) { await api(`/api/ports/${enc}/mods/${encodeURIComponent(t.dataset.modDel)}`, { method: "DELETE" }); toast("Mod rimossa"); }
  } catch (err) { t.disabled = false; return toast(err.message, true); }
  box.innerHTML = `<p class="muted">Carico le mod…</p>`;
  let r;
  try { r = await api(`/api/ports/${enc}/mods`); } catch (err) { box.innerHTML = `<p class="muted">${esc(err.message)}</p>`; return; }
  box.innerHTML = `${r.links.map((l) => `<a href="#" class="small" data-open="${esc(l.url)}">${esc(l.provider)} ↗</a>`).join(" · ")}
    ${r.items.filter((x) => !x.nsfw).slice(0, 60).map((x) => `<div class="sv-row"><span><b>${esc(x.name)}</b> <span class="muted small">${esc(x.owner)} · ${esc(x.version)}</span><br>
      <span class="muted small">${esc(x.description)}</span></span>
      ${r.installed[x.id] ? `<button class="btn" data-mod-del="${esc(x.id)}">Rimuovi</button>` : `<button class="btn" data-mod="${esc(x.id)}">Installa</button>`}</div>`).join("")
      || `<p class="muted small">Nessuna mod scaricabile da qui: usa i link sopra.</p>`}`;
}

/** Avanzamento di installazione/aggiornamento; alla fine la libreria si aggiorna con il port. */
async function followPortJob(pv, done = "Port installato: lo aggiungo alla libreria") {
  let j;
  do {
    try { j = await api("/api/ports/job"); } catch { return; }
    const box = $("#pt-job", pv);
    if (box) {
      const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
      box.innerHTML = `<p class="small">${j.status === "running" ? `⏳ ${j.total ? `${pct}% · ${fmtSize(j.done)} di ${fmtSize(j.total)}` : j.done ? fmtSize(j.done) : ""}` : ""}</p>
        <pre class="log">${esc(j.log.slice(-8).join("\n"))}</pre>`;
    }
    if (j.status === "running") await new Promise((r) => setTimeout(r, 1000));
  } while (j.status === "running");
  if (j.status === "error") return toast(j.log[j.log.length - 1] || "Installazione non riuscita", true);
  toast(done);

  pollStores(true);
  S.ports = null;
  if (PORTS_F.open && S.view.type === "ports") renderPort(pv, PORTS_F.open);
  else if (S.view.type === "ports") renderPorts(pv);
}

/** Prezzo dei negozi di key (GG.deals), con lo sconto rispetto al prezzo pieno (es. 60 € su Steam -> 9,50 € = -84%). */
function keyPrice(w, money, full) {
  const cut = full ? Math.round((1 - w.key_price / full) * 100) : 0;
  return `<span class="wl-key" title="Negozi di key${w.key_low != null ? ` · minimo storico ${money(w.key_low, w.currency)}` : ""}">🔑 `
    + `${cut > 0 ? `<span class="cut">-${cut}%</span>` : ""}<b>${money(w.key_price, w.currency)}</b>`
    + `${w.key_low != null ? `<span class="muted small"> · min. key ${money(w.key_low, w.currency)}</span>` : ""}</span>`;
}

/** Grafichino dello storico (un punto al giorno: il prezzo piu' basso tra store e negozi di key). */
function priceSpark(hist, money, cur) {
  const pts = (hist || []).map(([d, p, k]) => [d, Math.min(...[p, k].filter((v) => v != null))]).filter(([, v]) => isFinite(v));
  if (pts.length < 2) return "";
  const vs = pts.map(([, v]) => v), lo = Math.min(...vs), hi = Math.max(...vs), W = 90, H = 22;
  const xy = pts.map(([, v], i) => `${(i / (pts.length - 1) * W).toFixed(1)},${(hi === lo ? H / 2 : H - 2 - (v - lo) / (hi - lo) * (H - 4)).toFixed(1)}`);
  return `<span class="wl-spark" title="Da ${pts[0][0]}: minimo ${money(lo, cur)}, massimo ${money(hi, cur)}">`
    + `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><polyline points="${xy.join(" ")}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`
    + ` min ${money(lo, cur)}</span>`;
}
