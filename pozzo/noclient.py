"""Epic, GOG e Amazon senza i client ufficiali: usa le stesse utility open source di Heroic.

legendary (Epic), gogdl (GOG) e nile (Amazon) sono programmi di terzi sotto GPL: non sono inclusi in Pozzo, si
scaricano dalle loro release GitHub alla prima richiesta (come gli emulatori, vedi emuinstall.py) in
<dati>/noclient/bin. Ognuno lavora in una cartella di configurazione solo di Pozzo (variabili d'ambiente
LEGENDARY_CONFIG_PATH / NILE_CONFIG_PATH, per gogdl --auth-config-path): niente collisioni con un Heroic gia' installato.

Qui: scelta del file di release, file di accesso scritti dal token che Pozzo ha gia' (Epic, GOG), comandi, lettura
dell'avanzamento, giochi installati. Lo scarico vero e' downloads/engines/cli.py.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config as C
from . import ports as PT
from . import profilecfg as PC

STORES = {  # store -> (repo GitHub, nome del programma)
    "epic": ("derrod/legendary", "legendary"),
    "gog": ("Heroic-Games-Launcher/heroic-gogdl", "gogdl"),
    "amazon": ("imLinguin/nile", "nile"),
}
GOG_CLIENT_ID = "46899977096215655"  # lo stesso di stores/gog.py (e di gogdl): il suo refresh token vale per entrambi
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ---------------------------------------------------------------- cartelle e programmi

def root(cfg) -> Path:
    return C.settings_path(cfg).parent / "noclient"


def default_games_dir() -> Path:
    return Path.home() / "Games" / "Pozzo"


def exe_path(cfg, store: str) -> Path:
    return root(cfg) / "bin" / (STORES[store][1] + (".exe" if sys.platform == "win32" else ""))


def available(cfg, store: str) -> bool:
    return exe_path(cfg, store).is_file()


def version(cfg, store: str) -> str:
    try:
        return exe_path(cfg, store).with_suffix(".version").read_text("utf-8").strip()
    except OSError:
        return ""


def pick_asset(store: str, assets: list[dict], plat: str | None = None, machine: str | None = None) -> dict | None:
    """File della release per questo sistema: legendary_windows_x64.exe, gogdl_linux_x86_64, nile_macOS_arm64..."""
    plat, machine = plat or sys.platform, (machine or platform.machine()).lower()
    osw = "windows" if plat.startswith("win") else "macos" if plat == "darwin" else "linux"
    arm = machine in ("arm64", "aarch64")
    name = STORES[store][1]
    c = [a for a in assets if a["name"].lower().startswith(name + "_") and osw in a["name"].lower()
         and not a["name"].lower().endswith((".zip", ".sha256", ".sig"))]

    def arch(a):
        n = a["name"].lower()
        return "arm64" if "arm64" in n else "x64"
    for want in (("arm64", "x64") if arm else ("x64",)):  # arm senza file suo: l'x64 gira in emulazione (Windows)
        for a in c:
            if arch(a) == want:
                return a
    return None


def install_cli(cfg, store: str, progress=None) -> str:
    """Scarica l'ultima release del programma di `store` (sovrascrive la versione precedente); ritorna la versione."""
    repo, name = STORES[store]
    rels = [r for r in PT.releases("github", repo, PT._token(cfg)) if not r["prerelease"]]
    got = next(((r, a) for r in rels if (a := pick_asset(store, r["assets"]))), None)
    if not got:
        raise RuntimeError(f"nessun file per questo sistema nelle release di {repo}")
    rel, asset = got
    dest = exe_path(cfg, store)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    try:
        PT._download(asset["url"], tmp, progress, PT._token(cfg))
        if asset.get("sum") and PT._sha256(tmp) != asset["sum"]:
            raise RuntimeError(f"{name}: il file scaricato non corrisponde al checksum della release")
        tmp.chmod(0o755)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    dest.with_suffix(".version").write_text(rel["tag"], "utf-8")
    return rel["tag"]


