"""Apre una pagina nel WebView nascosto, clicca i pulsanti del sito e restituisce il link al file.

Serve agli accorciatori (ouo.io) e agli host che danno il file solo come download vero (DataNodes): lì
il link non compare mai nella pagina, è l'URL del download che il WebView avvia. pywebview annulla quel
download (`ALLOW_DOWNLOADS` falso: il file lo scarica il manager) ma non ne espone l'URL; su Windows lo
leggiamo dall'evento `DownloadStarting` di WebView2. Altrove la cattura non c'è: `available()` è falso e
chi chiama evita di far aspettare l'utente per niente.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from urllib.parse import urlparse

from ..downloads import hosts as H

TIMEOUT = 75.0
_URI = {"value": ""}
_REASON = {"why": ""}
_HOOKED = {"on": False}
SHOW = {"fn": None}  # impostata dal gestore dei download: True = finestra visibile
_NEWWIN: list[str] = []  # indirizzi che la pagina ha provato ad aprire in una finestra nuova
_LOCK = threading.Lock()  # una finestra alla volta: URI, motivo e titolo sono unici, due risoluzioni insieme si pesterebbero
TITLE = "Pozzo (risoluzione)"  # titolo unico: gli agganci riconoscono da qui la finestra nascosta e non toccano le altre
OFFSCREEN = -32000  # dove nasce (e resta) la finestra: anche se la piattaforma la mostrasse, fuori dallo schermo

# Iniettato a ogni documento (AddScriptToExecuteOnDocumentCreated) nella sola finestra nascosta: nessuna
# finestra, dialogo o richiesta di permesso deve poter uscire da qui.
QUIET_JS = """
(function () {
  const swallow = (fn) => { try { fn(); } catch (e) {} };
  // osservazione passiva, letta da DIAG_JS: richieste di rete, errori e finestre che la pagina prova ad aprire
  swallow(() => {
    window.__pozzoNet = []; window.__pozzoErr = []; window.__pozzoOpened = [];
    const push = (a, x) => { a.push(x); if (a.length > 40) a.shift(); };
    const of = window.fetch;
    if (of) window.fetch = function (i, o) {
      const u = String((i && i.url) || i).slice(0, 140), m = (o && o.method) || (i && i.method) || "GET";
      return of.apply(this, arguments).then((r) => { push(window.__pozzoNet, m + " " + u + " \u2192 " + r.status); return r; },
        (e) => { push(window.__pozzoNet, m + " " + u + " \u2717 " + e.message); throw e; });
    };
    const xo = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (m, u) {
      this.addEventListener("loadend", () => push(window.__pozzoNet, m + " " + String(u).slice(0, 140) + " \u2192 " + this.status));
      return xo.apply(this, arguments);
    };
    window.addEventListener("error", (e) => push(window.__pozzoErr, String(e.message).slice(0, 140)));
    window.addEventListener("unhandledrejection", (e) => push(window.__pozzoErr, "promise: " + String(e.reason).slice(0, 140)));
    window.open = (u) => { push(window.__pozzoOpened, String(u || "").slice(0, 200)); return null; };
  });
  swallow(() => { window.alert = () => {}; window.confirm = () => true; window.prompt = () => null; });
  swallow(() => { window.print = () => {}; });
  swallow(() => {
    Notification.requestPermission = () => Promise.resolve("denied");
    Object.defineProperty(Notification, "permission", { get: () => "denied" });
  });
  // niente «vuoi lasciare la pagina?»
  swallow(() => {
    window.addEventListener("beforeunload", (e) => e.stopImmediatePropagation(), true);
    Object.defineProperty(window, "onbeforeunload", { get: () => null, set: () => {} });
  });
  // link target=_blank: non aprono nulla (come NewWindowRequested, ma prima ancora che parta)
  swallow(() => document.addEventListener("click", (e) => {
    const a = e.target && e.target.closest && e.target.closest("a[target=_blank], area[target=_blank]");
    if (a) e.preventDefault();
  }, true));
})();
"""

# Clic in ordine: su ouo la sequenza dell'estensione (token + Turnstile, POST /go, poi /xreallcygo);
# altrove i pulsanti degli host — «Continue to Download», «Free Download», «Start Download» (DataNodes).
SKIPPER_JS = """
(function () {
  // le pubblicità di questi host aprono finestre: qui non servono e finirebbero nel browser dell'utente
  if (!window.__pozzoOpened) window.open = () => null;
  const text = ((document.body ? document.body.innerText : "") || "").toLowerCase();
  // file tolto dall'host: inutile aspettare il conto alla rovescia
  if (/file not found|file was deleted|has been removed|no such file|link (has )?expired/.test(text)) return "dead";
  const press = (needle) => {
    const el = Array.from(document.querySelectorAll('button, a, input[type=submit], [role=button]'))
      .find((b) => ((b.innerText || b.value || '').trim().toLowerCase().includes(needle)));
    if (el && !el.disabled) { el.click(); return true; }
    return false;
  };
  const host = location.hostname.replace(/^www\\./, "");
  const body = new URLSearchParams();
  for (const name of ["_token", "x-token", "cf-turnstile-response"]) {
    const el = document.querySelector('input[name="' + name + '"]');
    if (el && el.value) body.set(name, el.value);
  }

  if (host === "ouo.io" || host === "ouo.press") {
    if (!body.get("_token")) { press("i'm a human"); press("get link"); return; }
    if (window.__pozzoOuo) return;
    window.__pozzoOuo = true;
    fetch(location.origin + "/go" + location.pathname, {
      method: "POST", body: body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }).then(() => setTimeout(() => {
      const f = document.createElement("form");
      f.method = "POST";
      f.action = location.origin + "/xreallcygo" + location.pathname;
      f.style.display = "none";
      for (const [k, v] of body) {
        const i = document.createElement("input");
        i.type = "hidden"; i.name = k; i.value = v;
        f.appendChild(i);
      }
      document.body.appendChild(f);
      f.submit();
    }, 1000)).catch(() => { window.__pozzoOuo = false; });
    return;
  }

  if (host === "fuckingfast.co") {
    // il pulsante è un trigger htmx (POST /f/<id>/go) e non ha testo utile: si clicca quello
    if (!window.__pozzoFF || Date.now() - window.__pozzoFF > 4000) {
      window.__pozzoFF = Date.now();
      const go = document.querySelector("[hx-post]");
      if (go && !go.disabled) { go.click(); return; }
    }
  }

  const file = Array.from(document.querySelectorAll("a[href]")).map((a) => a.href)
    .find((h) => /\\.(nsp|xci|nsz|zip|rar|7z|iso)(\\?|$)/i.test(h) || /\\/d\\/[^/]+\\//.test(h));
  if (file) { window.__pozzoFile = file; return; }  // già il file: niente clic, che lo scaricherebbe qui
  // un clic ogni 4 s: «Continue to Download» si abilita dopo il controllo, poi compaiono gli altri
  if (!window.__pozzoHost || Date.now() - window.__pozzoHost > 4000) {
    window.__pozzoHost = Date.now();
    press("continue to download");
    press("free download");
    press("start download");
    press("download / view now");
  }
})();
"""


# Fotografia della pagina per il registro: indirizzo, titolo, testo visibile, pulsanti, controlli anti-bot, rete.
DIAG_JS = """
(function () {
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const btns = Array.from(document.querySelectorAll('button, input[type=submit], [role=button], [hx-post], a.btn'))
    .filter(vis).slice(0, 8).map((b) => ((b.innerText || b.value || b.getAttribute('hx-post') || '?').trim().slice(0, 40)) + (b.disabled ? ' (disattivo)' : ''));
  const text = ((document.body ? document.body.innerText : '') || '').replace(/\\s+/g, ' ').trim().slice(0, 180);
  const cap = !!document.querySelector('iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"], .cf-turnstile, #challenge-form, iframe[src*="recaptcha"], iframe[src*="hcaptcha"]')
    || /verify you are human|just a moment|checking your browser|captcha|verifica/i.test(document.title + ' ' + text);
  const take = (k) => { const a = window[k] || []; window[k] = []; return a; };
  return JSON.stringify({ url: location.href, title: document.title, text, btns, cap, frames: document.querySelectorAll('iframe').length,
    ready: document.readyState, net: take('__pozzoNet'), opened: take('__pozzoOpened'), err: take('__pozzoErr') });
})()
"""


def install() -> bool:
    """Aggancia l'evento di download di WebView2 (una volta sola). Falso dove pywebview non lo espone."""
    if _HOOKED["on"]:
        return True
    if sys.platform != "win32":
        return False
    try:
        from webview.platforms.edgechromium import EdgeChrome
    except Exception:  # piattaforma o versione di pywebview senza questo modulo
        return False
    old = EdgeChrome.on_download_starting
    old_window = EdgeChrome.on_new_window_request
    old_ready = EdgeChrome.on_webview_ready

    def on_download_starting(self, sender, args):
        if _mine(self):
            _URI["value"] = _record(args)  # l'URL del file che il WebView stava per scaricare
        return old(self, sender, args)  # pywebview annulla il download (senza dialogo): lo scarica il manager

    def on_new_window_request(self, sender, args):
        """Le pubblicità di questi host aprono popup: pywebview li manda nel browser di sistema (una scheda
        per ognuno). Nella finestra di risoluzione si chiudono qui; nelle altre, comportamento di prima."""
        if not _mine(self):
            return old_window(self, sender, args)
        try:
            _NEWWIN.append(str(args.Uri))
        except Exception:
            pass
        args.set_Handled(True)

    def on_webview_ready(self, sender, args):
        out = old_ready(self, sender, args)
        if _mine(self) and args.IsSuccess:
            _silence(sender.CoreWebView2)
        return out

    EdgeChrome.on_download_starting = on_download_starting
    EdgeChrome.on_new_window_request = on_new_window_request
    EdgeChrome.on_webview_ready = on_webview_ready
    _HOOKED["on"] = True
    return True


def _mine(browser) -> bool:
    """Vero se `browser` (EdgeChrome di pywebview) è la finestra nascosta di risoluzione."""
    return getattr(getattr(browser, "pywebview_window", None), "title", None) == TITLE


def _deny(sender, args) -> None:
    """Permessi (notifiche, posizione, camera, appunti...): sempre negati, senza chiedere."""
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
    args.State = CoreWebView2PermissionState.Deny


def _accept(sender, args) -> None:
    """alert/confirm/prompt/beforeunload nativi: chiusi da soli, nessun dialogo a schermo."""
    args.Accept()


def _silence(core) -> None:
    """Zittisce CoreWebView2: niente dialoghi, permessi negati, script anti-popup in ogni pagina."""
    def permissions():
        core.PermissionRequested += _deny

    def dialogs():
        core.ScriptDialogOpening += _accept

    for step in (
        lambda: setattr(core.Settings, "AreDefaultScriptDialogsEnabled", False),
        lambda: core.AddScriptToExecuteOnDocumentCreated(QUIET_JS),
        permissions,
        dialogs,
    ):
        try:
            step()
        except Exception:  # un pezzo che manca (versione di WebView2) non ferma gli altri
            pass


def _cloak(win) -> None:
    """Mostra la finestra senza che si veda: opacità 0, fuori schermo, fuori dalla barra e da Alt+Tab, mai attivata.

    Il WebView2 nascosto ferma i timer; così risulta visibile al motore ma non all'utente. Non si usa
    `win.show()`: attiva la finestra e la porta al centro dello schermo."""
    import ctypes
    from System import Func, Type
    from System.Drawing import Point

    form = win.native
    hwnd = form.Handle.ToInt32()
    user32 = ctypes.windll.user32
    # TOOLWINDOW (0x80) | NOACTIVATE (0x08000000): niente icona nella barra, niente fuoco rubato
    user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x80 | 0x08000000)

    def go():
        form.Opacity = 0
        form.Location = Point(OFFSCREEN, OFFSCREEN)
        form.Show()

    form.Invoke(Func[Type](go))


