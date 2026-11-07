"use strict";
/* Stile TV "Classico": hero + scaffali orizzontali, pagina del gioco con copertina. Gli altri stili
 * ereditano da qui ogni pezzo che non ridefiniscono. Le funzioni usano gli helper di bigpicture.js. */
(() => {
  function classicCard(g, i, extra = "", score = "") {
    const tag = g.store ? (STORE_SHORT[g.store] || "PC") : (SHORT[g.platform] || g.platform.toUpperCase());
    return `<div class="card${g.store && !g.installed ? " notinst" : ""}" data-i="${i}" ${extra}>`
      + `<div class="cv" style="--h:${hueOf(g.title)}"><div class="ph">${esc(g.title)}</div>`
      + (g.cover ? `<img loading="lazy" decoding="async" src="/img/${g.id}/cover?w=300" onerror="this.remove()">` : "")
      + `<span class="tag">${esc(tag)}</span>${score ? `<span class="score">${esc(score)}</span>` : ""}</div><div class="lbl">${esc(g.title)}</div></div>`;
  }

  function classicTextCard(label, sub, i, hueKey, img, it = {}) {
    if (it.art) {  // collezione: copertina a tutto riquadro + logo
      return `<div class="card tile-text coll-card" data-i="${i}"><div class="cv" style="--h:${hueOf(hueKey || label)}">`
        + `<img class="art" src="${it.art}" alt="" loading="lazy" onerror="this.remove()">`
        + (it.icon ? `<img class="logo" src="${it.icon}" alt="" loading="lazy" onerror="this.remove()">` : "")
        + `<div class="txt">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ""}</div></div></div>`;
    }
    return `<div class="card tile-text${img ? " with-img" : ""}" data-i="${i}"><div class="cv" style="--h:${hueOf(hueKey || label)}">`
      + (img ? `<img class="sys" src="${img}" alt="" loading="lazy" onerror="this.remove()">` : "")
      + `<div class="txt">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ""}</div></div></div>`;
  }

  /* ---- «Riprendi»: il gioco da riprendere, prima card della home (GET /api/home/resume) */
  function saveWhen(t) {
    const ms = typeof t === "number" ? (t < 1e12 ? t * 1000 : t) : Date.parse(t);
    const d = new Date(ms);
    if (isNaN(d)) return "";
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(new Date()) - day(d)) / 86400000);
    const hm = d.toLocaleTimeString(GSI18n.lang, { hour: "2-digit", minute: "2-digit" });
    if (diff === 0) return window.t("c.when.today", { hm });
    if (diff === 1) return window.t("c.when.yesterday", { hm });
    return `${d.toLocaleDateString(GSI18n.lang, { day: "numeric", month: "short" })} ${hm}`;
  }

  function resumeCard(it, i) {
    const r = it.resume;
    const left = r.remaining_secs > 0 ? t("c.resume.left", { h: Math.max(1, Math.round(r.remaining_secs / 3600)) }) : "";
    const when = r.save ? saveWhen(r.save.time) : "";
    const save = when ? t("c.resume.save", { when }) : "";
    return `<div class="card resume-card" data-i="${i}" style="--h:${hueOf(r.title || "")}">`
      + `<div class="rc-cover"><div class="ph">${esc(r.title || "")}</div>`
      + (r.cover ? `<img loading="lazy" decoding="async" src="/img/${r.id}/cover?w=400" onerror="this.remove()">` : "")
      + `</div><div class="rc-body"><h3>${esc(r.title || "")}</h3>`
      + (left ? `<p class="rc-meta">${esc(left)}</p>` : "") + (save ? `<p class="rc-meta">${esc(save)}</p>` : "") + `</div></div>`;
  }

  /* Come «Gioca» nella pagina del gioco: stessa strada (playGame); se il gioco non è avviabile così, si apre la pagina. */
  async function resumePlay(id) {
    const d = await detail(id);
    if (!d || (d.store && !d.installed) || !d.emulator) return push(gameScreen(id));
    playGame(d);
  }

  /* In cima alla home, se il server ha un gioco da riprendere. Lista vuota o errore: la home resta com'è. */
  async function addResume(scr) {
    const it = (await api("/api/home/resume").catch(() => null))?.items?.[0];
    if (!it || !it.id) return;
    scr.shelves.unshift({ title: t("c.shelf.resume"), resume: true, items: [{ id: it.id, label: it.title || "", sub: it.platform ? platName(it.platform) : "",
      resume: it, ok: () => resumePlay(it.id) }] });
    scr.cols.unshift(0);
    scr.row = scr.row > 0 ? scr.row + 1 : 0; // la scheda con il fuoco resta la stessa; senza fuoco in basso, si parte da Riprendi
    if (cur() === scr) scr.render(main);
  }

  function classicNav() {
    const s = cur();
    const html = (t, i) => `<span data-tab="${i}" class="bp-tab${s.tab === t.id ? " active" : ""}${s.navFocus === i ? " focus" : ""}"${t.aria ? ` aria-label="${esc(t.aria)}"` : ""}>${t.icon ? `<span class="bp-tab-ico">${t.icon}</span>` : ""}${esc(t.label)}</span>`;
    // «Esci» sta fuori dall'area scorrevole: resta sempre visibile e raggiungibile
    $("#bp-nav").innerHTML = TABS.map((t, i) => (t.id === "exit" ? "" : html(t, i))).join("");
    $("#bp-exit").innerHTML = TABS.map((t, i) => (t.id === "exit" ? html(t, i) : "")).join("");
    (document.querySelector("#bp-nav .bp-tab.focus") || document.querySelector("#bp-nav .bp-tab.active"))?.scrollIntoView({ inline: "center", block: "nearest" });
    if (typeof updateNavFade === "function") updateNavFade();
  }

  /* ---- home: scaffali orizzontali */
  function classicHome() {
    const games = visibleGames();
    const recent = games.filter((g) => g.grp.last).sort((a, b) => b.grp.last - a.grp.last).slice(0, 30);
    const favs = sortTitle(games.filter((g) => g.grp.favorite)).slice(0, 40);
    const pcInst = sortTitle(games.filter((g) => g.store && g.installed)).slice(0, 40);
    const counts = new Map();
    for (const g of games) for (const i of g.grp.colls) counts.set(i, (counts.get(i) || 0) + 1);
    const topColls = BP.lib.colls.filter((c) => !c.hidden && (counts.get(c.idx) || 0) >= 4)
      .sort((a, b) => (counts.get(b.idx) || 0) - (counts.get(a.idx) || 0)).slice(0, 6);
    const shelves = [];
    if (recent.length) shelves.push({ title: t("c.shelf.continue"), items: recent });
    if (favs.length) shelves.push({ title: t("c.tab.fav"), items: favs });
    if (pcInst.length) shelves.push({ title: t("c.shelf.pc"), items: pcInst });
    for (const id of ["loved", "critics", "gems"]) {
      const d = discover(games, { preset: id });
      if (d.items.length >= 5) shelves.push({ title: d.preset.label, items: d.items.slice().sort(d.cmp).slice(0, 30),
        more: () => { store.set("bpDisc", id); push(discoverScreen(t("c.tab.all"), sortTitle(games), "all", id)); } });
    }
    for (const c of topColls) {
      const items = games.filter((g) => g.grp.colls.includes(c.idx)).sort((a, b) => (a.year || 9999) - (b.year || 9999));
      shelves.push({ title: c.name, sub: t("c.count.games", { n: items.length }), items: items.slice(0, 40), more: () => push(gridScreen(c.name, items, "coll")) });
    }
    const n = new Map();
    for (const g of games) n.set(g.platform, (n.get(g.platform) || 0) + 1);
    const plats = [...BP.lib.plats.values()].filter((p) => p.id !== "windows" && n.get(p.id)).sort((a, b) => collator.compare(a.name, b.name));
    shelves.push({ title: t("c.tab.plat"), text: true, items: plats.map((p) => ({ label: p.name, sub: t("c.count.games", { n: n.get(p.id) }), key: p.id,
      img: `/icons/platform/${encodeURIComponent(p.id)}`,
      ok: () => push(gridScreen(p.name, sortTitle(games.filter((g) => g.platform === p.id)), "plat")) })) });
    if (!shelves.length || shelves.every((s) => !s.items.length)) shelves.unshift({ title: t("c.tab.all"), items: sortTitle(games).slice(0, 40) });

    return shelvesScreen(shelves, "home");
  }

  function classicShelves(shelves, tab) {
    const scr = {
      tab, row: 0, cols: shelves.map(() => 0), navFocus: null, shelves, resumeAsked: false,
      render(el) {
        if (tab === "home" && !this.resumeAsked) { this.resumeAsked = true; addResume(this); }
        el.innerHTML = `<div class="bp-home"><div class="bp-hero" id="hero"></div><div class="bp-shelves"><div class="bp-shelves-inner" id="shelves">`
          + shelves.map((sh, r) => `<section class="shelf" data-r="${r}"><h2>${esc(sh.title)}${sh.sub ? `<span>${esc(sh.sub)}</span>` : ""}</h2>`
            + `<div class="shelf-row">${sh.items.map((it, i) => (sh.resume ? resumeCard(it, i) : sh.text ? textCard(it.label, it.sub, i, it.key, it.img, it) : card(it, i))).join("")}</div></section>`).join("")
          + `</div></div></div>`;
        this.update();
      },
      current() { const sh = shelves[this.row]; return sh && !sh.text && !sh.resume ? sh.items[this.cols[this.row]] : null; },
      update() {
        document.querySelectorAll(".card.focus").forEach((c) => c.classList.remove("focus"));
        renderNav();
        if (this.navFocus !== null) return;
        const sec = document.querySelector(`.shelf[data-r="${this.row}"]`);
        if (!sec) return;
        const c = sec.querySelectorAll(".card")[this.cols[this.row]];
        c?.classList.add("focus");
        // scorrimento: scaffale corrente in alto, carta corrente visibile
        $("#shelves").style.transform = `translateY(${-sec.offsetTop}px)`;
        const row = sec.querySelector(".shelf-row");
        const off = c ? Math.max(0, c.offsetLeft - row.clientWidth * 0.3) : 0;
        row.style.transform = `translateX(${-off}px)`;
        const g = this.current();
        const hero = $("#hero");
        if (g) {
          hero.innerHTML = `<h1>${esc(g.title)}</h1><div class="meta">${esc([g.store ? STORE_SHORT[g.store] : platName(g.platform), g.year, g.dev].filter(Boolean).join("  ·  "))}</div>`;
          setBackground(g.id);
          detail(g.id).then((d) => {
            if (d && d.media.logo && this.current() === g) hero.innerHTML = `<img class="logo-img" src="${d.media.logo}?w=700" onerror="this.outerHTML='<h1>${esc(g.title).replace(/'/g, "")}</h1>'">`
              + `<div class="meta">${esc([d.store_name || d.platform_name, d.year, d.developer].filter(Boolean).join("  ·  "))}</div>`;
          });
        } else {
          const it = shelves[this.row].items[this.cols[this.row]];
          hero.innerHTML = it ? `<h1>${esc(it.label)}</h1><div class="meta">${esc(it.sub || "")}</div>` : "";
          setBackground(it?.resume ? it.id : null);
        }
      },
      move(dx, dy) {
        if (this.navFocus !== null) {
          if (dy > 0) { this.navFocus = null; this.update(); return true; }
          const n = this.navFocus + dx;
          if (n < 0 || n >= TABS.length) return false;
          this.navFocus = n; renderNav(); return true;
        }
        if (dy) {
          const r = this.row + dy;
          if (r < 0) { this.navFocus = 0; this.update(); return true; }
          if (r >= shelves.length) return false;
          this.row = r;
        } else {
          const c = this.cols[this.row] + dx;
          if (c < 0 || c >= shelves[this.row].items.length) return false;
          this.cols[this.row] = c;
        }
        this.update(); return true;
      },
      jump(d) { this.cols[this.row] = Math.max(0, Math.min(shelves[this.row].items.length - 1, this.cols[this.row] + d * 6)); this.update(); },
      ok() {
        if (this.navFocus !== null) { openTab(this.navFocus); return; }
        const sh = shelves[this.row], it = sh.items[this.cols[this.row]];
        if (!it) return;
        if (sh.text || sh.resume) it.ok(); else push(gameScreen(it.id));
      },
      fav() { const g = this.current(); if (g) toggleFav(g); },
      hints: [["a", t("c.action.open")], ["y", t("c.action.search")], ["x", t("c.action.fav")]],
    };
    return scr;
  }

  /* ---- pagina del gioco */
  function classicGame(id) {
    const scr = {
      tab: null, d: null, i: 0, buttons: [], navFocus: null,
      async render(el) {
        el.innerHTML = `<div class="bp-game"><div class="big-cover"></div><div class="info"><h1>…</h1></div></div>`;
        const d = this.d || await detail(id);
        if (!d) { toast(t("c.game.notfound"), true); pop(); return; }
        this.d = d;
        setBackground(id);
        const pc = !!d.store;
        this.buttons = [];
        if (pc && !d.installed) this.buttons.push({ label: "⬇ " + t("c.action.install"), cls: "main", run: () => installGame(d) });
        else this.buttons.push({ label: "▶ " + t("c.action.play"), cls: "main", run: () => playGame(d), disabled: !d.emulator });
        if (d.webplay) this.buttons.push({ label: "🌐 " + t("f.btn.webplay"), run: () => { location.href = `/play/${id}`; } });
        const stOrder = ["", "backlog", "playing", "done", "dropped"];
        const st = d.user.status || "";
        if (!d.store || d.store !== "online") this.buttons.push({ label: st ? `${STATUS[st].icon} ${STATUS[st].label}` : "📋 " + t("c.game.status"),
          cls: st ? "on" : "", run: async () => {
            const next = stOrder[(stOrder.indexOf(st) + 1) % stOrder.length];
            try { await api(`/api/game/${id}/flag`, { body: { field: "status", value: next } }); } catch (e) { return toast(e.message, true); }
            const g = BP.lib.byId.get(id);
            if (g) g.grp.status = next;
            BP.details.delete(id);
            toast(next ? t("c.game.statusset", { status: STATUS[next].label }) : t("c.game.statusremoved"));
            const i = this.i; this.d = null; await this.render(main); this.i = i; this.update();
          } });
        this.buttons.push({ label: (d.user.favorite ? "★ " : "☆ ") + t("c.action.fav"), cls: d.user.favorite ? "on" : "", run: () => toggleFav(BP.lib.byId.get(id)) });
        if (d.user.last_played) this.buttons.push({ label: "✖ " + t("c.game.removerecent"), run: async () => {
          try { await api(`/api/game/${id}/flag`, { body: { field: "last_played", value: null } }); } catch (e) { return toast(e.message, true); }
          const g = BP.lib.byId.get(id);
          if (g) g.grp.last = 0;
          BP.details.delete(id);
          toast(t("c.game.removedrecent", { shelf: t("c.shelf.continue") }));
          const i = this.i; this.d = null; await this.render(main); this.i = Math.min(i, this.buttons.length - 1); this.update();
        } });
        if (d.versions.length > 1) this.buttons.push({ label: t("c.game.versions", { n: d.versions.length }), run: () => push(versionsScreen(d)) });
        if (d.shots) this.buttons.push({ label: "📷 " + t("c.game.shots", { n: d.shots }), run: () => push(shotsScreen(d)) });
        this.buttons.push({ label: t("c.action.back"), run: () => pop() });
        const facts = [[t("c.fact.release"), d.release_date || d.year], [t("c.fact.developer"), d.developer], [t("c.fact.genres"), (d.genres || []).join(", ")],
          [t("c.fact.players"), d.players_local],
          [t("c.fact.duration"), d.hltb ? [d.hltb.main && t("c.game.story", { h: fmtHours(d.hltb.main) }), d.hltb.complete && `100% ${fmtHours(d.hltb.complete)}`].filter(Boolean).join(" · ") : ""], [t("c.fact.playtime"), fmtTime(d.user.playtime || d.store_playtime)],
          [t("c.fact.size"), fmtSize(d.size)],
          [t("c.fact.rating"), d.rating != null ? `${(d.rating * 5).toFixed(1)} / 5${d.rating_count ? ` (${t("c.game.votes", { n: d.rating_count.toLocaleString(GSI18n.lang) })})` : ""}` : ""],
          [t("c.fact.critics"), d.rating_critics != null ? `${Math.round(d.rating_critics * 100)} / 100` : ""]].filter(([, v]) => v);
        el.innerHTML = `<div class="bp-game"><div class="big-cover">${d.media.cover ? `<img src="${d.media.cover}?w=700">` : ""}</div>
          <div class="info">${d.media.logo ? `<img class="logo-img" src="${d.media.logo}?w=700" onerror="this.replaceWith(Object.assign(document.createElement('h1'),{textContent:${JSON.stringify(d.title)}}))">` : `<h1>${esc(d.title)}</h1>`}
          <div class="meta">${esc([pc ? d.store_name : d.platform_name, d.year].filter(Boolean).join("  ·  "))}
            ${pc ? (d.installed ? " · " + t("c.game.installed") : " · " + t("c.game.notinstalled")) : d.emulator ? " · " + esc(d.emulator) : " · " + t("c.game.noemulator")}</div>
          <div class="bp-actions">${this.buttons.map((b, i) => `<div class="bp-btn ${b.cls || ""}${b.disabled ? " disabled" : ""}" data-i="${i}">${esc(b.label)}</div>`).join("")}</div>
          <div class="bp-facts">${facts.map(([k, v]) => `<span>${k}: <b>${esc(v)}</b></span>`).join("")}</div>
          ${d.description ? `<div class="bp-desc">${esc(d.description)}</div>` : ""}</div></div>`;
        this.update();
      },
      update() {
        renderNav();
        document.querySelectorAll(".bp-btn").forEach((b) => b.classList.toggle("focus", +b.dataset.i === this.i && this.navFocus === null));
      },
      move(dx, dy) {
        if (this.navFocus !== null) {
          if (dy > 0) { this.navFocus = null; this.update(); return true; }
          const n = this.navFocus + dx;
          if (n < 0 || n >= TABS.length) return false;
          this.navFocus = n; renderNav(); return true;
        }
        if (dy < 0) { this.navFocus = 0; this.update(); return true; }
        const n = this.i + dx;
        if (n < 0 || n >= this.buttons.length) return false;
        this.i = n; this.update(); return true;
      },
      ok() {
        if (this.navFocus !== null) { openTab(this.navFocus); return; }
        const b = this.buttons[this.i];
        if (b && !b.disabled) b.run(); else if (b?.disabled) { beep("err"); toast(t("c.game.noemu.console"), true); }
      },
      fav() { toggleFav(BP.lib.byId.get(id)); },
      hints: [["a", t("c.action.select")], ["b", t("c.action.back")], ["x", t("c.action.fav")]],
    };
    return scr;
  }
  BPLayouts.classic = { label: "Classico", home: classicHome, shelves: classicShelves, card: classicCard, textCard: classicTextCard, game: classicGame, nav: classicNav };
})();