# ---------------------------------------------------------------- accesso

def _cfg_dir(cfg, store: str) -> Path:
    return root(cfg) / {"epic": "legendary", "gog": "gogdl", "amazon": "nile"}[store]


def env(cfg, store: str | None = None) -> dict:
    return {**os.environ, "LEGENDARY_CONFIG_PATH": str(_cfg_dir(cfg, "epic")),
            "NILE_CONFIG_PATH": str(_cfg_dir(cfg, "amazon"))}


def setup_env(cfg) -> None:
    """Variabili d'ambiente anche in questo processo: l'avvio di un gioco passa dal launcher, che lancia il
    programma senza ambiente suo."""
    os.environ.update({k: v for k, v in env(cfg).items() if k.endswith("_CONFIG_PATH")})


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def write_epic_auth(cfg, a: dict) -> bool:
    """user.json di legendary dal token di Pozzo (stesso client Epic): access token scaduto, quindi legendary
    rinnova da solo con il refresh token. False se l'account non e' collegato."""
    if not a.get("refresh_token"):
        return False
    d = _cfg_dir(cfg, "epic")
    d.mkdir(parents=True, exist_ok=True)
    exp = float(a.get("refresh_expires") or time.time() + 7 * 86400)
    (d / "user.json").write_text(json.dumps({
        "access_token": "", "expires_in": 0, "expires_at": _iso(0), "token_type": "bearer",
        "refresh_token": a["refresh_token"], "refresh_expires": max(int(exp - time.time()), 0),
        "refresh_expires_at": _iso(exp), "account_id": a.get("account_id") or "",
        "client_id": "34a02cf8f4414e29b15921876da36f9a", "internal_client": True, "client_service": "launcher",
        "displayName": a.get("displayName") or "", "app": "launcher", "in_app_id": a.get("account_id") or ""}), "utf-8")
    return True


def write_gog_auth(cfg, a: dict) -> Path | None:
    """File --auth-config-path di gogdl: {client_id: token}; loginTime 0 = scaduto, gogdl rinnova col refresh token."""
    if not a.get("refresh_token"):
        return None
    f = _cfg_dir(cfg, "gog") / "auth.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({GOG_CLIENT_ID: {
        "access_token": "", "refresh_token": a["refresh_token"], "expires_in": 0, "loginTime": 0,
        "token_type": "bearer", "scope": "", "session_id": "", "user_id": a.get("user_id") or ""}}), "utf-8")
    return f


def prepare(cfg, store: str) -> None:
    """Prima di ogni esecuzione: il token del profilo attivo diventa il file di accesso del programma."""
    if store == "epic" and not write_epic_auth(cfg, PC.get(cfg, "epic", {})):
        raise RuntimeError("collega prima l'account Epic (Impostazioni > Account)")
    if store == "gog" and not write_gog_auth(cfg, PC.get(cfg, "gog", {})):
        raise RuntimeError("collega prima l'account GOG (Impostazioni > Account)")
    if store == "amazon" and not amazon_user(cfg):
        raise RuntimeError("collega prima l'account Amazon (Impostazioni > Account)")