def available() -> bool:
    return _HOOKED["on"]


def uri() -> str:
    return _URI["value"]


def reason() -> str:
    """Perché l'ultima risoluzione non è arrivata al file (la coda lo mostra accanto all'errore)."""
    return _REASON["why"]


def _record(args) -> str:
    """L'URL del download dall'oggetto di WebView2 (a parte, così si può provare)."""
    try:
        return args.DownloadOperation.Uri or ""
    except Exception:
        return ""


def resolve(link: str, timeout: float = TIMEOUT) -> str | None:
    """Link al file, o None. Bloccante: da chiamare in un thread, con il ciclo dell'interfaccia avviato."""
    from ..downloads import resolvers
    if _LOCK.locked():
        resolvers.phase("Browser nascosto occupato da un altro download: aspetto il mio turno")
    with _LOCK:  # i download in parallelo aspettano il loro turno (il timeout parte dopo)
        resolvers.phase(f"Browser nascosto: apro {urlparse(link).hostname or link}")
        return _resolve(link, timeout)


def _step(msg: str) -> None:
    """Passo della finestra nascosta nel registro del download (stesso thread del risolutore)."""
    from ..downloads import resolvers
    resolvers.phase(msg)


def _note(msg: str, level: str = "info") -> None:
    """Dettaglio di quello che succede nella pagina: solo registro, la fase mostrata sulla riga non cambia."""
    from ..downloads import resolvers
    resolvers.log("Pagina: " + msg, level)


