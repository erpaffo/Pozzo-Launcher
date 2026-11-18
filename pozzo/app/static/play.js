const PLAY = JSON.parse(document.getElementById("play-data").textContent);
window.PLAY = PLAY;

(async () => {
  const P = window.PLAY, T = P.t, msg = document.getElementById("msg");
  const say = (s) => { msg.textContent = s; };
  const fmt = (s, o) => s.replace(/\{(\w+)\}/g, (_, k) => o[k]);
  const base = `/api/play/${P.gid}`;
  document.getElementById("back").onclick = () => (history.length > 1 ? history.back() : window.close());
  const fail = (e) => say(fmt(T.error, { msg: e && e.message ? e.message : String(e) }));
  const post = (kind, data) => fetch(`${base}/save?kind=${kind}`, { method: "POST", body: data, keepalive: data.length < 60000 }).catch(() => {});
  try {
    if (P.needBios && !P.bios) return say(T.noBios);
    say(T.preparing);
    let st = await (await fetch(`${base}/prepare`, { method: "POST" })).json();
    while (st.status !== "ready") {
      if (st.status === "error") throw new Error(st.error);
      say(fmt(T.downloading, { pct: Math.round((st.pct || 0) * 100) }));
      await new Promise((r) => setTimeout(r, 700));
      st = await (await fetch(`${base}/status`)).json();
    }
    const load = (src) => new Promise((ok, ko) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => ko(new Error(src)); document.head.appendChild(s); });
    const rom = `${base}/rom/${encodeURIComponent(P.name)}`;
    say("");
    if (P.kind === "ruffle") {
      await load("/play-assets/ruffle/ruffle.js");
      const player = window.RufflePlayer.newest().createPlayer();
      document.getElementById("game").appendChild(player);
      return player.load({ url: rom });
    }
    // EmulatorJS: stato salvato dal server (se c'e'), ram di salvataggio ripristinata all'avvio e inviata ogni 20 secondi
    const state = await fetch(`${base}/save?kind=state`);
    if (state.ok) window.EJS_loadStateURL = URL.createObjectURL(await state.blob());
    Object.assign(window, {
      EJS_player: "#game", EJS_core: P.system, EJS_gameUrl: rom, EJS_gameName: P.title, EJS_pathtodata: "/play-assets/ejs/",
      EJS_startOnLoaded: true, EJS_language: "en-US", EJS_disableAutoLang: false, EJS_color: "#4aa3ff",
      EJS_biosUrl: P.bios || undefined,
      EJS_onSaveState: (e) => { post("state", e.state); },
      EJS_onSaveSave: (e) => { post("sram", e.save); return true; },
      EJS_onGameStart: async () => {
        const gm = window.EJS_emulator.gameManager;
        try {
          const r = await fetch(`${base}/save?kind=sram`);
          if (r.ok) {
            const path = gm.getSaveFilePath(), parts = path.split("/");
            let dir = "";
            for (let i = 0; i < parts.length - 1; i++) if (parts[i]) { dir += "/" + parts[i]; if (!gm.FS.analyzePath(dir).exists) gm.FS.mkdir(dir); }
            gm.FS.writeFile(path, new Uint8Array(await r.arrayBuffer()));
            gm.loadSaveFiles();
          }
        } catch (e) { console.warn(e); }
        let last = "";
        const push = () => {
          try {
            const d = gm.getSaveFile();
            const sig = d ? d.length + ":" + d.reduce((a, b, i) => (a + b * (i % 251 + 1)) | 0, 0) : "";
            if (d && sig !== last) { last = sig; post("sram", d); }
          } catch (e) { /* core senza file di salvataggio */ }
        };
        setInterval(push, 20000);
        addEventListener("pagehide", push);
      },
    });
    await load("/play-assets/ejs/loader.js");
  } catch (e) { fail(e); }
})();
