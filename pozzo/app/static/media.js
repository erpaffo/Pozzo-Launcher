(() => {
  "use strict";
  const $ = (selector, root = document) => root.querySelector(selector);
  let spotifyState = null, discordState = null, lastPoll = 0, pollTimer = 0, busy = false;

  async function api(path, body) {
    const response = await fetch(path, body === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || t("i.media.requestFailed", { status: response.status }));
    return data;
  }

  function feedback(message, error = false) {
    const out = $("#bp-media-message");
    if (out) { out.textContent = message || ""; out.classList.toggle("err", error); }
  }

  function renderSpotify(data) {
    spotifyState = data;
    const title = $("#bp-media-title"), artist = $("#bp-media-artist"), cover = $("#bp-media-cover");
    if (title) title.textContent = data.track || (data.state === "no_device" ? t("i.media.noDevice") : t("i.media.noTrack"));
    if (artist) artist.textContent = (data.artists || []).join(", ") || data.message || t("i.media.spotifyNotLinked");
    if (cover) { cover.hidden = !data.cover; if (data.cover) cover.src = data.cover; else cover.removeAttribute("src"); }
    const progress = $("#bp-media-progress");
    if (progress) progress.style.width = `${data.duration_ms ? Math.min(100, 100 * data.progress_ms / data.duration_ms) : 0}%`;
    const volume = $("#bp-media-volume");
    if (volume && data.volume != null && document.activeElement !== volume) volume.value = data.volume;
  }

  function renderDiscord(data) {
    discordState = data;
    const channel = $("#bp-discord-channel"), participants = $("#bp-discord-participants");
    if (channel) channel.textContent = data.in_call ? t("i.media.voice", { c: data.channel }) : (data.message || t("i.media.noCall"));
    if (participants) {
      const names = (data.participants || []).map((p) => `${p.speaking ? "?? " : ""}${p.name}`).join(" ? ");
      const speakers = data.speakers?.length ? ` ? ${t("i.media.speaking", { list: data.speakers.join(", ") })}` : "";
      participants.textContent = `${names}${speakers}`;
    }
    const mute = $("[data-media-action='mute']"), deaf = $("[data-media-action='deafen']");
    if (mute) mute.textContent = data.muted ? t("i.media.unmuteMic") : t("i.media.muteMic");
    if (deaf) deaf.textContent = data.deafened ? t("i.media.undeafen") : t("i.media.deafen");
  }

  async function refresh() {
    if (!$("#bp-media-widget") || $("#bp-media-widget").hidden) return;
    const wait = 5000 - (Date.now() - lastPoll);
    if (wait > 0) { clearTimeout(pollTimer); pollTimer = setTimeout(refresh, wait); return; }
    if (busy) return;
    busy = true;
    lastPoll = Date.now();
    try {
      const [spotify, discord] = await Promise.all([
        api("/api/spotify/status").catch((e) => ({ state: "error", message: e.message })),
        api("/api/discord/status").catch((e) => ({ state: "error", message: e.message })),
      ]);
      renderSpotify(spotify); renderDiscord(discord);
      feedback(spotify.message || discord.message || "");
    } finally {
      busy = false;
      if (!$("#bp-media-widget")?.hidden) pollTimer = setTimeout(() => refresh(), 5000);
    }
  }

  function openWidget(open) {
    const widget = $("#bp-media-widget"), toggle = $("#bp-media-toggle");
    if (!widget) return false;
    if (open) {
      const top = $("#bp-top")?.getBoundingClientRect().bottom;
      if (top) widget.style.setProperty("--bp-media-top", `${Math.round(top + 8)}px`);
    }
    widget.hidden = !open;
    if (toggle) toggle.setAttribute("aria-expanded", String(open));
    clearTimeout(pollTimer);
    if (open) {
      $(".media-action", widget)?.focus();
      refresh();
    } else if (toggle) toggle.focus();
    else window.dispatchEvent(new CustomEvent("pozzo-media-close"));
    return true;
  }

  async function key(action) {
    const result = await api("/api/media/keys", { action });
    if (!result.ok) throw new Error(result.message || t("i.media.keyUnavailable"));
    return result;
  }

  async function spotifyAction(path, fallback) {
    try { await api(`/api/spotify/${path}`, {}); feedback(""); }
    catch (error) {
      try { await key(fallback); feedback(""); }
      catch { feedback(error.message, true); }
    }
  }

  async function volumeSystem(direction) {
    try { await key(direction > 0 ? "volume_up" : "volume_down"); feedback(""); }
    catch (error) { feedback(error.message, true); }
  }

  async function toggleVoice(kind) {
    const field = kind === "mute" ? "muted" : "deafened";
    const path = kind === "mute" ? "mute" : "deafen";
    try {
      if (!discordState || !discordState.connected) discordState = await api("/api/discord/status");
      const result = await api(`/api/discord/${path}`, { enabled: !discordState[field] });
      feedback(result.ok ? t("i.media.voiceUpdated") : t("i.media.commandFailed"));
      await refresh();
    } catch (error) { feedback(error.message, true); }
  }

  async function leaveCall() {
    try { await api("/api/discord/leave", {}); feedback(t("i.media.left")); await refresh(); }
    catch (error) { feedback(error.message, true); }
  }

  function controls() { return [...document.querySelectorAll("#bp-media-widget .media-action")].filter((el) => !el.disabled); }
  function handlePad(action) {
    const widget = $("#bp-media-widget");
    if (!widget) return false;
    if (action === "r3") { openWidget(widget.hidden); return true; }
    if (widget.hidden) return false;
    if (action === "b") { openWidget(false); return true; }
    if (["left", "right", "up", "down"].includes(action)) {
      const volume = $("#bp-media-volume"), step = action === "left" || action === "down" ? -5 : 5;
      if (document.activeElement === volume) { volume.value = Math.max(0, Math.min(100, Number(volume.value) + step)); volume.dispatchEvent(new Event("change", { bubbles: true })); return true; }
      const list = controls(), current = Math.max(0, list.indexOf(document.activeElement));
      const delta = action === "left" || action === "up" ? -1 : 1;
      list[(current + delta + list.length) % list.length]?.focus();
      return true;
    }
    if (action === "a") { document.activeElement?.click(); return true; }
    return false;
  }

  const player = {
    toggle() { return openWidget($("#bp-media-widget")?.hidden !== false); },
    open() { return openWidget(true); },
    close() { return openWidget(false); },
    next() { return spotifyAction("next", "next"); },
    prev() { return spotifyAction("prev", "previous"); },
    playPause() { return spotifyAction("play-pause", "play_pause"); },
    muteMic() { return toggleVoice("mute"); },
    deafen() { return toggleVoice("deafen"); },
    volumeUp() { return volumeSystem(1); },
    volumeDown() { return volumeSystem(-1); },
    handlePad,
  };
  window.PozzoMedia = player;

  $("#bp-media-toggle")?.addEventListener("click", () => openWidget($("#bp-media-widget").hidden));
  $("#bp-media-widget")?.addEventListener("click", (event) => {
    const action = event.target.closest("[data-media-action]")?.dataset.mediaAction;
    if (action === "prev") player.prev();
    else if (action === "next") player.next();
    else if (action === "play") player.playPause();
    else if (action === "mute" || action === "deafen") toggleVoice(action);
    else if (action === "leave") leaveCall();
    else if (action === "volume-up") player.volumeUp();
    else if (action === "volume-down") player.volumeDown();
  });
  $("#bp-media-volume")?.addEventListener("change", async (event) => {
    try { await api("/api/spotify/volume", { value: Number(event.target.value) }); }
    catch (error) { feedback(error.message, true); }
  });

  document.addEventListener("keydown", (event) => {
    if (!$("#bp-media-widget") || $("#bp-media-widget").hidden) return;
    const actions = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", Enter: "a", Escape: "b" };
    const action = actions[event.key];
    if (action && handlePad(action)) { event.preventDefault(); event.stopPropagation(); }
  }, true);

  async function initSettings(slot) {
    if (slot.dataset.mediaReady) return;
    slot.dataset.mediaReady = "1";
    try {
      const spotify = await api("/api/spotify/status");
      $("#media-spotify-id").value = spotify.client_id || "";
      $("#media-spotify-redirect").textContent = spotify.redirect_uri;
      $("#media-spotify-state").textContent = spotify.authenticated ? t("i.media.spotifyLinked") : t("i.media.spotifyNotLinkedDot");
    } catch (error) { const el = $("#media-spotify-state"); if (el) el.textContent = error.message; }
    try {
      const discord = await api("/api/discord/config");
      $("#media-discord-id").value = discord.client_id || "";
      $("#media-discord-state").textContent = discord.client_secret_set ? t("i.media.discordSaved") : t("i.media.discordEnter");
    } catch (error) { const el = $("#media-discord-state"); if (el) el.textContent = error.message; }
  }

  document.body.addEventListener("click", async (event) => {
    const button = event.target.closest("#media-spotify-save, #media-spotify-login, #media-spotify-logout, #media-discord-save, #media-discord-test");
    if (!button) return;
    const spotifyStateEl = $("#media-spotify-state"), discordStateEl = $("#media-discord-state");
    try {
      if (button.id === "media-spotify-save") {
        const result = await api("/api/spotify/settings", { client_id: $("#media-spotify-id").value.trim() });
        spotifyStateEl.textContent = result.authenticated ? t("i.media.clientSavedLinked") : t("i.media.clientSaved");
        $("#media-spotify-redirect").textContent = result.redirect_uri;
      } else if (button.id === "media-spotify-login") {
        const result = await api("/api/spotify/settings", { client_id: $("#media-spotify-id").value.trim() });
        $("#media-spotify-redirect").textContent = result.redirect_uri;
        const login = await api("/api/spotify/login");
        await api("/api/open", { url: login.url }); // browser di sistema: nell'app about:blank non ha un'applicazione
        spotifyStateEl.textContent = t("i.media.loginPrompt");
      } else if (button.id === "media-spotify-logout") {
        await api("/api/spotify/logout", {}); spotifyStateEl.textContent = t("i.media.loggedOut");
      } else if (button.id === "media-discord-save") {
        const result = await api("/api/discord/settings", { client_id: $("#media-discord-id").value.trim(), client_secret: $("#media-discord-secret").value });
        $("#media-discord-secret").value = "";
        discordStateEl.textContent = result.client_secret_set ? t("i.media.discordSaved") : result.message;
      } else if (button.id === "media-discord-test") {
        await api("/api/discord/settings", { client_id: $("#media-discord-id").value.trim(), client_secret: $("#media-discord-secret").value });
        $("#media-discord-secret").value = "";
        const result = await api("/api/discord/test", {});
        discordStateEl.textContent = result.in_call ? t("i.media.connected", { c: result.channel }) : t("i.media.discordOk");
      }
    } catch (error) {
      const target = button.id.startsWith("media-spotify") ? spotifyStateEl : discordStateEl;
      target.textContent = error.message;
    }
  });

  // Osserva solo il contenitore delle impostazioni (non tutto il body) e accorpa le mutazioni in un frame.
  let settingsCheckQueued = false;
  function checkSettings() {
    settingsCheckQueued = false;
    const slot = $("#settings-body [data-pane='integrazioni']");
    if (slot && !slot.hidden && !$("#settings-page")?.hidden && slot.querySelector("#media-spotify-id")) initSettings(slot);
  }
  const settingsObserver = new MutationObserver(() => {
    if (settingsCheckQueued) return;
    settingsCheckQueued = true;
    requestAnimationFrame(checkSettings);
  });
  const settingsBody = $("#settings-body"), settingsPage = $("#settings-page");
  if (settingsBody) settingsObserver.observe(settingsBody, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  if (settingsPage) settingsObserver.observe(settingsPage, { attributes: true, attributeFilter: ["hidden"] });
})();