def sync_back(cfg, store: str) -> None:
    """Dopo l'esecuzione: se il programma ha rinnovato il token (puo' cambiare il refresh token) lo riprende Pozzo."""
    try:
        if store == "epic":
            d = json.loads((_cfg_dir(cfg, "epic") / "user.json").read_text("utf-8"))
            tok = d.get("refresh_token")
            exp = d.get("refresh_expires_at") or ""
            a = PC.get(cfg, "epic", {})
            if tok and tok != a.get("refresh_token"):
                PC.set(cfg, "epic", {**a, "refresh_token": tok, "refresh_expires": datetime.strptime(
                    exp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp() if exp else a.get("refresh_expires")})
        elif store == "gog":
            d = json.loads((_cfg_dir(cfg, "gog") / "auth.json").read_text("utf-8")).get(GOG_CLIENT_ID) or {}
            a = PC.get(cfg, "gog", {})
            if d.get("refresh_token") and d["refresh_token"] != a.get("refresh_token"):
                PC.set(cfg, "gog", {**a, "refresh_token": d["refresh_token"], "time": time.time()})
    except (OSError, ValueError):
        pass  # file mancante o a meta': resta il token che Pozzo ha


def amazon_user(cfg) -> str:
    """Nome dell'account collegato a nile ('' se nessuno)."""
    try:
        return json.loads((_cfg_dir(cfg, "amazon") / "nile" / "current_user.json").read_text("utf-8")).get("name") or "?"
    except (OSError, ValueError):
        return ""


def amazon_login_data(cfg) -> dict:
    """`nile auth --login --non-interactive`: {url, client_id, code_verifier, serial}. Serve nile gia' scaricato."""
    r = subprocess.run([str(exe_path(cfg, "amazon")), "auth", "--login", "--non-interactive"], env=env(cfg),
                       capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    for line in r.stdout.splitlines():
        if line.lstrip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("nile non ha dato l'indirizzo di accesso: " + (r.stderr or r.stdout)[-200:])


def amazon_code(text: str) -> str:
    """Codice dall'indirizzo su cui Amazon rimanda dopo l'accesso (openid.oa2.authorization_code=...)."""
    m = re.search(r"authorization_code=([^&\s#]+)", unquote(text or ""))
    return m.group(1) if m else (text or "").strip()


def amazon_register(cfg, data: dict, redirect: str) -> str:
    code = amazon_code(redirect)
    if not code:
        raise RuntimeError("Indirizzo di accesso Amazon senza codice")
    r = subprocess.run([str(exe_path(cfg, "amazon")), "register", "--code", code, "--client-id", data["client_id"],
                        "--code-verifier", data["code_verifier"], "--serial", data["serial"]], env=env(cfg),
                       capture_output=True, text=True, timeout=90, creationflags=NO_WINDOW)
    user = amazon_user(cfg)
    if not user:
        raise RuntimeError("Accesso Amazon non riuscito: " + (r.stderr or r.stdout)[-200:])
    return user


# ---------------------------------------------------------------- giochi installati

def epic_app(install_uri: str) -> str:
    """Nome interno Epic (appName) dall'indirizzo d'installazione com.epicgames.launcher://apps/ns%3Acid%3Aapp."""
    return unquote(urlparse(install_uri).path.rsplit("/", 1)[-1]).split(":")[-1] if install_uri else ""


def _jload(f: Path):
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def installed(cfg, store: str) -> dict[str, dict]:
    """{id gioco: {"path", "title", ...}} dei giochi installati dal programma. Epic: per appName; GOG/Amazon: per id."""
    out: dict[str, dict] = {}
    if store == "epic":
        d = _jload(_cfg_dir(cfg, "epic") / "installed.json")
        for k, v in (d.items() if isinstance(d, dict) else ()):
            if isinstance(v, dict) and v.get("install_path") and not v.get("is_dlc"):
                out[k] = {"path": v["install_path"], "title": v.get("title") or k, "size": v.get("install_size") or 0,
                          "version": v.get("version") or ""}
    elif store == "amazon":
        d = _jload(_cfg_dir(cfg, "amazon") / "nile" / "installed.json")
        for v in (d if isinstance(d, list) else ()):
            if isinstance(v, dict) and v.get("id") and v.get("path"):
                out[v["id"]] = {"path": v["path"], "title": v["id"], "size": v.get("size") or 0, "version": v.get("version") or ""}
    else:  # gogdl non tiene un elenco: lo scriviamo noi a scarico finito
        d = _jload(root(cfg) / "gog_installed.json")
        out = {k: v for k, v in (d.items() if isinstance(d, dict) else ()) if isinstance(v, dict) and v.get("path")}
    return {k: v for k, v in out.items() if Path(v["path"]).is_dir()}


def amazon_library(cfg) -> list[dict]:
    """[{id, title, icon}] dai giochi posseduti letti da `nile library sync` (library.json)."""
    d = _jload(_cfg_dir(cfg, "amazon") / "nile" / "library.json")
    out = []
    for g in (d if isinstance(d, list) else ()):
        p = (g or {}).get("product") or {}
        if p.get("id") and p.get("title"):
            out.append({"id": p["id"], "title": p["title"], "icon": ((p.get("productDetail") or {}).get("iconUrl") or "")})
    return out


def amazon_sync(cfg) -> None:
    subprocess.run([str(exe_path(cfg, "amazon")), "library", "sync"], env=env(cfg), capture_output=True,
                   timeout=120, creationflags=NO_WINDOW)


def launch_cmd(cfg, store: str, gid: str, rec: dict) -> dict:
    """Comando di avvio da mettere in StoreGame.launch: il programma resta processo figlio del gioco."""
    exe = str(exe_path(cfg, store))
    args = {"epic": ["launch", gid], "amazon": ["launch", gid],
            "gog": ["launch", rec["path"], gid, "--platform", gog_platform()]}[store]
    return {"type": "exe", "target": exe, "args": args, "cwd": rec["path"], "track_dir": rec["path"]}


def gog_platform() -> str:
    return "windows" if sys.platform == "win32" else "osx" if sys.platform == "darwin" else "linux"


def record_gog(cfg, gid: str, path: str, title: str) -> None:
    f = root(cfg) / "gog_installed.json"
    d = _jload(f)
    d = d if isinstance(d, dict) else {}
    d[gid] = {"path": path, "title": title, "platform": gog_platform()}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d), "utf-8")


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "game"


