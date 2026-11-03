"""E2E Playwright di Aspetto (zoom, densita', editor tema) e del salvaschermo di Big Picture.
Esegui: python tests/e2e/test_ui_prefs.py"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_app import ROOT, _free_port, _prepare_app, _wait_for_app, sync_playwright  # noqa: E402

GOOD = {"bg": "#0f1115", "bg-2": "#151821", "bg-3": "#1c2030", "panel": "#171a23", "line": "#262b3a",
        "text": "#e7e9ee", "muted": "#8b92a5", "accent": "#5b8cff", "accent-2": "#8b72ff", "fav": "#ffcf4a"}


def _run() -> str | None:
    if sync_playwright is None:
        return "Playwright non installato"
    work = HERE / f".runtime-{uuid.uuid4().hex}"
    work.mkdir()
    process = None
    try:
        config, _title = _prepare_app(work)
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        log_path = work / "server.log"
        code = ("import sys, uvicorn; from pathlib import Path; from pozzo import config; from pozzo.app.server import create_app; "
                "uvicorn.run(create_app(config.load(Path(sys.argv[1]))), host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')")
        env = os.environ.copy()
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-c", code, str(config), str(port)], cwd=ROOT, env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
        _wait_for_app(base + "/", process, log_path)
        with sync_playwright() as pw:
            if not Path(pw.chromium.executable_path).is_file():
                return "Chromium Playwright non installato"
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base + "/") else r.abort())
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))

                # 1) predefiniti: nessuno zoom, layout invariato
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#search").wait_for(state="visible")
                assert page.evaluate("document.documentElement.dataset.uiZoom") is None
                assert page.evaluate("getComputedStyle(document.body).zoom") == "1"

                # 2) Aspetto: scelta salvata nel dispositivo e riapplicata al riavvio
                page.goto(base + "/#settings/aspetto", wait_until="domcontentloaded")
                page.locator("#ui-zoom").wait_for(state="attached")
                page.wait_for_function("document.querySelector('#ui-density option')")
                zoom = page.locator("#ui-zoom")
                assert [zoom.get_attribute(x) for x in ("type", "min", "max", "step")] == ["range", "90", "125", "5"]
                zoom.focus()
                zoom.evaluate("(el) => { el.value = 125; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                assert page.locator("#ui-zoom-out").inner_text() == "125%"
                page.select_option("#ui-density", "compact")
                assert json.loads(page.evaluate("localStorage.getItem('gs.ui')"))["zoom"] == 125
                assert page.evaluate("document.documentElement.dataset.uiZoom") == "125"
                assert page.evaluate("getComputedStyle(document.body).zoom") == "1.25"
                page.reload(wait_until="domcontentloaded")
                page.locator("#search").wait_for(state="attached")
                assert page.evaluate("document.documentElement.dataset.uiZoom") == "125"
                assert page.evaluate("document.documentElement.dataset.uiDensity") == "compact"
                assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--space-scale').trim()") == ".7"
                assert page.evaluate("getComputedStyle(document.querySelector('.nav-item')).paddingTop") == "4.2px"
                # il corpo della pagina riempie ancora la finestra (nessuna barra o vuoto)
                assert abs(page.evaluate("document.body.getBoundingClientRect().width") - 1280) < 2

                # 3) editor tema: anteprima non salvata, import rifiutato, salvataggio e persistenza
                page.goto(base + "/#settings/aspetto", wait_until="domcontentloaded")
                page.locator("#te-tokens [data-token='bg']").wait_for(state="attached")
                assert page.evaluate("localStorage.getItem('gs.userTheme')") is None
                page.evaluate("""() => { const r = document.querySelector("[data-token='accent'] [data-hsl='0']");
                  r.value = 10; r.dispatchEvent(new Event('input', { bubbles: true })); }""")
                assert page.evaluate("!!document.getElementById('gs-user-theme-preview')")
                assert page.evaluate("localStorage.getItem('gs.userTheme')") is None, "l'anteprima non si salva da sola"
                page.click("#te-revert")
                assert page.evaluate("!document.getElementById('gs-user-theme-preview')")
                bad = {"format": "pozzo-theme", "version": 1, "name": "X", "tokens": {**GOOD, "bg": "url(http://x/y)"}}
                page.set_input_files("#te-import", {"name": "t.json", "mimeType": "application/json", "buffer": json.dumps(bad).encode()})
                page.wait_for_function("document.querySelector('#te-msg').textContent.includes('Colore non valido')")
                ok = {"format": "pozzo-theme", "version": 1, "name": "Importato", "tokens": GOOD}
                page.set_input_files("#te-import", {"name": "t.json", "mimeType": "application/json", "buffer": json.dumps(ok).encode()})
                page.wait_for_function("document.querySelector('#te-msg').textContent.includes('importato')")
                page.click("#te-save")
                page.wait_for_function("localStorage.getItem('gs.userTheme') !== null")
                assert json.loads(page.evaluate("localStorage.getItem('gs.userTheme')"))["name"] == "Importato"
                page.reload(wait_until="domcontentloaded")
                page.locator("#search").wait_for(state="attached")
                assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#5b8cff"
                assert page.evaluate("!!document.getElementById('gs-user-theme')")

                # 3b) colore della copertina: attivo di predefinito, spento dall'opzione, mai --accent del tema
                page.evaluate("localStorage.removeItem('gs.ui')")
                page.route("**/cover-accent", lambda r: r.fulfill(status=200, content_type="application/json", body='{"accent":"#ff0000"}'))
                page.goto(base + "/#settings/aspetto", wait_until="domcontentloaded")
                page.locator("#ui-cover-accent").wait_for(state="attached")
                page.wait_for_function("document.querySelector('#ui-density option')")
                assert page.locator("#ui-cover-accent").is_checked(), "predefinito: attivo"
                theme_accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
                page.wait_for_function("typeof S !== 'undefined' && S.byId && S.byId.size > 0")
                page.evaluate("openDetail([...S.byId.keys()][0])")
                page.wait_for_function("document.querySelector('#detail').dataset.gameAccent === '1'")
                assert page.evaluate("document.querySelector('#detail').style.getPropertyValue('--game-accent')") == "#ff0000"
                page.locator("#ui-cover-accent").uncheck()
                assert json.loads(page.evaluate("localStorage.getItem('gs.ui')"))["coverAccent"] is False
                page.wait_for_function("!document.querySelector('#detail').dataset.gameAccent")
                page.locator("#ui-cover-accent").check()
                page.wait_for_function("document.querySelector('#detail').dataset.gameAccent === '1'")  # subito, dalla cache
                assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == theme_accent
                page.locator("#ui-cover-accent").uncheck()
                page.reload(wait_until="domcontentloaded")
                page.locator("#ui-cover-accent").wait_for(state="attached")
                page.wait_for_function("document.querySelector('#ui-density option')")
                assert not page.locator("#ui-cover-accent").is_checked(), "la scelta resta dopo il riavvio"
                page.wait_for_function("typeof S !== 'undefined' && S.byId && S.byId.size > 0")
                page.evaluate("openDetail([...S.byId.keys()][0])")
                page.wait_for_function("document.querySelector('#detail').classList.contains('open')")
                assert page.evaluate("!document.querySelector('#detail').dataset.gameAccent")

                # 4) Big Picture: salvaschermo con orologio finto, chiuso dal primo input senza inoltrarlo
                page.evaluate("localStorage.setItem('gs.ui', JSON.stringify({zoom: 100, density: 'comfortable', idle: 1}))")
                page.clock.install()
                page.goto(base + "/bigpicture", wait_until="domcontentloaded")
                page.wait_for_function("typeof BP !== 'undefined' && BP.lib && !document.querySelector('#bp-loading') || (BP.lib && document.querySelector('#bp-loading').hidden)")
                page.evaluate("BP.lib.games.forEach((g) => { g.cover = 1; })")
                before = page.evaluate("cur().title || ''")
                glow = "document.querySelector('#bp-bg').style.getPropertyValue('--game-accent')"
                bp_pref = ("(on) => { const u = JSON.parse(localStorage.getItem('gs.ui')); u.coverAccent = on; "
                           "localStorage.setItem('gs.ui', JSON.stringify(u)); window.dispatchEvent(new Event('gs-ui-change')); }")
                page.evaluate("setBackground(BP.lib.games[0].id)")
                page.wait_for_function(f"{glow} === '#ff0000'")
                page.evaluate(bp_pref, False)
                page.wait_for_function(f"{glow} === ''")
                page.evaluate(bp_pref, True)
                page.wait_for_function(f"{glow} === '#ff0000'")
                assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == theme_accent
                assert page.locator("#bp-attract").is_hidden()
                page.clock.fast_forward("00:59")
                assert page.locator("#bp-attract").is_hidden(), "non parte prima della soglia"
                page.clock.fast_forward("00:02")
                assert page.locator("#bp-attract").is_visible()
                page.keyboard.press("/")  # aprirebbe la ricerca se venisse inoltrato
                assert page.locator("#bp-attract").is_hidden()
                assert page.evaluate("cur().title || ''") == before
                assert page.evaluate("BP.stack.length") == 1
                # con un gioco in esecuzione non parte
                page.evaluate("BP.running = { title: 'x' }")
                page.clock.fast_forward("01:05")
                assert page.locator("#bp-attract").is_hidden()
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
        print("ok  Aspetto (zoom, densita', editor tema) e salvaschermo Big Picture (Playwright headless)")
        return None
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        shutil.rmtree(work, ignore_errors=True)


def test_ui_prefs_browser() -> None:
    reason = _run()
    if reason:
        try:
            import pytest
        except ImportError:
            print(f"SKIP {reason}")
            return
        pytest.skip(reason)


if __name__ == "__main__":
    test_ui_prefs_browser()
