/* Emulatori (extra): sotto ogni console di #emu-table mostra l'emulatore consigliato, lo stato dei BIOS e
   l'installazione «un clic». Si aggancia da solo alle righe tr[data-p] (la tabella viene ridisegnata spesso). */
(function (global) {
  "use strict";

  const STATI = {
    ok: { cls: "xe-ok", icona: "✓", testo: "trovato" },
    missing: { cls: "xe-bad", icona: "✗", testo: "mancante" },
    mismatch: { cls: "xe-bad", icona: "✗", testo: "non corrisponde" },
    unknown: { cls: "xe-warn", icona: "?", testo: "hash non riconosciuto" },
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
      try { r = await doFetch(url, init); } catch (e) { throw new Error("Rete non raggiungibile"); }
      if (r.status === 404 || r.status === 405) throw new Error("Funzione non disponibile in questa versione");
      let d = null;
      try { d = await r.json(); } catch (e) { /* corpo non JSON */ }
      if (!r.ok) throw new Error((d && (d.detail || d.message)) || `Errore ${r.status}`);
      return d || {};
    }

    const q = (c) => "?console=" + encodeURIComponent(c);

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
      box.setAttribute("aria-label", `Emulatore consigliato e BIOS per ${nome}`);
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
      td.appendChild(box); tr.appendChild(td);
      riga.parentNode.insertBefore(tr, riga.nextSibling);
      const v = { consoleId, nome, rec, bios, stato, barra, fill, tr };
      carica(v);
      return v;
    }

    async function carica(v) {
      v.rec.textContent = "Cerco il consiglio…";
      const [r, b] = await Promise.allSettled([
        json("/api/emulators/recommend" + q(v.consoleId)),
        json("/api/emulators/bios" + q(v.consoleId)),
      ]);
      v.rec.textContent = "";
      if (r.status === "fulfilled") disegnaConsiglio(v, r.value);
      else v.rec.appendChild(el("span", "muted small", "Consiglio non disponibile: " + r.reason.message));
      if (b.status === "fulfilled") disegnaBios(v, b.value);
      else v.bios.appendChild(el("span", "muted small", "BIOS non verificabili: " + b.reason.message));
    }

    function disegnaConsiglio(v, d) {
      const t = el("div", "xe-title");
      t.appendChild(el("b", null, d.emulator || "Nessun emulatore"));
      if (d.installed) t.appendChild(el("span", "xe-tag xe-ok", " ✓ installato"));
      v.rec.appendChild(t);
      if (d.reason) v.rec.appendChild(el("div", "muted small", d.reason));
      if (d.supported === false) {
        v.rec.appendChild(el("div", "xe-warn small", "Pozzo non sa installare questo emulatore: scegline uno a mano."));
        return;
      }
      if (d.installed) return;
      const btn = el("button", "btn xe-install", "⬇ Installa");
      btn.type = "button";
      btn.setAttribute("aria-label", `Installa ${d.emulator} per ${v.nome}`);
      btn.addEventListener("click", () => installa(v, btn));
      v.rec.appendChild(btn);
    }

    function disegnaBios(v, d) {
      const items = d.items || [];
      if (!items.length) { v.bios.appendChild(el("span", "muted small", "Nessun BIOS richiesto.")); return; }
      const ul = el("ul", "xe-list");
      items.forEach((it) => {
        const s = STATI[statoBios(it)];
        const li = el("li", "xe-item " + s.cls);
        li.appendChild(el("span", "xe-ico", s.icona));
        li.appendChild(el("span", "xe-file", " " + it.file));
        li.appendChild(el("span", "xe-txt small", ` — ${s.testo}${it.required ? "" : " (facoltativo)"}`));
        li.setAttribute("aria-label", `${it.file}: ${s.testo}${it.required ? ", richiesto" : ""}`);
        if (it.help_url) {
          const a = el("a", "xe-help small", " Come procurarlo");
          a.setAttribute("href", it.help_url);
          a.setAttribute("target", "_blank");
          a.setAttribute("rel", "noopener noreferrer");
          a.setAttribute("aria-label", `Come procurare ${it.file} (si apre in una nuova scheda)`);
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
      v.stato.textContent = "Installazione in corso…";
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
        v.stato.textContent = "✓ " + (res.x.message || "Installato");
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