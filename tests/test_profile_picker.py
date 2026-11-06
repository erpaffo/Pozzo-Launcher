"""Schermata «Chi gioca?»: apertura all'avvio, PIN, 429, 404, tastiera, controller e degrado. Node con DOM e fetch finti, nessuna rete."""
from __future__ import annotations

import _i18n_text  # noqa: F401
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"

HARNESS = r"""
const assert = require("assert");
require(process.argv[2]); // t() e GSI18n come nel browser (catalogo it.json)
class El {
  constructor() { this.map = {}; this.dataset = {}; this.textContent = ""; this.listeners = {}; this.attrs = {}; this.tagName = "DIV"; }
  querySelector(s) { return (this.map[s] = this.map[s] || new El()); }
  querySelectorAll() { return []; }
  addEventListener(t, f) { this.listeners[t] = f; }
  setAttribute(k, v) { this.attrs[k] = v; }
  focus() { document.activeElement = this; }
  remove() { document.body.removed = true; }
  appendChild(e) { document.body.child = e; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 10, height: 10 }; }
  set innerHTML(v) { this._h = v; this.map = {}; }
  get innerHTML() { return this._h || ""; }
}
global.window = global;
global.document = { body: new El(), activeElement: null, createElement: () => new El(), addEventListener() {}, readyState: "complete" };
global.navigator = {};
let calls = [], routes = {};
global.fetch = async (path, init = {}) => {
  calls.push([init.method || "GET", path, init.body]);
  const r = routes[(init.method || "GET") + " " + path];
  if (r === "throw" || !r) { if (r) throw new Error("rete"); return { ok: false, status: 404, headers: { get: () => null }, json: async () => ({}) }; }
  return { ok: r.status < 400, status: r.status, headers: { get: (h) => (r.retry && h === "Retry-After" ? String(r.retry) : null) }, json: async () => r.body };
};
const P = require(process.argv[1]);
const two = { profiles: [{ id: "default", name: "Principale", locked: false }, { id: "luca", name: "Luca", locked: true }], active: "default", ask: true };
const out = {};
(async () => {
  // degrado: route assente o rete caduta -> nessuna schermata, nessun errore
  assert.strictEqual(await P.load(), null);
  assert.strictEqual(await P.autoOpen(), false);
  P.autoDone = false; routes["GET /api/profiles"] = "throw";
  assert.strictEqual(await P.autoOpen(), false);
  // apertura all'avvio: solo ask=true e 2+ profili
  assert.strictEqual(P.shouldAutoOpen({ ...two, ask: false }), false);
  assert.strictEqual(P.shouldAutoOpen({ ...two, profiles: [two.profiles[0]] }), false);
  assert.strictEqual(P.shouldAutoOpen(two), true);
  P.autoDone = false; routes["GET /api/profiles"] = { status: 200, body: { ...two, ask: false } };
  assert.strictEqual(await P.autoOpen(), false);
  assert.strictEqual(await P.autoOpen(), false); // una volta per apertura della pagina
  P.autoDone = false; routes["GET /api/profiles"] = { status: 200, body: two };
  let changed = null;
  assert.strictEqual(await P.autoOpen({ onChange: async (id) => { changed = id; } }), true);
  assert.strictEqual(P.isOpen(), true);
  assert.strictEqual(await P.autoOpen(), false);
  // «entra sempre con questo profilo su questo dispositivo»: niente schermata all'avvio, e la casella manda remember
  assert.strictEqual(P.shouldAutoOpen({ ...two, remembered: true }), false);
  assert.strictEqual(P.shouldAutoOpen({ ...two, remembered: false }), true);
  routes["POST /api/profiles/active"] = { status: 200, body: { active: "default" } };
  calls = []; await P.choose("default", undefined, true);
  assert.deepStrictEqual(JSON.parse(calls[0][2]), { id: "default", remember: true });
  calls = []; await P.choose("default", "1234", false);
  assert.deepStrictEqual(JSON.parse(calls[0][2]), { id: "default", pin: "1234", remember: false });
  calls = []; await P.choose("default");
  assert.deepStrictEqual(JSON.parse(calls[0][2]), { id: "default" }, "senza casella non si tocca la scelta del dispositivo");
  // risposte del server
  routes["POST /api/profiles/active"] = { status: 403, body: { error: "pin" } };
  assert.strictEqual(P.errText(await P.choose("luca", "0000")), "PIN errato");
  routes["POST /api/profiles/active"] = { status: 429, retry: 12, body: {} };
  assert.strictEqual(P.errText(await P.choose("luca", "0000")), "Troppi tentativi: riprova tra 12 s");
  routes["POST /api/profiles/active"] = { status: 404, body: {} };
  assert.strictEqual(P.errText(await P.choose("zz")), "Profilo non trovato");
  routes["POST /api/profiles/active"] = "throw";
  assert.strictEqual(P.errText(await P.choose("zz")), "Server non raggiungibile");
  // PIN da tastiera: profilo protetto -> tastierino, PIN errato poi giusto
  const click = document.body.child.listeners.click;
  const clickOn = (ds) => click({ target: { closest: () => ({ dataset: ds }) } });
  const key = (k, extra = {}) => P.key({ key: k, target: new El(), stopPropagation() {}, preventDefault() {}, ...extra });
  clickOn({ pid: "luca" });
  calls = [];
  "1234".split("").forEach((d) => key(d));
  routes["POST /api/profiles/active"] = { status: 403, body: { error: "pin" } };
  key("Enter"); await new Promise((r) => setTimeout(r, 5));
  assert.deepStrictEqual(JSON.parse(calls[0][2]), { id: "luca", pin: "1234" });
  assert.strictEqual(document.body.child.querySelector("#pp-err").textContent, "PIN errato");
  assert.strictEqual(P.isOpen(), true);
  routes["POST /api/profiles/active"] = { status: 200, body: { active: "luca" } };
  "4321".split("").forEach((d) => key(d));
  key("Enter"); await new Promise((r) => setTimeout(r, 5));
  assert.strictEqual(changed, "luca");
  assert.strictEqual(P.isOpen(), false);
  // Esc chiude; controller: B indietro, direzioni non rompono
  P.autoDone = false;
  assert.strictEqual(await P.autoOpen({}), true);
  P.pad("right"); P.pad("a");
  assert.strictEqual(P.pad("b"), true); // B chiude il selettore (indietro dal primo livello)
  assert.strictEqual(P.isOpen(), false);
  assert.strictEqual(P.pad("a"), false); // chiuso: ignora
  // navigazione geometrica
  const R = (l, t) => ({ left: l, top: t, width: 10, height: 10 });
  const rects = [R(0, 0), R(20, 0), R(0, 20), R(20, 20)];
  assert.strictEqual(P.neighbor(rects, 0, "right"), 1);
  assert.strictEqual(P.neighbor(rects, 0, "down"), 2);
  assert.strictEqual(P.neighbor(rects, 3, "up"), 1);
  assert.strictEqual(P.neighbor(rects, 0, "left"), 0);
  assert.deepStrictEqual([P.PAD_MAP[0], P.PAD_MAP[1], P.PAD_MAP[15]], ["a", "b", "right"]);
  console.log("ok");
})().catch((e) => { console.log(e.stack); process.exit(1); });
"""


