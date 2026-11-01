"""Smoke test Playwright del frontend locale. Esegui: python tests/e2e/test_app.py"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "library.json"
sys.path.insert(0, str(ROOT))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _prepare_app(work: Path) -> tuple[Path, str]:
    from pozzo.library.build import SCHEMA

    cache = work / "cache"
    cache.mkdir(parents=True)
    rom = work / "fixture.gba"
    rom.write_bytes(b"Pozzo local e2e fixture")
    game = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db = sqlite3.connect(cache / "library.db")
    try:
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO games(key, platform, title, sort_title, year, genres, files, media, found, grp, "
            "is_primary, origin) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', 1, ?, 1, '{}')",
            (
                game["key"],
                game["platform"],
                game["title"],
                game["title"].lower(),
                game["year"],
                json.dumps([game["genre"]]),
                json.dumps([str(rom)]),
                game["key"],
            ),
        )
        db.execute("INSERT INTO meta(k, v) VALUES('built_at', '1')")
        db.commit()
    finally:
        db.close()

    config = work / "config.toml"
    config.write_text(
        '[paths]\nroms = "."\ncache = "cache"\noutput = "output"\n\n[scrape]\nsources = []\nmedia = []\n',
        encoding="utf-8",
    )
    return config, game["title"]


def _wait_for_app(url: str, process: subprocess.Popen, log_path: Path) -> bool:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server terminato all'avvio:\n{log_path.read_text(encoding='utf-8', errors='replace')}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"server non pronto entro 30 secondi:\n{log_path.read_text(encoding='utf-8', errors='replace')}")


def _run_browser_test() -> str | None:
    if sync_playwright is None:
        return "Playwright non installato"

    work = Path(__file__).resolve().parent / f".runtime-{uuid.uuid4().hex}"
    work.mkdir()
    process = None
    try:
        config, title = _prepare_app(work)
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        log_path = work / "server.log"
        child_code = (
            "import sys, uvicorn; from pathlib import Path; from pozzo import config; "
            "from pozzo.app.server import create_app; "
            "uvicorn.run(create_app(config.load(Path(sys.argv[1]))), host='127.0.0.1', "
            "port=int(sys.argv[2]), log_level='warning')"
        )
        env = os.environ.copy()
        for name in ("SS_USER", "SS_PASSWORD", "SS_DEVID", "SS_DEVPASSWORD", "IGDB_CLIENT_ID",
                     "IGDB_CLIENT_SECRET", "TGDB_API_KEY"):
            env.pop(name, None)
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", child_code, str(config), str(port)],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if not _wait_for_app(base_url, process, log_path):
            raise RuntimeError("la pagina iniziale non ha risposto 200")

        with sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                return "Chromium Playwright non installato"
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                context.route(
                    "**/*",
                    lambda route: route.continue_()
                    if route.request.url.startswith(base_url + "/")
                    else route.abort(),
                )
                page = context.new_page()
                response = page.goto(base_url + "/", wait_until="domcontentloaded")
                assert response and response.status == 200, "avvio dell'app"
                search = page.locator("#search")
                search.wait_for(state="visible")
                search.fill(title)
                tile = page.locator(".tile[data-id]").filter(has_text=title)
                tile.wait_for(state="visible")
                tile.first.click()
                detail_title = page.locator("#detail-title")
                detail_title.wait_for(state="visible")
                assert detail_title.inner_text().strip() == title, "apertura della scheda gioco"

                bigpicture = page.goto(base_url + "/bigpicture", wait_until="domcontentloaded")
                assert bigpicture and bigpicture.status == 200, "apertura di bigpicture.html"
                assert page.locator("body").is_visible()
                context.close()
            finally:
                browser.close()
        print("ok  avvio su porta libera, ricerca, scheda gioco e Big Picture (Playwright headless)")
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


def test_app_browser() -> None:
    reason = _run_browser_test()
    if reason:
        try:
            import pytest
        except ImportError:
            print(f"SKIP {reason}")
            return
        pytest.skip(reason)


if __name__ == "__main__":
    try:
        test_app_browser()
    except BaseException as error:
        if type(error).__name__ == "Skipped":
            print(f"SKIP {error}")
        else:
            raise