def _short(url: str, n: int = 70) -> str:
    u = urlparse(url)
    s = (u.hostname or "") + (u.path or "") + ("#…" if u.fragment else "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _same_site(a: str, b: str) -> bool:
    """Stesso sito (ultime due parti del dominio): un popup pubblicitario non e' mai il file."""
    ha, hb = (urlparse(a).hostname or "").split("."), (urlparse(b).hostname or "").split(".")
    return len(ha) > 1 and ha[-2:] == hb[-2:]


class Watch:
    """Legge ogni qualche secondo la pagina (DIAG_JS) e scrive nel registro solo quello che cambia."""

    EVERY = 2.5     # secondi tra due letture
    BEAT = 15.0     # senza novita' si scrive comunque che si sta ancora aspettando

    def __init__(self, win, started: float, hidden: bool):
        self.win, self.t0, self.hidden = win, started, hidden
        self.last = 0.0
        self.beat = started
        self.url = self.title = self.text = ""
        self.btns: list[str] = []
        self.cap = False
        self.info: dict = {}

    def poll(self) -> list[str]:
        """Aggiorna e ritorna gli indirizzi che la pagina ha provato ad aprire (candidati al file)."""
        now = time.time()
        if now - self.last < self.EVERY:
            return []
        self.last = now
        try:
            d = json.loads(self.win.evaluate_js(DIAG_JS) or "{}")
        except Exception:  # pagina in caricamento o non ancora pronta
            return []
        if not d:
            return []
        self.info, changed = d, False
        if d["url"] != self.url:
            self.url, changed = d["url"], True
            _note(f"{_short(d['url'])}" + (f" «{d['title'][:60]}»" if d.get("title") else ""))
        if d["btns"] != self.btns:
            self.btns, changed = d["btns"], True
            _note("pulsanti: " + (", ".join(d["btns"]) if d["btns"] else "nessuno visibile"))
        if d["text"] and d["text"] != self.text:
            self.text, changed = d["text"], True
            _note("testo: " + d["text"][:140])
        for x in d.get("net") or []:
            changed = True
            _note("rete: " + x, "warn" if re.search(r"\u2192 (4|5)\d\d|\u2717", x) else "info")
        for x in d.get("err") or []:
            changed = True
            _note("errore nella pagina: " + x, "warn")
        if d["cap"] and not self.cap:
            changed = True
            _note("c'è un controllo anti-bot (captcha/Cloudflare)" + (
                ": la finestra è nascosta, attiva «Mostra il browser» in Impostazioni › Download per superarlo a mano"
                if self.hidden else ": la finestra è visibile, completalo a mano"), "warn")
        self.cap = d["cap"]
        opened = [x for x in d.get("opened") or [] if x.startswith("http")]
        for x in opened:
            changed = True
            _note("la pagina ha provato ad aprire " + _short(x, 100))
        if changed:
            self.beat = now
        elif now - self.beat >= self.BEAT:
            self.beat = now
            _note(f"ancora in attesa dopo {now - self.t0:.0f} s su {_short(self.url or '?')}"
                  + (f" · «{self.text[:60]}»" if self.text else ""))
        return opened

    def where(self) -> str:
        """Per il motivo del fallimento: dove si era fermata la pagina."""
        if not self.url:
            return ""
        return f" (ultima pagina: {_short(self.url)}" + (f", «{self.text[:80]}»" if self.text else "") \
            + (", controllo anti-bot in attesa" if self.cap else "") + ")"


def _resolve(link: str, timeout: float) -> str | None:
    import webview  # qui: senza interfaccia il modulo non serve

    _URI["value"], _REASON["why"] = "", ""
    _NEWWIN.clear()
    show = bool((SHOW["fn"] or (lambda: False))())
    # di norma nasce nascosta, fuori schermo e senza prendere il fuoco; popup, dialoghi e permessi li zittisce
    # install() (riconosce la finestra dal titolo). Mai win.show()/focus: attivano e centrano la finestra.
    # Con «Mostra il browser» e' una finestra normale: si vede cosa fa la pagina e si puo' superare un captcha
    if show:
        win = webview.create_window(TITLE, link, width=980, height=720, focus=False)
    else:
        win = webview.create_window(TITLE, link, width=460, height=420, x=OFFSCREEN, y=OFFSCREEN,
                                    hidden=True, focus=False)
    if win is None:
        _REASON["why"] = "non riesco ad aprire la finestra del browser"
        return None
    _note("finestra visibile" if show else "finestra nascosta (Impostazioni › Download › «Mostra il browser» per vederla)")
    start = link.rstrip("/")
    t0 = time.time()
    end = t0 + timeout
    shown = False
    seen = ""  # ultimo host annunciato nel registro
    page, page_at = "", 0.0  # pagina di destinazione: si aspetta un attimo se il download parte li'
    watch = Watch(win, t0, hidden=not show)
    nw_seen = 0
    try:
        while time.time() < end:
            time.sleep(0.5)
            if _URI["value"]:
                _step(f"Browser nascosto: download avviato da {urlparse(_URI['value']).hostname}")
                return _URI["value"]  # download avviato: questo è il file
            try:
                cur = win.get_current_url() or ""
            except Exception:
                _REASON["why"] = "la finestra del browser si è chiusa"
                return None
            if cur.startswith("http") and cur.rstrip("/") != start:
                h = (urlparse(cur).hostname or "").replace("www.", "")
                if h in ("ouo.io", "ouo.press", "hikarinoakari.com"):
                    if h != seen:
                        seen = h
                        _step(f"Browser nascosto: pagina dell'accorciatore {h}, clicco i pulsanti")
                elif H.is_host_page(cur):
                    if h != seen:
                        seen = h
                        _step(f"Browser nascosto: pagina dell'host {h}" + (", attendo il conto alla rovescia" if h in H.VISIBLE else ""))
                    if h in H.VISIBLE and not shown and not show:
                        shown = True  # nascosta = timer fermi: «visibile» per il motore, mai per l'utente
                        try:
                            _cloak(win)
                        except Exception:  # senza WinForms resta nascosta (lo shim fa ripartire i timer)
                            pass
                    if not available() or h not in H.BROWSER_ONLY:
                        return cur  # host con un risolutore suo (1fichier, MegaUp…): lo fa lui
                else:
                    # pagina di destinazione: alcuni host la usano come salto verso il download vero
                    # (megaup -> download.megaup.net), quindi si lascia un attimo per vederlo partire
                    if cur != page:
                        page, page_at = cur, time.time()
                    elif time.time() - page_at > 4:
                        return page
            # finestre che la pagina ha provato ad aprire (window.open o link): spesso e' proprio il file
            fresh = list(_NEWWIN[nw_seen:])
            nw_seen = len(_NEWWIN)
            for x in fresh:
                _note("la pagina ha provato ad aprire " + _short(x, 100))
            for x in [*fresh, *watch.poll()]:
                if x.startswith("http") and x.rstrip("/") != start and H.is_file_url(x, cur or link) and (
                        _same_site(x, cur or link) or re.search(r"\.(zip|rar|7z|nsp|xci|nsz|iso)(\?|$)", x, re.I)):  # mai le pubblicita'
                    _step(f"Browser nascosto: la pagina apre il file ({urlparse(x).hostname})")
                    return x
            try:
                found = win.evaluate_js("window.__pozzoFile || ''")
            except Exception:
                found = ""  # pagina non ancora pronta: si riprova al giro dopo
            if found:
                _step(f"Browser nascosto: trovato il link nella pagina ({urlparse(found).hostname})")
                return found
            try:
                out = win.evaluate_js(SKIPPER_JS)
            except Exception:
                out = ""
            if out == "dead":
                _REASON["why"] = "il file non è più su " + ((urlparse(win.get_current_url() or "").hostname or "").replace("www.", "") or "questo host")
                return None
        _REASON["why"] = f"la pagina non è arrivata al file in {timeout:g} s" + watch.where()
        _note(_REASON["why"], "error")
        return None
    finally:
        try:
            win.destroy()
        except Exception:
            pass