def main() -> None:
    js = (STATIC / "profile-picker.js").read_text(encoding="utf-8")
    css = (STATIC / "profile-picker.css").read_text(encoding="utf-8")
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    bp = (STATIC / "bigpicture.html").read_text(encoding="utf-8")
    for page in (index, bp):
        assert "profile-picker.js" in page and "profile-picker.css" in page
    assert 'role", "dialog"' in js and "aria-modal" in js and "Chi gioca?" in js
    assert 'html[data-motion="off"]' in css and 'html[data-motion="reduced"]' in css and "focus-visible" in css
    assert 'type="password"' in js and "non protegge i file del computer" in js
    assert "GSProfilePicker.pad" in (STATIC / "bigpicture.js").read_text(encoding="utf-8")
    assert "Cambia utente" in (STATIC / "js" / "settings.js").read_text(encoding="utf-8")
    assert 'id="pp-remember"' in js, "casella «entra sempre con questo profilo su questo dispositivo»"
    menubar = (STATIC / "menubar.js").read_text(encoding="utf-8")
    assert 'id="mb-profile"' in menubar and "Cambia utente" in menubar, "utente attivo nella barra dei menu e voce in File"
    generale = (STATIC / "settings" / "generale.html").read_text(encoding="utf-8")
    assert 'id="prof-switch"' in generale and 'id="prof-remember"' in generale, "cambio utente nelle Impostazioni"
    node = shutil.which("node")
    if not node:
        print("ok  selettore profili: controlli statici (Node assente)")
        return
    r = subprocess.run([node, "-e", HARNESS, str(STATIC / "profile-picker.js"), str(ROOT / "tests" / "_i18n_stub.js")], capture_output=True, text=True,
                       encoding="utf-8", timeout=20)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stdout + r.stderr
    print("ok  selettore profili: avvio solo con ask e 2+ profili, PIN, 429, 404, tastiera, controller, degrado")


if __name__ == "__main__":
    sys.exit(main())
