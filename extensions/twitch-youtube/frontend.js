// Dirette Twitch e video YouTube: sezione «Dirette e video» nel dettaglio gioco; chiavi in Impostazioni › Streaming.

const P = "/plugin-api/twitch-youtube";
const TW_SEARCH = (q) => `https://www.twitch.tv/search?term=${encodeURIComponent(q)}`;
const YT_SEARCH = (q) => `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;

export default function (gs) {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const open = (url) => gs.api("/api/open", { body: { url } }).catch((err) => gs.toast(err.message, true));
  const link = (text, url) => { const a = el("a", "", text); a.href = "#"; a.onclick = (e) => { e.preventDefault(); open(url); }; return a; };

  function liveCard(s) {
    const c = el("a", "tv-card"); c.href = "#";
    c.onclick = (e) => { e.preventDefault(); open(s.url); };
    const media = el("div", "tv-media");
    if (s.thumbnail) { const img = el("img", "tv-thumb"); img.loading = "lazy"; img.alt = ""; img.referrerPolicy = "no-referrer"; img.src = s.thumbnail; img.onerror = () => img.remove(); media.append(img); }
    media.append(el("span", "tv-live", "● LIVE"));
    c.append(media, el("b", "", s.user), el("span", "tv-title", s.title), el("small", "muted", `${s.viewers.toLocaleString("it")} spettatori`));
    return c;
  }

  function videoCard(v) {
    const c = el("div", "tv-card");
    const media = el("div", "tv-media");
    const img = el("img", "tv-thumb"); img.loading = "lazy"; img.alt = ""; img.referrerPolicy = "no-referrer"; img.src = v.thumb;
    const play = el("button", "tv-play", "▶"); play.type = "button"; play.setAttribute("aria-label", `Guarda ${v.title}`);
    play.onclick = () => {  // il video si carica solo al clic
      const f = el("iframe"); f.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(v.videoId)}?autoplay=1`;
      f.allow = "autoplay; encrypted-media; picture-in-picture"; f.allowFullscreen = true; f.title = v.title;
      media.replaceChildren(f);
    };
    media.append(img, play);
    c.append(media, el("b", "tv-title", v.title), el("small", "muted", v.channel),
      link("Apri su YouTube", `https://www.youtube.com/watch?v=${encodeURIComponent(v.videoId)}`));
    return c;
  }

  gs.addDetailSection({
    id: "dirette-video",
    title: "📺 Dirette e video",
    async render(game) {
      const box = el("div", "tv-box");
      const q = game.title || "";
      let st;
      try { st = await gs.api(`${P}/stato`); } catch (e) { box.textContent = e.message; return box; }
      const liveNote = el("p", "muted small"), liveGrid = el("div", "tv-grid");
      const vidNote = el("p", "muted small"), vidGrid = el("div", "tv-grid");
      box.append(el("h4", "", "Dirette Twitch"), liveNote, liveGrid, el("h4", "", "Video YouTube"), vidNote, vidGrid);

      const cercaTwitch = () => liveNote.append(" ", link("Cerca su Twitch", TW_SEARCH(q)));
      if (!st.twitch) {
        liveNote.textContent = "Per le dirette inserisci Client ID e Client Secret in Impostazioni › Streaming.";
        cercaTwitch();
      } else {
        liveNote.textContent = "Caricamento dirette…";
        gs.api(`${P}/live/${encodeURIComponent(q)}`).then(({ streams }) => {
          liveNote.textContent = streams.length ? "" : "Nessuna diretta in questo momento.";
          liveGrid.replaceChildren(...streams.map(liveCard));
          cercaTwitch();
        }).catch((e) => { liveNote.textContent = e.message; cercaTwitch(); });
      }

      const cercaYt = () => vidNote.append(" ", link("Cerca su YouTube", YT_SEARCH(`${q} trailer`)));
      if (!st.youtube) {
        vidNote.textContent = "Per i video inserisci la chiave YouTube Data API in Impostazioni › Streaming.";
        cercaYt();
      } else {
        vidNote.textContent = "Caricamento video…";
        gs.api(`${P}/videos/${encodeURIComponent(q)}`).then(({ videos }) => {
          vidNote.textContent = videos.length ? "" : "Nessun video trovato.";
          vidGrid.replaceChildren(...videos.map(videoCard));
          cercaYt();
        }).catch((e) => { vidNote.textContent = e.message; cercaYt(); });
      }
      return box;
    },
  });

  gs.addSettingsTab({
    id: "twitch-youtube", label: "Dirette e video", category: "streaming",
    async render(root) {
      root.innerHTML = "";
      let st;
      try { st = await gs.api(`${P}/stato`); } catch (e) { root.textContent = e.message; return; }
      root.innerHTML = `<h3>Dirette Twitch e video YouTube</h3>
        <p class="muted">Usa le tue chiavi gratuite. Twitch: crea un'app su <a href="#" data-url="https://dev.twitch.tv/console/apps">dev.twitch.tv</a>
          e copia Client ID e Client Secret. YouTube (facoltativa): una chiave «YouTube Data API v3» da Google Cloud.
          Lascia vuoto un campo per non cambiarlo.</p>
        <p>${st.twitch ? "✔ Twitch configurato." : "Twitch non configurato."} ${st.youtube ? "✔ Chiave YouTube impostata." : "Chiave YouTube non impostata."}</p>
        <p><input id="tv-cid" placeholder="Twitch Client ID" autocomplete="off" style="width:320px"></p>
        <p><input id="tv-sec" type="password" placeholder="Twitch Client Secret" autocomplete="off" style="width:320px"></p>
        <p><input id="tv-yt" type="password" placeholder="Chiave YouTube Data API (facoltativa)" autocomplete="off" style="width:320px"></p>
        <p><button class="btn primary" id="tv-save">Salva</button> <span class="muted" id="tv-msg"></span></p>`;
      root.querySelector("a[data-url]").onclick = (e) => { e.preventDefault(); open(e.target.dataset.url); };
      root.querySelector("#tv-save").onclick = async () => {
        const body = {
          twitch_client_id: root.querySelector("#tv-cid").value,
          twitch_client_secret: root.querySelector("#tv-sec").value,
          youtube_key: root.querySelector("#tv-yt").value,
        };
        try { await gs.api(`${P}/impostazioni`, { body }); } catch (e) { return gs.toast(e.message, true); }
        gs.toast("Salvato");
        root.querySelector("#tv-msg").textContent = "Salvato. Riapri la scheda del gioco per vedere le modifiche.";
      };
    },
  });
}
