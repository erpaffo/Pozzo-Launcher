"use strict";
/* Scorciatoie di Pozzo Launcher: un solo registro per tastiera (desktop e Big Picture) e controller.
 * "Mod" = Ctrl su Windows/Linux, Cmd su macOS. Le voci "fixed" sono gia' gestite altrove (app.js, pad.js):
 * qui servono solo per l'elenco e per evitare doppioni. Override dell'utente in localStorage "gs.shortcuts".
 * La logica pura (combo, ricerca azione, mappa del pad) e' esportata anche per i test con node. */
(() => {
  const root = typeof window !== "undefined" ? window : globalThis;

  const isMacPlatform = (nav) => /mac|iphone|ipad/i.test(nav?.userAgentData?.platform || nav?.platform || nav?.userAgent || "");
  const MAC = typeof navigator !== "undefined" && isMacPlatform(navigator);

  /* ---- registro: id, etichetta, gruppo, keys (personalizzabili), fixed (gia' gestiti altrove), scope, typing */
  const REGISTRY = [
    { id: "search", label: "Cerca", group: "Navigazione", keys: ["Mod+K"], fixed: ["/"], scope: "desktop", typing: true },
    { id: "settings", label: "Impostazioni", group: "Navigazione", keys: ["Mod+,"], scope: "desktop", typing: true },
    { id: "viewAll", label: "Libreria", group: "Navigazione", keys: ["Mod+1"], scope: "desktop" },
    { id: "viewFav", label: "Preferiti", group: "Navigazione", keys: ["Mod+2"], scope: "desktop" },
    { id: "viewShop", label: "Store", group: "Navigazione", keys: ["Mod+3"], scope: "desktop" },
    { id: "sidebar", label: "Apri/chiudi la barra laterale Esplora", group: "Navigazione", keys: ["Mod+B"], scope: "desktop" },
    { id: "back", label: "Indietro / chiudi", group: "Navigazione", keys: ["Alt+ArrowLeft", "Mod+["], fixed: ["Escape"], scope: "desktop" },
    { id: "scanNew", label: "Cerca nuovi giochi", group: "Libreria", keys: ["Mod+Shift+S"], scope: "desktop" },
    { id: "play", label: "Avvia il gioco aperto", group: "Libreria", keys: [], fixed: ["Enter"], scope: "desktop" },
    { id: "favorite", label: "Preferito (gioco aperto)", group: "Libreria", keys: ["F"], scope: "desktop" },
    { id: "bigPicture", label: "Big Picture (entra / esci)", group: "Aspetto", keys: ["Mod+Shift+B", "F11"], scope: "both" },
    { id: "nextExperience", label: "Grafica successiva", group: "Aspetto", keys: ["Mod+Shift+E"], scope: "desktop" },
    { id: "nextTheme", label: "Tema successivo", group: "Aspetto", keys: ["Mod+Shift+T"], scope: "desktop" },
    { id: "legend", label: "Mostra/nascondi la legenda dei comandi", group: "Big Picture", keys: ["Mod+Shift+H"], scope: "bp" },
    { id: "help", label: "Elenco delle scorciatoie", group: "Aiuto", keys: ["Mod+/", "?"], scope: "both", typing: true },
    { id: "playPause", label: "Musica: play/pausa", group: "Musica e Discord", keys: ["Mod+Alt+P"], scope: "both", typing: true },
    { id: "next", label: "Musica: brano successivo", group: "Musica e Discord", keys: ["Mod+Alt+ArrowRight"], scope: "both", typing: true },
    { id: "prev", label: "Musica: brano precedente", group: "Musica e Discord", keys: ["Mod+Alt+ArrowLeft"], scope: "both", typing: true },
    { id: "muteMic", label: "Discord: microfono muto", group: "Musica e Discord", keys: ["Mod+Alt+M"], scope: "both", typing: true },
    { id: "deafen", label: "Discord: audio disattivato (sordo)", group: "Musica e Discord", keys: ["Mod+Alt+D"], scope: "both", typing: true },
  ];
  const MEDIA_IDS = ["playPause", "next", "prev", "muteMic", "deafen"];

  /* ---- controller: indici della mappa standard della Gamepad API (Xbox, PlayStation, Switch Pro) */
  const PAD_BTN = { a: 0, b: 1, x: 2, y: 3, lb: 4, rb: 5, lt: 6, rt: 7, select: 8, start: 9, l3: 10, r3: 11,
    up: 12, down: 13, left: 14, right: 15, guide: 16 };
  const PAD_CHORDS = { a: "playPause", rb: "next", lb: "prev", x: "muteMic", y: "deafen", b: "exitBigPicture" }; // con Select/Guide
  const PAD_HELP = [
    [["a"], "Conferma / apri"], [["b"], "Indietro"], [["x"], "Preferito"], [["y"], "Cerca"],
    [["lb", "rb"], "Categoria precedente / successiva"], [["lt", "rt"], "Pagina su / giù"],
    [["start"], "Menu della schermata"], [["l3"], "Torna alla Home"], [["r3"], "Mostra/nascondi la legenda"],
    [["back"], "Elenco delle scorciatoie (tieni premuto 1 s: esci da Big Picture)"],
    [["back", "a"], "Musica: play/pausa"], [["back", "rb"], "Musica: brano successivo"], [["back", "lb"], "Musica: brano precedente"],
    [["back", "x"], "Discord: microfono muto"], [["back", "y"], "Discord: audio disattivato"], [["back", "b"], "Esci da Big Picture"],
  ];
  const PAD_DEADZONE = 0.25, PAD_THRESHOLD = 0.55;

  /** Stato logico di un pad: pressed(i) dice se il pulsante i e' premuto, axes sono gli assi (stick con zona morta radiale). */
  function padState(pressed, axes = [], dz = PAD_DEADZONE, th = PAD_THRESHOLD) {
    const stick = (x, y) => (Math.hypot(x || 0, y || 0) < dz ? [0, 0] : [x || 0, y || 0]);
    const [lx, ly] = stick(axes[0], axes[1]), [, ry] = stick(axes[2], axes[3]);
    const b = (k) => !!pressed(PAD_BTN[k]);
    const s = {};
    for (const k of ["a", "b", "x", "y", "lb", "rb", "lt", "rt", "select", "start", "l3", "r3", "guide"]) s[k] = b(k);
    s.left = b("left") || lx < -th; s.right = b("right") || lx > th;
    s.up = b("up") || ly < -th; s.down = b("down") || ly > th;
    s.scrollUp = ry < -th; s.scrollDown = ry > th;
    return s;
  }
  const padPressed = (p) => (i) => !!p.buttons[i]?.pressed || (i === 6 || i === 7 ? (p.buttons[i]?.value || 0) > 0.5 : false);
  /** Unisce piu' pad collegati: un tasto e' premuto se lo e' su uno qualsiasi. */
  function padStateAll(pads, dz, th) {
    const out = {};
    for (const p of pads) for (const [k, v] of Object.entries(padState(padPressed(p), p.axes, dz, th))) out[k] = out[k] || v;
    return out;
  }
  const isPlayStation = (id) => /054c|sony|dualsense|dualshock|wireless controller/i.test(id || "");

  /* ---- tastiera */
  const MODIFIER_KEYS = ["Control", "Shift", "Alt", "Meta", "AltGraph", "Dead", "OS", "CapsLock"];

  /** Evento -> combo canonico ("Mod+Alt+Shift+Tasto"); "" se non e' una combinazione utilizzabile. */
  function comboFromEvent(e, mac = MAC) {
    const mod = mac ? e.metaKey : e.ctrlKey;
    if (mac ? e.ctrlKey : e.metaKey) return ""; // Ctrl su Mac / Windows-key: non usati
    if (e.getModifierState?.("AltGraph")) return ""; // AltGr = Ctrl+Alt su Windows: servirebbe a scrivere simboli
    let k = e.key;
    if (!k || MODIFIER_KEYS.includes(k)) return "";
    if ((mod || e.altKey) && /^(Key[A-Z]|Digit\d)$/.test(e.code || "")) k = e.code.slice(-1); // con Alt su Mac il tasto cambia carattere
    else if (k === " ") k = "Space";
    else if (k.length === 1) k = k.toUpperCase();
    const symbol = k.length === 1 && !/[A-Z0-9]/.test(k); // "?" "/" ",": lo Shift e' gia' nel carattere
    return [mod && "Mod", e.altKey && "Alt", e.shiftKey && !symbol && "Shift", k].filter(Boolean).join("+");
  }

  const KEY_NAMES = { ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓", Escape: "Esc", Space: "Spazio" };
  /** Combo -> testo da mostrare: ⌘⇧B su Mac, Ctrl+Shift+B altrove. */
  function formatCombo(combo, mac = MAC) {
    const parts = String(combo).split(/\+(?=.)/);
    if (mac) return parts.map((p) => ({ Mod: "⌘", Alt: "⌥", Shift: "⇧" }[p] || KEY_NAMES[p] || p)).join("");
    return parts.map((p) => ({ Mod: "Ctrl" }[p] || KEY_NAMES[p] || p)).join("+");
  }

  let overrides = {};
  try { overrides = JSON.parse(root.localStorage?.getItem("gs.shortcuts") || "{}") || {}; } catch { overrides = {}; }
  const keysOf = (entry, ov = overrides) => (Array.isArray(ov[entry.id]) ? ov[entry.id] : entry.keys);
  const inScope = (entry, scope) => entry.scope === "both" || entry.scope === scope;

  /** Voce del registro che risponde a una combo in quel contesto (solo i tasti personalizzabili, non i "fixed"). */
  function findAction(combo, scope, ov = overrides, registry = REGISTRY) {
    if (!combo) return null;
    return registry.find((en) => inScope(en, scope) && keysOf(en, ov).includes(combo)) || null;
  }
  /** Combo gia' usata da un'altra voce visibile nello stesso contesto (null se libera). */
  function conflictOf(id, combo, ov = overrides, registry = REGISTRY) {
    const me = registry.find((en) => en.id === id);
    return registry.find((en) => en.id !== id && (en.scope === "both" || me.scope === "both" || en.scope === me.scope)
      && [...keysOf(en, ov), ...(en.fixed || [])].includes(combo)) || null;
  }
  const isTyping = (el) => !!el && (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || !!el.isContentEditable);
  /** In un campo di testo passano solo le voci "typing" con Mod: il resto e' scrittura normale. */
  const allowedWhileTyping = (entry, combo) => !!entry.typing && combo.startsWith("Mod+");

  function saveOverrides(next) {
    overrides = next;
    try { root.localStorage?.setItem("gs.shortcuts", JSON.stringify(overrides)); } catch { /* spazio non disponibile */ }
  }

  /* ---- collegamento agli eventi */
  const handlers = {};
  let capturing = false;
  function dispatch(e, scope) {
    if (capturing || e.defaultPrevented || e.isComposing || e.repeat) return false;
    const combo = comboFromEvent(e);
    const entry = findAction(combo, scope);
    if (!entry) return false;
    const typing = isTyping(e.target);
    if (typing && !allowedWhileTyping(entry, combo)) return false;
    if (!typing && !entry.typing && document.querySelector("dialog[open]") && entry.id !== "back") return false;
    const run = handlers[scope]?.[entry.id];
    const res = run ? run(e) : false;
    if (res === false) return false;
    if (res instanceof Promise) res.catch((err) => root.GS?.toast?.(err.message, true));
    e.preventDefault();
    return true;
  }
  function bind(scope, map) {
    handlers[scope] = { ...handlers[scope], ...map };
    for (const id of MEDIA_IDS) handlers[scope][id] = () => runMedia(id);
  }
  /** Azioni musica/Discord di window.PozzoMedia, se presente (false = non gestito, il tasto resta al browser). */
  function runMedia(name) {
    const fn = root.PozzoMedia?.[name];
    if (typeof fn !== "function") return false;
    try { fn.call(root.PozzoMedia); } catch (err) { root.GS?.toast?.(err.message, true); }
    return true;
  }

  const PS = { REGISTRY, MEDIA_IDS, PAD_BTN, PAD_CHORDS, PAD_HELP, PAD_DEADZONE, PAD_THRESHOLD, isMacPlatform, MAC, padState,
    padStateAll, isPlayStation, comboFromEvent, formatCombo, findAction, conflictOf, keysOf, isTyping, allowedWhileTyping,
    dispatch, bind, runMedia, saveOverrides, getOverrides: () => overrides,
    keyLabel: (id) => { const en = REGISTRY.find((x) => x.id === id); const k = en && (keysOf(en)[0] || en.fixed?.[0]); return k ? formatCombo(k) : ""; } };
  root.PozzoShortcuts = PS;
  if (typeof module !== "undefined" && module.exports) module.exports = PS;
  if (typeof document === "undefined") return;

  /* ---- pannello con l'elenco (e personalizzazione), valido per desktop e Big Picture */
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const STYLE = `#sc-dlg { width: min(640px, 94vw); max-height: 86vh; padding: 0; border: 1px solid var(--line, #262b3a); border-radius: 12px;
      background: var(--panel, #171a23); color: var(--text, #e7e9ee); }
    #sc-dlg::backdrop { background: rgba(0,0,0,.55); }
    #sc-dlg .sc-in { padding: 16px 20px; max-height: 86vh; overflow: auto; }
    #sc-dlg h3 { margin: 14px 0 6px; font-size: 13px; color: var(--muted, #8b92a5); text-transform: uppercase; letter-spacing: .04em; }
    #sc-dlg table { width: 100%; border-collapse: collapse; font-size: 13px; }
    #sc-dlg td { padding: 5px 6px; border-bottom: 1px solid var(--line, #262b3a); vertical-align: middle; }
    #sc-dlg kbd { display: inline-block; padding: 1px 7px; margin-right: 4px; border: 1px solid var(--line, #262b3a); border-radius: 5px;
      background: var(--bg-3, #1c2030); font: 12px/1.6 inherit; }
    #sc-dlg .sc-act { text-align: right; white-space: nowrap; }
    #sc-dlg button { font: inherit; font-size: 12px; cursor: pointer; }
    #mb-drop .ac { margin-left: auto; padding-left: 24px; color: var(--muted, #8b92a5); }`;
  document.head.appendChild(Object.assign(document.createElement("style"), { textContent: STYLE }));

  const kbds = (keys) => keys.map((k) => `<kbd>${h(formatCombo(k))}</kbd>`).join("");
  function panelHtml() {
    const rows = REGISTRY.filter((en) => inScope(en, "desktop"));
    const groups = [...new Set(rows.map((en) => en.group))];
    const body = groups.map((g) => `<h3>${h(g)}</h3><table>${rows.filter((en) => en.group === g).map((en) => {
      const keys = keysOf(en), custom = Array.isArray(overrides[en.id]);
      return `<tr><td>${h(en.label)}${MEDIA_IDS.includes(en.id) && !root.PozzoMedia ? ' <span style="color:var(--muted)">(non disponibile)</span>' : ""}</td>
        <td>${kbds([...keys, ...(en.fixed || [])]) || "—"}</td>
        <td class="sc-act">${en.keys.length ? `<button type="button" data-sc-edit="${en.id}">Cambia</button>` : ""}
        ${custom ? `<button type="button" data-sc-reset="${en.id}">Ripristina</button>` : ""}</td></tr>`;
    }).join("")}</table>`).join("");
    const pad = `<h3>Controller (Big Picture)</h3><table>${PAD_HELP.map(([k, l]) =>
      `<tr><td>${k.map((x) => `<kbd>${h(({ back: "Select / View", lb: "LB", rb: "RB", lt: "LT", rt: "RT", start: "Start", l3: "L3", r3: "R3" }[x]) || x.toUpperCase())}</kbd>`).join("+")}</td><td>${h(l)}</td></tr>`).join("")}</table>`;
    return `<div class="sc-in"><div style="display:flex;justify-content:space-between;align-items:center">
      <b style="font-size:16px">Scorciatoie da tastiera · ${MAC ? "macOS (⌘ = Cmd)" : "Windows (Ctrl)"}</b>
      <button type="button" data-sc-close>✕</button></div>
      <p style="color:var(--muted);font-size:12px;margin:6px 0 0">«Cambia» imposta una nuova combinazione (Esc annulla). Le scorciatoie non scattano mentre scrivi in un campo.
      In Big Picture valgono anche il controller e queste tastiere.</p>${body}${pad}
      <p style="margin-top:12px"><button type="button" data-sc-reset-all>Ripristina tutte</button></p></div>`;
  }

  function closePanel() { document.getElementById("sc-dlg")?.close(); }
  function openPanel() {
    let dlg = document.getElementById("sc-dlg");
    if (dlg?.open) return closePanel();
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "sc-dlg";
      document.body.appendChild(dlg);
      dlg.addEventListener("click", (ev) => {
        if (ev.target === dlg || ev.target.closest("[data-sc-close]")) return dlg.close();
        const edit = ev.target.closest("[data-sc-edit]")?.dataset.scEdit;
        if (edit) return capture(dlg, edit, ev.target.closest("button"));
        const reset = ev.target.closest("[data-sc-reset]")?.dataset.scReset;
        if (reset) { const { [reset]: _, ...rest } = overrides; saveOverrides(rest); dlg.innerHTML = panelHtml(); }
        else if (ev.target.closest("[data-sc-reset-all]")) { saveOverrides({}); dlg.innerHTML = panelHtml(); }
      });
    }
    dlg.innerHTML = panelHtml();
    dlg.showModal();
  }

  function capture(dlg, id, btn) {
    capturing = true;
    btn.textContent = "Premi i tasti…";
    const done = () => { capturing = false; document.removeEventListener("keydown", onKey, true); dlg.innerHTML = panelHtml(); };
    const onKey = (ev) => {
      if (MODIFIER_KEYS.includes(ev.key)) return;
      ev.preventDefault(); ev.stopPropagation();
      if (ev.key === "Escape") return done();
      const combo = comboFromEvent(ev);
      const other = combo && conflictOf(id, combo);
      if (!combo || /^(Enter|Tab|Backspace|Space)$/.test(combo)) { btn.textContent = "Combinazione non valida"; return; }
      if (other) { btn.textContent = `Già usata: ${other.label}`; return; }
      saveOverrides({ ...overrides, [id]: [combo] });
      done();
    };
    document.addEventListener("keydown", onKey, true);
  }
  PS.openPanel = openPanel;
  PS.closePanel = closePanel;
  document.addEventListener("click", (e) => { if (e.target.closest("[data-sc-open]")) openPanel(); });

  /* ---- azioni del desktop: solo se c'e' app.js (funzioni globali dello stesso ambito) */
  if (typeof setView !== "function" || typeof S === "undefined") return;
  const leaveLayers = () => { if (settingsOpen()) closeSettings(); if (S.detail) closeDetail(); };
  const cycle = (list, current) => list[(Math.max(0, list.findIndex((x) => x.id === current)) + 1) % list.length];
  bind("desktop", {
    search: () => { leaveLayers(); const el = $("#search"); el.focus(); el.select(); },
    settings: () => { openSettings(); },
    viewAll: () => { leaveLayers(); setView({ type: "all" }); },
    viewFav: () => { leaveLayers(); setView({ type: "favorites" }); },
    viewShop: () => { leaveLayers(); setView({ type: "shop" }); },
    sidebar: () => {
      if (!usesDrawer()) { toast("In questa grafica la barra laterale è sempre visibile"); return true; }
      setDrawer(!$("#sidebar").classList.contains("drawer-open"));
    },
    back: () => {
      if (settingsOpen()) return closeSettings();
      if (S.detail) return closeDetail();
      return false; // niente da chiudere: Alt+← resta la navigazione del browser
    },
    scanNew: () => window.GSMenu.scan("new"),
    favorite: () => { if (!S.detail || !$("#d-fav")) return false; $("#d-fav").click(); },
    bigPicture: () => enterBigPicture(),
    help: () => openPanel(),
    nextTheme: async () => {
      const ext = await api("/api/extensions"), next = cycle(ext.themes, ext.active_theme);
      await api("/api/app/theme", { body: { theme: next.id } });
      await loadExtensions();
      toast(`Tema: ${next.name}`);
    },
    nextExperience: async () => {
      const ext = await api("/api/extensions");
      const next = cycle(ext.experiences.filter((x) => x.available), GS.experience.id);
      await api("/api/app/experience", { body: { experience: next.id } });
      store.set("view", GS.experiences.get(next.id)?.home ? { type: "home" } : { type: "all" });
      location.reload();
    },
  });
  document.addEventListener("keydown", (e) => { dispatch(e, "desktop"); });
  const sb = $("#search");
  if (sb) sb.title = `Cerca (${PS.keyLabel("search")} oppure /)`;
})();
