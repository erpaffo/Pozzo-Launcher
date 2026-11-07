/* Emulatori (extra): sotto ogni console di #emu-table mostra l'emulatore consigliato, lo stato dei BIOS e
   l'installazione «un clic». Si aggancia da solo alle righe tr[data-p] (la tabella viene ridisegnata spesso). */
(function (global) {
  "use strict";
  // t() viene da i18n.js nel browser; nei test in node manca e resta il testo italiano
  const trad = (k, it, p) => (global.t ? global.t(k, p) : it.replace(/\{(\w+)\}/g, (m, n) => (p && n in p ? p[n] : m)));

  const STATI = {
    ok: { cls: "xe-ok", icona: "✓", testo: () => trad("k.emu.st.ok", "trovato") },
    missing: { cls: "xe-bad", icona: "✗", testo: () => trad("k.emu.st.missing", "mancante") },
    mismatch: { cls: "xe-bad", icona: "✗", testo: () => trad("k.emu.st.mismatch", "non corrisponde") },
    unknown: { cls: "xe-warn", icona: "?", testo: () => trad("k.emu.st.unknown", "hash non riconosciuto") },
  };

  // found/ok/sha1 arrivano da bios.check; mismatch/status espliciti (se il backend li aggiunge) hanno la precedenza
  function statoBios(it) {
    if (it.status === "mismatch" || it.mismatch === true) return "mismatch";
    if (!it.found) return "missing";
    if (it.ok) return "ok";
    return it.sha1 ? "unknown" : "mismatch";
  }

  function creaComponente(opt) {
    opt = opt || {};
    const doc = opt.document || global.document;
    const radice = opt.root || doc.body;
    const doFetch = opt.fetch || global.fetch.bind(global);
    const attesa = opt.pollMs || 500;
    const dormi = opt.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
    const installazioni = new Set();

    function el(tag, cls, testo) {
      const e = doc.createElement(tag);
      if (cls) e.className = cls;
      if (testo != null) e.textContent = testo;
      return e;
    }

    async function json(url, init) {
      let r;
      try { r = await doFetch(url, init); } catch (e) { throw new Error(trad("k.emu.net", "Rete non raggiungibile")); }
      if (r.status === 404 || r.status === 405) throw new Error(trad("k.emu.nofn", "Funzione non disponibile in questa versione"));
      let d = null;
      try { d = await r.json(); } catch (e) { /* corpo non JSON */ }
      if (!r.ok) throw new Error((d && (d.detail || d.message)) || trad("k.emu.http", "Errore {status}", {status: r.status}));
      return d || {};
    }

    const q = (c) => "?console=" + encodeURIComponent(c);

    // «Impostazioni consigliate» per console: legge /api/emu-presets, salva al cambio
    const SCELTE = () => [["leave", trad("k.emu.pre.leave", "Non toccare")], ["quality", trad("k.emu.pre.quality", "Qualità")], ["performance", trad("k.emu.common.perf", "Prestazioni")], ["faithful", trad("k.emu.pre.faithful", "Fedele")]];
    let presetCorrenti = null;
    function rigaPreset(consoleId, nome) {
      const riga = el("div", "xe-preset");
      const sel = el("select", "field xe-preset-sel");
      sel.id = "xe-preset-" + consoleId;
      SCELTE().forEach(([v, t]) => { const o = el("option", null, t); o.value = v; sel.appendChild(o); });
      const lab = el("label", "small", trad("k.emu.pre.label", "Impostazioni consigliate") + " ");
      lab.setAttribute("for", sel.id);
      riga.appendChild(lab); riga.appendChild(sel);
      presetCorrenti = presetCorrenti || json("/api/emu-presets");
      presetCorrenti.then((m) => { sel.value = (m && m[consoleId]) || "leave"; }, () => { presetCorrenti = null; });
      sel.addEventListener("change", async () => {
        try {
          await json("/api/emu-presets/console", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ platform: consoleId, preset: sel.value }) });
          if (global.toast) global.toast(trad("k.emu.pre.saved", "Impostazioni consigliate salvate per {nome}", {nome}));
        } catch (e) { if (global.toast) global.toast(e.message, true); }
      });
      return riga;
    }

    function costruisci(riga) {
      const consoleId = riga.getAttribute("data-p");
      const cella = riga.querySelector("td");
      const nome = cella ? (cella.textContent || "").split("consigliati")[0].trim() || consoleId : consoleId;
      const tr = el("tr", "xe-row");
      tr.setAttribute("data-xe", consoleId);
      const td = el("td");
      td.setAttribute("colspan", "5");
      const box = el("div", "xe-box");
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", trad("k.emu.group_aria", "Emulatore consigliato e BIOS per {nome}", {nome}));
      const rec = el("div", "xe-rec");
      const bios = el("div", "xe-bios");
      const stato = el("div", "xe-state");
      stato.setAttribute("role", "status");
      stato.setAttribute("aria-live", "polite");
      const barra = el("div", "xe-bar");
      barra.hidden = true;
      const fill = el("div", "xe-fill");
      barra.appendChild(fill);
      box.appendChild(rec); box.appendChild(bios); box.appendChild(barra); box.appendChild(stato);
      box.appendChild(rigaPreset(consoleId, nome));
      td.appendChild(box); tr.appendChild(td);
      riga.parentNode.insertBefore(tr, riga.nextSibling);
      const v = { consoleId, nome, rec, bios, stato, barra, fill, tr };
      carica(v);
      return v;
    }

    async function carica(v) {
      v.rec.textContent = trad("k.emu.rec.search", "Cerco il consiglio…");
      const [r, b] = await Promise.allSettled([
        json("/api/emulators/recommend" + q(v.consoleId)),
        json("/api/emulators/bios" + q(v.consoleId)),
      ]);
      v.rec.textContent = "";
      if (r.status === "fulfilled") disegnaConsiglio(v, r.value);
      else v.rec.appendChild(el("span", "muted small", trad("k.emu.rec.unavail", "Consiglio non disponibile: {msg}", {msg: r.reason.message})));
      if (b.status === "fulfilled") disegnaBios(v, b.value);
      else v.bios.appendChild(el("span", "muted small", trad("k.emu.bios.unavail", "BIOS non verificabili: {msg}", {msg: b.reason.message})));
    }

    function disegnaConsiglio(v, d) {
      const t = el("div", "xe-title");
      t.appendChild(el("b", null, d.emulator || trad("k.emu.none", "Nessun emulatore")));
      if (d.installed) t.appendChild(el("span", "xe-tag xe-ok", trad("k.emu.installed_tag", " ✓ installato")));
      v.rec.appendChild(t);
      if (d.reason) v.rec.appendChild(el("div", "muted small", d.reason));
      if (d.reasons) {  // fedeltà / prestazioni / controller: chip con il testo nel tooltip
        const chips = el("div", "xe-chips");
        [["fedelta", trad("k.emu.chip.fedelta", "Fedeltà")], ["prestazioni", trad("k.emu.common.perf", "Prestazioni")], ["controller", trad("k.emu.common.controller", "Controller")]].forEach(([k, t]) => {
          if (!d.reasons[k]) return;
          const c = el("span", "xe-chip small", t);
          c.tabIndex = 0;
          c.title = d.reasons[k];
          chips.appendChild(c);
        });
        v.rec.appendChild(chips);
      }
      if (d.supported === false) {
        v.rec.appendChild(el("div", "xe-warn small", trad("k.emu.unsupported", "Pozzo non sa installare questo emulatore: scegline uno a mano.")));
        return;
      }
      if (d.installed) return;
      const btn = el("button", "btn xe-install", trad("k.emu.install", "⬇ Installa"));
      btn.type = "button";
      btn.setAttribute("aria-label", trad("k.emu.install_aria", "Installa {emu} per {nome}", {emu: d.emulator, nome: v.nome}));
      btn.addEventListener("click", () => installa(v, btn));
      v.rec.appendChild(btn);
    }

    function disegnaBios(v, d) {
      const items = d.items || [];
      if (!items.length) { v.bios.appendChild(el("span", "muted small", trad("k.emu.bios.none", "Nessun BIOS richiesto."))); return; }
      const ul = el("ul", "xe-list");
      items.forEach((it) => {
        const s = STATI[statoBios(it)];
        const li = el("li", "xe-item " + s.cls);
        li.appendChild(el("span", "xe-ico", s.icona));
        li.appendChild(el("span", "xe-file", " " + it.file));
        li.appendChild(el("span", "xe-txt small", ` — ${s.testo()}${it.required ? "" : trad("k.emu.optional", " (facoltativo)")}`));
        li.setAttribute("aria-label", `${it.file}: ${s.testo()}${it.required ? trad("k.emu.required", ", richiesto") : ""}`);
        if (it.help_url) {
          const a = el("a", "xe-help small", trad("k.emu.help_link", " Come procurarlo"));
          a.setAttribute("href", it.help_url);
          a.setAttribute("target", "_blank");
          a.setAttribute("rel", "noopener noreferrer");
          a.setAttribute("aria-label", trad("k.emu.help_aria", "Come procurare {file} (si apre in una nuova scheda)", {file: it.file}));
          li.appendChild(a);
        }
        ul.appendChild(li);
      });
      v.bios.appendChild(ul);
    }

    function messaggio(snap) {
      const passi = (snap && snap.steps) || [];
      const attivo = passi.find((s) => s.state === "running") || passi[passi.length - 1];
      return attivo ? attivo.label : "";
    }

    async function installa(v, btn) {
      if (installazioni.has(v.consoleId)) return;
      installazioni.add(v.consoleId);
      btn.disabled = true;
      v.barra.hidden = false;
      v.stato.className = "xe-state";
      v.stato.textContent = trad("k.emu.installing", "Installazione in corso…");
      v.fill.style.transform = "scaleX(0)";
      let finita = false;
      const post = json("/api/emulators/install-recommended", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ console: v.consoleId }),
      }).then((x) => ({ ok: true, x }), (e) => ({ ok: false, e }))
        .then((res) => { finita = true; return res; });
      while (!finita) {
        await dormi(attesa);
        if (finita) break;
        try {
          const s = await json("/api/emulators/install-recommended" + q(v.consoleId));
          if (finita) break;
          v.fill.style.transform = `scaleX(${Math.max(0, Math.min(1, s.progress || 0))})`;
          const m = messaggio(s);
          if (m) v.stato.textContent = m;
        } catch (e) { /* un sondaggio fallito non ferma l'installazione */ }
      }
      const res = await post;
      installazioni.delete(v.consoleId);
      v.barra.hidden = true;
      if (res.ok && res.x.ok !== false) {
        v.fill.style.transform = "scaleX(1)";
        v.stato.className = "xe-state xe-ok";
        v.stato.textContent = "✓ " + (res.x.message || trad("k.emu.installed_ok", "Installato"));
        btn.hidden = true;
      } else {
        v.stato.className = "xe-state xe-bad";
        v.stato.textContent = "✗ " + (res.ok ? res.x.message : res.e.message);
        btn.disabled = false;
      }
    }

    function scansiona() {
      radice.querySelectorAll("tr[data-p]").forEach((riga) => {
        const prossima = riga.nextSibling;
        if (prossima && prossima.getAttribute && prossima.getAttribute("data-xe") === riga.getAttribute("data-p")) return;
        costruisci(riga);
      });
    }

    function avvia() {
      scansiona();
      const Obs = opt.MutationObserver || global.MutationObserver;
      if (!Obs) return null;
      const o = new Obs(() => scansiona());
      o.observe(radice, { childList: true, subtree: true });
      return o;
    }

    return { avvia, scansiona, statoBios };
  }

  const api = { creaComponente, statoBios };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    global.PozzoEmuExtra = api;
    const parti = () => creaComponente().avvia();
    if (global.document.readyState === "loading") global.document.addEventListener("DOMContentLoaded", parti);
    else parti();
  }
})(typeof window !== "undefined" ? window : globalThis);
/* Disco veloce (copia del gioco su SSD): carica le impostazioni quando si apre la scheda Emulatori e Avvio,
   e salva/sfoglia con delegazione, perche' la scheda viene inserita con innerHTML dopo il caricamento. */
