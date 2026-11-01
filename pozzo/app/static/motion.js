/* Ingresso scaglionato delle copertine + pausa a scheda nascosta + preferenza gs.motion.
   Nessuna dipendenza; non tocca il DOM dell'app oltre a una classe temporanea. */
(() => {
  "use strict";
  const root = document.documentElement;
  const MAX = 24, MIN_BATCH = 6;
  const SEL = ".tile .cover, .cnx-card, .gs-dashboard__tile, .vetrina-game, .gs-console-game, .card .cv";
  const FPS_SAMPLE_MS = 1400; // Finestra abbastanza lunga da smussare oscillazioni brevi, senza ritardare l'avvio.
  const LOW_FPS_THRESHOLD = 30; // Sotto 30 FPS il movimento può risultare poco fluido.
  const LOW_MEMORY_GB = 4; // 4 GB o meno indicano poca memoria disponibile per l'interfaccia.
  const LOW_CPU_CORES = 4; // 4 core logici o meno indicano una CPU di fascia bassa.
  const LOW_BATTERY_LEVEL = 0.20; // Sotto il 20% segnala una batteria scarica mentre non è in carica.

  const read = () => { try { return JSON.parse(localStorage.getItem("gs.motion")); } catch { return null; } };
  const valid = (v) => v === "off" || v === "reduced" || v === "normal";
  let manualOverride = read();
  if (!valid(manualOverride)) manualOverride = null;
  const state = {
    fps: null,
    fpsMeasurement: "measuring",
    sampleDurationMs: 0,
    sampleFrames: 0,
    deviceMemoryGb: null,
    hardwareConcurrency: null,
    batteryAvailable: false,
    batteryChecked: false,
    batteryLevel: null,
    batteryCharging: null,
    lowEnd: false,
    lowFps: false,
    onBattery: false,
    lowBattery: false,
    reduced: false,
    reasons: [],
  };
  const setEffectiveMotion = () => {
    const value = manualOverride || (state.reduced ? "reduced" : null);
    if (value) root.dataset.motion = value;
    else delete root.dataset.motion;
  };
  const refreshBudget = () => {
    state.reasons = [];
    if (state.lowEnd) state.reasons.push("low-end");
    if (state.lowFps) state.reasons.push("low-fps");
    if (state.onBattery) state.reasons.push("on-battery");
    state.reduced = state.reasons.length > 0;
    setEffectiveMotion();
    if (typeof window.dispatchEvent === "function" && typeof Event === "function") {
      window.dispatchEvent(new Event("gs-motion-budget-change"));
    }
  };

  const memory = typeof navigator !== "undefined" ? Number(navigator.deviceMemory) : NaN;
  const cores = typeof navigator !== "undefined" ? Number(navigator.hardwareConcurrency) : NaN;
  state.deviceMemoryGb = Number.isFinite(memory) && memory > 0 ? memory : null;
  state.hardwareConcurrency = Number.isFinite(cores) && cores > 0 ? cores : null;
  state.lowEnd = (state.deviceMemoryGb !== null && state.deviceMemoryGb <= LOW_MEMORY_GB)
    || (state.hardwareConcurrency !== null && state.hardwareConcurrency <= LOW_CPU_CORES);
  setEffectiveMotion();
  refreshBudget();

  function measureFps() {
    if (typeof requestAnimationFrame !== "function") {
      state.fpsMeasurement = "unavailable";
      refreshBudget();
      return;
    }
    let start = null, frames = 0;
    const frame = (timestamp) => {
      const now = Number.isFinite(timestamp) ? timestamp : performance.now();
      if (start === null) start = now;
      frames++;
      const duration = now - start;
      if (duration >= FPS_SAMPLE_MS) {
        state.sampleDurationMs = duration;
        state.sampleFrames = frames;
        state.fps = duration > 0 ? Math.max(0, frames - 1) * 1000 / duration : null;
        state.lowFps = state.fps !== null && state.fps < LOW_FPS_THRESHOLD;
        state.fpsMeasurement = "complete";
        refreshBudget();
        return;
      }
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  function measureBattery() {
    state.batteryChecked = true;
    if (typeof navigator === "undefined" || typeof navigator.getBattery !== "function") return;
    const update = (battery) => {
      if (!battery || typeof battery !== "object") return;
      state.batteryAvailable = true;
      const level = Number(battery.level);
      state.batteryLevel = Number.isFinite(level) && level >= 0 && level <= 1 ? level : null;
      state.batteryCharging = typeof battery.charging === "boolean" ? battery.charging : null;
      state.onBattery = state.batteryCharging === false;
      state.lowBattery = state.batteryCharging === false
        && state.batteryLevel !== null && state.batteryLevel <= LOW_BATTERY_LEVEL;
      refreshBudget();
    };
    try {
      Promise.resolve(navigator.getBattery()).then((battery) => {
        update(battery);
        if (battery && typeof battery.addEventListener === "function") {
          try {
            battery.addEventListener("levelchange", () => update(battery));
            battery.addEventListener("chargingchange", () => update(battery));
          } catch { /* API batteria parzialmente implementata */ }
        }
      }).catch(() => { state.batteryAvailable = false; });
    } catch { /* API batteria non disponibile */ }
  }

  window.GSMotionBudget = {
    state,
    thresholds: {
      sampleMs: FPS_SAMPLE_MS,
      lowFps: LOW_FPS_THRESHOLD,
      lowMemoryGb: LOW_MEMORY_GB,
      lowCpuCores: LOW_CPU_CORES,
      lowBatteryLevel: LOW_BATTERY_LEVEL,
    },
  };
  measureFps();
  measureBattery();

  window.GSMotion = {
    set(v) {
      if (!valid(v)) return;
      manualOverride = v;
      try { localStorage.setItem("gs.motion", JSON.stringify(v)); } catch { /* storage non disponibile */ }
      setEffectiveMotion();
    },
    // ingresso di un contenitore (cambio vista): WAAPI, si ripulisce da sola
    enter(el) {
      if (!el || !el.animate || !enabled() || document.hidden) return;
      const cs = getComputedStyle(root);
      el.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
        { duration: parseFloat(cs.getPropertyValue("--mo-base")) || 200, easing: cs.getPropertyValue("--mo-ease-out").trim() || "ease-out" });
    },
  };

  const sync = () => root.classList.toggle("mo-paused", document.hidden);
  document.addEventListener("visibilitychange", sync); sync();

  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const enabled = () => root.dataset.motion !== "off" && root.dataset.motion !== "reduced" && (root.dataset.motion === "normal" || !reduced.matches);

  let lastScroll = 0, pending = [], queued = false;
  document.addEventListener("scroll", () => { lastScroll = performance.now(); }, { capture: true, passive: true });

  function flush() {
    queued = false;
    const nodes = pending; pending = [];
    if (!enabled() || document.hidden || performance.now() - lastScroll < 250) return;
    const found = new Set();
    for (const n of nodes) {
      if (!n.isConnected) continue;
      if (n.matches(SEL)) found.add(n);
      else if (n.firstElementChild) for (const el of n.querySelectorAll(SEL)) { found.add(el); if (found.size > 120) break; }
    }
    if (found.size < MIN_BATCH) return;
    const vh = innerHeight, vw = innerWidth, picked = [];
    for (const el of found) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw) picked.push([r, el]);
    }
    if (picked.length < MIN_BATCH) return;
    picked.sort((a, b) => (a[0].top - b[0].top) || (a[0].left - b[0].left));
    picked.slice(0, MAX).forEach(([, el], i) => {
      el.style.setProperty("--mo-i-idx", i);
      el.classList.add("mo-in");
      el.addEventListener("animationend", () => { el.classList.remove("mo-in"); el.style.removeProperty("--mo-i-idx"); }, { once: true });
    });
  }

  new MutationObserver((muts) => {
    for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1 && !n.classList.contains("mo-in")) pending.push(n);
    if (pending.length && !queued) { queued = true; requestAnimationFrame(flush); }
  }).observe(document.body || root, { childList: true, subtree: true });

})();
