"""Scorciatoie da tastiera e da controller: registro senza doppioni, logica Mod (Windows/macOS), mappa del pad, docs.

Esegui: PYTHONUTF8=1 python tests/test_shortcuts.py   (serve node per i controlli sul JS)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"
NODE = shutil.which("node")

NODE_TEST = r"""
const S = require(process.argv[1]);
const assert = require("assert");
const ev = (o) => ({ key: "", code: "", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o });

// Mod: Ctrl su Windows, Cmd su Mac; l'altro modificatore non conta
assert.strictEqual(S.comboFromEvent(ev({ key: "k", code: "KeyK", ctrlKey: true }), false), "Mod+K");
assert.strictEqual(S.comboFromEvent(ev({ key: "k", code: "KeyK", metaKey: true }), true), "Mod+K");
assert.strictEqual(S.comboFromEvent(ev({ key: "k", code: "KeyK", metaKey: true }), false), "");
assert.strictEqual(S.comboFromEvent(ev({ key: "k", code: "KeyK", ctrlKey: true }), true), "");
assert.strictEqual(S.comboFromEvent(ev({ key: "B", code: "KeyB", ctrlKey: true, shiftKey: true }), false), "Mod+Shift+B");
assert.strictEqual(S.comboFromEvent(ev({ key: "∫", code: "KeyB", metaKey: true, altKey: true }), true), "Mod+Alt+B"); // Alt su Mac cambia il carattere
assert.strictEqual(S.comboFromEvent(ev({ key: ",", code: "Comma", ctrlKey: true }), false), "Mod+,");
assert.strictEqual(S.comboFromEvent(ev({ key: "?", shiftKey: true }), false), "?");
assert.strictEqual(S.comboFromEvent(ev({ key: "f" }), false), "F");
assert.strictEqual(S.comboFromEvent(ev({ key: "ArrowLeft", altKey: true }), false), "Alt+ArrowLeft");
assert.strictEqual(S.comboFromEvent(ev({ key: "Shift", shiftKey: true }), false), "");
assert.strictEqual(S.comboFromEvent({ ...ev({ key: "@", ctrlKey: true, altKey: true }), getModifierState: (m) => m === "AltGraph" }, false), "");

// testo mostrato
assert.strictEqual(S.formatCombo("Mod+Shift+B", true), "⌘⇧B");
assert.strictEqual(S.formatCombo("Mod+Shift+B", false), "Ctrl+Shift+B");
assert.strictEqual(S.formatCombo("Mod+,", false), "Ctrl+,");
assert.strictEqual(S.formatCombo("Alt+ArrowLeft", false), "Alt+←");
assert.strictEqual(S.isMacPlatform({ platform: "MacIntel" }), true);
assert.strictEqual(S.isMacPlatform({ userAgentData: { platform: "macOS" }, platform: "" }), true);
assert.strictEqual(S.isMacPlatform({ platform: "Win32" }), false);

// evento -> azione
const find = (combo, scope) => S.findAction(combo, scope, {})?.id;
assert.strictEqual(find("Mod+K", "desktop"), "search");
assert.strictEqual(find("Mod+K", "bp"), undefined);
assert.strictEqual(find("Mod+Shift+B", "bp"), "bigPicture");
assert.strictEqual(find("F11", "desktop"), "bigPicture");
assert.strictEqual(find("Mod+R", "desktop"), undefined); // ricarica del browser: libera
assert.strictEqual(find("Mod+C", "desktop"), undefined); // copia/incolla intatti
assert.strictEqual(find("Mod+V", "desktop"), undefined);
assert.strictEqual(S.findAction("Mod+K", "desktop", { search: ["Mod+J"] })?.id, undefined); // override
assert.strictEqual(S.findAction("Mod+J", "desktop", { search: ["Mod+J"] })?.id, "search");
assert.strictEqual(S.conflictOf("viewFav", "Mod+1", {})?.id, "viewAll");
assert.strictEqual(S.conflictOf("viewFav", "Escape", {})?.id, "back");
assert.strictEqual(S.conflictOf("viewFav", "Mod+9", {}), null);

// campi di testo: passano solo le voci "typing" con Mod
const en = (id) => S.REGISTRY.find((x) => x.id === id);
assert.strictEqual(S.allowedWhileTyping(en("search"), "Mod+K"), true);
assert.strictEqual(S.allowedWhileTyping(en("help"), "?"), false);
assert.strictEqual(S.allowedWhileTyping(en("favorite"), "F"), false);
assert.strictEqual(S.allowedWhileTyping(en("viewAll"), "Mod+1"), false);
assert.strictEqual(S.isTyping({ tagName: "INPUT" }), true);
assert.strictEqual(S.isTyping({ tagName: "DIV", isContentEditable: true }), true);
assert.strictEqual(S.isTyping({ tagName: "BUTTON" }), false);

// media: nessuna PozzoMedia = non gestito (il tasto resta al browser)
assert.strictEqual(S.runMedia("playPause"), false);
global.PozzoMedia = { playPause() { global.pp = (global.pp || 0) + 1; } };
assert.strictEqual(S.runMedia("playPause"), true);
assert.strictEqual(global.pp, 1);
assert.strictEqual(S.runMedia("next"), false);

