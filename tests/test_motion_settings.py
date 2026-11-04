"""Animazioni: l'interruttore (motion-settings.js) e i segnaposto delle griglie (skeleton.css).

La logica gira davvero: un DOM finto in Node esegue il file e si controllano i valori restituiti.
Se Node non c'e' (o non c'e' il file) restano i controlli sul contenuto dei file.

Esegui: python tests/test_motion_settings.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"

HARNESS = r"""
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
let systemReduced = false;
const store = new Map();

function makeEl(tag) {
  const el = {
    tagName: tag, className: "", textContent: "", children: [], dataset: {}, attrs: {}, parent: null,
    setAttribute(k, v) { this.attrs[k] = v; },
    append(...nodes) { for (const n of nodes) { n.parent = this; this.children.push(n); } },
    remove() {
      const p = this.parent;
      if (!p) return;
      const i = p.children.indexOf(this);
      if (i >= 0) p.children.splice(i, 1);
    },
    addEventListener() {},
    querySelectorAll(sel) {
      const out = [];
      const walk = (n) => {
        for (const c of n.children) {
          if (sel === "[data-gs-skel]" && c.dataset.gsSkel) out.push(c);
          walk(c);
        }
      };
      walk(this);
      return out;
    },
  };
  return el;
}

global.window = global;
global.document = {
  readyState: "complete",
  documentElement: { dataset: {} },
  getElementById: () => null, // niente pannello impostazioni: si prova solo la logica
  createElement: makeEl,
  addEventListener() {},
};
global.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => { store.set(k, String(v)); },
};
global.matchMedia = () => ({ get matches() { return systemReduced; }, addEventListener() {} });
// /api/profile/settings: il profilo attivo ha exp_animations = profileAnimations (null = nessuna scelta salvata)
let profileAnimations = null;
const posts = [];
global.fetch = (url, opts = {}) => {
  if (opts.method === "POST") { posts.push(JSON.parse(opts.body)); return Promise.resolve({ ok: true }); }
  const value = profileAnimations; // letto al momento della richiesta
  return Promise.resolve({ ok: true, json: async () => ({ exp_animations: value }) });
};
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

eval(code);

const out = {};
out.defaultChoice = window.GSMotionSettings.current();      // "normal"
systemReduced = true;
out.systemReduced = window.GSMotionSettings.current();      // "reduced": segue il sistema
localStorage.setItem("gs.motion", JSON.stringify("off"));
out.explicit = window.GSMotionSettings.current();           // "off": la scelta vince sul sistema
localStorage.setItem("gs.motion", "spazzatura");
out.invalid = window.GSMotionSettings.current();            // valore rotto -> torna al sistema
store.delete("gs.motion");
window.GSMotionSettings.set("off");
out.saved = localStorage.getItem("gs.motion");
out.dataset = document.documentElement.dataset.motion;
window.GSMotionSettings.set("boh");
out.savedAfterInvalid = localStorage.getItem("gs.motion");
out.postsAfterInvalid = posts.length;
out.lastPost = posts[posts.length - 1];
window.GSMotionSettings.set("reduced");
out.lastPostAfterReduced = posts[posts.length - 1];


const host = makeEl("div");
const layer = window.GSSkeleton.show(host, 4);
out.layers = host.children.length;
out.items = layer.children.length;
out.hiddenText = layer.attrs["aria-hidden"];
window.GSSkeleton.show(host, 3);
out.layersAfterShow = host.children.length;
out.itemsAfterShow = host.children[0].children.length;
window.GSSkeleton.hide(host);
out.layersAfterHide = host.children.length;
out.noContainer = window.GSSkeleton.show(null);

// ricarica con una scelta del profilo: il profilo vince e finisce anche in localStorage
profileAnimations = "normal";
localStorage.setItem("gs.motion", JSON.stringify("off"));
const postsBeforeReload = posts.length;
eval(code);
(async () => {
  await tick();
  out.profileWins = localStorage.getItem("gs.motion");
  out.profileDataset = document.documentElement.dataset.motion;
  out.reloadPosts = posts.length - postsBeforeReload; // caricare non deve scrivere sul server
  console.log(JSON.stringify(out));
})();
"""


def run_js() -> dict:
    node = shutil.which("node")
    if not node:
        return {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp) / "harness.js"
        path.write_text(HARNESS, encoding="utf-8")
        env = {**os.environ, "PYTHONUTF8": "1"}
        out = subprocess.run([node, str(path), str(STATIC / "motion-settings.js")],
                             capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> None:
    js = (STATIC / "motion-settings.js").read_text(encoding="utf-8")
    css = (STATIC / "skeleton.css").read_text(encoding="utf-8")
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    big = (STATIC / "bigpicture.html").read_text(encoding="utf-8")
    # inclusi in entrambe le pagine (li mette chi tiene index.html/bigpicture.html)
    assert 'motion-settings.js' in index and 'motion-settings.js' in big, "motion-settings.js non incluso"
    assert 'skeleton.css' in index and 'skeleton.css' in big, "skeleton.css non incluso"
    # stessi valori di motion.js/motion.css, nessuna nuova chiave di storage
    assert '"gs.motion"' in js and 'localStorage.getItem(KEY)' in js
    assert 'window.GSMotion && window.GSMotion.set' in js, "deve passare da GSMotion.set di motion.js"
    assert 'html[data-motion="off"] .gs-skel' in css and 'html[data-motion="reduced"] .gs-skel' in css
    assert "prefers-reduced-motion: reduce" in css
    assert "animation: gs-skel-pulse" in css and "opacity" in css
    assert "background-position" not in css and "width:" not in css.split("@keyframes")[1], \
        "solo transform/opacity nelle animazioni"
    for value in ("normal", "reduced", "off"):
        assert value in js, f"manca il valore {value}"

    result = run_js()
    if result:
        assert result["defaultChoice"] == "normal", result
        assert result["systemReduced"] == "reduced", result
        assert result["explicit"] == "off", result
        assert result["invalid"] == "reduced", result  # valore illeggibile: decide il sistema
        assert result["saved"] == '"off"' and result["dataset"] == "off", result
        assert result["savedAfterInvalid"] == '"off"', "un valore sconosciuto non deve essere salvato"
        assert result["layers"] == 1 and result["items"] == 4, result
        assert result["hiddenText"] == "true", "i segnaposto non vanno letti dallo screen reader"
        assert result["layersAfterShow"] == 1 and result["itemsAfterShow"] == 3, "show non duplica il livello"
        assert result["layersAfterHide"] == 0, result
        assert result["noContainer"] is None, result
        assert result["postsAfterInvalid"] == 1, "un valore sconosciuto non va nemmeno al server"
        assert result["lastPost"] == {"exp_animations": "off"}, result
        assert result["lastPostAfterReduced"] == {"exp_animations": "reduced"}, result
        assert result["profileWins"] == '"normal"' and result["profileDataset"] == "normal", \
            "al caricamento il valore del profilo vince su localStorage"
        assert result["reloadPosts"] == 0, "caricare la pagina non scrive sul server"
        route = (ROOT / "pozzo" / "app" / "routes" / "profile_settings.py").read_text(encoding="utf-8")
        assert '"exp_animations")' in route, "exp_animations deve essere tra le chiavi consentite"
        print("ok  animazioni: scelta salvata e rispettata, sistema come predefinito, segnaposto delle griglie")
    else:
        print("ok  animazioni: file e collegamenti a posto (Node assente: logica non eseguita)")


if __name__ == "__main__":
    sys.exit(main())
