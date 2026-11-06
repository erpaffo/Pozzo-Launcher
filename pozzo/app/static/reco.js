"use strict";
/* Pozzo Launcher - raccomandazioni ("Per te") e questionario "A cosa vuoi giocare?".
 *
 * Tutto avviene nel browser sui dati della libreria, senza servizi esterni:
 *  1. ogni gioco diventa un insieme di caratteristiche pesate: generi (normalizzati tra lingue e
 *     fonti diverse), franchise/collezione, sviluppatore, console, decennio, multigiocatore locale;
 *  2. il profilo dell'utente e' la somma delle caratteristiche dei giochi giocati, pesate per tempo
 *     di gioco (anche quello degli store, es. Steam), preferiti, numero di avvii e partite recenti;
 *  3. il punteggio di un gioco non giocato = somiglianza col profilo + qualita' (voti di pubblico e
 *     critica, con poco peso se i voti sono pochi) + i gusti dichiarati nel questionario.
 */

const RECO = (() => {
  // generi canonici: le fonti usano nomi diversi (Role-Playing, Role-playing (RPG), Gioco di Ruolo...)
  const GENRES = [
    ["action", "i.reco.genre.action", /action|azione/], ["platform", "i.reco.genre.platform", /platform|piattaform/],
    ["adventure", "i.reco.genre.adventure", /adventure|avventura/], ["rpg", "i.reco.genre.rpg", /role|rpg|ruolo|jrpg/],
    ["shmup", "i.reco.genre.shmup", /shoot.?.?em|shmup|scrolling shooter/],
    ["shooter", "i.reco.genre.shooter", /shooter|sparatutto|sparo|fps|lightgun/], ["racing", "i.reco.genre.racing", /racing|corsa|guida|driving|kart/],
    ["sports", "i.reco.genre.sports", /sport|calcio|football|soccer|tennis|golf|basket|hockey|baseball|wrestling|boxing/],
    ["puzzle", "i.reco.genre.puzzle", /puzzle|thinking|rompicapo|logic/], ["strategy", "i.reco.genre.strategy", /strateg|tactic|tattic|rts|tbs|4x/],
    ["fighting", "i.reco.genre.fighting", /fight|picchiaduro|combattimento|versus/],
    ["beatemup", "i.reco.genre.beatemup", /beat.?.?em|hack and slash|beat.?em all/],
    ["simulation", "i.reco.genre.simulation", /simul|management|construction|gestional|farming|tycoon/],
    ["horror", "i.reco.genre.horror", /horror|survival horror/], ["music", "i.reco.genre.music", /music|danc|rhythm|ritm/],
    ["party", "i.reco.genre.party", /party|board|card|quiz|trivia|casino|pinball|tavolo|gambling/],
    ["stealth", "i.reco.genre.stealth", /stealth/], ["sandbox", "i.reco.genre.sandbox", /sandbox|open world|mondo aperto|survival/],
    ["story", "i.reco.genre.story", /visual novel|point.?and.?click|interactive|narrative/], ["arcade", "i.reco.genre.arcade", /arcade/],
    ["indie", "i.reco.genre.indie", /indie/], ["roguelike", "i.reco.genre.roguelike", /rogue/],
  ];
  const GENRE_LABEL = Object.fromEntries(GENRES.map(([id, l]) => [id, l]));
  const genreCache = new Map();
  function canonGenres(str) {
    if (genreCache.has(str)) return genreCache.get(str);
    const f = fold(str), out = new Set();
    for (const [id, , re] of GENRES) if (re.test(f)) out.add(id);
    genreCache.set(str, [...out]);
    return [...out];
  }

  const minutes = (g) => ((g.grp.playtime || 0) + (g.splay || 0) * 60) / 60;
  const played = (g) => !!(g.grp.last || g.grp.playtime || g.splay > 0 || g.grp.status === "done");
  const quality = (g) => {
    // voto "prudente": con pochi voti si avvicina a 0.6
    const r = g.rating != null ? (g.rating * Math.min(g.votes || 3, 50) + 0.6 * 5) / (Math.min(g.votes || 3, 50) + 5) : 0.55;
    return g.critics != null ? (r + g.critics) / 2 : r;
  };

  function features(g) {
    if (g._f) return g._f;
    const f = new Map();
    for (const x of canonGenres(g.genres)) f.set("g:" + x, 1);
    for (const c of g.grp.colls) f.set("c:" + c, 1.4);
    if (g.dev) f.set("d:" + fold(g.dev.split(",")[0]).trim(), 0.6);
    f.set("p:" + g.platform, 0.35);
    if (g.year) f.set("y:" + Math.floor(g.year / 10), 0.25);
    if (g.players >= 2) f.set("m", 0.3);
    g._f = f;
    return f;
  }

  /** Giochi giocati con il loro peso (quanto dicono dei gusti dell'utente). */
  function seeds(games) {
    const now = Date.now() / 1000;
    return games.filter(played).map((g) => {
      let w = Math.log1p(minutes(g) / 20) + (g.grp.favorite ? 3 : 0) + Math.min(g.grp.plays || 0, 10) * 0.15;
      if (g.grp.last && now - g.grp.last < 30 * 86400) w += 1;
      return { g, w: Math.max(w, 0.3) };
    }).sort((a, b) => b.w - a.w);
  }

  function profile(games, tastes) {
    const p = new Map();
    for (const { g, w } of seeds(games)) for (const [k, v] of features(g)) p.set(k, (p.get(k) || 0) + v * w);
    // gusti dichiarati nel questionario
    for (const x of tastes?.genres || []) p.set("g:" + x, (p.get("g:" + x) || 0) + 4);
    for (const x of moodGenres(tastes?.moods || [])) p.set("g:" + x, (p.get("g:" + x) || 0) + 2);
    const max = Math.max(1, ...p.values());
    for (const [k, v] of p) p.set(k, v / max);
    return p;
  }

  function affinity(g, prof) {
    let s = 0, n = 0;
    for (const [k, v] of features(g)) { s += (prof.get(k) || 0) * v; n += v; }
    return n ? s / Math.sqrt(n) : 0;
  }

  /** Candidati: un gioco per gruppo, non nascosto, mai giocato (o anche giocati se allowPlayed). */
  function pool(games, allowPlayed = false) {
    return games.filter((g) => g.id === g.grp.primary && !g.grp.hidden && (allowPlayed || !played(g))
      && g.grp.status !== "dropped" && g.grp.status !== "done"
      && !/switch online|bios|demo/i.test(g.title)
      && !(g.store === "online" && g.installed));
  }

  function ranked(list, score, n = 30) {
    return list.map((g) => ({ g, s: score(g) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, n).map((x) => x.g);
  }

  function similar(seed, cands, n = 24) {
    const fs = features(seed);
    return ranked(cands.filter((g) => g.gi !== seed.gi), (g) => {
      let s = 0;
      for (const [k, v] of features(g)) if (fs.has(k)) s += v * fs.get(k);
      return s > 0.9 ? s + quality(g) * 1.5 : 0;
    }, n);
  }

  /** Righe della vista "Per te". `ownedOnly`: esclude i giochi da scaricare/installare. */
  function rows(games, tastes = null) {
    const out = [];
    const sd = seeds(games);
    const prof = profile(games, tastes);
    const cands = pool(games);
    const notOnline = cands.filter((g) => g.store !== "online");
    const recent = games.filter((g) => g.id === g.grp.primary && g.grp.last && !g.grp.hidden).sort((a, b) => b.grp.last - a.grp.last);
    const playing = games.filter((g) => g.id === g.grp.primary && g.grp.status === "playing" && !g.grp.hidden)
      .sort((a, b) => (b.grp.last || 0) - (a.grp.last || 0));
    if (playing.length) out.push({ id: "playing", title: t("i.reco.row.playing"), items: playing.slice(0, 20) });
    const rest = recent.filter((g) => g.grp.status !== "playing");
    if (rest.length) out.push({ id: "continue", title: t("i.reco.row.recent"), items: rest.slice(0, 20) });
    const backlog = games.filter((g) => g.id === g.grp.primary && g.grp.status === "backlog" && !g.grp.hidden);
    if (backlog.length) out.push({ id: "backlog", title: t("i.reco.row.backlog"), why: t("i.reco.why.shortest"),
      items: backlog.sort((a, b) => (a.hltb ?? 999) - (b.hltb ?? 999)).slice(0, 30) });
    if (prof.size) {
      out.push({ id: "foryou", title: sd.length ? t("i.reco.title") : t("i.reco.foryou.byTastes"),
        why: sd.length ? t("i.reco.foryou.whyPlayed") : t("i.reco.foryou.whyQuiz"),
        items: ranked(notOnline, (g) => affinity(g, prof) * 2 + quality(g), 30) });
    }
    for (const { g } of sd.slice(0, 4)) {
      const items = similar(g, notOnline);
      if (items.length >= 4) out.push({ id: "because:" + g.id, title: t("i.reco.because", { title: g.title }), items, seed: g.id });
    }
    // generi preferiti
    const topGenres = [...prof.entries()].filter(([k]) => k.startsWith("g:")).sort((a, b) => b[1] - a[1]).slice(0, 3);
    for (const [k] of topGenres) {
      const id = k.slice(2);
      const items = ranked(notOnline.filter((g) => canonGenres(g.genres).includes(id)), (g) => quality(g) + affinity(g, prof) * 0.5, 30);
      if (items.length >= 4) out.push({ id: "genre:" + id, title: t("i.reco.bestOf", { g: t(GENRE_LABEL[id]) }), items });
    }
    const add = (id, title, list, score, why) => { const items = ranked(list, score, 30); if (items.length >= 4) out.push({ id, title, items, why }); };
    add("multi", t("i.reco.row.multi"), notOnline.filter((g) => g.players >= 2),
      (g) => quality(g) + affinity(g, prof) * 0.5 + Math.min(g.players, 4) * 0.03, t("i.reco.why.localMulti"));
    add("top", t("i.reco.row.top"), notOnline.filter((g) => g.critics >= 0.88 || (g.rating >= 0.85 && g.votes >= 50)),
      (g) => quality(g) + affinity(g, prof) * 0.3);
    add("gems", t("i.reco.row.gems"), notOnline.filter((g) => g.rating >= 0.8 && g.votes >= 5 && g.votes < 200),
      (g) => quality(g) + affinity(g, prof) * 0.6, t("i.reco.why.gems"));
    add("classics", t("i.reco.row.classics"), notOnline.filter((g) => g.year && g.year < 2000),
      (g) => (quality(g) > 0.72 ? quality(g) + affinity(g, prof) * 0.4 : 0));
    // console piu' giocate
    const platW = new Map();
    for (const { g, w } of sd) platW.set(g.platform, (platW.get(g.platform) || 0) + w);
    for (const [pid] of [...platW.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2)) {
      add("plat:" + pid, t("i.reco.row.platform", { p: GS_platName(pid) }), notOnline.filter((g) => g.platform === pid),
        (g) => quality(g) + affinity(g, prof) * 0.4);
    }
    add("new", t("i.reco.row.new"), notOnline.filter((g) => g.year >= new Date().getFullYear() - 3), (g) => g.year / 3000 + quality(g));
    add("shop", t("i.reco.row.shop"), cands.filter((g) => g.store && !g.installed),
      (g) => affinity(g, prof) * 2 + quality(g));
    // niente ripetizioni troppo vicine: lo stesso gioco al massimo in 2 righe
    const seen = new Map();
    for (const r of out) {
      if (r.id === "continue" || r.id === "playing" || r.id === "backlog") continue;
      r.items = r.items.filter((g) => { const n = seen.get(g.id) || 0; seen.set(g.id, n + 1); return n < 2; });
    }
    return out.filter((r) => r.items.length);
  }

  /** Collezioni (saghe/franchise) da scoprire: [{id, title, why, items: [{coll, games, played, why}]}]. */
  function collectionRows(games, colls, tastes = null) {
    const prof = profile(games, tastes);
    const by = new Map();
    for (const g of games) {
      if (g.id !== g.grp.primary || g.grp.hidden || g.store === "online") continue;
      for (const i of g.grp.colls) { if (!by.has(i)) by.set(i, []); by.get(i).push(g); }
    }
    const info = colls.filter((c) => !c.hidden && (by.get(c.idx) || []).length >= 2).map((c) => {
      const gs = by.get(c.idx);
      const playedG = gs.filter(played);
      const top = gs.slice().sort((a, b) => quality(b) - quality(a)).slice(0, 5);
      return { coll: c, games: gs, played: playedG.length,
        minutes: playedG.reduce((a, g) => a + minutes(g), 0),
        quality: top.reduce((a, g) => a + quality(g), 0) / top.length,
        affinity: top.reduce((a, g) => a + affinity(g, prof), 0) / top.length };
    });
    const rows = [];
    const cont = info.filter((x) => x.played && x.played < x.games.length).sort((a, b) => b.minutes - a.minutes).slice(0, 15)
      .map((x) => ({ ...x, why: t("i.reco.coll.played", { a: x.played, b: x.games.length }) }));
    if (cont.length) rows.push({ id: "c-continue", title: t("i.reco.coll.continue"), items: cont });
    const seen = new Set(cont.map((x) => x.coll.slug));
    const fit = info.filter((x) => !seen.has(x.coll.slug) && x.affinity > 0)
      .sort((a, b) => b.affinity * Math.log(2 + b.games.length) - a.affinity * Math.log(2 + a.games.length)).slice(0, 15)
      .map((x) => ({ ...x, why: t("i.reco.coll.similar", { n: x.games.length }) }));
    if (fit.length >= 3) rows.push({ id: "c-fit", title: t("i.reco.coll.fit"), items: fit });
    fit.forEach((x) => seen.add(x.coll.slug));
    const best = info.filter((x) => !seen.has(x.coll.slug) && x.games.length >= 3).sort((a, b) => b.quality - a.quality).slice(0, 15)
      .map((x) => ({ ...x, why: t("i.reco.coll.avg", { n: x.games.length, v: Math.round(x.quality * 100) }) }));
    if (best.length >= 3) rows.push({ id: "c-best", title: t("i.reco.coll.best"), items: best });
    const big = info.filter((x) => !seen.has(x.coll.slug)).sort((a, b) => b.games.length - a.games.length).slice(0, 15)
      .map((x) => ({ ...x, why: t("i.reco.coll.count", { n: x.games.length }) }));
    if (big.length >= 3) rows.push({ id: "c-big", title: t("i.reco.coll.big"), items: big });
    return rows;
  }

  /* ------------------------------------------------------------ questionario */
  const MOODS = {
    relax: { label: t("i.reco.mood.relax"), genres: ["puzzle", "simulation", "party", "sandbox", "music"] },
    action: { label: t("i.reco.mood.action"), genres: ["action", "shooter", "beatemup", "platform", "fighting", "shmup"] },
    story: { label: t("i.reco.mood.story"), genres: ["rpg", "adventure", "story"] },
    challenge: { label: t("i.reco.mood.challenge"), genres: ["roguelike", "shmup", "platform", "fighting", "arcade"] },
    compete: { label: t("i.reco.mood.compete"), genres: ["racing", "sports", "fighting", "party"] },
    brain: { label: t("i.reco.mood.brain"), genres: ["puzzle", "strategy"] },
    scary: { label: t("i.reco.mood.scary"), genres: ["horror"] },
    explore: { label: t("i.reco.mood.explore"), genres: ["adventure", "sandbox", "rpg"] },
  };
  function moodGenres(moods) { return moods.flatMap((m) => MOODS[m]?.genres || []); }
  const TIME = {
    short: { label: t("i.reco.time.short"), genres: ["arcade", "puzzle", "racing", "fighting", "sports", "shmup", "party", "platform"], avoid: ["rpg", "strategy"] },
    medium: { label: t("i.reco.time.medium"), genres: [], avoid: [] },
    long: { label: t("i.reco.time.long"), genres: ["rpg", "adventure", "strategy", "sandbox", "simulation"], avoid: ["arcade", "party"] },
  };

  const questions = () => [
    { id: "time", title: t("i.reco.q.time"), options: Object.entries(TIME).map(([id, x]) => ({ id, label: t(x.label) })) },
    { id: "people", title: t("i.reco.q.people"), options: [
      { id: "1", label: "🙋 " + t("i.reco.people.solo") }, { id: "2", label: "👫 " + t("i.reco.people.two") }, { id: "3", label: "👨‍👩‍👧 " + t("i.reco.people.more") }] },
    { id: "moods", multi: true, title: t("i.reco.q.moods"), sub: t("i.reco.q.moodsSub"),
      options: Object.entries(MOODS).map(([id, x]) => ({ id, label: t(x.label) })) },
    { id: "genres", multi: true, title: t("i.reco.q.genres"), sub: t("i.reco.q.genresSub"),
      options: GENRES.map(([id, l]) => ({ id, label: t(l) })) },
    { id: "era", title: t("i.reco.q.era"), options: [{ id: "retro", label: "👾 " + t("i.reco.era.retro") },
      { id: "mid", label: "📀 " + t("i.reco.era.mid") }, { id: "modern", label: "✨ " + t("i.reco.era.modern") }, { id: "any", label: "🤷 " + t("i.reco.era.any") }] },
    { id: "where", title: t("i.reco.q.where"), options: [{ id: "any", label: "🤷 " + t("i.reco.where.any") }, { id: "pc", label: "🖥 " + t("i.reco.where.pc") },
      { id: "console", label: "🎮 " + t("i.reco.where.console") }, { id: "installed", label: "✅ " + t("i.reco.where.ready") }] },
    { id: "novelty", title: t("i.reco.q.novelty"), options: [{ id: "new", label: "🆕 " + t("i.reco.novelty.new") },
      { id: "again", label: "🔁 " + t("i.reco.novelty.again") }, { id: "any", label: "🎲 " + t("i.reco.novelty.any") }] },
  ];

  /** Suggerimenti "da giocare adesso", con il motivo di ciascuno. */
  function suggest(games, a, n = 12) {
    const prof = profile(games, { genres: a.genres || [], moods: a.moods || [] });
    let list = pool(games, a.novelty !== "new").filter((g) => g.store !== "online");
    if (a.novelty === "again") list = list.filter((g) => played(g) || g.grp.favorite);
    const people = +a.people || 1;
    if (people >= 2) list = list.filter((g) => g.players >= people);
    if (a.era === "retro") list = list.filter((g) => g.year && g.year < 2000);
    if (a.era === "mid") list = list.filter((g) => g.year >= 2000 && g.year <= 2012);
    if (a.era === "modern") list = list.filter((g) => g.year > 2012);
    if (a.where === "pc") list = list.filter((g) => g.platform === "windows");
    if (a.where === "console") list = list.filter((g) => g.platform !== "windows");
    if (a.where === "installed") list = list.filter((g) => !g.store || g.installed);
    const want = new Set([...(a.genres || []), ...moodGenres(a.moods || []), ...(TIME[a.time]?.genres || [])]);
    const avoid = new Set(TIME[a.time]?.avoid || []);
    const scored = list.map((g) => {
      const gs = canonGenres(g.genres);
      const hit = gs.filter((x) => want.has(x));
      let s = quality(g) * 1.2 + affinity(g, prof) * 1.5 + hit.length * 0.5 - gs.filter((x) => avoid.has(x)).length * 0.6;
      if (g.hltb != null) {  // durata vera, quando nota
        if (a.time === "short") s += g.hltb <= 4 ? 0.6 : g.hltb > 15 ? -0.8 : 0;
        if (a.time === "long") s += g.hltb >= 15 ? 0.5 : g.hltb < 3 ? -0.5 : 0;
      }
      if (a.novelty === "again") s += Math.log1p(minutes(g) / 30) * 0.3 + (g.grp.favorite ? 1 : 0);
      if (want.size && !hit.length) s -= 0.8;
      const q = quality(g);
      if (q < 0.65) s -= (0.65 - q) * 3; // giochi mediocri in fondo
      s += Math.random() * 0.35; // un po' di varieta' a ogni richiesta
      const why = [];
      if (hit.length) why.push(hit.map((x) => t(GENRE_LABEL[x])).slice(0, 2).join(", "));
      if (people >= 2) why.push(t("i.reco.why.upTo", { n: g.players }));
      if (g.hltb != null) why.push(`⏱ ${fmtHours(g.hltb)}`);
      if (g.critics >= 0.85) why.push(t("i.reco.why.critics", { n: Math.round(g.critics * 100) }));
      else if (g.rating >= 0.8 && g.votes >= 10) why.push(`★ ${Math.round(g.rating * 100)}%`);
      if (affinity(g, prof) > 0.9) why.push(t("i.reco.why.similar"));
      if (g.store && !g.installed) why.push(t("i.reco.why.install"));
      return { g, s, why: why.join(" · ") };
    }).sort((x, y) => y.s - x.s);
    // varieta': al massimo 3 giochi per console
    const perPlat = new Map(), out = [];
    for (const x of scored) {
      const k = perPlat.get(x.g.platform) || 0;
      if (k >= 3) continue;
      perPlat.set(x.g.platform, k + 1);
      out.push(x);
      if (out.length >= n) break;
    }
    return out;
  }

  /** Salva le risposte come gusti (generi e atmosfere): usati anche nella vista "Per te". */
  function saveTastes(a) {
    const old = store.get("tastes", { genres: [], moods: [] });
    store.set("tastes", { genres: a.genres?.length ? a.genres : old.genres, moods: a.moods?.length ? a.moods : old.moods });
  }

  let GS_platName = (id) => id;
  return { rows, collectionRows, suggest, get QUESTIONS() { return questions(); }, saveTastes, tastes: () => store.get("tastes", null), canonGenres, GENRE_LABEL,
    setPlatName(fn) { GS_platName = fn; }, quality };
})();
