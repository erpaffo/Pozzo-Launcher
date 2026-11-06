"use strict";
/* Pozzo Launcher: schermata «Chi gioca?» (desktop e Big Picture) e dialogo di modifica dei profili.
 * Libreria, metadati e copertine sono UNA sola copia comune: qui si cambia solo il profilo attivo (POST /api/profiles/active)
 * e poi la pagina ricarica quello che il server restituisce per quel profilo (opts.onChange, di solito applyProfile()).
 * Se le route dei profili non esistono, tutto degrada in silenzio (nessuna schermata, nessun errore).
 * La logica (richieste, messaggi, navigazione) e' esportata anche per i test con node. */
(() => {
  const root = typeof window !== "undefined" ? window : globalThis;
  const AVATARS = ["🙂", "😎", "🦊", "🐱", "🐶", "🐼", "🦄", "🐙", "🚀", "👾", "🎮", "⭐"];
  const COLORS = ["#5b8cff", "#8b72ff", "#3ecf8e", "#f5b84a", "#ff6b6b", "#ff8fd0", "#36c5d6", "#9aa3b8"];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ---- rete e messaggi (testabili senza DOM) */
  async function req(path, method = "GET", body) {
    let r;
    try {
      r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch { return { status: 0, ok: false, data: {}, retry: 0 }; }
    let data = {};
    try { data = await r.json(); } catch { /* risposta non JSON */ }
    return { status: r.status, ok: r.ok, data: data || {}, retry: Number(r.headers?.get?.("Retry-After")) || 0 };
  }
  function errText(res) {
    if (res.status === 429) return t("i.pp.tooMany", { s: res.retry || 30 });
    if (res.status === 403 && (res.data.error === "pin" || !res.data.detail)) return t("i.pp.wrongPin");
    if (res.status === 404) return t("i.pp.notFound");
    if (res.status === 0) return t("i.pp.unreachable");
    return res.data.detail || res.data.error || t("i.pp.error", { s: res.status });
  }
  /** Elenco dei profili, o null se la route manca o il server non risponde. */
  async function load() {
    const r = await req("/api/profiles");
    return r.ok && Array.isArray(r.data.profiles) ? r.data : null;
  }
  // `remembered`: questo dispositivo ha scelto «entra sempre con lo stesso profilo» (e il PIN, se c'e', e' sbloccato)
  const shouldAutoOpen = (d) => !!d && d.ask === true && d.profiles.length >= 2 && !d.remembered;
  // remember true/false (solo se la casella c'e'): ricorda / dimentica la scelta su questo dispositivo
  const choose = (id, pin, remember) => req("/api/profiles/active", "POST",
    { id, ...(pin ? { pin } : {}), ...(typeof remember === "boolean" ? { remember } : {}) });

  /* ---- navigazione col fuoco: il pulsante piu' vicino nella direzione richiesta (rettangoli, senza DOM) */
  function neighbor(rects, i, dir) {
    const c = rects[i];
    if (!c) return rects.length ? 0 : -1;
    const cx = c.left + c.width / 2, cy = c.top + c.height / 2;
    let best = -1, bestScore = Infinity;
    rects.forEach((r, k) => {
      if (k === i) return;
      const dx = r.left + r.width / 2 - cx, dy = r.top + r.height / 2 - cy;
      const along = { left: -dx, right: dx, up: -dy, down: dy }[dir], across = dir === "left" || dir === "right" ? Math.abs(dy) : Math.abs(dx);
      if (along <= 1) return;
      const score = along + across * 3;
      if (score < bestScore) { bestScore = score; best = k; }
    });
    return best < 0 ? i : best;
  }
  const PAD_MAP = { 0: "a", 1: "b", 2: "x", 9: "start", 12: "up", 13: "down", 14: "left", 15: "right" };

  const st = { open: false, el: null, view: null, opts: {}, data: null, manage: false, pin: "", busy: false, timer: 0, raf: 0, held: {}, prevFocus: null };
  const api = { req, errText, load, shouldAutoOpen, choose, neighbor, PAD_MAP, AVATARS, COLORS, autoDone: false, isOpen: () => st.open };

  /* ---- interfaccia */
  const $ = (s, el = st.el) => el?.querySelector(s);
  const btns = () => [...st.el.querySelectorAll("button:not([disabled]), input")].filter((b) => !b.hidden);
  const live = (t) => { const n = $("#pp-live"); if (n) n.textContent = t; };
  const tile = (p, extra = "") => `<button type="button" class="pp-tile" data-pid="${esc(p.id)}" aria-label="${esc(p.name)}${p.locked ? t("i.pp.lockedAria") : ""}">`
    + `<span class="pp-av" style="background:${esc(p.color || "#5b8cff")}">${esc(p.avatar || "👤")}${p.locked ? '<i class="pp-lock" aria-hidden="true">🔒</i>' : ""}</span>`
    + `<span class="pp-name">${esc(p.name)}</span>${extra}</button>`;

  function setView(name, html, back) {
    st.view = { name, back };
    $("#pp-body").innerHTML = html;
    $("#pp-live").textContent = "";
    (btns()[0] || $("#pp-body")).focus?.();
  }

  function close() {
    if (!st.open) return;
    st.open = false;
    clearInterval(st.timer);
    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(st.raf);
    st.el.remove();
    st.prevFocus?.focus?.();
  }

  function showPicker() {
    const ps = st.data.profiles;
    setView("pick", `<h1 id="pp-title">${t("i.pp.who")}</h1>
      <div class="pp-grid" role="group" aria-label="${t("i.pp.profiles")}">${ps.map((p) => tile(p, st.manage ? '<span class="pp-edit" aria-hidden="true">✎</span>' : "")).join("")}
        <button type="button" class="pp-tile pp-new" data-act="new" aria-label="${t("i.pp.new")}"><span class="pp-av">＋</span><span class="pp-name">${t("i.pp.new")}</span></button></div>
      <p class="pp-hint muted">${st.manage ? t("i.pp.pickManage") : t("i.pp.pickHint")}</p>
      ${st.manage ? "" : `<label class="pp-remember"><input type="checkbox" id="pp-remember"${st.data.remembered ? " checked" : ""}> ${t("i.pp.remember")}</label>`}
      <div class="pp-row"><button type="button" class="pp-btn" data-act="manage" aria-pressed="${st.manage}">${st.manage ? t("i.pp.done") : t("i.pp.manage")}</button>
      <button type="button" class="pp-btn" data-act="close">${t("i.pp.close")}</button></div>`, close);
    ([...st.el.querySelectorAll("[data-pid]")].find((b) => b.dataset.pid === st.data.active) || btns()[0])?.focus?.();
  }

  async function reloadList() { const d = await load(); if (d) st.data = d; }

  /* tastierino del PIN: submit(pin) -> risposta di req(); in caso di successo chiama done(res) */
  function showPin(p, submit, done, back = showPicker) {
    st.pin = "";
    const keys = [1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button type="button" class="pp-key" data-d="${n}">${n}</button>`).join("")
      + `<button type="button" class="pp-key" data-act="del" aria-label="${t("i.pp.delAria")}">⌫</button><button type="button" class="pp-key" data-d="0">0</button>`
      + `<button type="button" class="pp-key pp-ok" data-act="ok">OK</button>`;
    setView("pin", `<div class="pp-pinwho">${tile({ ...p, locked: false })}</div><h1 id="pp-title">${t("i.pp.pinOf", { name: esc(p.name) })}</h1>
      <div class="pp-dots" id="pp-dots" role="img" aria-label="${t("i.pp.digitsIn", { n: 0 })}"></div>
      <p class="pp-err" id="pp-err" role="alert"></p>
      <div class="pp-pad" role="group" aria-label="${t("i.pp.keypad")}">${keys}</div>
      <div class="pp-row"><button type="button" class="pp-btn" data-act="back">${t("i.pp.back")}</button></div>`, back);
    const dots = () => { const d = $("#pp-dots"); d.textContent = "●".repeat(st.pin.length) || "–"; d.setAttribute("aria-label", t("i.pp.digitsIn", { n: st.pin.length })); };
    dots();
    const ctl = {
      digit(n) { if (!st.busy && st.pin.length < 8) { st.pin += n; dots(); $("#pp-err").textContent = ""; } },
      del() { st.pin = st.pin.slice(0, -1); dots(); },
      async ok() {
        if (st.busy || st.pin.length < 4) { $("#pp-err").textContent = t("i.pp.pinLength"); return; }
        st.busy = true;
        const res = await submit(st.pin);
        st.busy = false;
        if (res.ok) return done(res);
        st.pin = ""; dots();
        const err = $("#pp-err");
        if (!err) return;
        err.textContent = errText(res);
        live(err.textContent);
        if (res.status === 429) { // blocco temporaneo: tastierino fermo e conto alla rovescia
          let n = res.retry || 30;
          const lock = (on) => st.el.querySelectorAll(".pp-key").forEach((k) => { k.disabled = on; });
          lock(true);
          clearInterval(st.timer);
          st.timer = setInterval(() => {
            n -= 1;
            if (n <= 0 || !$("#pp-err")) { clearInterval(st.timer); if ($("#pp-err")) { lock(false); $("#pp-err").textContent = ""; btns()[0]?.focus?.(); } return; }
            $("#pp-err").textContent = errText({ status: 429, retry: n, data: {} });
          }, 1000);
        }
      },
    };
    st.view.pin = ctl;
  }

  async function pick(id) {
    const p = st.data.profiles.find((x) => x.id === id);
    if (!p) return;
    if (st.manage) return editDialog(p, { onDone: afterManage });
    // la casella si legge ora: con il PIN la vista cambia e sparisce
    const box = $("#pp-remember"), remember = box ? box.checked : undefined;
    if (id === st.data.active) {
      if (remember !== undefined && remember !== !!st.data.remembered) await req("/api/profiles/remember", "POST", { remember });
      return close();
    }
    const finish = async () => { close(); await (st.opts.onChange || (() => location.reload()))(id); };
    if (p.locked) return showPin(p, (pin) => choose(id, pin, remember), finish);
    const res = await choose(id, undefined, remember);
    if (res.ok) return finish();
    if (res.status === 404) await reloadList();
    showPicker();
    $(".pp-hint").textContent = errText(res);
    live(errText(res));
  }

  // dopo una modifica dal «Gestisci»: aggiorna elenco e pulsante; se il profilo attivo e' sparito, passa a quello nuovo
  async function afterManage() {
    const old = st.data.active;
    await reloadList();
    await root.loadProfile?.();
    if (st.data.active !== old) { close(); await (st.opts.onChange || (() => location.reload()))(st.data.active); } else showPicker();
  }

  /* dialogo di modifica/creazione: nome, avatar, colore, PIN (campo password vero), elimina */
  function editDialog(p, { onDone } = {}) {
    const isNew = !p;
    const go = () => ensure(() => {
      const cur = p || { name: "", avatar: AVATARS[0], color: COLORS[0], locked: false };
      let avatar = cur.avatar || AVATARS[0], color = cur.color || COLORS[0];
      const back = () => (onDone ? onDone() : close());
      setView("form", `<form id="pp-form" autocomplete="off"><h1 id="pp-title">${isNew ? t("i.pp.new") : t("i.pp.editNamed", { name: esc(cur.name) })}</h1>
        <label class="pp-f">${t("i.common.name")} <input name="name" maxlength="40" required value="${esc(cur.name)}"></label>
        <div class="pp-f">${t("i.pp.avatar")} <div class="pp-choices" role="radiogroup" aria-label="${t("i.pp.avatar")}">${AVATARS.map((a) => `<button type="button" role="radio" class="pp-ch" data-av="${a}" aria-checked="${a === avatar}">${a}</button>`).join("")}</div>
          <input name="avatar" maxlength="8" value="${esc(avatar)}" aria-label="${t("i.pp.avatarEmoji")}"></div>
        <div class="pp-f">${t("i.pp.color")} <div class="pp-choices" role="radiogroup" aria-label="${t("i.pp.color")}">${COLORS.map((c) => `<button type="button" role="radio" class="pp-ch pp-sw" data-co="${c}" style="background:${c}" aria-label="${c}" aria-checked="${c === color}"></button>`).join("")}</div></div>
        <label class="pp-f">${cur.locked ? t("i.pp.newPin") : t("i.pp.pin")}
          <input name="pin" type="password" inputmode="numeric" pattern="[0-9]{4,8}" maxlength="8" autocomplete="new-password"></label>
        ${cur.locked ? '<label class="pp-f chk"><input type="checkbox" name="nopin"> ' + t("i.pp.removePin") + '</label>' : ""}
        <p class="pp-hint muted">${t("i.pp.pinNote")}</p>
        <p class="pp-err" id="pp-err" role="alert"></p>
        <div class="pp-row"><button type="submit" class="pp-btn pp-primary">${t("i.common.save")}</button><button type="button" class="pp-btn" data-act="back">${t("i.pp.cancel")}</button>
          ${!isNew && cur.id !== "default" ? '<button type="button" class="pp-btn pp-danger" data-act="del">' + t("i.pp.delete") + '</button>' : ""}</div></form>`, back);
      const f = $("#pp-form");
      const mark = (attr, val) => f.querySelectorAll(`[${attr}]`).forEach((b) => b.setAttribute("aria-checked", String(b.getAttribute(attr) === val)));
      f.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (b?.dataset.av) { avatar = b.dataset.av; f.avatar.value = avatar; mark("data-av", avatar); }
        if (b?.dataset.co) { color = b.dataset.co; mark("data-co", color); }
        if (b?.dataset.act === "back") back();
        if (b?.dataset.act === "del") remove(cur, back);
      });
      f.avatar.addEventListener("input", () => { avatar = f.avatar.value.trim(); mark("data-av", avatar); });
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = f.name.value.trim(), pin = f.pin.value;
        const err = (t) => { $("#pp-err").textContent = t; live(t); };
        if (!name) return err(t("i.pp.writeName"));
        if (pin && !/^\d{4,8}$/.test(pin)) return err(t("i.pp.pinLength"));
        const body = { name, avatar: f.avatar.value.trim() || AVATARS[0], color };
        if (pin) body.pin = pin; else if (f.nopin?.checked) body.pin = "";
        let id = cur.id, res;
        if (isNew) {
          res = await req("/api/profiles", "POST", { name });
          if (res.ok) id = res.data.created?.id;
        }
        if (!isNew || res.ok) res = await req(`/api/profiles/${encodeURIComponent(id)}`, "PATCH", body);
        if (!res.ok) return err(errText(res));
        (st.opts.toast || root.toast)?.(isNew ? t("i.pp.created") : t("i.pp.updated"));
        back();
      });
    });
    // un profilo protetto si modifica solo dopo aver inserito il PIN
    const ensure = (next) => (p?.locked ? showPin(p, (pin) => req(`/api/profiles/${encodeURIComponent(p.id)}/unlock`, "POST", { pin }), next, solo ? close : showPicker) : next());
    const solo = !st.open;
    if (solo) openShell();
    go();
  }

  async function remove(p, back) {
    if (!(root.confirm?.(t("i.pp.confirmDelete", { name: p.name })) ?? true)) return;
    const res = await req(`/api/profiles/${encodeURIComponent(p.id)}`, "DELETE");
    if (!res.ok) { $("#pp-err").textContent = errText(res); return; }
    (st.opts.toast || root.toast)?.(t("i.pp.deleted"));
    st.removed = p.id;
    back();
  }

  /* ---- guscio a tutto schermo, tastiera e controller */
  function openShell(opts = {}) {
    if (st.open) return;
    st.opts = { ...st.opts, ...opts };
    st.open = true;
    st.prevFocus = document.activeElement;
    const el = document.createElement("div");
    el.id = "pp";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-labelledby", "pp-title");
    el.innerHTML = `<div id="pp-body" tabindex="-1"></div><div id="pp-live" class="sr-only" role="status" aria-live="polite"></div>`;
    document.body.appendChild(el);
    st.el = el;
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || st.view.name === "form") return;
      const a = b.dataset.act;
      if (b.dataset.pid) pick(b.dataset.pid);
      else if (a === "new") editDialog(null, { onDone: afterManage });
      else if (a === "manage") { st.manage = !st.manage; showPicker(); }
      else if (a === "close") close();
      else if (a === "back") st.view.back();
      else if (b.dataset.d !== undefined) st.view.pin?.digit(b.dataset.d);
      else if (a === "del") st.view.pin?.del();
      else if (a === "ok") st.view.pin?.ok();
    });
    if (typeof Pad === "undefined" && typeof navigator !== "undefined" && navigator.getGamepads) pollOwnPad();
  }

  /** Azione logica: left/right/up/down/a/b/x(cancella)/start(OK). */
  function act(a) {
    if (!st.open) return false;
    const v = st.view;
    if (["left", "right", "up", "down"].includes(a)) {
      const list = btns(), i = list.indexOf(document.activeElement);
      const to = neighbor(list.map((b) => b.getBoundingClientRect()), i < 0 ? 0 : i, a);
      list[to]?.focus();
    } else if (a === "a") document.activeElement?.click?.();
    else if (a === "b") v.back?.();
    else if (v.name === "pin" && a === "x") v.pin.del();
    else if (v.name === "pin" && a === "start") v.pin.ok();
    return true;
  }

  function onKey(e) {
    if (!st.open) return;
    e.stopPropagation(); // sotto la schermata non scattano scorciatoie
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const typing = /^(INPUT|TEXTAREA)$/.test(e.target?.tagName || "") && e.target.type !== "checkbox";
    if (e.key === "Escape") { e.preventDefault(); return act("b"); }
    if (e.key === "Tab") {
      const list = btns(), i = list.indexOf(document.activeElement), n = list.length;
      e.preventDefault();
      list[(i + (e.shiftKey ? -1 : 1) + n) % n]?.focus();
      return;
    }
    if (st.view.name === "pin") {
      if (/^\d$/.test(e.key)) { e.preventDefault(); return st.view.pin.digit(e.key); }
      if (e.key === "Backspace") { e.preventDefault(); return st.view.pin.del(); }
      if (e.key === "Enter" && !e.target?.dataset?.d && !e.target?.dataset?.act) { e.preventDefault(); return st.view.pin.ok(); }
    }
    if (typing) return; // nei campi di testo le frecce muovono il cursore
    const dir = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" }[e.key];
    if (dir) { e.preventDefault(); act(dir); }
  }

  // senza pad.js (desktop) legge il controller da solo, solo finche' la schermata e' aperta
  function pollOwnPad() {
    const tick = () => {
      if (!st.open) return;
      const pad = [...navigator.getGamepads()].find((p) => p && p.connected);
      if (pad) {
        const on = {};
        for (const [i, a] of Object.entries(PAD_MAP)) if (pad.buttons[i]?.pressed) on[a] = true;
        const [x, y] = [pad.axes[0] || 0, pad.axes[1] || 0];
        if (x < -0.6) on.left = true; if (x > 0.6) on.right = true; if (y < -0.6) on.up = true; if (y > 0.6) on.down = true;
        for (const a of Object.keys({ ...st.held, ...on })) { if (on[a] && !st.held[a]) act(a); }
        st.held = on;
      }
      st.raf = requestAnimationFrame(tick);
    };
    st.raf = requestAnimationFrame(tick);
  }

  /* ---- API pubblica */
  api.open = async (opts = {}) => {
    if (st.open) return false;
    const d = await load();
    if (!d) { (opts.toast || root.toast)?.(t("i.pp.unavailable"), true); return false; }
    st.data = d; st.manage = false;
    openShell(opts);
    showPicker();
    return true;
  };
  /** All'avvio: solo con ask=true e almeno due profili, una volta per apertura della pagina. */
  api.autoOpen = async (opts = {}) => {
    if (api.autoDone) return false;
    api.autoDone = true;
    const d = await load();
    if (!shouldAutoOpen(d)) return false;
    st.data = d; st.manage = false;
    openShell(opts);
    showPicker();
    return true;
  };
  api.edit = (p, opts = {}) => { st.opts = { ...st.opts, ...opts }; return editDialog(p, { onDone: async () => { close(); await opts.onDone?.(); } }); };
  api.pad = act;
  api.key = onKey;
  api.close = close;
  root.GSProfilePicker = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined" || typeof module !== "undefined") return;
  document.addEventListener("keydown", onKey, true);
  // da Big Picture il controller passa da Pad: input() in bigpicture.js chiama GSProfilePicker.pad
  const start = () => api.autoOpen({ onChange: root.applyProfile });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else setTimeout(start, 0);
})();
