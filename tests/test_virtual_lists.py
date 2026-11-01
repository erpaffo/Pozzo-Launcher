"""Viste virtuali: le liste delle viste a pagina disegnano solo le righe visibili (vlist in grid.js).

Controlli statici (ogni lista usa vlist con il suo contenitore), sintassi con node se c'e', e un controllo nel browser
con Playwright se c'e': libreria finta in una cartella temporanea, risposte finte per /api/top, /api/wishlist, /api/free,
/api/ports e /api/shots (nessuna rete). Senza Playwright il controllo nel browser si salta.

Esegui: python tests/test_virtual_lists.py   (oppure pytest tests/test_virtual_lists.py)
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JS = ROOT / "pozzo" / "app" / "static" / "js"
GAMES = 600  # quanti giochi nella libreria finta: basta a superare la finestra visibile piu' volte
ROWS = 2000  # voci delle liste finte: se il DOM crescesse con la lista, supererebbe il limite


def _src(name):
    return (JS / name).read_text(encoding="utf-8")


def test_viste_a_pagina_usano_vlist():
    grid, pages, ports = _src("grid.js"), _src("pages.js"), _src("ports.js")
    assert "function vlist(" in grid
    for host in ("top-rows", "wl-rows", "sh-rows"):
        assert f'id="{host}"' in pages and f'"#{host}"' in pages, host
    for host in ("free-rows", "pt-grid"):
        assert f'"#{host}"' in ports, host
    # niente piu' righe costruite con map().join() dentro il template della pagina
    assert "items.map(row)" not in pages
    assert 'wl-list">${d.items.map' not in pages
    assert "free-grid\">${items.map" not in ports


def test_sintassi_js():
    node = shutil.which("node")
    if not node:
        pytest.skip("node non installato")
    for name in ("grid.js", "pages.js", "ports.js"):
        r = subprocess.run([node, "--check", str(JS / name)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def _library(work: Path) -> None:
    from pozzo.library.build import SCHEMA

    (work / "cache").mkdir()
    (work / "config.toml").write_text('[paths]\nroms = "."\ncache = "cache"\noutput = "output"\n\n'
                                      '[scrape]\nsources = []\nmedia = []\n', encoding="utf-8")
    db = sqlite3.connect(work / "cache" / "library.db")
    try:
        db.executescript(SCHEMA)
        rows = [(f"nes-{i:04d}", "nes", f"Gioco {i:04d}", f"gioco {i:04d}", 1990, "[]", "[]", f"nes-{i:04d}")
                for i in range(GAMES)]
        db.executemany("INSERT INTO games(key, platform, title, sort_title, year, genres, files, grp, found, is_primary, "
                       "media, origin) VALUES (?,?,?,?,?,?,?,?,1,1,'{}','{}')", rows)
        db.execute("INSERT INTO meta(k, v) VALUES('built_at', '1')")
        db.commit()
    finally:
        db.close()


def _mock_routes(ctx) -> None:
    """Risposte finte delle liste: ROWS voci ciascuna, per vedere che nel DOM ne restano poche."""
    def fulfill(payload):
        return lambda route, req: route.fulfill(json=payload)

    top = [{"id": i + 1, "title": f"Top {i}", "platform": "nes", "year": 1990, "also": [], "critics": 0.8, "rating": 0.7,
            "votes": 900, "sources": ["IGDB"], "owned": True, "best": 0.75, "score": 0.74} for i in range(ROWS)]
    wish = [{"id": f"w{i}", "title": f"Desiderio {i}", "owned": False, "checked": 1700000000, "shop": "Steam", "low": 9.5,
             "currency": "EUR", "history": [], "steam": {"price": 19.9, "regular": 29.9, "cut": 33}, "key_price": None,
             "alert": "", "seen": True, "target": None, "url": "", "key_url": "", "cover": "", "steam_appid": None}
            for i in range(ROWS)]
    free = [{"id": i, "title": f"Gratis {i}", "full_title": f"Gratis {i}", "kind": "game", "console": "pc", "cover": "",
             "drm": "steam", "owned": False, "claimed": False, "new": False, "wished": False, "end": "2099-01-01 00:00:00",
             "worth": "", "upcoming": False} for i in range(ROWS)]
    ports = [{"slug": f"p{i}", "name": f"Port {i}", "project": f"P {i}", "developer": "", "tags": [], "consoles": ["pc"],
              "type": "port", "cover": "", "roms": [], "in_store": [], "installed": None, "recommended": 0, "version": "1",
              "description": "", "url": ""} for i in range(ROWS)]
    shots = [{"url": f"/nonexistente/{i}.png", "taken": 1700000000 + i, "source": "test", "game": 1 + i % 200,
              "title": f"Gioco {i % 200}", "platform": "nes", "key": None} for i in range(ROWS)]
    ctx.route(re.compile(r"/api/top\?"), fulfill({"job": {"status": "idle", "phase": "", "tasks": []}, "items": top}))
    ctx.route(re.compile(r"/api/wishlist$"), fulfill({"settings": {"has_key": True, "has_gg": True, "threshold": 30,
                                                                  "country": "IT"}, "checking": False, "log": [],
                                                      "unseen": 0, "items": wish}))
    ctx.route(re.compile(r"/api/free(\?|$)"), fulfill({"items": free, "errors": [], "time": 0, "first": False,
                                                      "stale": False, "new": 0}))
    ctx.route(re.compile(r"/api/ports(\?|$)"), fulfill({"items": ports, "consoles": {"pc": "PC"}, "error": "",
                                                       "refreshing": False, "time": 0, "stale": False}))
    ctx.route(re.compile(r"/api/shots$"), fulfill({"settings": {"hotkey": "ctrl+shift+s", "pad": True,
                                                               "import_emulator": False}, "shots": shots}))


def test_liste_nel_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright non installato")
    work = Path(tempfile.mkdtemp(prefix="pozzo-vlist-"))
    proc = None
    try:
        _library(work)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        child = ("import sys, uvicorn; from pathlib import Path; from pozzo import config; "
                 "from pozzo.app.server import create_app; "
                 "uvicorn.run(create_app(config.load(Path(sys.argv[1]))), host='127.0.0.1', port=int(sys.argv[2]), "
                 "log_level='warning')")
        env = os.environ.copy()
        for name in ("SS_USER", "SS_PASSWORD", "SS_DEVID", "SS_DEVPASSWORD", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET",
                     "TGDB_API_KEY"):
            env.pop(name, None)
        proc = subprocess.Popen([sys.executable, "-c", child, str(work / "config.toml"), str(port)], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(150):
            try:
                urllib.request.urlopen(base + "/api/status", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as error:  # Chromium di Playwright non installato
                pytest.skip(f"Chromium Playwright non disponibile: {error}")
            try:
                ctx = browser.new_context(viewport={"width": 1100, "height": 800})
                ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base + "/") else r.abort())
                _mock_routes(ctx)
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/", wait_until="domcontentloaded")
                page.locator(".tile").first.wait_for(state="attached", timeout=60000)
                for view, host, row in [("top", "#top-rows", ".top-row"), ("wishlist", "#wl-rows", ".wl-row"),
                                        ("free", "#free-rows", ".free-card"), ("ports", "#pt-grid", ".free-card"),
                                        ("shots", "#sh-rows", ".sh-group")]:
                    page.evaluate(f"() => document.querySelector('[data-view=\"{view}\"]').click()")
                    page.wait_for_selector(host, state="attached", timeout=20000)
                    for top in (0, 3000, 60000):
                        page.evaluate(f"() => {{ const pv = document.querySelector('#plugin-view'); "
                                      f"pv.scrollTop = {top}; pv.dispatchEvent(new Event('scroll')); }}")
                        page.wait_for_timeout(300)
                        n = page.locator(f"{host} {row}").count()
                        assert 0 < n < 60, f"{view} a {top}px: {n} righe nel DOM su {ROWS}"
                assert not errors, errors
                ctx.close()
            finally:
                browser.close()
        print("ok  liste virtuali nel browser: poche righe nel DOM a ogni scorrimento")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except BaseException as error:
                if type(error).__name__ == "Skipped":
                    print(f"SKIP {name}: {error}")
                else:
                    raise
