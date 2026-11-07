"use strict";
/* Scheda gioco: pannello RetroArch (bezel, shader, cheat). Solo DOM e textContent. */
(function () {
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const opt = (v, label) => { const o = el("option", null, label); o.value = v; return o; };

  async function build(game) {
    const body = document.querySelector("#detail-body");
    if (!body) return;
    body.querySelector("#d-raextra")?.remove();
    if (game.store || !(game.files || []).length) return;
    let st;
    try { st = await api(`/api/game/${game.id}/retroarch`); } catch { return; } // 409: non è un gioco RetroArch
    if (window.S?.detail?.id !== game.id) return;
    body.querySelector("#d-raextra")?.remove();
    const sec = el("section", "emucfg");
    sec.id = "d-raextra";
    sec.setAttribute("aria-labelledby", "d-raextra-h");
    const h = el("div", "d-h", t("f.raextra.heading"));
    h.id = "d-raextra-h";
    const scope = el("input");
    scope.type = "checkbox";
    scope.id = "d-raextra-core";
    const scopeLbl = el("label", "small", " " + t("f.raextra.core", { core: st.core }));
    scopeLbl.prepend(scope);
    const note = el("p", "muted small", t("f.raextra.restartNote"));
    const save = async (patch) => {
      try {
        await api(`/api/game/${game.id}/retroarch`, { body: { ...patch, scope: scope.checked ? "console" : "game" } });
        toast(t("f.raextra.saved"));
      } catch (e) { toast(e.message, true); }
    };

    // bezel: «Predefinito» (toglie la nostra scelta) / «Nessuno» / elenco caricato a richiesta con anteprime
    const bez = el("select", "field");
    bez.id = "d-raextra-bezel";
    const bl = el("label", "emucfg-label", t("f.raextra.bezel") + " ");
    bl.setAttribute("for", bez.id);
    bez.append(opt("inherit", t("f.raextra.inherit")), opt("", t("f.raextra.none")));
    const cur = st.bezel.game;
    if (cur) bez.append(opt(cur, cur.replace(/\.cfg$/, "")));
    bez.value = cur === null || cur === undefined ? "inherit" : cur;
    const pick = el("button", "btn", t("f.raextra.choose"));
    pick.type = "button";
    const thumbs = el("div", "emucfg-preview");
    const brow = el("div", "emucfg-row");
    brow.append(bl, bez, pick);
    bez.addEventListener("change", () => save({ bezel: bez.value === "inherit" ? null : bez.value }));
    pick.addEventListener("click", async () => {
      pick.disabled = true;
      try {
        const list = await api(`/api/game/${game.id}/retroarch/bezels`);
        thumbs.replaceChildren();
        for (const b of list) {
          const btn = el("button", "btn");
          btn.type = "button";
          btn.title = b.name;
          const img = el("img");
          img.loading = "lazy";
          img.alt = b.name;
          img.width = 160;
          img.src = `/api/retroarch/bezel-preview?id=${encodeURIComponent(b.id)}`;
          btn.append(img);
          btn.addEventListener("click", () => {
            if (![...bez.options].some((o) => o.value === b.id)) bez.append(opt(b.id, b.name));
            bez.value = b.id;
            save({ bezel: b.id });
          });
          thumbs.append(btn);
        }
      } catch (e) { toast(e.message, true); } finally { pick.disabled = false; }
    });

    // shader: preset già presenti nella cartella di RetroArch
    const sh = el("select", "field");
    sh.id = "d-raextra-shader";
    const sl = el("label", "emucfg-label", t("f.raextra.shader") + " ");
    sl.setAttribute("for", sh.id);
    sh.append(opt("", t("f.raextra.none")), ...st.shader.options.map((s) => opt(s.id, s.name)));
    sh.value = st.shader.game || "";
    sh.addEventListener("change", () => save({ shader: sh.value }));
    const srow = el("div", "emucfg-row");
    srow.append(sl, sh);

    // cheat: elenco cercato per nome, con interruttori
    const find = el("button", "btn", t("f.raextra.loadCheats"));
    find.type = "button";
    const list = el("ul", "emucfg-list small");
    find.addEventListener("click", async () => {
      find.disabled = true;
      try {
        const r = await api(`/api/game/${game.id}/retroarch/cheats`);
        list.replaceChildren();
        if (!r.file) { list.append(el("li", "muted", t("f.raextra.noCheats"))); return; }
        const boxes = r.entries.map((c) => {
          const cb = el("input");
          cb.type = "checkbox";
          cb.checked = c.enable;
          const li = el("li");
          const lb = el("label", null, " " + c.desc);
          lb.prepend(cb);
          li.append(lb);
          list.append(li);
          return cb;
        });
        const apply = () => api(`/api/game/${game.id}/retroarch/cheats`, {
          body: { enabled: boxes.flatMap((b, i) => b.checked ? [i] : []) } }).then(() => toast(t("f.raextra.saved")), (e) => toast(e.message, true));
        for (const b of boxes) b.addEventListener("change", apply);
      } catch (e) { toast(e.message, true); } finally { find.disabled = false; }
    });
    const crow = el("div", "emucfg-row");
    crow.append(el("span", "emucfg-label", t("f.raextra.cheats") + " "), find);
    sec.append(h, brow, thumbs, srow, crow, list, scopeLbl, note);
    body.append(sec);
  }

  window.addEventListener("pozzo:detail-open", (event) => { build(event.detail); });
})();