# ---------------------------------------------------------------- comandi

def command(cfg, store: str, action: str, gid: str, o: dict | None = None) -> list[str]:
    """Riga di comando per install | update | verify (le tre durano e passano dalla coda dei download).
    o: path (cartella dei giochi), title, with_dlcs (bool), dlcs (id DLC GOG), threads."""
    o = o or {}
    exe = str(exe_path(cfg, store))
    base = o.get("path") or str(default_games_dir())
    if store == "epic":
        cmd = {"install": ["install", gid, "--base-path", base, "--skip-dlcs" if not o.get("with_dlcs") else "--with-dlcs"],
               "update": ["update", gid, "--skip-dlcs"], "verify": ["repair", gid]}[action]
        return [exe, "-y", *cmd]
    if store == "amazon":
        cmd = {"install": ["install", gid, "--base-path", base], "update": ["update", gid], "verify": ["verify", gid]}[action]
        return [exe, *cmd]
    rec = installed(cfg, "gog").get(gid) or {}
    path = rec.get("path") or str(Path(base) / _safe(o.get("title") or gid))
    cmd = {"install": "download", "update": "update", "verify": "repair"}[action]
    argv = [exe, "--auth-config-path", str(_cfg_dir(cfg, "gog") / "auth.json"), cmd, gid, "--platform", gog_platform(),
            "--path", path, "--lang", o.get("lang") or "en-US"]
    argv.append("--with-dlcs" if o.get("with_dlcs") else "--skip-dlcs")
    if o.get("dlcs"):
        argv += ["--dlcs", ",".join(map(str, o["dlcs"]))]
    return argv


def run_quick(cfg, argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(argv, env=env(cfg), capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WINDOW, encoding="utf-8", errors="replace")


def uninstall(cfg, store: str, gid: str) -> None:
    """Toglie il gioco e i suoi file (solo cartelle di giochi installati da qui)."""
    rec = installed(cfg, store).get(gid)
    if not rec:
        raise RuntimeError("gioco non installato da Pozzo")
    if store == "gog":
        shutil.rmtree(rec["path"], ignore_errors=True)
        f = root(cfg) / "gog_installed.json"
        d = _jload(f) or {}
        d.pop(gid, None)
        f.write_text(json.dumps(d), "utf-8")
        return
    r = run_quick(cfg, [str(exe_path(cfg, store)), *(["-y"] if store == "epic" else []), "uninstall", gid])
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout)[-300:] or "disinstallazione non riuscita")