(function (global) {
  "use strict";
  const doc = global.document;
  if (!doc) return; // test in node: niente DOM
  const campo = (id) => doc.getElementById(id);
  // t() viene da i18n.js nel browser; nei test in node manca e resta il testo italiano
  const trad = (k, it, p) => (global.t ? global.t(k, p) : it.replace(/\{(\w+)\}/g, (m, n) => (p && n in p ? p[n] : m)));

  function mostra(d) {
    campo("fc-dir").value = d.dir || "";
    campo("fc-dir").placeholder = d.default_dir || "";
    campo("fc-del").checked = !!d.delete_after;
    campo("fc-free").textContent = d.free_gb == null ? "" : trad("k.emu.fc.free", "Spazio libero: {gb} GB", {gb: Number(d.free_gb).toFixed(1)});
  }

  async function carica() {
    try { mostra(await global.api("/api/app/fastcopy")); } catch (e) { global.toast(e.message, true); }
    try { campo("pl-proto").checked = !!(await global.api("/api/party")).register_protocol; } catch (e) { global.toast(e.message, true); }
    try { campo("crash-mode").value = (await global.api("/api/app/crash-fallback")).mode; } catch (e) { global.toast(e.message, true); }
  }

  doc.addEventListener("change", async (ev) => {
    if (!ev.target || ev.target.id !== "crash-mode") return;
    try { await global.api("/api/app/crash-fallback", { body: { mode: ev.target.value } }); }
    catch (e) { global.toast(e.message, true); carica(); }  // ripristina il valore salvato
  });

  // registrazione del link pozzo:// (scheda Avvio); in caso di errore ripristina il valore precedente
  doc.addEventListener("change", async (ev) => {
    if (!ev.target || ev.target.id !== "pl-proto") return;
    const el = ev.target;
    const prima = !el.checked;
    try {
      const r = await global.api("/api/party/settings", { body: { register_protocol: el.checked } });
      el.checked = !!r.register_protocol;
    } catch (e) { el.checked = prima; global.toast(e.message, true); }
  });

  async function salva() {
    const body = { dir: campo("fc-dir").value.trim(), delete_after: campo("fc-del").checked };
    try {
      mostra(await global.api("/api/app/fastcopy", { body }));
      global.toast(trad("k.emu.fc.saved", "Impostazioni del disco veloce salvate"));
    } catch (e) { global.toast(e.message, true); }  // il server dice il motivo (es. cartella non valida)
  }

  doc.addEventListener("click", async (ev) => {
    const b = ev.target.closest && ev.target.closest("#fc-save, #fc-pick");
    if (!b || !campo("fc-dir")) return;
    if (b.id === "fc-save") return salva();
    const p = await global.pickPath("folder");
    if (p) campo("fc-dir").value = p;
  });

  // la scheda diventa visibile (showTab toglie hidden al pannello data-pane="emulatori")
  const corpo = doc.getElementById("settings-body") || doc.body;
  new global.MutationObserver((mutazioni) => {
    if (mutazioni.some((m) => m.target.dataset && m.target.dataset.pane === "emulatori" && !m.target.hidden)) carica();
  }).observe(corpo, { attributes: true, attributeFilter: ["hidden"], subtree: true });
})(typeof window !== "undefined" ? window : globalThis);

