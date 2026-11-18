
"use strict";
const T = {
  it: { intro: "Inserisci il codice dell'invito per sfogliare la libreria.", code: "Codice", name: "Il tuo nome", go: "Entra",
        q: "Cerca", out: "Esci", dl: "Scarica", play: "Gioca qui", zip: "cartella: scaricata come zip, senza ripresa", bad: "Codice non valido" },
  en: { intro: "Enter the invite code to browse the library.", code: "Code", name: "Your name", go: "Join",
        q: "Search", out: "Leave", dl: "Download", play: "Play here", zip: "folder: downloaded as a zip, not resumable", bad: "Invalid code" },
};
const L = T[(navigator.language || "en").slice(0, 2)] || T.en;
const $ = (id) => document.getElementById(id);
$("intro").textContent = L.intro; $("code").placeholder = L.code; $("name").placeholder = L.name;
$("go").textContent = L.go; $("q").placeholder = L.q; $("out").textContent = L.out;
const hash = new URLSearchParams(location.hash.slice(1));
if (hash.get("code")) $("code").value = hash.get("code");
history.replaceState(null, "", location.pathname);  // il codice non resta nell'indirizzo
let games = [];
function mb(n) { return n ? (n / 1048576 >= 1024 ? (n / 1073741824).toFixed(1) + " GB" : Math.round(n / 1048576) + " MB") : ""; }
function draw() {
  const q = $("q").value.trim().toLowerCase(), g = $("grid");
  g.textContent = "";
  for (const x of games.filter((x) => !q || x.title.toLowerCase().includes(q))) {
    const c = document.createElement("div"); c.className = "g";
    if (x.cover) { const i = document.createElement("img"); i.loading = "lazy"; i.alt = ""; i.src = x.cover; c.append(i); }
    else { const d = document.createElement("div"); d.className = "nocover"; c.append(d); }
    const b = document.createElement("div"); b.className = "b";
    const t = document.createElement("b"); t.textContent = x.title;
    const s = document.createElement("small"); s.textContent = [x.platform, mb(x.size)].filter(Boolean).join(" · ");
    const a = document.createElement("div"); a.className = "acts";
    const dl = document.createElement("a"); dl.className = "btn"; dl.textContent = L.dl; dl.href = "/api/lib-share/download/" + x.id;
    if (x.kind === "zip") dl.title = L.zip;
    a.append(dl);
    if (x.play) { const p = document.createElement("a"); p.className = "btn"; p.textContent = L.play; p.href = "/play/" + x.id; p.target = "_blank"; a.append(p); }
    b.append(t, s, a); c.append(b); g.append(c);
  }
}
async function load() {
  const r = await fetch("/api/lib-share/list");
  if (!r.ok) { $("login").hidden = false; $("lib").hidden = true; return; }
  games = (await r.json()).games; $("login").hidden = true; $("lib").hidden = false; draw();
}
$("q").oninput = draw;
$("go").onclick = async () => {
  $("err").textContent = "";
  const r = await fetch("/l/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: $("code").value, name: $("name").value }) });
  if (!r.ok) { $("err").textContent = ((await r.json().catch(() => ({}))).detail) || L.bad; return; }
  load();
};
$("out").onclick = async () => { await fetch("/l/api/logout", { method: "POST" }); location.reload(); };
load();
