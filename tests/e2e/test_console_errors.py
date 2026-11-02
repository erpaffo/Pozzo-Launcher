"""Nessun errore JavaScript nelle pagine principali (desktop, Impostazioni › Emulatori, Big Picture) e risposta 200 delle
API nuove (avvio, profili, BIOS, installazione consigliata, gusto, serie, consigli, classifica ROM).
Esegui: python tests/e2e/test_console_errors.py   (serve Playwright con Chromium: altrimenti il test salta)"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import ROOT, _free_port, _prepare_app, _wait_for_app, sync_playwright  # noqa: E402

API = ["/api/boot", "/api/profiles", "/api/profile/settings", "/api/emulators/bios?console=gba",
       "/api/emulators/recommend?console=ps2", "/api/taste", "/api/recommend?limit=5", "/api/top/roms?console=all",
       "/api/cache/sources", "/api/extensions"]


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def run() -> str | None:
    if sync_playwright is None:
        return "Playwright non installato"
    work = Path(__file__).resolve().parent / f".runtime-{uuid.uuid4().hex}"
    work.mkdir()
    process = None
    try:
        config, title = _prepare_app(work)
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        log_path = work / "server.log"
        child = ("import sys, uvicorn; from pathlib import Path; from pozzo import config; "
                 "from pozzo.app.server import create_app; "
                 "uvicorn.run(create_app(config.load(Path(sys.argv[1]))), host='127.0.0.1', "
                 "port=int(sys.argv[2]), log_level='warning')")
        env = {k: v for k, v in os.environ.items() if k not in (
            "SS_USER", "SS_PASSWORD", "SS_DEVID", "SS_DEVPASSWORD", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET", "TGDB_API_KEY")}
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-c", child, str(config), str(port)], cwd=ROOT, env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
        _wait_for_app(base, process, log_path)

        bad = {url: code for url in API if (code := _get(base + url)) != 200}
        assert not bad, f"API con risposta diversa da 200: {bad}"
        gid = json.loads(urllib.request.urlopen(base + "/api/library?part=owned").read())["games"]["rows"][0][0]
        assert _get(f"{base}/api/franchise/{gid}") == 200, "/api/franchise/{id}"

        with sync_playwright() as pw:
            if not Path(pw.chromium.executable_path).is_file():
                return "Chromium Playwright non installato"
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context()
                ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base + "/") else r.abort())
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                page.on("console", lambda m: errors.append(f"console.error: {m.text}")
                        if m.type == "error" and "Failed to load resource" not in m.text else None)
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator("#search").wait_for(state="visible")
                page.locator("#settings-btn").click()
                page.locator("#settings-nav").wait_for(state="visible")
                page.locator("#settings-nav >> text=Emulatori e avvio").click()
                page.locator("#emu-table").wait_for(state="attached")
                page.wait_for_timeout(1200)  # il componente BIOS/installazione si aggancia alle righe
                page.goto(base + "/bigpicture", wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                assert not errors, "errori JavaScript:\n" + "\n".join(errors)
                ctx.close()
            finally:
                browser.close()
        print("ok  nessun errore JavaScript in desktop, Emulatori e Big Picture; API nuove con risposta 200")
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


def test_console_errors() -> None:
    skipped = run()
    if skipped:
        import pytest
        pytest.skip(skipped)


if __name__ == "__main__":
    skipped = run()
    print(f"-- saltato: {skipped}" if skipped else "TUTTI I TEST OK")
