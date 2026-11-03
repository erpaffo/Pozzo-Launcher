"""La finestra nascosta di risoluzione non deve mai farsi vedere: nasce nascosta e fuori schermo, non si chiama
show()/focus, popup/dialoghi/permessi sono zittiti. Oggetti `webview` finti: la prova vera e' solo nell'app.

Esegui: python -m pytest tests/test_browserdl.py -q
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo.app import browserdl as B  # noqa: E402


class FakeWin:
    def __init__(self, urls, found=""):
        self.urls, self.found, self.calls = list(urls), found, []

    def get_current_url(self):
        return self.urls.pop(0) if len(self.urls) > 1 else self.urls[0]

    def evaluate_js(self, js):
        return self.found if js == "window.__pozzoFile || ''" else ""

    def show(self):
        self.calls.append("show")

    def focus(self):
        self.calls.append("focus")

    def destroy(self):
        self.calls.append("destroy")


def _run(monkeypatch, win, url="https://filekeeper.net/f/abc"):
    made = {}

    def create_window(*a, **kw):
        made["args"], made["kw"] = a, kw
        return win

    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(create_window=create_window))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    return made


def test_finestra_nascosta_fuori_schermo_senza_fuoco(monkeypatch):
    win = FakeWin(["https://x/"], found="https://cdn/file.zip")
    made = _run(monkeypatch, win)
    assert B.resolve("https://ouo.io/abc") == "https://cdn/file.zip"
    kw = made["kw"]
    assert kw["hidden"] is True and kw["focus"] is False
    assert kw["x"] == kw["y"] == B.OFFSCREEN < 0
    assert made["args"][0] == B.TITLE
    assert win.calls == ["destroy"]  # mai show()/focus()


def test_host_visibile_usa_cloak_non_show(monkeypatch):
    win = FakeWin(["https://filekeeper.net/f/abc"])
    _run(monkeypatch, win)
    seen = []
    monkeypatch.setattr(B, "_cloak", lambda w: seen.append(w))
    monkeypatch.setitem(B._HOOKED, "on", False)  # senza aggancio al download: l'host lo risolve altrove
    assert B.resolve("https://multiup.io/x", timeout=5) == "https://filekeeper.net/f/abc"
    assert seen == [win] and "show" not in win.calls and "focus" not in win.calls


def test_cloak_rotto_non_mostra_nulla(monkeypatch):
    win = FakeWin(["https://filekeeper.net/f/abc"])
    _run(monkeypatch, win)
    monkeypatch.setattr(B, "_cloak", lambda w: 1 / 0)
    monkeypatch.setitem(B._HOOKED, "on", False)
    assert B.resolve("https://multiup.io/x", timeout=5)
    assert "show" not in win.calls


def test_shim_copre_popup_dialoghi_permessi():
    for needle in ("window.open", "window.alert", "window.confirm", "window.prompt", "Notification",
                   "denied", "beforeunload", "target=_blank"):
        assert needle in B.QUIET_JS, needle


class Args:
    def __init__(self, uri=""):
        self.handled = self.cancel = False
        self.accepted = 0
        self.DownloadOperation = types.SimpleNamespace(Uri=uri)
        self.IsSuccess = True

    def set_Handled(self, v):
        self.handled = v

    def Accept(self):
        self.accepted += 1


class Ev(list):  # evento .NET: `evento += gestore`
    def __iadd__(self, fn):
        self.append(fn)
        return self


class Core:
    def __init__(self):
        self.Settings = types.SimpleNamespace(AreDefaultScriptDialogsEnabled=True)
        self.scripts, self.PermissionRequested, self.ScriptDialogOpening = [], Ev(), Ev()

    def AddScriptToExecuteOnDocumentCreated(self, js):
        self.scripts.append(js)


def _fake_edge(monkeypatch):
    class EdgeChrome:
        def on_download_starting(self, sender, args):
            args.cancel = True

        def on_new_window_request(self, sender, args):
            args.opened = True  # pywebview: browser di sistema

        def on_webview_ready(self, sender, args):
            sender.ready = True

    mod = types.ModuleType("webview.platforms.edgechromium")
    mod.EdgeChrome = EdgeChrome
    monkeypatch.setitem(sys.modules, "webview.platforms.edgechromium", mod)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(B._HOOKED, "on", False)
    assert B.install()
    return EdgeChrome


def _browser(cls, title):
    b = cls()
    b.pywebview_window = types.SimpleNamespace(title=title)
    return b


def test_nuova_finestra_annullata_solo_nella_risoluzione(monkeypatch):
    E = _fake_edge(monkeypatch)
    a = Args()
    E.on_new_window_request(_browser(E, B.TITLE), None, a)
    assert a.handled and not hasattr(a, "opened")
    b = Args()
    E.on_new_window_request(_browser(E, "Accedi a X"), None, b)
    assert not b.handled and b.opened  # le altre finestre: come prima


def test_download_annullato_ma_url_catturato(monkeypatch):
    E = _fake_edge(monkeypatch)
    B._URI["value"] = ""
    a = Args("https://cdn/file.zip")
    E.on_download_starting(_browser(E, B.TITLE), None, a)
    assert a.cancel and B.uri() == "https://cdn/file.zip"  # niente dialogo di salvataggio, URL letto
    B._URI["value"] = ""
    E.on_download_starting(_browser(E, "Pozzo Launcher"), None, Args("https://altro/x"))
    assert B.uri() == ""  # le altre finestre non toccano lo stato


def test_webview_pronto_installa_silenzio_solo_nella_risoluzione(monkeypatch):
    E = _fake_edge(monkeypatch)
    monkeypatch.setitem(sys.modules, "Microsoft.Web.WebView2.Core", types.SimpleNamespace(
        CoreWebView2PermissionState=types.SimpleNamespace(Deny="deny")))
    core = Core()
    sender = types.SimpleNamespace(CoreWebView2=core)
    E.on_webview_ready(_browser(E, B.TITLE), sender, Args())
    assert sender.ready and core.scripts == [B.QUIET_JS]
    assert core.Settings.AreDefaultScriptDialogsEnabled is False
    assert core.PermissionRequested == [B._deny] and core.ScriptDialogOpening == [B._accept]
    other = Core()
    E.on_webview_ready(_browser(E, "Pozzo Launcher"), types.SimpleNamespace(CoreWebView2=other), Args())
    assert other.scripts == [] and other.Settings.AreDefaultScriptDialogsEnabled is True


def test_permessi_negati_e_dialoghi_accettati(monkeypatch):
    monkeypatch.setitem(sys.modules, "Microsoft.Web.WebView2.Core", types.SimpleNamespace(
        CoreWebView2PermissionState=types.SimpleNamespace(Deny="deny")))
    a = types.SimpleNamespace(State="ask")
    B._deny(None, a)
    assert a.State == "deny"
    b = Args()
    B._accept(None, b)
    assert b.accepted == 1


def test_watch_scrive_nel_registro_solo_le_novita():
    import json as _j
    from pozzo.downloads import resolvers
    snap = {"url": "https://fuckingfast.co/abc#x.rar", "title": "x.rar", "text": "Download", "btns": ["Download"],
            "cap": True, "frames": 1, "ready": "complete", "net": ["POST https://fuckingfast.co/f/abc/go → 403"],
            "opened": ["https://dl.fuckingfast.co/file.rar"], "err": []}
    def js(self, _):  # come la pagina vera: rete, errori e finestre aperte si leggono una volta sola
        out = _j.dumps(snap)
        snap.update(net=[], opened=[], err=[])
        return out

    win = type("W", (), {"evaluate_js": js})()
    lines = []
    resolvers._tl.on_log = lambda m, lv: lines.append((lv, m))
    try:
        w = B.Watch(win, 0.0, hidden=True)
        w.EVERY = 0
        opened = w.poll()
        n = len(lines)
        w.poll()  # stessa pagina: niente righe doppie
        assert len(lines) == n
    finally:
        resolvers._tl.on_log = None
    text = "\n".join(m for _, m in lines)
    assert opened == ["https://dl.fuckingfast.co/file.rar"]
    assert "pulsanti: Download" in text and "403" in text and "anti-bot" in text and "Mostra il browser" in text
    assert any(lv == "warn" and "403" in m for lv, m in lines), "una risposta 4xx e' un avviso"
    assert "ultima pagina" in w.where() and "anti-bot" in w.where()


def test_un_popup_pubblicitario_non_e_il_file():
    assert B._same_site("https://dl.fuckingfast.co/x", "https://fuckingfast.co/a")
    assert not B._same_site("https://ads.example.net/x.rar", "https://fuckingfast.co/a")