/* Aggiornamenti degli emulatori (scheda Emulatori): modalità del controllo automatico e lista di quelli disponibili. */
(function (global) {
  "use strict";
  const doc = global.document;
  if (!doc) return; // test in node: niente DOM
  const campo = (id) => doc.getElementById(id);
  const MODI = ["off", "notify", "install"];
  // t() viene da i18n.js nel browser; nei test in node manca e resta il testo italiano
  const trad = (k, it, p) => (global.t ? global.t(k, p) : it.replace(/\{(\w+)\}/g, (m, n) => (p && n in p ? p[n] : m)));


  function mostra(d) {
    campo("emu-au-mode").value = MODI.includes(d.mode) ? d.mode : "off";
    const box = campo("emu-upd");
    box.textContent = "";
    if (!d.updates || !d.updates.length) { box.textContent = trad("k.emu.upd.none", "Nessun aggiornamento disponibile."); return; }
    d.updates.filter((u) => u.update).forEach((u) => {
      const riga = doc.createElement("div");
      riga.className = "row";
      const testo = doc.createElement("span");
      testo.className = "grow";
      testo.textContent = `${u.name}: ${u.current || "?"} → ${u.latest}`;
      const btn = doc.createElement("button");
      btn.className = "btn";
      btn.type = "button";
      btn.dataset.upd = u.id;
      btn.textContent = trad("k.emu.upd.btn", "Aggiorna");
      btn.setAttribute("aria-label", trad("k.emu.upd.aria", "Aggiorna {name} a {latest}", {name: u.name, latest: u.latest}));
      riga.appendChild(testo); riga.appendChild(btn);
      box.appendChild(riga);
    });
  }

  async function carica() {
    if (!campo("emu-upd")) return;
    campo("emu-upd").textContent = trad("k.emu.upd.checking", "Controllo gli aggiornamenti…");
    try { mostra(await global.api("/api/emulators/updates")); }
    catch (e) { campo("emu-upd").textContent = e.message; }
  }

  doc.addEventListener("change", async (ev) => {
    if (!ev.target || ev.target.id !== "emu-au-mode") return;
    try {
      await global.api("/api/emulators/autoupdate", { body: { mode: ev.target.value } });
      global.toast(trad("k.emu.upd.saved", "Aggiornamento automatico degli emulatori salvato"));
    } catch (e) { global.toast(e.message, true); }
    carica();
  });

  doc.addEventListener("click", async (ev) => {
    if (ev.target.closest && ev.target.closest("#emu-upd-check")) return carica();
    const btn = ev.target.closest && ev.target.closest("[data-upd]");
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = trad("k.emu.upd.updating", "Aggiorno…");
    try {
      const r = await global.api("/api/emulators/update/" + encodeURIComponent(btn.dataset.upd), { method: "POST" });
      global.toast(trad("k.emu.upd.done", "Aggiornato {id} ({path})", {id: btn.dataset.upd, path: r.path}));
      carica();
    } catch (e) {
      global.toast(e.message, true);
      btn.disabled = false;
      btn.textContent = trad("k.emu.upd.btn", "Aggiorna");
    }
  });

  // la scheda diventa visibile: si controlla la modalità e gli aggiornamenti
  const corpo = doc.getElementById("settings-body") || doc.body;
  new global.MutationObserver((mutazioni) => {
    if (mutazioni.some((m) => m.target.dataset && m.target.dataset.pane === "emulatori" && !m.target.hidden)) carica();
  }).observe(corpo, { attributes: true, attributeFilter: ["hidden"], subtree: true });
})(typeof window !== "undefined" ? window : globalThis);
