"""Controlli della splash desktop/Big Picture senza rete."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
global.window = global;
global.location = { pathname: "/", href: "http://localhost/" };
global.document = { documentElement: { dataset: {} }, body: null };
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"), { filename: "splash.js" });
const running = GSSplash.summarize({
  ready: false, progress: 0.4,
  steps: [
    { id: "server", label: "Server", state: "done" },
    { id: "library", label: "Libreria", state: "running" },
    { id: "stores", label: "Store", state: "pending" },
  ],
});
const failed = GSSplash.summarize({
  ready: true, progress: 0.8,
  steps: [{ id: "library", label: "Libreria", state: "error" }],
});
console.log(JSON.stringify({ running, failed }));
"""


def run_js() -> dict:
    node = shutil.which("node")
    if not node:
        return {}
    result = subprocess.run(
        [node, "-e", HARNESS, str(STATIC / "splash.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> None:
    script = (STATIC / "splash.js").read_text(encoding="utf-8")
    css = (STATIC / "splash.css").read_text(encoding="utf-8")
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    big_picture = (STATIC / "bigpicture.html").read_text(encoding="utf-8")

    assert "POLL_MS = 300" in script and "REQUEST_TIMEOUT_MS = 1200" in script
    assert 'getJson("/api/boot")' in script and 'getJson("/api/status")' in script
    assert "status.has_library && !status.building" in script
    assert "boot.ready && !state.error" in script and "Continua" in script
    assert "/static/splash.css" in script
    assert "splash.js" in index and "splash.js" in big_picture
    assert 'role="progressbar"' in script and 'aria-live="polite"' in script
    assert 'html[data-motion="off"] .bs-fill' in css
    assert 'html[data-motion="reduced"] .bs-fill' in css
    assert "prefers-reduced-motion" in css

    result = run_js()
    if result:
        assert result["running"] == {
            "progress": 0.4,
            "error": "",
            "label": "In corso: Libreria",
        }, result
        assert result["failed"]["progress"] == 1, result
        assert result["failed"]["error"] == "Errore: Libreria", result
        print("ok  splash: fasi, avanzamento, errori, fallback legacy e movimento ridotto")
    else:
        print("ok  splash: controlli statici (Node assente: riepilogo non eseguito)")


if __name__ == "__main__":
    sys.exit(main())
