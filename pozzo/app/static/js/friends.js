"use strict";
/* Pozzo Launcher - Amici e Presenza Online in Tempo Reale via Supabase Realtime (Serverless & Gratuito).
 * Gestisce: profilo locale, codici amico (#PZ-xxxx), aggiunta amici, presenza WebSocket e inviti netplay.
 */

const Friends = (() => {
  const SUPABASE_URL = "https://ikvvmhpwhclknoekizsg.supabase.co";
  const SUPABASE_KEY = "sb_publishable_ExJEJS6EEeOuxbZpjuvJFg_n0uDOKEe";

  let socket = null;
  let retryMs = 6000;
  let heartbeatTimer = null;
  let gameCheckTimer = null;
  let onlineUsers = new Map(); // userId -> { user_id, username, friend_code, game, party_code }
  let cachedFriends = [];
  let lastTrackedState = { game: null, party_code: null };
  let detailId = null; // amico aperto nel confronto
  const CACHE_KEY = "gs.social_cache", LOG_KEY = "gs.social_log";
  // I riepiloghi sono cifrati per il solo destinatario; restano visibili i metadati (chi chiede a chi).
  let myPub = null; // chiave pubblica ECDH (base64) pubblicata nella presenza
  const keyCache = new Map(); // pk amico -> chiave AES derivata
  const friendIds = () => new Set(cachedFriends.map((f) => f.id));

  // Condivisione di cosa si sta giocando: spenta finché l'utente non la attiva
  const shareOn = () => { try { return localStorage.getItem("gs.social_share") === "1"; } catch { return false; } };
  const setShare = (v) => { try { localStorage.setItem("gs.social_share", v ? "1" : "0"); } catch {} };
  const flag = (k) => { try { return localStorage.getItem(k) === "1"; } catch { return false; } };
  const shareTimeOn = () => flag("gs.social_share_time");
  const shareAchOn = () => flag("gs.social_share_ach");
  const tr = (k, p, fb) => { const v = typeof t === "function" ? t(k, p) : k; return v === k ? fb || k : v; };
  const jget = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch { return d; } };
  const jset = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

  // ---- funzioni pure (testate in tests/test_friends_social.js)
  const normKey = (title) => String(title || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "");
  // Riepilogo da inviare: solo i dati con l'interruttore acceso, altrimenti null (non si invia niente).
  // games: [{title, minutes, last}], ach: [{title, unlocked, total}] (opzionale)
  function buildSummary({ games = [], ach = [], time = false, achievements = false, max = 50 }) {
    if (!time && !achievements) return null;
    const out = new Map();
    if (time) for (const g of games) if (g.minutes > 0 && normKey(g.title)) out.set(normKey(g.title), { k: normKey(g.title), t: g.title, m: Math.round(g.minutes), l: g.last || 0 });
    let list = [...out.values()].sort((a, b) => b.m - a.m).slice(0, max);
    if (achievements) {
      const byKey = new Map(ach.filter((a) => normKey(a.title) && a.total > 0).map((a) => [normKey(a.title), a]));
      for (const e of list) { const a = byKey.get(e.k); if (a) { e.a = a.unlocked; e.n = a.total; byKey.delete(e.k); } }
      if (!time) list = [...byKey.values()].slice(0, max).map((a) => ({ k: normKey(a.title), t: a.title, a: a.unlocked, n: a.total }));
    }
    return list;
  }
  // Giochi in comune: i più giocati (somma dei due tempi) per primi. Chi non condivide il tempo ha m assente.
  function commonGames(mine, theirs) {
    const th = new Map((theirs || []).map((g) => [g.k, g]));
    return (mine || []).filter((g) => th.has(g.k)).map((g) => ({ k: g.k, title: g.t, mine: g.m || 0, theirs: th.get(g.k).m || 0, a: th.get(g.k).a, n: th.get(g.k).n }))
      .sort((a, b) => b.mine + b.theirs - (a.mine + a.theirs));
  }
  // ---- cifratura (WebCrypto): ECDH P-256 -> HKDF-SHA256 -> AES-GCM 256
  const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  async function genKeys() {
    const kp = await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]);
    return { priv: await crypto.subtle.exportKey("jwk", kp.privateKey), pub: b64(await crypto.subtle.exportKey("raw", kp.publicKey)) };
  }
  async function deriveKey(privJwk, pubB64) {
    const priv = await crypto.subtle.importKey("jwk", privJwk, { name: "ECDH", namedCurve: "P-256" }, false, ["deriveBits"]);
    const pub = await crypto.subtle.importKey("raw", unb64(pubB64), { name: "ECDH", namedCurve: "P-256" }, false, []);
    const bits = await crypto.subtle.deriveBits({ name: "ECDH", public: pub }, priv, 256);
    const hk = await crypto.subtle.importKey("raw", bits, "HKDF", false, ["deriveKey"]);
    return crypto.subtle.deriveKey({ name: "HKDF", hash: "SHA-256", salt: new Uint8Array(32), info: new TextEncoder().encode("pozzo-friends-v1") }, hk, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  }
  async function encryptSummary(key, obj) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    return { iv: b64(iv), ct: b64(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(JSON.stringify(obj)))) };
  }
  async function decryptSummary(key, { iv, ct } = {}) {
    try { return JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: unb64(iv) }, key, unb64(ct)))); } catch { return null; }
  }
  async function ensureKeys() {
    let k = jget("gs.social_keys", null);
    if (!k || !k.priv || !k.pub) { k = await genKeys(); jset("gs.social_keys", k); }
    myPub = k.pub;
    return k;
  }
  async function sharedKey(friendPk) {
    if (!keyCache.has(friendPk)) keyCache.set(friendPk, await deriveKey((await ensureKeys()).priv, friendPk));
    return keyCache.get(friendPk);
  }

  const pushActivity = (log, entry, cap = 100) => [entry, ...(log || [])].slice(0, cap);
  const fmtMin = (m) => (m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}` : `${m} min`);

  const I = (n) => (typeof ic === "function" ? ic(n, { size: 16 }) : "");

  // ------------------------------------------------------------ Profilo Utente Locale
  function getMyProfile() {
    let u = null;
    try {
      u = JSON.parse(localStorage.getItem("gs.social_user") || "null");
    } catch {}

    if (!u || !u.id || !u.friend_code) {
      const code = "#PZ-" + Math.floor(1000 + Math.random() * 9000);
      const activeName = (typeof $("#profile-name")?.textContent === "string" ? $("#profile-name").textContent.trim() : "") || "Giocatore";
      u = {
        id: "u_" + Math.random().toString(36).slice(2, 10),
        username: activeName && activeName !== "Profilo" ? activeName : "Giocatore " + code.slice(4),
        friend_code: code,
        avatar_url: ""
      };
      saveMyProfile(u);
    }
    return u;
  }

  function saveMyProfile(u) {
    try {
      localStorage.setItem("gs.social_user", JSON.stringify(u));
    } catch {}
  }

  // Sincronizza il profilo locale con Supabase (upsert)
  async function syncMyProfile() {
    const me = getMyProfile();
    try {
      await fetch(`${SUPABASE_URL}/rest/v1/profiles`, {
        method: "POST",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": `Bearer ${SUPABASE_KEY}`,
          "Content-Type": "application/json",
          "Prefer": "resolution=merge-duplicates"
        },
        body: JSON.stringify({
          id: me.id,
          username: me.username,
          friend_code: me.friend_code,
          avatar_url: me.avatar_url || null,
          updated_at: new Date().toISOString()
        })
      });
    } catch (err) {
      // Offline o server temporaneamente irraggiungibile
    }
  }

  // ------------------------------------------------------------ API Amicizie (REST Supabase)
  async function fetchFriendsList() {
    const me = getMyProfile();
    try {
      // 1. Trova tutte le amicizie (in cui sono user_id o friend_id)
      const res = await fetch(`${SUPABASE_URL}/rest/v1/friendships?or=(user_id.eq.${me.id},friend_id.eq.${me.id})&select=*`, {
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": `Bearer ${SUPABASE_KEY}`
        }
      });
      if (!res.ok) return cachedFriends;
      const friendships = await res.json();
      if (!Array.isArray(friendships) || !friendships.length) {
        cachedFriends = [];
        updateBadge();
        return [];
      }

      // 2. Raccogli tutti gli id degli amici
      const friendIds = friendships.map((f) => (f.user_id === me.id ? f.friend_id : f.user_id));
      const uniqueIds = [...new Set(friendIds)];

      // 3. Recupera i profili degli amici
      const profRes = await fetch(`${SUPABASE_URL}/rest/v1/profiles?id=in.(${uniqueIds.join(",")})&select=*`, {
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": `Bearer ${SUPABASE_KEY}`
        }
      });
      if (!profRes.ok) return cachedFriends;
      const profiles = await profRes.json();
      const profMap = new Map((profiles || []).map((p) => [p.id, p]));

      cachedFriends = friendships.map((f) => {
        const otherId = f.user_id === me.id ? f.friend_id : f.user_id;
        const prof = profMap.get(otherId) || { id: otherId, username: "Giocatore", friend_code: "???" };
        return {
          friendshipId: f.id,
          status: f.status,
          isRequester: f.user_id === me.id,
          ...prof
        };
      });

      updateBadge();
      return cachedFriends;
    } catch (err) {
      return cachedFriends;
    }
  }

  async function addFriendByCode(rawInput) {
    const me = getMyProfile();
    const clean = String(rawInput || "").trim();
    if (!clean) throw new Error("Inserisci un codice amico o un nome utente");

    const code = clean.startsWith("#") ? clean.toUpperCase() : ("#PZ-" + clean).toUpperCase();

    // Cerca profilo
    // Valori tra virgolette: una virgola o parentesi nel testo non può alterare il filtro PostgREST
    const q = (v) => `"${v.replace(/["\\]/g, "")}"`;
    const filter = encodeURIComponent(`(friend_code.eq.${q(code)},friend_code.eq.${q(clean)},username.eq.${q(clean)})`);
    const searchRes = await fetch(`${SUPABASE_URL}/rest/v1/profiles?or=${filter}&select=*`, {
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": `Bearer ${SUPABASE_KEY}`
      }
    });

    if (!searchRes.ok) throw new Error("Errore durante la ricerca dell'amico");
    const found = await searchRes.json();
    if (!Array.isArray(found) || !found.length) {
      throw new Error(`Nessun giocatore trovato con il codice o nome "${clean}"`);
    }

    const target = found[0];
    if (target.id === me.id) {
      throw new Error("Non puoi aggiungere te stesso come amico!");
    }

    // Inserisci l'amicizia
    const addRes = await fetch(`${SUPABASE_URL}/rest/v1/friendships`, {
      method: "POST",
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": `Bearer ${SUPABASE_KEY}`,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
      },
      body: JSON.stringify({
        user_id: me.id,
        friend_id: target.id,
        status: "accepted" // Amicizia istantanea
      })
    });

    if (!addRes.ok && addRes.status !== 409) {
      throw new Error("Impossibile salvare l'amicizia in questo momento");
    }

    await fetchFriendsList();
    renderDialog();
    return target;
  }

  async function removeFriendship(friendshipId) {
    try {
      await fetch(`${SUPABASE_URL}/rest/v1/friendships?id=eq.${friendshipId}`, {
        method: "DELETE",
        headers: {
          "apikey": SUPABASE_KEY,
          "Authorization": `Bearer ${SUPABASE_KEY}`
        }
      });
      cachedFriends = cachedFriends.filter((f) => f.friendshipId !== friendshipId);
      updateBadge();
      renderDialog();
    } catch {}
  }

  // ------------------------------------------------------------ WebSocket Presenza Realtime
  function connectRealtime() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

    try {
      const wsUrl = `wss://ikvvmhpwhclknoekizsg.supabase.co/realtime/v1/websocket?apikey=${SUPABASE_KEY}&vsn=1.0.0`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        retryMs = 6000;
        const me = getMyProfile();
        // 1. Join nel canale globale di presenza
        socket.send(JSON.stringify({
          topic: "realtime:pozzo_presence",
          event: "phx_join",
          payload: {
            config: { presence: { key: me.id }, broadcast: { self: false } },
            access_token: SUPABASE_KEY
          },
          ref: "join_friends"
        }));

        // 2. Heartbeat ogni 25 secondi
        clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(() => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ topic: "phoenix", event: "heartbeat", payload: {}, ref: "hb" }));
          }
        }, 25000);

        // 3. Invia presenza iniziale
        trackPresence();
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event === "presence_state") {
            // Stato completo degli utenti online
            onlineUsers.clear();
            const state = msg.payload || {};
            for (const [key, val] of Object.entries(state)) {
              const meta = val.metas?.[0];
              if (meta && meta.user_id) {
                onlineUsers.set(meta.user_id, meta);
              }
            }
            updateBadge();
            if (isOpen()) renderDialog(true);
            for (const id of onlineUsers.keys()) requestSummary(id);
          } else if (msg.event === "broadcast") {
            onBroadcast(msg.payload);
          } else if (msg.event === "presence_diff") {
            // Variazioni (utenti entrati / usciti)
            const joins = msg.payload?.joins || {};
            const leaves = msg.payload?.leaves || {};
            for (const [key, val] of Object.entries(joins)) {
              const meta = val.metas?.[0];
              if (meta && meta.user_id) {
                const prev = onlineUsers.get(meta.user_id);
                if (meta.game && meta.game !== prev?.game) logActivity(meta);
                if (!prev) requestSummary(meta.user_id);
                onlineUsers.set(meta.user_id, meta);
              }
            }
            for (const key of Object.keys(leaves)) {
              if (!joins[key]) onlineUsers.delete(key); // un aggiornamento di presenza arriva come leave+join con la stessa chiave
            }
            updateBadge();
            if (isOpen()) renderDialog(true);
          }
        } catch {}
      };

      socket.onclose = () => {
        clearInterval(heartbeatTimer);
        setTimeout(connectRealtime, retryMs); // Riconnessione automatica con backoff (max 2 min)
        retryMs = Math.min(retryMs * 2, 120000);
      };

      socket.onerror = () => {
        try { socket.close(); } catch {}
      };
    } catch {}
  }

  // ------------------------------------------------------------ Riepilogo giochi / attività (broadcast, solo con opt-in)
  function logActivity(meta) {
    if (!friendIds().has(meta.user_id)) return;
    jset(LOG_KEY, pushActivity(jget(LOG_KEY, []), { u: meta.user_id, n: meta.username || "", g: meta.game, at: Date.now() }));
  }

  function bcast(event, payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    try { socket.send(JSON.stringify({ topic: "realtime:pozzo_presence", event: "broadcast", payload: { type: "broadcast", event, payload }, ref: "bc_" + Date.now() })); } catch {}
  }

  function requestSummary(toId) {
    if (friendIds().has(toId)) bcast("fr_req", { from: getMyProfile().id, to: toId });
  }

  async function mySummary() {
    if (!shareTimeOn() && !shareAchOn()) return null;
    const games = [];
    if (typeof S !== "undefined" && S.games) {
      for (const g of S.games) if (g.grp && g.grp.primary === g.id && g.grp.playtime > 0) games.push({ title: g.title, minutes: g.grp.playtime / 60, last: g.grp.last });
    }
    let ach = [];
    if (shareAchOn() && typeof window.api === "function") {
      // l'endpoint arriva da un altro ramo: se manca (404) niente obiettivi
      try { const r = await window.api("/api/achievements"); ach = Array.isArray(r) ? r : Array.isArray(r?.games) ? r.games : []; } catch {}
    }
    return buildSummary({ games, ach, time: shareTimeOn(), achievements: shareAchOn() });
  }

  async function onBroadcast(msg) {
    const p = msg?.payload;
    const me = getMyProfile();
    if (!p || p.to !== me.id || !friendIds().has(p.from)) return;
    if (msg.event === "fr_req") {
      const pk = onlineUsers.get(p.from)?.pk;
      if (!pk) return; // client senza chiave: niente riepilogo in chiaro
      const games = await mySummary();
      if (!games) return;
      try { bcast("fr_sum", { from: me.id, to: p.from, ...(await encryptSummary(await sharedKey(pk), games)) }); } catch {}
    } else if (msg.event === "fr_sum" && p.iv && p.ct) {
      const pk = onlineUsers.get(p.from)?.pk;
      let games = null;
      try { if (pk) games = await decryptSummary(await sharedKey(pk), p); } catch {}
      if (!Array.isArray(games)) return;
      const cache = jget(CACHE_KEY, {});
      cache[p.from] = { at: Date.now(), games: games.slice(0, 50) };
      jset(CACHE_KEY, cache);
      if (isOpen()) renderDialog(true);
    }
  }

  // Nomi degli amici (dalla cache) che hanno questo gioco: riga «Amici che ci giocano» nel dettaglio
  function playingNames(title) {
    const k = normKey(title), cache = jget(CACHE_KEY, {});
    return cachedFriends.filter((f) => (cache[f.id]?.games || []).some((g) => g.k === k)).map((f) => f.username).join(", ");
  }

  function trackPresence(forceGame = null, forceParty = null) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const me = getMyProfile();

    let game = forceGame !== null ? forceGame : lastTrackedState.game;
    let party = forceParty !== null ? forceParty : lastTrackedState.party_code;
    if (!shareOn()) { game = null; party = null; }

    lastTrackedState.game = game;
    lastTrackedState.party_code = party;

    try {
      socket.send(JSON.stringify({
        topic: "realtime:pozzo_presence",
        event: "presence",
        payload: {
          type: "presence",
          event: "TRACK",
          payload: {
            user_id: me.id,
            username: me.username,
            friend_code: me.friend_code,
            game: game || null,
            party_code: party || null,
            pk: myPub,
            status: game ? "in_game" : "online"
          }
        },
        ref: "track_" + Date.now()
      }));
    } catch {}
  }

  function startLiveWatch() {
    clearInterval(gameCheckTimer);
    gameCheckTimer = setInterval(async () => {
      if (!shareOn() && lastTrackedState.game === null) return; // niente da leggere né da inviare
      let activeGame = null;
      let activeParty = null;

      // 1. Controlla gioco in esecuzione
      if (typeof window.api === "function") {
        try {
          const runSt = await window.api("/api/running").catch(() => null);
          if (runSt && ["starting", "running", "extracting"].includes(runSt.status) && runSt.title) {
            activeGame = runSt.title;
          }
        } catch {}
      }

      // Se non da API, controlla Big Picture
      if (!activeGame && typeof window.BP !== "undefined" && window.BP?.running?.title) {
        activeGame = window.BP.running.title;
      }

      if (!shareOn()) activeGame = activeParty = null;
      if (activeGame !== lastTrackedState.game || activeParty !== lastTrackedState.party_code) {
        trackPresence(activeGame, activeParty);
      }
    }, 4000);
  }

  // ------------------------------------------------------------ Badge sul pulsante nella barra in alto
  function updateBadge() {
    const badge = $("#friends-badge");
    if (!badge) return;
    const me = getMyProfile();
    const n = cachedFriends.filter((f) => f.id !== me.id && onlineUsers.has(f.id)).length;
    badge.textContent = String(n);
    badge.hidden = n === 0;
    $("#mb-friends")?.classList.toggle("has-online", n > 0);
  }

  // ------------------------------------------------------------ Pannello Amici (popover sotto il pulsante)
  let editingName = false;
  let confirmRemoveId = null;

  const isOpen = () => !!$("#fr-pop");

  function closePop() {
    $("#fr-pop")?.remove();
    editingName = false;
    confirmRemoveId = null;
    detailId = null;
    $("#mb-friends")?.setAttribute("aria-expanded", "false");
  }

  async function openPop() {
    const btn = $("#mb-friends");
    if (!btn) return;
    document.body.insertAdjacentHTML("beforeend", `<div id="fr-pop" role="dialog" aria-label="Amici"></div>`);
    const r = btn.getBoundingClientRect();
    const el = $("#fr-pop");
    el.style.top = `${Math.round(r.bottom + 4)}px`;
    el.style.right = `${Math.max(8, Math.round(innerWidth - r.right))}px`;
    btn.setAttribute("aria-expanded", "true");
    renderDialog();
    $("#fr-close")?.focus();
    // i miei giochi (per il confronto) vengono dalla libreria già caricata, senza chiamate di rete
    jset("gs.social_mine", buildSummary({ games: (typeof S !== "undefined" && S.games || []).filter((g) => g.grp && g.grp.primary === g.id && g.grp.playtime > 0).map((g) => ({ title: g.title, minutes: g.grp.playtime / 60 })), time: true, max: 500 }));
    await fetchFriendsList();
    renderDialog(true);
  }

  function avatar(p, online) {
    const hue = [...String(p.id || "")].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 0);
    const ini = (String(p.username || "?").trim()[0] || "?").toUpperCase();
    const dot = online === undefined ? "" : `<i class="fr-dot${online ? " on" : ""}"></i><span class="sr-only">${online ? "in linea" : "offline"}</span>`;
    return `<span class="fr-av" style="--h:${hue}">${escapeHtml(ini)}${dot}</span>`;
  }

  function renderDialog(keepScroll = false) {
    const pop = $("#fr-pop");
    if (!pop) return;
    const me = getMyProfile();
    const scrollPos = keepScroll ? pop.querySelector(".fr-body")?.scrollTop || 0 : 0;
    // Gli aggiornamenti di presenza ridisegnano il pannello: non perdere quello che l'utente sta scrivendo.
    const keep = {};
    const a = document.activeElement;
    const focusKey = a && pop.contains(a) ? (a.id ? "#" + a.id : a.dataset.removeFriendship ? `[data-remove-friendship="${a.dataset.removeFriendship}"]` : a.dataset.joinParty ? "[data-join-party]" : null) : null;
    for (const id of ["add-friend-input", "fr-name-input"]) {
      const el = pop.querySelector("#" + id);
      if (el) keep[id] = { v: el.value, focus: document.activeElement === el };
    }

    if (detailId) return renderDetail(pop, me);
    const online = [];
    const offline = [];
    for (const f of cachedFriends) {
      if (f.id === me.id) continue;
      const presence = onlineUsers.get(f.id);
      (presence ? online : offline).push({ ...f, presence });
    }
    online.sort((a, b) => !!b.presence.game - !!a.presence.game || String(a.username).localeCompare(String(b.username)));
    offline.sort((a, b) => String(a.username).localeCompare(String(b.username)));

    const section = (title, list, isOn, empty) => `
      <div class="fr-sec">${title} <span class="fr-n">${list.length}</span></div>
      ${list.length ? list.map((f) => renderFriendRow(f, isOn)).join("") : `<div class="fr-empty">${empty}</div>`}`;

    pop.innerHTML = `
      <div class="fr-head"><b>Amici</b><button type="button" class="fr-x" id="fr-close" aria-label="Chiudi" title="Chiudi">${I("close")}</button></div>
      <div class="fr-body">
        <div class="fr-me">
          ${avatar(me, true)}
          <div class="fr-who">
            ${editingName
              ? `<input id="fr-name-input" class="field" maxlength="24" value="${escapeHtml(me.username)}" aria-label="Il tuo nome visibile agli amici" autocomplete="off">`
              : `<strong>${escapeHtml(me.username)}</strong>`}
            <span class="fr-code">${escapeHtml(me.friend_code)}</span>
          </div>
          <button class="fr-ib" type="button" id="copy-my-code-btn" title="Copia il tuo codice amico" aria-label="Copia codice amico">${I("copy")}</button>
          <button class="fr-ib" type="button" id="edit-my-name-btn" title="${editingName ? "Salva nome" : "Modifica nome"}" aria-label="${editingName ? "Salva nome" : "Modifica nome"}">${I(editingName ? "check" : "edit")}</button>
        </div>
        <div class="fr-add">
          <input type="text" id="add-friend-input" class="field" placeholder="Aggiungi con codice (#PZ-1234) o nome" autocomplete="off" aria-label="Codice amico o nome">
          <button class="btn primary" type="button" id="add-friend-btn" aria-label="Aggiungi amico">+</button>
        </div>
        <div id="add-friend-msg" class="fr-msg" role="status"></div>
        <label class="fr-share"><input type="checkbox" id="fr-share"${shareOn() ? " checked" : ""}> Mostra agli amici a cosa sto giocando</label>
        <label class="fr-share"><input type="checkbox" id="fr-share-time"${shareTimeOn() ? " checked" : ""}> ${tr("fr.shareTime", 0, "Condividi il tempo di gioco")}</label>
        <label class="fr-share"><input type="checkbox" id="fr-share-ach"${shareAchOn() ? " checked" : ""}> ${tr("fr.shareAch", 0, "Condividi gli obiettivi")}</label>
        <div class="fr-priv">${tr("fr.privacy")}</div>
        ${section("In linea", online, true, "Nessun amico in linea")}
        ${section("Offline", offline, false, "Nessun amico offline")}
        <div class="fr-sec">${tr("fr.activity")}</div>
        ${activityHtml(jget(LOG_KEY, []).slice(0, 10), true)}
      </div>`;

    pop.querySelector(".fr-body").scrollTop = scrollPos;
    for (const [id, k] of Object.entries(keep)) {
      const el = pop.querySelector("#" + id);
      if (el) { el.value = k.v; if (k.focus) el.focus(); }
    }
    if (editingName && !keep["fr-name-input"]) pop.querySelector("#fr-name-input")?.select();
    else if (focusKey && !(keep["add-friend-input"]?.focus || keep["fr-name-input"]?.focus)) pop.querySelector(focusKey)?.focus();

    $("#fr-close").onclick = () => { closePop(); $("#mb-friends")?.focus(); };

    $("#copy-my-code-btn").onclick = async () => {
      try {
        await navigator.clipboard.writeText(me.friend_code);
        if (typeof window.toast === "function") window.toast("Codice amico copiato ✓");
      } catch {
        if (typeof window.toast === "function") window.toast(me.friend_code);
      }
    };

    const saveName = () => {
      const nuovo = (pop.querySelector("#fr-name-input")?.value || "").trim();
      editingName = false;
      if (nuovo && nuovo !== me.username) {
        me.username = nuovo;
        saveMyProfile(me);
        syncMyProfile();
        trackPresence();
      }
      renderDialog(true);
    };
    $("#edit-my-name-btn").onclick = () => {
      if (editingName) return saveName();
      editingName = true;
      renderDialog(true);
    };
    const nameInp = pop.querySelector("#fr-name-input");
    if (nameInp) {
      nameInp.onkeydown = (e) => {
        if (e.key === "Enter") { e.preventDefault(); saveName(); }
        else if (e.key === "Escape") { e.stopPropagation(); editingName = false; renderDialog(true); }
      };
    }

    const doAdd = async () => {
      const inp = $("#add-friend-input");
      const msg = $("#add-friend-msg");
      if (!inp || !inp.value.trim()) return;
      msg.className = "fr-msg";
      msg.textContent = "Ricerca in corso…";
      try {
        const added = await addFriendByCode(inp.value.trim());
        // addFriendByCode ridisegna il pannello: il messaggio va scritto sul nuovo elemento
        const m2 = $("#add-friend-msg");
        if (m2) { m2.className = "fr-msg ok"; m2.textContent = `✓ ${added.username} aggiunto`; }
        if (typeof window.toast === "function") window.toast(`Amico ${added.username} aggiunto!`);
      } catch (err) {
        msg.className = "fr-msg bad";
        msg.textContent = err.message || "Errore durante l'aggiunta";
      }
    };
    $("#fr-share").onchange = (e) => { setShare(e.target.checked); trackPresence(); };
    $("#fr-share-time").onchange = (e) => { try { localStorage.setItem("gs.social_share_time", e.target.checked ? "1" : "0"); } catch {} };
    $("#fr-share-ach").onchange = (e) => { try { localStorage.setItem("gs.social_share_ach", e.target.checked ? "1" : "0"); } catch {} };
    pop.querySelectorAll("[data-friend-detail]").forEach((b) => {
      b.onclick = () => { detailId = b.dataset.friendDetail; renderDialog(); requestSummary(detailId); };
    });
    $("#add-friend-btn").onclick = doAdd;
    $("#add-friend-input").onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); doAdd(); }
    };

    pop.querySelectorAll("[data-remove-friendship]").forEach((b) => {
      b.onclick = (e) => {
        e.stopPropagation();
        const fid = Number(b.dataset.removeFriendship);
        if (confirmRemoveId === fid) {
          confirmRemoveId = null;
          removeFriendship(fid);
        } else {
          confirmRemoveId = fid; // secondo clic per confermare, niente finestre di sistema
          renderDialog(true);
          setTimeout(() => { if (confirmRemoveId === fid) { confirmRemoveId = null; if (isOpen()) renderDialog(true); } }, 3000);
        }
      };
    });

    pop.querySelectorAll("[data-join-party]").forEach((b) => {
      b.onclick = (e) => {
        e.stopPropagation();
        const code = b.dataset.joinParty;
        closePop();
        // Anteprima dell'invito: l'utente conferma, nessuna partecipazione automatica
        if (typeof window.openJoinWith === "function") window.openJoinWith(code);
      };
    });
  }

  function activityHtml(list, withName) {
    if (!list.length) return `<div class="fr-empty">${tr("fr.noActivity")}</div>`;
    return list.map((e) => `<div class="fr-act">${withName ? `<b>${escapeHtml(e.n)}</b> ` : ""}${escapeHtml(e.g)} <span class="fr-sub">${escapeHtml(new Date(e.at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" }))}</span></div>`).join("");
  }

  // Confronto con un amico: giochi in comune con i due tempi affiancati + sue attività
  function renderDetail(pop, me) {
    const f = cachedFriends.find((x) => x.id === detailId);
    if (!f) { detailId = null; return renderDialog(); }
    const sum = jget(CACHE_KEY, {})[f.id];
    const mine = (jget("gs.social_mine", null) || []);
    const rows = sum ? commonGames(mine, sum.games) : [];
    const max = Math.max(1, ...rows.map((r) => Math.max(r.mine, r.theirs)));
    const bar = (m) => `<i class="fr-bar" style="width:${Math.round((m / max) * 100)}%"></i>`;
    pop.innerHTML = `
      <div class="fr-head"><button type="button" class="fr-x" id="fr-back" aria-label="${tr("fr.back", 0, "Indietro")}" title="${tr("fr.back", 0, "Indietro")}">&larr;</button><b>${escapeHtml(f.username)}</b><button type="button" class="fr-x" id="fr-close" aria-label="Chiudi" title="Chiudi">${I("close")}</button></div>
      <div class="fr-body">
        <div class="fr-sec">${tr("fr.common")}</div>
        ${sum ? `<div class="fr-sub">${tr("fr.updated", { date: new Date(sum.at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) })}</div>` : ""}
        ${rows.length ? rows.map((r) => `<div class="fr-cmp"><div>${escapeHtml(r.title)}${r.n ? ` <span class="fr-sub">${tr("fr.achv", { n: r.a, m: r.n })}</span>` : ""}</div>
          <div class="fr-line"><span>${tr("fr.you")}</span>${bar(r.mine)}<span>${fmtMin(r.mine)}</span></div>
          <div class="fr-line"><span>${escapeHtml(f.username)}</span>${bar(r.theirs)}<span>${r.theirs ? fmtMin(r.theirs) : "-"}</span></div></div>`).join("")
          : `<div class="fr-empty">${sum ? tr("fr.noCommon") : tr("fr.noData", { name: f.username })}</div>`}
        <div class="fr-sec">${tr("fr.activity")}</div>
        ${activityHtml(jget(LOG_KEY, []).filter((e) => e.u === f.id), false)}
      </div>`;
    $("#fr-back").onclick = () => { detailId = null; renderDialog(); };
    $("#fr-close").onclick = () => { closePop(); $("#mb-friends")?.focus(); };
  }

  function renderFriendRow(f, isOnline) {
    const game = f.presence?.game;
    const party = f.presence?.party_code;
    const confirming = confirmRemoveId === f.friendshipId;
    return `
      <div class="fr-row${isOnline ? "" : " off"}">
        ${avatar(f, isOnline)}
        <div class="fr-who" data-friend-detail="${escapeHtml(f.id)}" role="button" tabindex="0" title="${tr("fr.compare", 0, "Confronta")}" style="cursor:pointer">
          <strong>${escapeHtml(f.username || "Giocatore")}</strong>
          <span class="fr-sub${game ? " game" : ""}">${game ? `🎮 ${escapeHtml(game)}` : isOnline ? "Nel menu" : escapeHtml(f.friend_code || "Offline")}</span>
        </div>
        ${party ? `<button class="btn primary small fr-join" type="button" data-join-party="${escapeHtml(party)}">${I("play")} Unisciti</button>` : ""}
        <button class="fr-ib${confirming ? " danger" : ""}" type="button" data-remove-friendship="${f.friendshipId}" title="Rimuovi amico" aria-label="Rimuovi ${escapeHtml(f.username || "amico")}">${confirming ? "Rimuovere?" : I("close")}</button>
      </div>`;
  }


  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[m]);
  }

  // ------------------------------------------------------------ Inizializzazione
  async function init() {
    getMyProfile();
    try { await ensureKeys(); } catch {}
    await syncMyProfile();
    connectRealtime();
    startLiveWatch();

    const btn = $("#mb-friends");
    if (btn) btn.onclick = (e) => { e.stopPropagation(); if (isOpen()) closePop(); else openPop(); };
    if (typeof window !== "undefined" && window.addEventListener) window.addEventListener("resize", () => { if (isOpen()) closePop(); });
    if (typeof document !== "undefined") {
      document.addEventListener("mousedown", (e) => { if (isOpen() && !e.target.closest("#fr-pop, #mb-friends")) closePop(); });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && isOpen()) { closePop(); $("#mb-friends")?.focus(); }
      });
    }
    await fetchFriendsList();
  }


  return {
    init,
    getMyProfile,
    fetchFriendsList,
    addFriendByCode,
    trackPresence,
    renderDialog,
    playingNames,
    genKeys, deriveKey, encryptSummary, decryptSummary,
    normKey, buildSummary, commonGames, pushActivity
  };
})();

if (typeof window !== "undefined") window.Friends = Friends;
if (typeof module !== "undefined") module.exports = Friends;

// Avvio automatico quando il DOM è pronto
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => Friends.init());
  } else {
    Friends.init();
  }
}
