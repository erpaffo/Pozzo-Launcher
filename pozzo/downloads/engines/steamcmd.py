"""Giochi Steam senza il client, con SteamCMD (lo strumento da riga di comando di Valve).

SteamCMD si scarica al primo uso nella cartella dati dell'app. La password non viene mai salvata: serve solo per il
primo accesso (`+login utente password codice`), poi SteamCMD tiene da solo la sessione (config/ e file ssfn) e gli
accessi successivi usano `+login utente`. Pozzo ricorda solo il nome utente (account.json).
Il download e' un task della coda (type "steamcmd"): pausa e annulla terminano il processo, la ripresa e' gratuita
perche' `app_update ... validate` riparte dai file gia' scritti.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ... import i18n as I

URLS = {"win32": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip",
        "darwin": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_osx.tar.gz",
        "linux": "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"}
EXE = "steamcmd.exe" if sys.platform == "win32" else "steamcmd.sh"
NOWIN = 0x08000000 if sys.platform == "win32" else 0
_PROGRESS = re.compile(r"Update state \(0x([0-9a-f]+)\) ([^,]+), progress: ([\d.]+) \((\d+) / (\d+)\)")
_SUCCESS = re.compile(r"Success! App '(\d+)' fully installed")
_SPLIT = re.compile(rb"[\r\n]+")
_USER = re.compile(r"^[\w.\-]{2,64}$")
_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def home(cfg) -> Path:
    return Path(cfg.cache) / "steamcmd"


def exe(cfg) -> Path:
    return home(cfg) / EXE


# ------------------------------------------------------------------ comandi (nessuna password nelle righe di log)
def login_args(user: str, password: str = "", guard: str = "") -> list[str]:
    return ["+login", user, *([password] if password else []), *([guard] if password and guard else [])]


def mask(cmd: list[str]) -> str:
    """La riga di comando come si puo' scrivere nei log: password e codice Steam Guard (dopo l'utente) nascosti."""
    out, hide = [], False
    for i, a in enumerate(cmd):
        hide = hide and not a.startswith("+")
        out.append("***" if hide and i > 0 and cmd[i - 1] != "+login" else a)
        hide = hide or a == "+login"
    return " ".join(out)


def install_cmd(steamcmd: Path, folder: str, user: str, appid: str) -> list[str]:
    return [str(steamcmd), "+force_install_dir", folder, *login_args(user), "+app_update", str(appid), "validate", "+quit"]


def parse_progress(line: str):
    """(codice, nome, percentuale, byte fatti, byte totali) da «Update state (0x61) downloading, progress: …», o None."""
    m = _PROGRESS.search(line)
    return (m[1], m[2].strip(), float(m[3]), int(m[4]), int(m[5])) if m else None


def classify(text: str) -> str | None:
    """Esito di un accesso dall'output: guard (serve il codice), password, ratelimit, nocache (sessione assente)."""
    t = text.lower()
    if any(k in t for k in ("two-factor code mismatch", "invalid login auth code", "incorrect code")):
        return "guard_bad"
    if any(k in t for k in ("steam guard code", "two-factor code", "account logon denied", "enter the current code")):
        return "guard"
    if "invalid password" in t:
        return "password"
    if "rate limit" in t or "too many login failures" in t:
        return "ratelimit"
    if "cached credentials not found" in t:
        return "nocache"
    return None


# ------------------------------------------------------------------ SteamCMD: scarico e account
def ensure(cfg, say=lambda m: None) -> Path:
    """Scarica SteamCMD se manca e gli lascia fare il primo aggiornamento di se' stesso (parte da solo, poi esce)."""
    from ... import ports as PT
    path = exe(cfg)
    if path.is_file() and (home(cfg) / ".ready").is_file():
        return path
    url = URLS.get(sys.platform) or URLS["linux"]
    if not path.is_file():
        say(I.tr("s.steamcmd.fetching"))
        home(cfg).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=home(cfg)) as tmp:
            arc = Path(tmp) / Path(url).name
            PT._download(url, arc, None, "")
            PT._extract(arc, Path(tmp) / "x", arc.name)
            for p in (Path(tmp) / "x").iterdir():
                shutil.move(str(p), home(cfg) / p.name)
        path.chmod(0o755)
    say(I.tr("s.steamcmd.selfUpdate"))
    # shortcut: l'aggiornamento iniziale a volte esce con codice != 0 pur riuscendo; due giri e poi si va avanti
    for _ in range(2):
        r = subprocess.run([str(path), "+quit"], cwd=home(cfg), capture_output=True, timeout=900, creationflags=NOWIN)
        if r.returncode == 0:
            (home(cfg) / ".ready").write_text("1")
            return path
    raise RuntimeError(I.tr("s.steamcmd.updateFailed"))


def _account_file(cfg) -> Path:
    return home(cfg) / "account.json"


def account(cfg) -> str:
    try:
        return json.loads(_account_file(cfg).read_text("utf-8")).get("user") or ""
    except (OSError, ValueError):
        return ""


def _session_files(cfg) -> list[Path]:
    h = home(cfg)
    return [*h.glob("ssfn*"), h / "config" / "config.vdf", h / "config" / "loginusers.vdf"]


def status(cfg) -> dict:
    user = account(cfg)
    return {"installed": exe(cfg).is_file(), "user": user,
            "logged_in": bool(user)}  # l'utente si salva solo dopo un accesso riuscito; logout() lo toglie


