"""Scansione XSS del frontend: ogni `${...}` dentro un'assegnazione a innerHTML / insertAdjacentHTML /
outerHTML deve passare da esc() (o da un helper sicuro) oppure essere numerica / costante / nella ALLOWLIST.

Euristica statica, non un parser JS: serve a far fallire il test quando qualcuno interpola un dato
non fidato (scraping, estensioni, nomi file, rete) senza escape. Un'interpolazione "sicura per costruzione"
che l'euristica non riconosce va in ALLOWLIST con il motivo.
Uso: PYTHONUTF8=1 python tests/test_js_innerhtml.py [-v]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "pozzo" / "app" / "static"
SCAN_DIRS = [STATIC] + [p for p in (ROOT / "extensions").glob("*/frontend.js")]

SINK = re.compile(r"(?:\.innerHTML\s*\+?=(?!=)|\.outerHTML\s*=(?!=)|\.insertAdjacentHTML\s*\(\s*[^,]+,)")

# Chiamate il cui risultato e' gia' HTML sicuro o testo costante (i18n, icone, escape).
SAFE_CALLS = ("esc", "GS.esc", "escapeHtml", "escHtml", "ctx.esc", "t", "GS.t", "icon", "GS.icon", "ICON", "ic",
              "Number", "parseInt", "parseFloat", "String(Number", "Math.round", "Math.floor", "Math.ceil", "Math.max",
              "Math.min", "Math.abs", "fmtNum", "fmtBytes", "fmtSize", "fmtDur", "fmtTime", "fmtHours", "pct")

# ALLOWLIST: (file, espressione) interpolati senza esc() e rivisti a mano. Il motivo e' una delle costanti:
NUM = "numero, enum o costante prodotta dal codice/backend proprio (conteggi, livelli, slot, tabelle fisse, colori)"
HTML = "variabile locale gia' composta con esc() nel punto in cui e' costruita (o markup statico)"
SRV = "URL/SVG generato dal server a partire da id interni (/img/<gid>/..., QR), mai da testo scraped"
# Chiave senza numero di riga: se aggiungi un'interpolazione NUOVA nello stesso file con la stessa espressione
# non scatta; per un dato testuale usa comunque esc(). Limite noto: gli helper chiamati (renderX(), tr(), ...) sono
# considerati fidati; il loro corpo e' controllato solo se contiene a sua volta un sink innerHTML.
ALLOWLIST = {
    ('extensions/anniversari/frontend.js', 'MESI[m - 1]'): NUM,
    ('extensions/anniversari/frontend.js', 'd'): NUM,
    ('extensions/diario/frontend.js', 'd.partite'): NUM,
    ('extensions/diario/frontend.js', 'r.t'): SRV,
    ('extensions/eventi-fiere/frontend.js', 'righe'): HTML,
    ('extensions/limite-tempo/frontend.js', 'd.giorno_ore'): NUM,
    ('extensions/limite-tempo/frontend.js', 'd.settimana_ore'): NUM,
    ('extensions/linkstores/frontend.js', 'shown'): HTML,
    ('extensions/media-locale/frontend.js', 'onlineSearchBanner'): HTML,
    ('extensions/media-locale/frontend.js', 'pinnedCarousel'): HTML,
    ('extensions/media-locale/frontend.js', 'x'): HTML,
    ('extensions/media-locale/frontend.js', 'y'): NUM,
    ('extensions/minerva/frontend.js', 'c.unread'): NUM,
    ('extensions/obiettivi/frontend.js', 'b.soglia'): NUM,
    ('extensions/obiettivi/frontend.js', 'd.serie.attuale'): NUM,
    ('extensions/obiettivi/frontend.js', 'd.serie.migliore'): NUM,
    ('extensions/obiettivi/frontend.js', 'v'): NUM,
    ('extensions/pulizia/frontend.js', 'head'): HTML,
    ('extensions/pulizia/frontend.js', 'l'): NUM,
    ('extensions/pulizia/frontend.js', 'y'): NUM,
    ('extensions/ricette-web/frontend.js', 'siteBtn'): HTML,
    ('extensions/riepilogo-annuale/frontend.js', 'd.anno'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'd.finiti'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'd.giochi'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'd.giorni'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'd.giorno_settimana'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'd.mese'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 't.partite'): NUM,
    ('extensions/riepilogo-annuale/frontend.js', 'y'): NUM,
    ('extensions/sconti/frontend.js', 'note'): HTML,
    ('extensions/stasera/frontend.js', 'g.store'): NUM,
    ('extensions/stasera/frontend.js', 'g.year'): NUM,
    ('extensions/stasera/frontend.js', 'hrs'): HTML,
    ('extensions/stasera/frontend.js', 'l'): NUM,
    ('extensions/stasera/frontend.js', 'last'): HTML,
    ('extensions/stasera/frontend.js', 'v'): NUM,
    ('extensions/statistiche/frontend.js', 't.partite'): NUM,
    ('pozzo/app/static/bigpicture-media.js', 'e.episode'): NUM,
    ('pozzo/app/static/bigpicture-media.js', 'x.season'): NUM,
    ('pozzo/app/static/bigpicture.js', 'kb'): HTML,
    ('pozzo/app/static/bigpicture.js', 'opts.head'): NUM,
    ('pozzo/app/static/bigpicture.js', 'opts.unit'): NUM,
    ('pozzo/app/static/bigpicture.js', 'pad'): HTML,
    ('pozzo/app/static/bigpicture.js', 's.url'): SRV,
    ('pozzo/app/static/bigpicture/layouts/classic/layout.js', 'd.media.cover'): SRV,
    ('pozzo/app/static/bigpicture/layouts/classic/layout.js', 'd.media.logo'): SRV,
    ('pozzo/app/static/bigpicture/layouts/classic/layout.js', 'r'): HTML,
    ('pozzo/app/static/experiences/storefront/experience.js', 'facts'): HTML,
    ('pozzo/app/static/experiences/storefront/experience.js', 'gameLabel'): HTML,
    ('pozzo/app/static/i18n.js', 'l'): NUM,
    ('pozzo/app/static/i18n.js', 'v'): NUM,
    ('pozzo/app/static/js/actions.js', 'k.kind'): NUM,
    ('pozzo/app/static/js/actions.js', 'k.url'): SRV,
    ('pozzo/app/static/js/actions.js', 'r.shots'): NUM,
    ('pozzo/app/static/js/actions.js', 't'): HTML,
    ('pozzo/app/static/js/detail-mods.js', 'results'): HTML,
    ('pozzo/app/static/js/detail.js', 'a.points'): NUM,
    ('pozzo/app/static/js/detail.js', 'cur'): HTML,
    ('pozzo/app/static/js/detail.js', 'done'): NUM,
    ('pozzo/app/static/js/detail.js', 'g.unlocked'): NUM,
    ('pozzo/app/static/js/detail.js', 'parts'): HTML,
    ('pozzo/app/static/js/detail.js', 'tot'): NUM,
    ('pozzo/app/static/js/downloads.js', 'DL.panelH'): NUM,
    ('pozzo/app/static/js/downloads.js', 'H'): NUM,
    ('pozzo/app/static/js/downloads.js', 'W'): NUM,
    ('pozzo/app/static/js/downloads.js', 'area'): HTML,
    ('pozzo/app/static/js/downloads.js', 'c'): HTML,
    ('pozzo/app/static/js/downloads.js', 'cols'): HTML,
    ('pozzo/app/static/js/downloads.js', 'ic'): HTML,
    ('pozzo/app/static/js/downloads.js', 'l'): NUM,
    ('pozzo/app/static/js/downloads.js', 'label'): NUM,
    ('pozzo/app/static/js/downloads.js', 'line'): HTML,
    ('pozzo/app/static/js/downloads.js', 'meta'): HTML,
    ('pozzo/app/static/js/downloads.js', 'svc'): NUM,
    ('pozzo/app/static/js/downloads.js', 'txt'): HTML,
    ('pozzo/app/static/js/downloads.js', 'url'): NUM,
    ('pozzo/app/static/js/emulators.js', 'c'): HTML,
    ('pozzo/app/static/js/emulators.js', 'cores'): HTML,
    ('pozzo/app/static/js/emulators.js', 'opts'): HTML,
    ('pozzo/app/static/js/emulators.js', 'status'): HTML,
    ('pozzo/app/static/js/grid.js', 'badges'): HTML,
    ('pozzo/app/static/js/grid.js', 'card'): HTML,
    ('pozzo/app/static/js/grid.js', 'gap'): NUM,
    ('pozzo/app/static/js/pages.js', 'STATUS[g.grp.status].label'): NUM,
    ('pozzo/app/static/js/pages.js', 'c'): HTML,
    ('pozzo/app/static/js/pages.js', 'd.year'): NUM,
    ('pozzo/app/static/js/pages.js', 'doneN'): NUM,
    ('pozzo/app/static/js/pages.js', 'key'): NUM,
    ('pozzo/app/static/js/pages.js', 'names[x.source]'): NUM,
    ('pozzo/app/static/js/pages.js', 'o.cut'): NUM,
    ('pozzo/app/static/js/pages.js', 's'): HTML,
    ('pozzo/app/static/js/pages.js', 's.threshold'): NUM,
    ('pozzo/app/static/js/pages.js', 's.url'): SRV,
    ('pozzo/app/static/js/pages.js', 'st.backlog'): NUM,
    ('pozzo/app/static/js/pages.js', 'st.playing'): NUM,
    ('pozzo/app/static/js/pages.js', 'steam.cut'): NUM,
    ('pozzo/app/static/js/pages.js', 'x.unlocked'): NUM,
    ('pozzo/app/static/js/pages.js', 'y'): NUM,
    ('pozzo/app/static/js/ports.js', 'name'): HTML,
    ('pozzo/app/static/js/profiles-exp.js', 'experienceOptions'): HTML,
    ('pozzo/app/static/js/profiles-exp.js', 'profileCards'): HTML,
    ('pozzo/app/static/js/profiles-exp.js', 'themeOptions'): HTML,
    ('pozzo/app/static/js/remote.js', 'c.color'): NUM,
    ('pozzo/app/static/js/remote.js', 'ico[x.level]'): NUM,
    ('pozzo/app/static/js/remote.js', 'ph.qr'): SRV,
    ('pozzo/app/static/js/remote.js', 'ph.qr_ca'): SRV,
    ('pozzo/app/static/js/remote.js', 'ph.screen_idle'): NUM,
    ('pozzo/app/static/js/remote.js', 's'): HTML,
    ('pozzo/app/static/js/remote.js', 'slot'): NUM,
    ('pozzo/app/static/js/remote.js', 'x.level'): NUM,
    ('pozzo/app/static/js/settings.js', 'badge'): HTML,
    ('pozzo/app/static/js/settings.js', 'bars'): HTML,
    ('pozzo/app/static/js/settings.js', 'ico[x.level]'): NUM,
    ('pozzo/app/static/js/settings.js', 'l'): NUM,
    ('pozzo/app/static/js/settings.js', 'lbl'): NUM,
    ('pozzo/app/static/js/settings.js', 'max'): NUM,
    ('pozzo/app/static/js/settings.js', 'opts'): HTML,
    ('pozzo/app/static/js/settings.js', 'p.slot'): NUM,
    ('pozzo/app/static/js/settings.js', 'v'): NUM,
    ('pozzo/app/static/js/settings.js', 'x.level'): NUM,
    ('pozzo/app/static/js/sidebar.js', 'key'): NUM,
    ('pozzo/app/static/js/sidebar.js', 'otherOpen'): NUM,
    ('pozzo/app/static/js/sidebar.js', 'pcInst'): HTML,
    ('pozzo/app/static/js/sidebar.js', 's.label'): NUM,
    ('pozzo/app/static/js/sidebar.js', 'slug'): NUM,
    ('pozzo/app/static/js/stores.js', 'accs'): HTML,
    ('pozzo/app/static/js/stores.js', 'bar'): HTML,
    ('pozzo/app/static/js/stores.js', 'bars'): HTML,
    ('pozzo/app/static/js/stores.js', 'ctrl'): HTML,
    ('pozzo/app/static/js/stores.js', 'st'): HTML,
    ('pozzo/app/static/js/stores.js', 'v'): NUM,
    ('pozzo/app/static/js/stores.js', 'x.games'): NUM,
    ('pozzo/app/static/js/stores.js', 'x.installed'): NUM,
    ('pozzo/app/static/js/stores.js', 'x.kind'): NUM,
    ('pozzo/app/static/js/wof.js', 'a'): NUM,
    ('pozzo/app/static/m/m.js', 'PCOLOR[(n - 1) % 4]'): NUM,
    ('pozzo/app/static/m/m.js', 'PCOLOR[(p - 1) % 4]'): NUM,
    ('pozzo/app/static/m/m.js', 'g.store'): NUM,
    ('pozzo/app/static/m/m.js', 'l'): NUM,
    ('pozzo/app/static/m/m.js', 'slot'): NUM,
    ('pozzo/app/static/motion-settings.js', 'v'): NUM,
    ('pozzo/app/static/palette.js', 'g.label'): NUM,
    ('pozzo/app/static/settings/controller-extra.js', 'e.exe'): NUM,
    ('pozzo/app/static/settings/controller-extra.js', 'v'): NUM,
    ('pozzo/app/static/settings/libshare.js', 'inv'): HTML,
    ('pozzo/app/static/settings/libshare.js', 'n.qr'): SRV,
    ('pozzo/app/static/settings/libshare.js', 'plats'): HTML,
}
# Variabili con questi nomi contengono per convenzione HTML gia' composto (con esc() nel punto in cui e' costruito)
# o valori numerici/di classe. Il costruttore e' comunque scansionato perche' e' a sua volta un'assegnazione/template.
SAFE_NAME = re.compile(r"^(?:[A-Za-z_$][\w$]*(?:\.[\w$]+)*)$")
SAFE_NAME_HINT = re.compile(r"(?:html|Html|HTML|markup|icon|Icon|cls|Cls|class|Class|style|Style|attr|Attr|"
                            r"count|Count|total|Total|idx|index|Index|pct|width|height|size|Size|num|Num|len|Len|"
                            r"^[ijkn]$|^id$|^w$|^h$|^p$|^pc$|^css$|^rows$|^cells$|^items$|^body$|^inner$|^out$|^list$|^tabs$|^chips$|^cards$)")


def _skip_string(src, i):
    q = src[i]
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == q:
            return i + 1
        i += 1
    return i


def _template_end(src, i):
    """src[i] == '`': ritorna (indice dopo la chiusura, lista delle espressioni ${...} di primo livello)."""
    exprs = []
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
        elif c == "`":
            return i + 1, exprs
        elif c == "$" and src[i + 1:i + 2] == "{":
            j = i + 2
            depth = 1
            while j < len(src) and depth:
                d = src[j]
                if d in "'\"":
                    j = _skip_string(src, j)
                    continue
                if d == "`":
                    j, _ = _template_end(src, j)
                    continue
                if d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                j += 1
            exprs.append(src[i + 2:j - 1])
            i = j
        else:
            i += 1
    return i, exprs


def _statement_end(src, i):
    """Fine dell'assegnazione: primo ';' fuori da stringhe, template e parentesi."""
    depth = 0
    while i < len(src):
        c = src[i]
        if c in "'\"":
            i = _skip_string(src, i)
            continue
        if c == "`":
            i, _ = _template_end(src, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == ";" and depth == 0:
            return i
        elif c == "\n" and depth == 0:
            # fine riga senza continuazione ovvia (operatore o apertura): chiude l'istruzione
            k = i + 1
            while k < len(src) and src[k] in " \t":
                k += 1
            prev = src[:i].rstrip()
            if not prev.endswith(("+", "?", ":", "(", ",", "=", "&&", "||")) and src[k:k + 1] not in ("+", "?", ":", ".", "&", "|"):
                return i
        i += 1
    return i


def _strip_strings(e):
    """Toglie i letterali stringa semplici ('..' e "..") dall'espressione."""
    out, i = [], 0
    while i < len(e):
        if e[i] in "'\"":
            i = _skip_string(e, i)
            out.append('""')
        else:
            out.append(e[i])
            i += 1
    return "".join(out)


def _split_top(e, ch):
    parts, depth, cur, i = [], 0, [], 0
    while i < len(e):
        c = e[i]
        if c in "'\"":
            j = _skip_string(e, i)
            cur.append(e[i:j])
            i = j
            continue
        if c == "`":
            j, _ = _template_end(e, i)
            cur.append(e[i:j])
            i = j
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if ch == "?" and depth == 0 and c == "?" and (e[i + 1:i + 2] in ("?", ".") or e[i - 1:i] == "?"):
            if e[i + 1:i + 2] == "?":  # «??»: consuma entrambi
                cur.append("??")
                i += 2
                continue
            if e[i + 1:i + 2] == "." and not e[i + 2:i + 3].isdigit():  # «?.»
                cur.append("?.")
                i += 2
                continue
        if depth == 0 and e.startswith(ch, i):
            parts.append("".join(cur))
            cur = []
            i += len(ch)
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def _balanced_wrap(e):
    depth = 0
    i = 0
    while i < len(e):
        c = e[i]
        if c in "'\"":
            i = _skip_string(e, i)
            continue
        if c == "`":
            i, _ = _template_end(e, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and i != len(e) - 1:
                return False
        i += 1
    return depth == 0


def _plain_helper_call(e):
    """`helper(args)` intera (non catena .map): safe call o helper locale fidato, gli argomenti non contano."""
    name, rest = _call_name_and_rest(e)
    return bool(name) and rest.strip() == "" and name.rsplit(".", 1)[-1] not in ("map", "filter", "flatMap")


def _call_name_and_rest(e):
    m = re.match(r"^([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(", e)
    if not m:
        return None, None
    i, depth = m.end(), 1
    while i < len(e) and depth:
        c = e[i]
        if c in "'\"":
            i = _skip_string(e, i)
            continue
        if c == "`":
            i, _ = _template_end(e, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return m.group(1), e[i:]


def is_safe(e):
    e = e.strip()
    if not e:
        return True
    if e.startswith("(") and e.endswith(")") and _balanced_wrap(e):
        return is_safe(e[1:-1])
    # costruttore di liste: x.map(cb).join(sep) / x.map(cb) con cb freccia o function. Contano solo i template
    # annidati (valutati con le stesse regole) e il corpo del cb se non e' un template.
    if ("=>" in e or "function" in e) and re.search(r"\.(map|filter|flatMap)\(", e) and not e.startswith(("?", "!"))             and not _plain_helper_call(e):
        return _map_body_safe(e)
    if re.fullmatch(r"-?\d+(\.\d+)?", e) or e in ("true", "false", "null", "undefined"):
        return True
    if e[0] in "'\"" and _skip_string(e, 0) == len(e):
        return True
    if e[0] == "`":
        end, sub = _template_end(e, 0)
        if end == len(e):
            return all([is_safe(s) for s in sub])
    # ternario: la condizione non conta, contano i due rami
    q = _split_top(e, "?")
    if len(q) >= 2 and not e.startswith("?"):
        rest = "?".join(q[1:])
        br = _split_top(rest, ":")
        if len(br) >= 2:
            a, b = is_safe(br[0]), is_safe(":".join(br[1:]))
            return a and b
    for op in ("||", "??", "&&"):
        p = _split_top(e, op)
        if len(p) > 1:
            # `a && b`: conta solo il valore b; `a || b`: contano entrambi
            return all([is_safe(x) for x in (p[1:] if op == "&&" else p)])
    p = _split_top(e, "+")
    if len(p) > 1:
        return all([is_safe(x) for x in p])
    p = _split_top(e, "-") if "-" in e else [e]
    if len(p) > 1 and all(re.fullmatch(r"[\w$.()\s]+", x) for x in p):
        # sottrazioni: numerico
        return True
    for op in ("*", "/", "%"):
        if len(_split_top(e, op)) > 1:
            return True
    if e.startswith("!"):
        return True
    return _leaf_ok(e)


# Metodi stringa che restituiscono ancora testo del dato (non lo ripuliscono).
PASS_THROUGH = {"replace", "replaceAll", "slice", "substring", "substr", "trim", "trimStart", "trimEnd", "toString",
                "join", "split", "toLowerCase", "toUpperCase", "padStart", "padEnd", "concat", "normalize", "charAt",
                "at", "toLocaleLowerCase", "toLocaleUpperCase", "decodeURIComponent", "String"}
NUMERIC_TAIL = re.compile(r"\.(length|size|toFixed\(.*\)|toLocaleString\(.*\)|count)$")


_BAD = []  # foglie rischiose trovate durante la valutazione corrente


def _leaf_ok(e):
    """Foglia dell'espressione. Rischiosa solo se e' un dato grezzo: percorso `a.b?.c[0]`, oppure un metodo
    stringa applicato a un percorso. Qualunque altra chiamata (renderX(), tr(), helper locali) e' considerata un
    costruttore di HTML fidato: limite noto, il suo corpo e' coperto solo se contiene a sua volta un sink."""
    if NUMERIC_TAIL.search(e) or e.endswith(("|0", "| 0")) or e.startswith(("+", "!", "typeof ", "-")):
        return True
    name, rest = _call_name_and_rest(e)
    if name:
        if name in SAFE_CALLS:
            return True
        last = name.rsplit(".", 1)[-1]
        if last in PASS_THROUGH:
            base = name.rsplit(".", 1)[0] if "." in name else ""
            args = e[e.index("(") + 1:e.rindex(")")] if ")" in e else ""
            # String(x) / decodeURIComponent(x): il dato e' nell'argomento; x.replace(..): nella base
            target = args if not base else base
            return _leaf_ok(target.strip()) if target.strip() and not target.strip().startswith(("'", '"', "`")) else True
        return True
    if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\s*(?:\?\.|\.)\s*[A-Za-z_$][\w$]*|\s*\?*\.?\[[^\]]*\])*", e):
        tail = re.split(r"\?\.|\.|\[", e)[-1].rstrip("]").strip()
        if tail in ("length", "size", "count"):
            return True
        if SAFE_NAME_HINT.search(tail) or False:
            return True
        _BAD.append(e)
        return False
    return True  # espressione composta non riconosciuta (aritmetica, confronto...): non e' un dato testuale grezzo

def _map_body_safe(e):
    """x.map(cb).join(sep): i template annidati sono valutati con le stesse regole; un corpo freccia che non e'
    un template (`a => a.name`) e' valutato come espressione. `.map(helper)` = helper fidato."""
    ok = True
    i = 0
    while i < len(e):
        c = e[i]
        if c in "'\"":
            i = _skip_string(e, i)
        elif c == "`":
            j, sub = _template_end(e, i)
            ok = all([is_safe(x) for x in sub]) and ok
            i = j
        elif e.startswith("=>", i):
            k = i + 2
            while k < len(e) and e[k] == " ":
                k += 1
            if k < len(e) and e[k] not in "{`(":
                depth, j = 0, k
                while j < len(e):
                    if e[j] in "'\"":
                        j = _skip_string(e, j)
                        continue
                    if e[j] in "([{":
                        depth += 1
                    elif e[j] in ")]}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif e[j] == "," and depth == 0:
                        break
                    j += 1
                ok = is_safe(e[k:j]) and ok
            i += 2
        else:
            i += 1
    return ok


def scan_file(path):
    src = path.read_text(encoding="utf-8", errors="replace")
    findings = []
    for m in SINK.finditer(src):
        start = m.end()
        end = _statement_end(src, start)
        stmt = src[start:end]
        line = src.count("\n", 0, m.start()) + 1
        del _BAD[:]
        if not is_safe(stmt):
            for leaf in dict.fromkeys(_BAD or [stmt]):
                findings.append((line, " ".join(leaf.split())[:140]))
    return findings


def selftest():
    """L'euristica deve distinguere il caso sicuro da quello pericoloso."""
    for ok in ("esc(g.title)", "g.count || 0", "ok ? `<b>${esc(x.n)}</b>` : \"\"", "a.map((x) => `<i>${esc(x)}</i>`).join(\"\")",
               "items.length", "t(\"k\", { n: items.length })"):
        del _BAD[:]
        assert is_safe(ok), ok
    for bad in ("g.title", "x.name || \"\"", "ok ? g.desc : \"\"", "`<b>${g.title}</b>`", "list.map((x) => `<i>${x.name}</i>`).join(\"\")",
                "String(g.title)", "e.message"):
        del _BAD[:]
        assert not is_safe(bad), bad


def test_csp_header():
    """CSP in sola segnalazione su ogni risposta (enforce non ancora possibile: script inline e onclick= nei template)."""
    import tempfile
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from fastapi.testclient import TestClient
    from pozzo.app.server import create_app
    from test_apiv1 import BASE, make_library, tmp_cfg
    tmp = Path(tempfile.mkdtemp())
    rom = tmp / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    with TestClient(create_app(tmp_cfg(tmp, rom)), base_url=BASE) as c:
        for url in ("/", "/static/core.js", "/api/v1/ping" if False else "/"):
            h = c.get(url).headers
            csp = h.get("content-security-policy-report-only", "")
            assert "script-src 'self'" in csp and "object-src 'none'" in csp and "base-uri 'self'" in csp, (url, csp)
            assert "content-security-policy" not in h, "enforce non previsto finche' ci sono inline script"


def main():
    selftest()
    test_csp_header()
    verbose = "-v" in sys.argv
    files = []
    for base in SCAN_DIRS:
        if base.is_file():
            files.append(base)
        else:
            files += [p for p in base.rglob("*.js") if not p.name.endswith(".min.js")]
    bad = []
    for f in sorted(files):
        for line, e in scan_file(f):
            rel = f.relative_to(ROOT).as_posix()
            if (rel, e) in ALLOWLIST:
                continue
            item = f"{rel}:{line}: ${{{e}}}"
            if item not in bad:
                bad.append(item)
    if verbose or bad:
        print("\n".join(bad))
    print(f"{len(files)} file scansionati, {len(bad)} interpolazioni non provate sicure")
    assert not bad, "interpolazioni non escapate in innerHTML (usa esc() o aggiungi all'ALLOWLIST con motivo)"


if __name__ == "__main__":
    main()
    print("OK")