def dlc_list(cfg, store: str, gid: str) -> list[dict]:
    """DLC posseduti e installabili: [{"id", "title"}]. Amazon non ne ha."""
    if store == "epic":
        r = run_quick(cfg, [str(exe_path(cfg, "epic")), "info", gid, "--json"], 120)
        d = _json_tail(r.stdout)
        return [{"id": x["app_name"], "title": x.get("title") or x["app_name"]}
                for x in ((d.get("game") or {}).get("owned_dlc") or []) if x.get("app_name") and x.get("installable")]
    if store == "gog":
        r = run_quick(cfg, [str(exe_path(cfg, "gog")), "--auth-config-path", str(_cfg_dir(cfg, "gog") / "auth.json"),
                            "info", gid, "--platform", gog_platform()], 120)
        return [{"id": str(x["id"]), "title": x.get("title") or x.get("name") or str(x["id"])}
                for x in (_json_tail(r.stdout).get("dlcs") or []) if isinstance(x, dict) and x.get("id")]
    return []


def _json_tail(out: str) -> dict:
    out = out or ""
    try:
        return json.loads(out[out.index("{"):])
    except ValueError:
        pass
    for line in reversed(out.splitlines()):
        if line.lstrip().startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


def sync_saves(cfg, store: str, gid: str, direction: str = "sync") -> str:
    """Salvataggi nel cloud (solo Epic): sync | download | upload. Ritorna l'ultima riga di testo del programma."""
    if store != "epic":
        raise RuntimeError("salvataggi nel cloud disponibili solo per Epic")
    flag = {"download": ["--skip-upload"], "upload": ["--skip-download"], "sync": []}[direction]
    r = run_quick(cfg, [str(exe_path(cfg, "epic")), "-y", "sync-saves", gid, *flag], 600)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-300:] or "sincronizzazione non riuscita")
    return ((r.stderr or r.stdout).strip().splitlines() or [""])[-1]


# ---------------------------------------------------------------- avanzamento

_PROG = re.compile(r"Progress:\s*([\d.]+)\s*%?\s*(?:\(?(\d+)/(\d+)\)?)?")
_SIZE = re.compile(r"Download size:\s*([\d.]+)\s*MiB")
_RATE = re.compile(r"Download\s*-\s*([\d.]+)\s*MiB/s")
_ETA = re.compile(r"ETA:\s*(\d+):(\d+):(\d+)")


def parse_line(store: str, line: str) -> dict:
    """Una riga di log -> {"pct", "done", "total", "size", "speed", "eta"} (solo le chiavi presenti).
    legendary conta chunk (x/y), gogdl e nile byte: i byte valgono solo per questi due."""
    out: dict = {}
    if m := _PROG.search(line):
        out["pct"] = float(m[1])
        if m[3] and store != "epic" and int(m[3]) > 0:
            out["done"], out["total"] = int(m[2]), int(m[3])
        if e := _ETA.search(line):
            out["eta"] = int(e[1]) * 3600 + int(e[2]) * 60 + int(e[3])
    if m := _SIZE.search(line):
        out["size"] = int(float(m[1]) * 1048576)
    if m := _RATE.search(line):
        out["speed"] = float(m[1]) * 1048576
    return out


def finished(cfg, store: str, gid: str, action: str, o: dict) -> None:
    """Scarico riuscito: per GOG si registra il gioco (gli altri due lo scrivono da soli); i token rinnovati tornano a Pozzo."""
    sync_back(cfg, store)
    if store == "gog" and action == "install":
        path = (installed(cfg, "gog").get(gid) or {}).get("path") or str(
            Path(o.get("path") or default_games_dir()) / _safe(o.get("title") or gid))
        record_gog(cfg, gid, path, o.get("title") or gid)
