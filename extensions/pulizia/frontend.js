// Pulizia libreria: liste di giochi da sistemare, con azioni di massa e badge «DUP» sui duplicati.
import { afterApply, baseName, confirmText, duplicates, fmtBytes, freeable, freeableTotal, incomplete, linkable, neverPlayed, stale } from "./logica.js";

const TABS = [["dup", "Duplicati"], ["mai", "Mai avviati"], ["fermi", "Fermi da anni"], ["meta", "Dati incompleti"]];
const ACTIONS = { hide: ["Nascondi", { field: "hidden", value: true }],
  dropped: ["Segna abbandonato", { field: "status", value: "dropped" }],
  backlog: ["Metti nel backlog", { field: "status", value: "backlog" }] };

export default function (gs) {
  let dupIds = new Set(), builtAt = null;
  // «File identici su disco»: stato fuori dal render, cosi' sopravvive tra una visita e l'altra alla pagina
  let box = null, disk = null, scanning = false, busy = false;
  const refreshDup = () => {
    const lib = gs.library();
    if (!lib || lib.builtAt === builtAt) return;
    builtAt = lib.builtAt;
    dupIds = new Set(duplicates(lib.games).flat().map((g) => g.id));
  };
  gs.addTileBadge({ id: "dup", render: (g) => { refreshDup(); return dupIds.has(g.id) ? "DUP" : null; } });
  gs.addSidebarItem({ id: "pulizia", label: "Pulizia libreria", icon: "🧹", view: "pulizia" });

  gs.registerView("pulizia", {
    title: "Pulizia libreria",
    render(el) {
      let tab = gs.store.get("pulizia.tab", "dup"), years = gs.store.get("pulizia.anni", 2);
      const sel = new Set();
      const main = document.createElement("div");
      box = document.createElement("div");
      box.className = "pl-disk";
      el.replaceChildren(main, box);

      const rows = () => {
        const lib = gs.library();
        if (tab === "dup") return duplicates(lib.games).map((l) => ({ ids: l.map((g) => g.id), main: l[0], extra: `${l.length} copie` }));
        if (tab === "mai") return neverPlayed(lib.games).map((g) => ({ ids: [g.id], main: g, extra: g.year || "" }));
        if (tab === "fermi") return stale(lib.games, years).map((g) => ({ ids: [g.id], main: g,
          extra: `ultima volta ${new Date(g.grp.last * 1000).toLocaleDateString("it")}` }));
        return incomplete(lib.games).map(({ g, m }) => ({ ids: [g.id], main: g, extra: "manca: " + m.join(", ") }));
      };
      const platName = (g) => gs.library().plats.get(g.platform)?.name || g.store || g.platform;

      const draw = () => {
        const list = rows();
        const shown = list.slice(0, 500);
        main.innerHTML = `<div class="pl-tabs">${TABS.map(([k, l]) => `<button class="btn ${k === tab ? "primary" : ""}" data-tab="${k}">${l}</button>`).join("")}
            ${tab === "fermi" ? `<label class="pl-years">da <select id="pl-y">${[1, 2, 3, 5].map((y) => `<option ${y === years ? "selected" : ""}>${y}</option>`).join("")}</select> anni</label>` : ""}</div>
          <p class="muted">${list.length.toLocaleString("it")} ${list.length === 1 ? "voce" : "voci"}${list.length > shown.length ? ` (le prime ${shown.length})` : ""}.
            ${tab === "dup" ? "Per i duplicati le azioni valgono per tutte le copie tranne la prima." : ""}</p>
          <div class="pl-bar"><button class="btn" id="pl-all">Seleziona tutto</button><button class="btn" id="pl-none">Nessuno</button>
            ${Object.entries(ACTIONS).map(([k, [l]]) => `<button class="btn" data-act="${k}" ${sel.size ? "" : "disabled"}>${l} (${sel.size})</button>`).join("")}
            <button class="btn" id="pl-manual-dupes" title="Toglie le voci aggiunte a mano due volte (stesso eseguibile e stessi argomenti)">🧹 Rimuovi doppioni manuali</button></div>
          <ul class="pl-list">${shown.map((r, i) => {
            const on = r.ids.slice(r.ids.length > 1 ? 1 : 0).every((id) => sel.has(id));
            return `<li><label><input type="checkbox" data-i="${i}" ${on ? "checked" : ""}> <b>${gs.esc(r.main.title)}</b>
              <span class="muted">${gs.esc(platName(r.main))} · ${gs.esc(r.extra)}</span></label>
              <a href="#" data-open="${r.main.id}">Apri</a></li>`; }).join("")}</ul>`;
        el._rows = shown;
      };

      const targets = (r) => (r.ids.length > 1 ? r.ids.slice(1) : r.ids);   // duplicati: si tiene la prima copia
      el.onchange = (e) => {
        if (e.target.id === "pl-y") { years = +e.target.value; gs.store.set("pulizia.anni", years); sel.clear(); return draw(); }
        const i = e.target.dataset.i;
        if (i === undefined) return;
        for (const id of targets(el._rows[+i])) (e.target.checked ? sel.add(id) : sel.delete(id));
        draw();
      };
      el.onclick = async (e) => {
        const t = e.target.closest("[data-tab],[data-act],[data-open],#pl-all,#pl-none,#pl-manual-dupes");
        if (!t) return;
        if (t.dataset.open) { e.preventDefault(); return gs.openGame(+t.dataset.open); }
        if (t.dataset.tab) { tab = t.dataset.tab; gs.store.set("pulizia.tab", tab); sel.clear(); return draw(); }
        if (t.id === "pl-all") { el._rows.forEach((r) => targets(r).forEach((id) => sel.add(id))); return draw(); }
        if (t.id === "pl-none") { sel.clear(); return draw(); }
        if (t.id === "pl-manual-dupes") {
          if (!confirm("Rimuovere i doppioni tra le voci aggiunte a mano (stesso eseguibile e stessi argomenti)? Si tiene la più vecchia.")) return;
          try {
            const r = await gs.api("/api/manual/dedupe", { body: {} });
            gs.toast(r.removed ? `${r.removed} ${r.removed === 1 ? "doppione rimosso" : "doppioni rimossi"}` : "Nessun doppione da rimuovere");
            if (r.removed) await gs.refresh();
          } catch (err) { gs.toast(err.message, true); }
          return draw();
        }
        const [label, body] = ACTIONS[t.dataset.act];
        if (!sel.size || !confirm(`${label}: ${sel.size} giochi?`)) return;
        let ok = 0, fail = 0;
        for (const id of sel) { try { await gs.api(`/api/game/${id}/flag`, { body }); ok++; } catch { fail++; } }
        gs.toast(`${label}: ${ok} fatti${fail ? `, ${fail} non riusciti` : ""}`, !!fail);
        sel.clear();
        await gs.refresh();
        draw();
      };
      draw();

      const card = (g, i) => {
        const can = linkable(g);
        const why = "Una copia è su un altro disco: il collegamento (hardlink) non è possibile";
        const files = g.files.map((f, j) => `<label class="pl-dup-file">
            <input type="radio" name="keep-${i}" data-g="${i}" data-j="${j}" ${j === g.keep ? "checked" : ""} ${busy ? "disabled" : ""}>
            <span><b>${gs.esc(f.game || baseName(f.path))}</b> ${f.region ? `<span class="muted">${gs.esc(f.region)}</span>` : ""}
              ${j !== g.keep && (f.dev != null ? f.dev !== g.files[g.keep].dev : !!j && f.same_volume_as_first === false) ? `<span class="pl-tag" title="Su un altro disco rispetto alla copia da tenere">altro disco</span>` : ""}
              ${f.is_hardlink ? `<span class="pl-tag">già collegato</span>` : ""}<br><code>${gs.esc(f.path)}</code></span></label>`).join("");
        return `<div class="pl-dup-card"><div class="muted">${g.files.length} copie · ${fmtBytes(g.size)} ciascuna · con questa scelta liberi ${fmtBytes(freeable(g))}</div>
          ${files}
          <div class="pl-bar"><button class="btn" data-dup="hardlink" data-g="${i}" ${can && !busy ? "" : "disabled"} title="${can ? "" : why}">Sostituisci con collegamento (hardlink)</button>
            <button class="btn" data-dup="delete" data-g="${i}" ${busy ? "disabled" : ""}>Elimina le altre copie</button></div></div>`;
      };
      const drawDisk = () => {
        const head = `<h3>File identici su disco</h3>`;
        if (scanning) return void (box.innerHTML = head + `<p class="muted">Calcolo impronte…</p>`);
        if (!disk) return void (box.innerHTML = head + `<p class="muted">Cerca copie di file uguali in cartelle diverse, anche con nomi diversi. Il calcolo può richiedere molto tempo.</p>
          <button class="btn" id="pl-dup-scan">Cerca file identici</button>`);
        box.innerHTML = head + `<p><b>Spazio liberabile: ${fmtBytes(disk.freeable)}</b> · ${disk.groups.length} ${disk.groups.length === 1 ? "gruppo" : "gruppi"}
            <button class="btn" id="pl-dup-scan" ${busy ? "disabled" : ""}>Ricalcola</button></p>`
          + (disk.groups.length ? disk.groups.map(card).join("") : `<p class="muted">Nessun file identico trovato.</p>`);
      };
      const scan = async () => {
        scanning = true; drawDisk();
        try { const r = await gs.api("/plugin-api/pulizia/dup-files"); disk = { groups: r.groups || [], freeable: r.freeable || 0 }; }
        catch (err) { gs.toast(err.message, true); }
        scanning = false; drawDisk();
      };
      box.onchange = (e) => {   // scelta della copia da tenere: si ricalcola lo spazio liberabile
        const g = e.target.dataset.g;
        if (g === undefined || e.target.type !== "radio") return;
        disk.groups[+g].keep = +e.target.dataset.j;
        disk.freeable = freeableTotal(disk.groups);
        drawDisk();
      };
      box.onclick = async (e) => {
        if (e.target.closest("#pl-dup-scan")) { if (!busy && !scanning) await scan(); return; }
        const b = e.target.closest("[data-dup]");
        if (!b || b.disabled || busy) return;
        const i = +b.dataset.g, g = disk.groups[i], action = b.dataset.dup;
        if (!confirm(confirmText(action, g))) return;
        busy = true; drawDisk();
        try {
          const r = await gs.api("/plugin-api/pulizia/dup-apply", { body: { hash: g.hash, keep: g.files[g.keep].path, action } });
          const res = r.results || [], bad = res.filter((x) => !x.ok).length;
          gs.toast(`${action === "delete" ? "Eliminate" : "Collegate"} ${res.length - bad} copie${bad ? `, ${bad} non riuscite` : ""}`, !!bad);
          const next = afterApply(g, action, res);
          disk.groups.splice(i, 1, ...(next ? [next] : []));
          disk.freeable = freeableTotal(disk.groups);
        } catch (err) { gs.toast(err.message, true); }
        busy = false; drawDisk();
      };
      drawDisk();
    },
  });
}
