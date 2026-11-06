/* Splash all'avvio: logo, barra di avanzamento e fase letti da GET /api/boot.
   Se manca, ripiega su /api/status fino alla prima libreria pronta; timeout ed errori offrono Continua.
   Il CSS si carica qui, senza modifiche a index.html / bigpicture.html. */
(() => {
  "use strict";
  const POLL_MS = 300;
  const SHOW_AFTER_MS = 150;
  const REQUEST_TIMEOUT_MS = 1200;
  const MAX_MS = 30000;
  const root = document.documentElement;
  const bigPicture = location.pathname.startsWith("/bigpicture");

  /** Riepilogo di /api/boot: frazione 0..1, fase corrente ed eventuale errore. */
  function summarize(boot) {
    const steps = Array.isArray(boot?.steps) ? boot.steps : [];
    const err = steps.find((s) => s.state === "error");
    const run = steps.find((s) => s.state === "running") || steps.find((s) => s.state === "pending");
    const p = Number(boot?.progress);
    const done = steps.filter((s) => s.state === "done" || s.state === "error").length;
    const progress = boot?.ready ? 1 : Number.isFinite(p) ? Math.min(1, Math.max(0, p)) : steps.length ? done / steps.length : 0;
    return {
      progress,
      error: err ? t("b.splash.error", {nome: err.message || err.label || err.id}) : "",
      label: run ? t("b.splash.step", {stato: run.state === "pending" ? t("b.splash.waiting") : t("b.core.status.playing"), nome: run.label || run.id}) : t("b.common.starting"),
    };
  }

  if (typeof window !== "undefined") window.GSSplash = { summarize };
  if (typeof document === "undefined" || !document.body) return;
  const version = root.dataset.v || new URL(document.currentScript.src, location.href).searchParams.get("v");
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/splash.css" + (version ? `?v=${encodeURIComponent(version)}` : "");
  document.head.appendChild(style);

  const el = document.createElement("div");
  el.id = "boot-splash";
  el.className = bigPicture ? "bs-bp" : "";
  el.innerHTML = `<div class="bs-box">
      <img class="bs-logo" src="/static/m/icon.png" alt="" width="96" height="96">
      <div class="bs-name">Pozzo Launcher</div>
      <div class="bs-bar" role="progressbar" aria-label="Avvio di Pozzo Launcher" data-i18n-aria="b.splash.aria" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i class="bs-fill"></i></div>
      <p class="bs-msg" role="status" aria-live="polite" aria-atomic="true"></p>
      <button type="button" class="bs-ok" data-i18n="b.splash.continue" hidden>Continua</button>
    </div>`;
  const bar = el.querySelector(".bs-bar"), fill = el.querySelector(".bs-fill"), msg = el.querySelector(".bs-msg"), ok = el.querySelector(".bs-ok");

  let timer = 0, showTimer = 0, capTimer = 0, done = false, stopped = false, hasError = false, lastMsg = null;
  const quiet = () => root.dataset.motion === "off" || root.dataset.motion === "reduced";

  function paint(s) {
    const pct = Math.round(s.progress * 100);
    bar.setAttribute("aria-valuenow", String(pct));
    fill.style.transform = `scaleX(${s.progress})`;
    hasError = !!s.error;
    const text = s.error || s.label;
    if (text !== lastMsg) msg.textContent = lastMsg = text; // aria-live annuncia solo i cambi
    msg.classList.toggle("err", hasError);
    ok.hidden = !hasError;
  }

  function finish() {
    if (done) return;
    done = true;
    clearTimeout(timer); clearTimeout(showTimer); clearTimeout(capTimer);
    if (quiet()) el.remove();
    else { el.classList.add("bs-out"); setTimeout(() => el.remove(), 220); } // dissolvenza solo di opacity
  }

  async function getJson(path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(path, { cache: "no-store", signal: controller.signal });
      return { status: response.status, ok: response.ok, data: response.ok ? await response.json() : null };
    } finally {
      clearTimeout(timeout);
    }
  }

  function showError(text) {
    paint({ progress: 0, label: text, error: text });
  }

  async function pollLegacy() {
    let failures = 0;
    async function tick() {
      timer = 0;
      if (done || stopped) return;
      try {
        const result = await getJson("/api/status");
        if (!result.ok) throw new Error(`HTTP ${result.status}`);
        const status = result.data || {};
        const lines = Array.isArray(status.build_log) ? status.build_log : [];
        const last = String(lines[lines.length - 1] || "");
        failures = 0;
        if (status.has_library && !status.building) return finish();
        if (!status.building && /^errore\b/i.test(last)) {
          showError(last);
          return;
        }
        paint({
          progress: 0,
          label: last || (status.building ? t("b.splash.preparing") : t("b.splash.waitingFirst")),
          error: "",
        });
      } catch {
        failures += 1;
        if (failures >= 3) {
          showError(t("b.splash.statusUnavailable"));
          return;
        }
      }
      timer = setTimeout(tick, POLL_MS);
    }
    await tick();
  }

  let failures = 0;
  async function poll() {
    timer = 0;
    if (done || stopped) return;
    try {
      const result = await getJson("/api/boot");
      if (result.status === 404 || result.status === 410) return pollLegacy();
      if (!result.ok) throw new Error(`HTTP ${result.status}`);
      const boot = result.data;
      if (!boot || typeof boot !== "object") return pollLegacy();
      const state = summarize(boot);
      paint(state);
      failures = 0;
      if (boot.ready && !state.error) return finish();
      if (boot.ready) return; // errore: rimane visibile finche' non si preme Continua
    } catch {
      failures += 1;
      if (failures >= 3) return pollLegacy();
    }
    timer = setTimeout(poll, POLL_MS);
  }

  ok.addEventListener("click", finish);
  showTimer = setTimeout(() => { if (!done) document.body.appendChild(el); }, SHOW_AFTER_MS);
  capTimer = setTimeout(() => {
    if (done || hasError) return;
    stopped = true;
    clearTimeout(timer);
    showError(t("b.splash.timeout"));
  }, MAX_MS);
  poll();
})();