def logout(cfg) -> None:
    """Cancella la sessione che SteamCMD tiene in cache e il nome utente ricordato."""
    for p in [*_session_files(cfg), _account_file(cfg)]:
        p.unlink(missing_ok=True)


def _exec(cmd: list[str], on_line, holder: dict | None = None, cwd=None) -> int:
    """Esegue SteamCMD e passa ogni riga (anche quelle a «\\r» dell'avanzamento) a on_line. Ritorna il codice di uscita."""
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=NOWIN)
    if holder is not None:
        holder["p"] = p
    buf = b""
    while chunk := p.stdout.read1(4096):
        *lines, buf = _SPLIT.split(buf + chunk)
        for ln in lines:
            if ln.strip():
                on_line(ln.decode("utf-8", "replace").strip())
    if buf.strip():
        on_line(buf.decode("utf-8", "replace").strip())
    return p.wait()


def login(cfg, user: str, password: str, guard: str = "") -> dict:
    """Primo accesso (bloccante). Ritorna {"ok": True} o {"ok": False, "code": guard|guard_bad|password|ratelimit|other, "error"}.
    La password e' solo nella riga di comando di questo processo: non viene scritta da nessuna parte."""
    user = user.strip()
    if not _USER.match(user) or not password:
        return {"ok": False, "code": "other", "error": I.tr("s.steamcmd.badInput")}
    path = ensure(cfg)
    lines: list[str] = []
    scrub = lambda s: s.replace(password, "***") if password else s  # noqa: E731
    _exec([str(path), *login_args(user, password, guard.strip()), "+quit"], lambda s: lines.append(scrub(s)), cwd=home(cfg))
    text = "\n".join(lines)
    code = classify(text)
    if code is None and re.search(r"Logged in OK|Waiting for user info\.\.\.OK", text):
        _account_file(cfg).write_text(json.dumps({"user": user}), "utf-8")
        return {"ok": True}
    msgs = {"guard": "s.steamcmd.needGuard", "guard_bad": "s.steamcmd.badGuard", "password": "s.steamcmd.badPassword",
            "ratelimit": "s.steamcmd.rateLimit"}
    fail = next((ln for ln in reversed(lines) if "FAILED" in ln or "ERROR" in ln), "")
    return {"ok": False, "code": code or "other", "error": I.tr(msgs[code]) if code in msgs else (fail or I.tr("s.steamcmd.loginFailed"))}


# ------------------------------------------------------------------ download (task della coda)
def folder_for(base: str, title: str, appid: str) -> str:
    return str(Path(base).expanduser() / "SteamCMD" / (_BAD_NAME.sub("", title).strip(" .") or f"app{appid}"))


async def run(t, cfg) -> None:
    """Corpo del job: SteamCMD scarica/aggiorna l'app in t.save_path. Annullo = processo terminato."""
    appid, user = str(t.options.get("appid") or ""), t.options.get("user") or account(cfg)
    if not appid.isdigit() or not user:
        raise RuntimeError(I.tr("s.steamcmd.needLogin"))
    path = await asyncio.to_thread(ensure, cfg, t.log)
    cmd = install_cmd(path, t.save_path, user, appid)
    t.log("SteamCMD: " + mask(cmd))
    holder: dict = {}
    seen: list[str] = []

    def on_line(s: str):
        if (pr := parse_progress(s)):
            code, name, _pct, done, total = pr
            t.phase = "" if code == "61" else name
            if code == "61" and total:  # solo lo scarico: le altre fasi (verifica, commit) ripartono da zero
                t.size, t.done = total, done
        else:
            seen.append(s)
            t.log(s, "error" if "ERROR" in s else "info")

    try:
        rc = await asyncio.to_thread(_exec, cmd, on_line, holder, home(cfg))
    except asyncio.CancelledError:
        if p := holder.get("p"):
            p.terminate()  # il thread di lettura finisce da solo: i file scritti restano per la ripresa
        raise
    text = "\n".join(seen)
    if any(_SUCCESS.search(s) for s in seen):
        t.phase = ""
        t.done = t.size = max(t.size, t.done)
        return
    code = classify(text)
    if code in ("guard", "guard_bad", "password", "nocache"):
        raise RuntimeError(I.tr("s.steamcmd.needLogin"))
    err = next((s for s in reversed(seen) if "ERROR" in s or "FAILED" in s), "")
    raise RuntimeError(err or I.tr("s.steamcmd.exitCode", rc=rc))


def finish(t, mgr, ctx) -> None:
    """Scaricato: la cartella entra in libreria come gioco PC aggiunto a mano (stesso exe-picker del setup dei repack)."""
    from ..install import _exe_in
    try:
        folder = Path(t.save_path)
        game = _exe_in(folder)
        if not game:
            # shortcut: se non si trova un exe l'utente lo aggiunge a mano da «Aggiungi gioco» (la cartella e' nel log)
            raise RuntimeError(I.tr("s.steamcmd.noExe", path=str(folder)))
        mid = ctx.user.add_manual(t.name or folder.name, str(game), [], str(game.parent), "game")
        ctx._refresh_manual(mid)
        t.set_stage("library", "done")
        t.set_stage("data", "done")
        t.log(I.tr("s.steamcmd.drmWarning"), "warn")
    except Exception as e:  # noqa: BLE001 - il download e' finito: l'errore e' solo del passaggio in libreria
        t.fail_stage()
        t.log(f"{type(e).__name__}: {e}", "error")
    finally:
        t.phase = ""
        t.options["post_done"] = True
        mgr.store.save([t])
        mgr._poke()