// pad: indici standard, zona morta, stick, trigger, piu' pad
const pad = (down, axes = [0, 0, 0, 0]) => ({ buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: down.includes(i), value: down.includes(i) ? 1 : 0 })), axes });
let s = S.padStateAll([pad([0, 8])]);
assert.ok(s.a && s.select && !s.b);
s = S.padStateAll([pad([], [0.2, 0.1, 0, 0])]);
assert.ok(!s.left && !s.right && !s.up && !s.down, "zona morta");
s = S.padStateAll([pad([], [-0.9, 0, 0, 0.8])]);
assert.ok(s.left && !s.right && s.scrollDown && !s.scrollUp);
s = S.padStateAll([pad([14, 12])]);
assert.ok(s.left && s.up);
s = S.padStateAll([pad([]), pad([1, 9, 10, 11])]);
assert.ok(s.b && s.start && s.l3 && s.r3, "secondo pad");
assert.deepStrictEqual(S.PAD_CHORDS, { a: "playPause", rb: "next", lb: "prev", x: "muteMic", y: "deafen", b: "exitBigPicture" });
assert.strictEqual(S.isPlayStation("054c-0ce6-Wireless Controller"), true);
assert.strictEqual(S.isPlayStation("Xbox 360 Controller (STANDARD GAMEPAD Vendor: 045e)"), false);
console.log("ok");
"""


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8")


def main():
    assert (STATIC / "shortcuts.js").exists()

    for page, expected in (("index.html", True), ("bigpicture.html", True)):
        html = (STATIC / page).read_text(encoding="utf-8")
        assert "/static/shortcuts.js" in html, f"{page}: shortcuts.js non referenziato"
        assert expected
    bp = (STATIC / "bigpicture.html").read_text(encoding="utf-8")
    assert bp.index("/static/shortcuts.js") < bp.index("/static/pad.js") < bp.index("/static/bigpicture.js"), "ordine degli script"
    assert "data-sc-open" in (STATIC / "settings" / "generale.html").read_text(encoding="utf-8")

    if not NODE:
        print("skip  node non trovato: controlli JS saltati")
        return

    for name in ("shortcuts.js", "pad.js", "bigpicture.js", "menubar.js", "app.js", *(f"js/{f.name}" for f in sorted((STATIC / "js").glob("*.js")))):
        r = run(NODE, "--check", str(STATIC / name))
        assert r.returncode == 0, f"{name}: {r.stderr}"

    dump = run(NODE, "-e", f"console.log(JSON.stringify(require({json.dumps(str(STATIC / 'shortcuts.js'))}).REGISTRY))")
    assert dump.returncode == 0, dump.stderr
    registry = json.loads(dump.stdout)

    # nessuna combinazione ripetuta tra voci che convivono nello stesso contesto
    seen: dict[tuple[str, str], str] = {}
    for entry in registry:
        scopes = ("desktop", "bp") if entry["scope"] == "both" else (entry["scope"],)
        for combo in entry["keys"] + entry.get("fixed", []):
            assert combo == combo.strip() and combo.split("+")[0] in ("Mod", "Alt", "Shift") or "+" not in combo, combo
            for scope in scopes:
                other = seen.get((scope, combo))
                assert other is None, f"combinazione doppia {combo} ({scope}): {other} e {entry['id']}"
                seen[(scope, combo)] = entry["id"]
        assert len(set(entry["keys"])) == len(entry["keys"]), entry["id"]
    ids = [e["id"] for e in registry]
    assert len(ids) == len(set(ids)), "id duplicati nel registro"
    for must in ("search", "settings", "viewAll", "viewFav", "viewShop", "bigPicture", "nextExperience", "nextTheme", "sidebar",
                 "back", "favorite", "hide", "random", "viewWishlist", "viewStats", "help", "playPause", "next", "prev", "muteMic", "deafen"):
        assert must in ids, f"manca l'azione {must}"
    # ogni azione desktop con tasti ha un gestore in bind("desktop", {...}) (le media sono legate da bind per tutti)
    js = (STATIC / "shortcuts.js").read_text(encoding="utf-8")
    block = js[js.index('bind("desktop", {'):js.index('document.addEventListener("keydown", (e) => { dispatch(e, "desktop")')]
    for entry in registry:
        if entry["scope"] in ("desktop", "both") and entry["keys"] and entry["id"] not in ("playPause", "next", "prev", "muteMic", "deafen"):
            assert re.search(rf"^\s{{4}}{entry['id']}:", block, re.M), f"nessun gestore desktop per {entry['id']}"
    # non rubano il copia/incolla/ricarica del browser
    reserved = {"Mod+C", "Mod+V", "Mod+X", "Mod+A", "Mod+Z", "Mod+R", "Mod+W", "Mod+Q", "Mod+L", "Mod+S"}
    assert not reserved & {k for e in registry for k in e["keys"]}, "combinazione riservata al browser"

    r = run(NODE, "-e", NODE_TEST, str(STATIC / "shortcuts.js"))
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stdout + r.stderr

    # la documentazione elenca ogni combinazione (Windows e macOS)
    doc = (ROOT / "docs" / "scorciatoie.md").read_text(encoding="utf-8")
    fmt = run(NODE, "-e", "const S=require(process.argv[1]);console.log(JSON.stringify(S.REGISTRY.flatMap(e=>[...e.keys,...(e.fixed||[])]"
              ".map(k=>[S.formatCombo(k,false),S.formatCombo(k,true)]))))", str(STATIC / "shortcuts.js"))
    for win, mac in json.loads(fmt.stdout):
        assert f"`{win}`" in doc, f"docs/scorciatoie.md: manca {win}"
        assert f"`{mac}`" in doc, f"docs/scorciatoie.md: manca {mac}"
    assert "scorciatoie.md" in (ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    print(f"ok  scorciatoie: {len(registry)} azioni senza doppioni, Mod Windows/macOS, mappa del pad, docs allineati")


if __name__ == "__main__":
    main()
