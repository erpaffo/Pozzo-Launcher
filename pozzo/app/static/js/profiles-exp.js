"use strict";
(() => {
  const animations = new Set(["normal", "reduced", "off"]);

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  async function request(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Errore ${response.status}`);
    return data;
  }

  function applyAnimations(value) {
    if (!animations.has(value)) return;
    if (window.GSMotionSettings && window.GSMotionSettings.apply) window.GSMotionSettings.apply(value);
    else if (window.GSMotion && window.GSMotion.set) window.GSMotion.set(value);
  }

  async function applyProfile(id, status) {
    try {
      const applied = await request("/api/exp-profiles/activate", {
        method: "POST",
        body: JSON.stringify({ id }),
      });
      applyAnimations(applied.animations);
      if (status) status.textContent = "Preset applicato";
      window.location.reload();
    } catch (error) {
      if (status) status.textContent = error.message;
    }
  }

  function render(panel, state, extensions) {
    const experiences = extensions.experiences.filter((item) => item.available);
    const themes = extensions.themes;
    const experienceOptions = experiences.map((item) =>
      `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("");
    const themeOptions = themes.map((item) =>
      `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("");
    const profileCards = state.profiles.map((profile) => {
      const current = profile.id === state.active;
      return `<article class="srow exp-profile" data-profile="${esc(profile.id)}">
        <div class="srow-txt"><div class="srow-title">${esc(profile.nome)}</div>
          <div class="srow-desc">${esc(profile.experience)} · ${esc(profile.theme)} · ${esc(profile.animations)}</div></div>
        <div class="row"><button class="btn" type="button" data-activate="${esc(profile.id)}"${current ? " disabled" : ""}>
          ${current ? "Attivo" : "Applica"}</button>
          <button class="btn" type="button" data-delete="${esc(profile.id)}" aria-label="Elimina ${esc(profile.nome)}">Elimina</button></div>
      </article>`;
    }).join("");

    panel.innerHTML = `<div data-exp-profiles-list>${profileCards || '<p class="muted">Nessun preset salvato.</p>'}</div>
      <form data-exp-profiles-form>
        <label class="srow"><span class="srow-txt"><span class="srow-title">Nome</span></span>
          <input class="field" name="nome" maxlength="40" required placeholder="Il mio profilo"></label>
        <div class="row">
          <label>Esperienza <select class="field" name="experience">${experienceOptions}</select></label>
          <label>Tema <select class="field" name="theme">${themeOptions}</select></label>
          <label>Animazioni <select class="field" name="animations">
            <option value="normal">Complete</option><option value="reduced">Ridotte</option><option value="off">Nessuna</option>
          </select></label>
          <button class="btn" type="submit">Salva preset</button>
        </div>
      </form>
      <p data-exp-profiles-status class="muted small" role="status" aria-live="polite"></p>`;

    const form = panel.querySelector("[data-exp-profiles-form]");
    if (extensions.active_experience) form.elements.experience.value = extensions.active_experience;
    if (extensions.active_theme) form.elements.theme.value = extensions.active_theme;
    const motion = state.animations || (window.GSMotionSettings && window.GSMotionSettings.current());
    if (animations.has(motion)) form.elements.animations.value = motion;

    const status = panel.querySelector("[data-exp-profiles-status]");
    panel.addEventListener("click", async (event) => {
      const activate = event.target.closest("[data-activate]");
      if (activate) return applyProfile(activate.dataset.activate, status);
      const remove = event.target.closest("[data-delete]");
      if (!remove) return;
      try {
        const next = await request("/api/exp-profiles", {
          method: "DELETE",
          body: JSON.stringify({ id: remove.dataset.delete }),
        });
        const latest = await request("/api/extensions");
        render(panel, next, latest);
      } catch (error) {
        status.textContent = error.message;
      }
    }, { once: true });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const values = new FormData(form);
      try {
        const next = await request("/api/exp-profiles", {
          method: "POST",
          body: JSON.stringify({
            nome: values.get("nome"),
            experience: values.get("experience"),
            theme: values.get("theme"),
            animations: values.get("animations"),
          }),
        });
        const latest = await request("/api/extensions");
        render(panel, next, latest);
      } catch (error) {
        status.textContent = error.message;
      }
    });
  }

  async function refresh(panel) {
    try {
      const [state, extensions] = await Promise.all([
        request("/api/exp-profiles"),
        request("/api/extensions"),
      ]);
      if (state.animations) applyAnimations(state.animations);
      render(panel, state, extensions);
      return state;
    } catch (error) {
      panel.textContent = error.message;
      return null;
    }
  }

  function mount() {
    const anchor = document.getElementById("experience-list");
    if (!anchor || document.getElementById("exp-profiles")) return;
    const title = document.createElement("h3");
    title.textContent = "Preset esperienza";
    const panel = document.createElement("div");
    panel.id = "exp-profiles";
    anchor.before(title, panel);
    refresh(panel);
  }

  function start() {
    mount();
    if (typeof MutationObserver === "function") {
      new MutationObserver(mount).observe(document.documentElement, { childList: true, subtree: true });
    }
    request("/api/exp-profiles").then((state) => applyAnimations(state.animations)).catch(() => {});
  }

  window.GSExpProfiles = { mount, refresh, applyProfile };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
