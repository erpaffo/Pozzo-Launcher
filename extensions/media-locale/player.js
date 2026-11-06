import { compositeKey, isSeen } from "./logica.js";

export const CONTINUE_KEY = "gs.pm_continue_watching";

const BROWSER_EXTS = new Set([".mp4", ".webm", ".mp3", ".flac", ".ogg", ".m4a", ".ogv", ".opus", ".wav", ".m4v", ".m3u8"]);
const AUDIO_EXTS = new Set([".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav"]);

/** Carica la lista degli elementi da continuare dallo storage (localStorage di default). */
export function loadContinueCache(storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  if (!storage || typeof storage.getItem !== "function") return [];
  try {
    const raw = storage.getItem(CONTINUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Salva o aggiorna un elemento nella cache di visione continua. */
export function saveContinueCache(item, pos, seen, duration, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  const current = loadContinueCache(storage);
  if (!hasValidId(item)) return current;
  const key = compositeKey(item);
  if (!key) return current;

  const p = Number(pos != null && Number.isFinite(pos) ? pos : (item.resume_pos ?? item.pos ?? 0));
  const dur = Number(duration != null && Number.isFinite(duration) ? duration : (item.duration || 0));
  const isWatched = seen === true || isSeen({ resume_pos: p, duration: dur, seen: item.seen });

  const filtered = current.filter((it) => compositeKey(it) !== key);

  if (!isWatched && p > 0) {
    const entry = {
      ...item,
      resume_pos: Math.round(p * 10) / 10,
      seen: false,
      ...(dur > 0 ? { duration: Math.round(dur * 10) / 10 } : {}),
    };
    filtered.unshift(entry);
  }

  const updated = filtered.slice(0, 20);
  if (storage && typeof storage.setItem === "function") {
    try {
      storage.setItem(CONTINUE_KEY, JSON.stringify(updated));
    } catch {}
  }
  return updated;
}

/** Rimuove un elemento dalla cache di visione continua per chiave o id. */
export function removeFromContinueCache(itemOrKey, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  const current = loadContinueCache(storage);
  const targetKey = typeof itemOrKey === "string" ? itemOrKey : (itemOrKey ? compositeKey(itemOrKey) : null);
  const targetId = typeof itemOrKey === "object" && itemOrKey ? String(itemOrKey.id ?? "") : (typeof itemOrKey === "string" ? itemOrKey : "");
  const filtered = current.filter((it) => {
    const k = compositeKey(it);
    if (targetKey && k === targetKey) return false;
    if (targetId && String(it.id) === targetId) return false;
    return true;
  });
  if (storage && typeof storage.setItem === "function") {
    try {
      storage.setItem(CONTINUE_KEY, JSON.stringify(filtered));
    } catch {}
  }
  return filtered;
}

/** Vero se la sorgente o il file può essere riprodotto direttamente nel browser (<video> o <audio>). */
export function isBrowserPlayable(target) {
  if (!target) return false;
  if (target.external === true) return false;
  const path = String(target.path || "");
  const url = String(target.url || "");
  const mime = String(target.mime || "").toLowerCase();

  if (target.external === false && (url || path)) return true;
  if (mime.startsWith("video/mp4") || mime.startsWith("video/webm") || mime.startsWith("video/ogg") || mime.startsWith("audio/")) {
    return true;
  }
  const ext = (path || url).split(/[?#]/)[0].toLowerCase().match(/\.[a-z0-9]+$/);
  return Boolean(ext && BROWSER_EXTS.has(ext[0]));
}

function hasValidId(it) {
  if (!it || it.id == null) return false;
  const s = String(it.id).trim();
  return s.length > 0 && s !== "undefined" && s !== "null";
}

let _hlsLoading = null;
/** Carica hls.js (vendorizzato accanto a questo file) al primo uso; null se non disponibile. */
function loadHls() {
  const w = typeof window !== "undefined" ? window : globalThis;
  if (w.Hls) return Promise.resolve(w.Hls);
  if (typeof document === "undefined") return Promise.resolve(null);
  _hlsLoading ||= new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = new URL("./hls.min.js", import.meta.url).href;
    s.onload = () => resolve(w.Hls || null);
    s.onerror = () => { _hlsLoading = null; resolve(null); };
    document.head.appendChild(s);
  });
  return _hlsLoading;
}

/** Tenta di aprire il file o l'url nel lettore esterno. */
export async function openExternal(gs, item, target, apiPrefix = "/plugin-api/media-locale") {
  const isHttpOnly = !target?.path && (target?.url?.startsWith("http://") || target?.url?.startsWith("https://"));
  try {
    if (isHttpOnly) {
      try {
        await gs.api(`${apiPrefix}/external`, { body: { id: item?.id } });
        return;
      } catch {
        await gs.api("/api/open", { body: { url: target.url } });
        return;
      }
    }
    await gs.api(`${apiPrefix}/external`, { body: { id: item?.id } });
  } catch (err) {
    gs?.toast?.(err?.message || "Impossibile aprire il lettore esterno", true);
  }
}

/** Riproduce un MediaItem: verifica id, chiede play_target, apre l'overlay adatto e gestisce il progresso. */
export async function play(gs, item, onClose) {
  if (!hasValidId(item)) {
    gs?.toast?.("Elemento non valido", true);
    return null;
  }

  const doc = typeof document !== "undefined" ? document : null;
  if (doc) {
    const prev = doc.querySelector(".pm-player-overlay");
    if (prev && typeof prev._pmClose === "function") prev._pmClose();
  }

  const src = item.source || "media-locale";
  const isSrv = src === "jellyfin" || src === "plex";
  const apiPrefix = isSrv
    ? "/plugin-api/media-server"
    : (src !== "locale" && src !== "media-locale" ? `/plugin-api/${src}` : "/plugin-api/media-locale");
  const srcQuery = isSrv ? `&source=${encodeURIComponent(src)}` : "";

  let target;
  try {
    target = await gs.api(`${apiPrefix}/play_target?id=${encodeURIComponent(item.id)}${srcQuery}`);
  } catch (err) {
    gs?.toast?.(err?.message || "Errore nel caricamento del file", true);
    return null;
  }

  if (!target) {
    gs?.toast?.("Sorgente non trovata", true);
    return null;
  }

  const browserPlayable = isBrowserPlayable(target);
  if (!doc) return { item, target, browserPlayable };

  return openOverlay(gs, item, target, browserPlayable, apiPrefix, onClose);
}

function openOverlay(gs, item, target, browserPlayable, apiPrefix, onClose) {
  const doc = document;
  const esc = gs?.esc || ((s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));

  let titleText = item.title || "Riproduzione";
  if (item.series) {
    const s = item.season != null ? `S${item.season}` : "";
    const e = item.episode != null ? `E${item.episode}` : "";
    const ep = (s || e) ? ` — ${s}${e}` : "";
    titleText = `${item.series}${ep}: ${item.title || ""}`;
  } else if (item.album) {
    titleText = `${item.title || "Brano"} — ${item.album}`;
  }

  const overlay = doc.createElement("div");
  overlay.className = "pm-player-overlay";
  overlay.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";

  let closed = false;
  let saveTimer = null;
  let resumeApplied = false;
  let mediaEl = null;
  let hls = null;

  const resumePos = Number(target.resume_pos ?? item.resume_pos ?? 0);

  async function saveProgress(overridePos) {
    if (closed || !hasValidId(item)) return;

    const rawPos = mediaEl ? Number(mediaEl.currentTime) : 0;
    const curPos = (overridePos != null && Number.isFinite(overridePos))
      ? overridePos
      : (Number.isFinite(rawPos) && rawPos > 0 ? rawPos : 0);

    const rawDur = mediaEl ? Number(mediaEl.duration) : 0;
    const curDur = (Number.isFinite(rawDur) && rawDur > 0) ? rawDur : Number(item.duration || 0);

    const isWatched = isSeen({ resume_pos: curPos, duration: curDur, seen: item.seen });

    saveContinueCache(item, curPos, isWatched, curDur);

    const payload = {
      id: String(item.id),
      pos: Math.round(curPos * 10) / 10,
      seen: isWatched,
    };
    if (item.source === "jellyfin" || item.source === "plex") {
      payload.source = item.source;
    }
    if (curDur > 0) {
      payload.duration = Math.round(curDur * 10) / 10;
    }

    item.resume_pos = isWatched ? 0 : payload.pos;
    item.seen = isWatched;
    if (curDur > 0 && !item.duration) {
      item.duration = payload.duration;
    }

    try {
      await gs.api(`${apiPrefix}/set_progress`, { body: payload });
    } catch {}
  }

  let isFullscreen = false;

  async function setWindowFullscreen(on) {
    const shouldBeFs = Boolean(on);
    try {
      const pw = (typeof window !== "undefined" ? window : globalThis)?.pywebview?.api;
      if (pw && typeof pw.set_fullscreen === "function") {
        await pw.set_fullscreen(shouldBeFs);
      }
    } catch {}

    try {
      if (shouldBeFs) {
        if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
          if (overlay.requestFullscreen) {
            await overlay.requestFullscreen({ navigationUI: "hide" });
          } else if (doc.documentElement.requestFullscreen) {
            await doc.documentElement.requestFullscreen({ navigationUI: "hide" });
          } else if (mediaEl && mediaEl.webkitEnterFullscreen) {
            mediaEl.webkitEnterFullscreen();
          }
        }
      } else {
        if (doc.fullscreenElement || doc.webkitFullscreenElement) {
          if (doc.exitFullscreen) {
            await doc.exitFullscreen();
          } else if (doc.webkitExitFullscreen) {
            await doc.webkitExitFullscreen();
          }
        }
      }
    } catch {}
  }

  function updateFullscreenUI(on) {
    isFullscreen = Boolean(on);
    if (isFullscreen) {
      overlay.classList.add("pm-fullscreen-mode");
    } else {
      overlay.classList.remove("pm-fullscreen-mode");
    }
    const fsBtn = overlay.querySelector("#pm-fullscreen-btn");
    if (fsBtn) {
      fsBtn.innerHTML = isFullscreen ? "🗗 Finestra" : "⛶ Schermo intero";
      fsBtn.title = isFullscreen ? "Esci da schermo intero (F)" : "Schermo intero (F)";
    }
    const fsHeadBtn = overlay.querySelector("#pm-fs-head-btn");
    if (fsHeadBtn) {
      fsHeadBtn.innerHTML = isFullscreen ? "🗗" : "⛶";
      fsHeadBtn.title = isFullscreen ? "Esci da schermo intero (F)" : "Schermo intero (F)";
    }
  }

  async function toggleFullscreen(force) {
    const target = typeof force === "boolean" ? force : !isFullscreen;
    updateFullscreenUI(target);
    await setWindowFullscreen(target);
  }

  function onFullscreenChange() {
    const active = Boolean(doc.fullscreenElement || doc.webkitFullscreenElement);
    if (active !== isFullscreen) {
      updateFullscreenUI(active);
      try {
        const pw = (typeof window !== "undefined" ? window : globalThis)?.pywebview?.api;
        if (pw && typeof pw.set_fullscreen === "function") {
          pw.set_fullscreen(active);
        }
      } catch {}
    }
  }

  doc.addEventListener("fullscreenchange", onFullscreenChange);
  doc.addEventListener("webkitfullscreenchange", onFullscreenChange);

  function closeOverlay() {
    if (closed) return;
    if (browserPlayable && mediaEl) {
      saveProgress();
    }
    closed = true;
    if (isFullscreen || doc.fullscreenElement || doc.webkitFullscreenElement) {
      setWindowFullscreen(false);
    }
    if (saveTimer) {
      clearInterval(saveTimer);
      saveTimer = null;
    }
    if (hls) {
      try { hls.destroy(); } catch {}
      hls = null;
    }
    if (mediaEl) {
      try {
        mediaEl.pause();
        mediaEl.removeAttribute("src");
        mediaEl.load();
      } catch {}
    }
    overlay.remove();
    doc.removeEventListener("keydown", onKeyDown);
    doc.removeEventListener("fullscreenchange", onFullscreenChange);
    doc.removeEventListener("webkitfullscreenchange", onFullscreenChange);
    if (typeof onClose === "function") {
      try { onClose(item); } catch {}
    }
  }

  function onKeyDown(e) {
    const targetTag = (e.target?.tagName || "").toLowerCase();
    if (targetTag === "input" || targetTag === "textarea" || targetTag === "select") {
      return;
    }
    if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleFullscreen();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      if (isFullscreen || doc.fullscreenElement || doc.webkitFullscreenElement) {
        toggleFullscreen(false);
      } else {
        closeOverlay();
      }
    }
  }
  doc.addEventListener("keydown", onKeyDown);
  overlay._pmClose = closeOverlay;

  if (!browserPlayable) {
    overlay.innerHTML = `
      <div class="pm-player-modal" style="width:100%;max-width:640px;background:var(--panel,#18181b);border:1px solid var(--line,#27272a);border-radius:12px;padding:20px;box-sizing:border-box;display:flex;flex-direction:column;gap:14px;box-shadow:0 20px 40px rgba(0,0,0,0.6);">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line,#27272a);padding-bottom:10px;">
          <h3 class="pm-title" style="margin:0;font-size:1.05rem;font-weight:600;">${esc(titleText)}</h3>
          <button type="button" class="pm-player-btn" id="pm-close-x" aria-label="Chiudi" style="padding:4px 8px;font-size:1rem;line-height:1;">✕</button>
        </div>
        <div class="pm-player-fallback">
          <p class="pm-player-fallback-text">Questo formato non può essere riprodotto direttamente nel browser.</p>
          <button type="button" class="pm-player-external" id="pm-open-ext">Apri nel lettore esterno</button>
        </div>
        <div class="pm-player-actions" style="justify-content:flex-end;">
          <button type="button" class="pm-player-btn" id="pm-close-btn">Chiudi</button>
        </div>
      </div>
    `;

    overlay.querySelector("#pm-open-ext")?.addEventListener("click", () => openExternal(gs, item, target, apiPrefix));
    overlay.querySelector("#pm-close-x")?.addEventListener("click", closeOverlay);
    overlay.querySelector("#pm-close-btn")?.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });

    doc.body.appendChild(overlay);
    return { overlay, close: closeOverlay, browserPlayable: false };
  }

  const cleanExt = (target.path || target.url || "").split(/[?#]/)[0].toLowerCase().match(/\.[a-z0-9]+$/);
  const isAudio = item.kind === "brano" ||
    Boolean(target.mime && target.mime.startsWith("audio/")) ||
    Boolean(cleanExt && AUDIO_EXTS.has(cleanExt[0]));

  const mediaTag = isAudio ? "audio" : "video";

  overlay.innerHTML = `
    <div class="pm-player-modal" style="width:100%;max-width:960px;background:var(--panel,#18181b);border:1px solid var(--line,#27272a);border-radius:12px;padding:16px;box-sizing:border-box;display:flex;flex-direction:column;gap:12px;box-shadow:0 20px 40px rgba(0,0,0,0.6);">
      <div class="pm-player-header" style="display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line,#27272a);padding-bottom:8px;">
        <h3 class="pm-title" style="margin:0;font-size:1.05rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(titleText)}</h3>
        <div style="display:flex;align-items:center;gap:8px;">
          ${!isAudio ? `<button type="button" class="pm-player-btn" id="pm-fs-head-btn" title="Schermo intero (F)" style="padding:4px 8px;font-size:0.95rem;line-height:1;">⛶</button>` : ""}
          <button type="button" class="pm-player-btn" id="pm-close-x" aria-label="Chiudi" style="padding:4px 8px;font-size:1rem;line-height:1;">✕</button>
        </div>
      </div>
      <div class="pm-player" style="${isAudio ? 'aspect-ratio:auto;padding:28px 16px;display:flex;align-items:center;justify-content:center;background:var(--bg-2,#111);' : ''}">
        <${mediaTag} class="pm-player-video" controls autoplay playsinline style="${isAudio ? 'width:100%;max-width:600px;height:54px;' : ''}"></${mediaTag}>
      </div>
      <div class="pm-player-actions">
        ${!isAudio ? `<button type="button" class="pm-player-btn" id="pm-fullscreen-btn" title="Schermo intero (F)">⛶ Schermo intero</button>` : ""}
        <button type="button" class="pm-player-external" id="pm-open-ext">Apri nel lettore esterno</button>
        <button type="button" class="pm-player-btn pm-primary" id="pm-close-btn">Chiudi</button>
      </div>
    </div>
  `;

  mediaEl = overlay.querySelector(mediaTag);
  if (!isAudio && mediaEl) {
    mediaEl.addEventListener("dblclick", (e) => {
      e.preventDefault();
      toggleFullscreen();
    });
  }

  const streamSrc = target.url || (target.path ? `${apiPrefix}/stream?id=${encodeURIComponent(item.id)}` : "");
  const isHls = /\.m3u8$/i.test(streamSrc.split(/[?#]/)[0]);

  /** Errore fatale: niente spinner/player bloccato, solo messaggio e il pulsante del lettore esterno. */
  function showPlayError(msg) {
    if (closed) return;
    try { mediaEl.pause(); } catch {}
    const box = overlay.querySelector(".pm-player");
    if (box) box.innerHTML = `<p class="pm-player-fallback-text" style="padding:24px;margin:0;">${esc(msg)}</p>`;
  }

  if (isHls) {
    loadHls().then((Hls) => {
      if (closed) return;
      if (Hls && Hls.isSupported()) {
        hls = new Hls();
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data?.fatal) showPlayError("Impossibile riprodurre questo flusso (HLS). Prova il lettore esterno.");
        });
        hls.loadSource(streamSrc);
        hls.attachMedia(mediaEl);
      } else if (mediaEl.canPlayType("application/vnd.apple.mpegurl")) {
        mediaEl.src = streamSrc;
      } else {
        showPlayError("Il flusso HLS non è riproducibile qui. Usa il lettore esterno.");
      }
    });
  } else if (streamSrc) {
    mediaEl.src = streamSrc;
  }
  mediaEl.addEventListener("error", () => { if (!isHls || !hls) showPlayError("Impossibile riprodurre questo file. Prova il lettore esterno."); });

  function applyResume() {
    if (resumeApplied) return;
    if (Number.isFinite(resumePos) && resumePos > 0) {
      try {
        mediaEl.currentTime = resumePos;
        resumeApplied = true;
      } catch {}
    } else {
      resumeApplied = true;
    }
  }

  mediaEl.addEventListener("loadedmetadata", () => {
    if (!resumeApplied) applyResume();
  });
  mediaEl.addEventListener("canplay", () => {
    if (!resumeApplied) applyResume();
  });
  if (!isHls) applyResume(); // con HLS la posizione si applica a loadedmetadata, a manifest caricato

  saveTimer = setInterval(() => {
    if (closed) {
      clearInterval(saveTimer);
      return;
    }
    if (mediaEl && !mediaEl.paused && !mediaEl.ended) {
      saveProgress();
    }
  }, 10000);

  mediaEl.addEventListener("pause", () => {
    if (!closed) saveProgress();
  });
  mediaEl.addEventListener("ended", () => {
    if (!closed) {
      const dur = Number(mediaEl.duration || item.duration || 0);
      saveProgress(dur > 0 ? dur : undefined);
    }
  });

  overlay.querySelector("#pm-open-ext")?.addEventListener("click", () => {
    try { mediaEl?.pause(); } catch {}
    openExternal(gs, item, target, apiPrefix);
  });
  overlay.querySelector("#pm-close-x")?.addEventListener("click", closeOverlay);
  overlay.querySelector("#pm-close-btn")?.addEventListener("click", closeOverlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });

  doc.body.appendChild(overlay);
  return { overlay, mediaEl, close: closeOverlay, saveProgress, browserPlayable: true };
}

/** Registra window.__pmPlay(item) usando gs. */
export function attachPlay(gs) {
  const win = typeof window !== "undefined" ? window : globalThis;
  win.__pmPlay = (item, onClose) => play(gs, item, onClose);
  return win.__pmPlay;
}
