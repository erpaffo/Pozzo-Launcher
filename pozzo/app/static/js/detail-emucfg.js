"use strict";
/* Scheda gioco: «Impostazioni emulatore» (preset per gioco, anteprima, ripristino). Solo DOM e textContent (nessun markup costruito da stringhe). */
(function () {
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };

  async function build(game) {
    const body = document.querySelector("#detail-body");
    if (!body) return;
    body.querySelector("#d-emucfg")?.remove();
    if (game.store || !(game.files || []).length) return;
    let info;
    try { info = await api(`/api/game/${game.id}/emu-preset`); } catch { return; }
    if (window.S?.detail?.id !== game.id) return; // risposta tardiva: la scheda è cambiata
    body.querySelector("#d-emucfg")?.remove();
    const section = el("section", "emucfg");
    section.id = "d-emucfg";
    section.setAttribute("aria-labelledby", "d-emucfg-h");
    const h = el("div", "d-h", "Impostazioni emulatore");
    h.id = "d-emucfg-h";
    section.append(h);
    body.append(section);
    if (!info.supported) {
      section.append(el("p", "muted small", info.note || "Emulatore non supportato"));
      return;
    }
    render(section, game, info);
  }

  function render(section, game, info) {
    const sel = el("select", "field emucfg-select");
    sel.id = "d-emucfg-sel";
    const opts = [["inherit", "Eredita dalla console"], ["leave", "Non toccare"],
      ...(info.levels || []).map((l) => [l.id, l.name])];
    for (const [v, t] of opts) {
      const o = el("option", null, t);
      o.value = v;
      sel.append(o);
    }
    sel.value = info.selection || "inherit";
    const label = el("label", "emucfg-label", "Preset ");
    label.setAttribute("for", sel.id);
    const row = el("div", "emucfg-row");
    row.append(label, sel);
    const preview = el("div", "emucfg-preview");
    preview.setAttribute("aria-live", "polite");
    const restore = el("button", "btn emucfg-restore", "Ripristina impostazioni originali");
    restore.type = "button";
    section.append(row, preview, restore);
    drawPreview(preview, info.preview);

    sel.addEventListener("change", async () => {
      sel.disabled = true;
      try {
        // la rotta riscrive tutto il profilo: si rimanda quello esistente con il solo preset cambiato
        const cur = (await api(`/api/game/${game.id}/profile`)).profile || {};
        await api(`/api/game/${game.id}/profile`, { body: { ...cur, preset: sel.value === "inherit" ? "" : sel.value } });
        const fresh = await api(`/api/game/${game.id}/emu-preset`);
        if (window.S?.detail?.id === game.id) drawPreview(preview, fresh.preview);
        toast("Preset salvato");
      } catch (e) {
        toast(e.message, true);
      } finally { sel.disabled = false; }
    });

    restore.addEventListener("click", async () => {
      if (!window.confirm("Ripristinare le impostazioni originali dell'emulatore per questo gioco?")) return;
      restore.disabled = true;
      try {
        const r = await api(`/api/game/${game.id}/emu-preset/restore`, { method: "POST" });
        toast(r.restored ? "Impostazioni originali ripristinate" : "Niente da ripristinare");
      } catch (e) {
        toast(e.message, true);
      } finally { restore.disabled = false; }
    });
  }

  function drawPreview(box, pv) {
    box.replaceChildren();
    const values = (pv && pv.values) || {};
    const lines = Object.entries(values).flatMap(([sec, kv]) => Object.entries(kv || {}).map(([k, v]) => `${sec}.${k} = ${v}`));
    box.append(el("div", "emucfg-h", "Cosa cambierà"));
    if (!lines.length) {
      box.append(el("p", "muted small", "Nessuna modifica: l'emulatore resta com'è."));
    } else {
      const ul = el("ul", "emucfg-list small");
      for (const t of lines) ul.append(el("li", null, t));
      box.append(ul);
      if (pv.reason) box.append(el("p", "muted small", pv.reason));
    }
    const links = [...new Set((pv && pv.sources) || [])].filter((u) => /^https:\/\//.test(u));
    for (const u of links) {
      const a = el("a", "small emucfg-src", `Fonte: ${u.replace(/^https:\/\//, "")} ↗`);
      a.href = u;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      box.append(a, el("br"));
    }
  }

  window.addEventListener("pozzo:detail-open", (event) => { build(event.detail); });
})();
