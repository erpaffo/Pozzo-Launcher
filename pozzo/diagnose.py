"""«Perché non parte?»: controlli senza effetti collaterali (nessun processo avviato, nessuna scrittura)."""
from __future__ import annotations

from pathlib import Path

from . import bios as BI, platforms as P
from .library import launcher as L

NOPE = ("", "")


def _file(cfg, game: dict, profile, st: dict):
    plat = P.PLATFORMS.get(game.get("platform"))
    files = [Path(f) for f in game.get("files") or []]
    if not files:
        return False, "Nessun file registrato per questo gioco.", "Riscansiona la libreria dalle Impostazioni."
    path = next((f for f in files if f.exists()), None)
    if not path:
        return False, f"File non trovato: {files[0]} (disco scollegato o file spostato?).", f"Ricollega il disco o riscansiona la cartella {files[0].parent}."
    st["path"] = path
    if path.is_file():
        if path.stat().st_size == 0:
            return False, f"Il file {path.name} è vuoto (0 byte).", "Scaricalo o copialo di nuovo."
        try:
            with open(path, "rb") as f:
                f.read(1)
        except OSError as e:
            return False, f"Il file {path.name} non è leggibile: {e}.", "Controlla i permessi o che non sia in uso da un altro programma."
        if plat and path.suffix.lower().lstrip(".") not in plat.all_exts:
            return False, f"L'estensione {path.suffix or '(nessuna)'} non è supportata per {plat.name}.", "Formati accettati: " + ", ".join(plat.all_exts) + "."
    return True, "", ""


def _plan(cfg, game: dict, profile, st: dict):
    plat = P.PLATFORMS.get(game.get("platform"))
    if not plat:
        return False, f"Console sconosciuta: {game.get('platform')}.", "Controlla la cartella in cui si trova il gioco."
    st["plat"] = plat
    try:
        pl = L.plan(cfg, plat, profile)
    except L.LaunchError as e:
        return False, str(e), "Correggi il profilo del gioco (eseguibile o emulatore) oppure eliminalo."
    if pl:
        st["pl"] = pl
        return True, "", ""
    over = cfg.launch.get(plat.id, {})
    emu = over.get("emulator")
    presets = L.PRESETS.get(plat.id, [])
    if emu:
        exe = over.get("exe") or cfg.emulators.get(emu)
        if not exe:
            return False, f"Per {plat.name} hai scelto {emu} ma manca il suo percorso.", "Apri Impostazioni › Emulatori e clicca Installa (o indica l'eseguibile)."
        if not Path(exe).exists():
            return False, f"L'eseguibile di {emu} non esiste: {exe}.", "Apri Impostazioni › Emulatori e clicca Installa, oppure correggi il percorso."
        if emu == L.RA:
            core = over.get("core") or L.default_core(plat.id, emu)
            return False, f"Manca il core RetroArch «{core}».", "In RetroArch: Carica core › Scarica un core, oppure scegline un altro in Impostazioni › Emulatori."
    cand = ", ".join(dict.fromkeys(e for e, _ in presets)) or "nessun preset"
    return False, f"Nessun emulatore utilizzabile per {plat.name} (candidati: {cand}).", "Apri Impostazioni › Emulatori e clicca Installa."


def _exe(cfg, game: dict, profile, st: dict):
    pl = st.get("pl")
    if not pl:
        return False, "Senza un emulatore scelto non si può verificare l'eseguibile.", "Risolvi prima il controllo sull'emulatore."
    if not Path(pl["exe"]).is_file():
        return False, f"L'eseguibile {pl['exe']} non esiste.", "Apri Impostazioni › Emulatori e clicca Installa."
    if pl["core"] and not L._core_path(cfg, pl["core"]).is_file():
        return False, f"Manca il core {pl['core']} in {L._core_path(cfg, pl['core'])}.", "In RetroArch scarica il core da Carica core › Scarica un core."
    return True, "", ""


def _bios(cfg, game: dict, profile, st: dict):
    r = BI.check(game.get("platform") or "")
    bad = [i for i in r["items"] if i["required"] and not i["ok"]]
    if not bad:
        return True, "", ""
    i = bad[0]
    folder = BI._cartelle(r["console"], None)
    dove = f" in {folder[0]}" if folder else ""
    if not i["found"]:
        return False, f"Manca il BIOS {i['file']}{dove}.", f"Copia {i['file']} nella cartella dei BIOS" + (f" ({i['help_url']})" if i.get("help_url") else "") + "."
    return False, f"Il BIOS {i['file']} non è valido: {i.get('motivo') or 'hash non riconosciuto'}.", "Sostituiscilo con il dump corretto."


def command_line(cfg, plat, pl: dict, path: Path) -> list[str]:
    """Comando che _run_emu userebbe (senza fast-copy, estrazione e argomenti una tantum)."""
    target = L.resolve_target(plat, path)
    core = str(L._core_path(cfg, pl["core"])) if pl["core"] else ""
    return [pl["exe"], *[a.replace("{rom}", str(target)).replace("{core}", core) for a in pl["args"]]]


def _args(cfg, game: dict, profile, st: dict):
    pl, path = st.get("pl"), st.get("path")
    if not pl or not path:
        return False, "Comando non costruibile: mancano il file del gioco o l'emulatore.", "Risolvi i controlli precedenti."
    cmd = command_line(cfg, st["plat"], pl, path)
    st["cmd"] = cmd
    line = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    left = [a for a in cmd[1:] if "{" in a and "}" in a]
    if left:
        return False, f"Nel comando restano segnaposto non risolti ({', '.join(left)}): {line}", "Correggi gli argomenti in Impostazioni › Emulatori."
    miss = [a for a in cmd[1:] if (a.startswith(("/", "\\")) or ":\\" in a or ":/" in a) and not Path(a).exists()]
    if miss:
        return False, f"Percorso inesistente negli argomenti: {miss[0]}. Comando: {line}", "Verifica il file o il core indicato."
    return True, "", ""


def _crash(cfg, game: dict, profile, st: dict):
    c = L.last_crash(cfg, game.get("key") or "")
    if not c:
        return True, "", ""
    log = "\n".join((c.get("log") or "").strip().splitlines()[-5:])
    causa = f"Ultimo avvio chiuso dopo {c.get('duration')} s con codice {c.get('code')}." + (f" Ultime righe del log:\n{log}" if log else "")
    alt = None
    if st.get("plat"):
        try:
            a = L.plan(cfg, st["plat"], profile, skip=L.cand_id(st["pl"])) if st.get("pl") else None
            alt = a and L.cand_id(a) != L.cand_id(st["pl"]) and L.cand_id(a)
        except Exception:  # noqa: BLE001
            alt = None
    return False, causa, f"Prova l'alternativa {alt} (Gioca con… dopo un crash)." if alt else "Prova un altro core o emulatore, o controlla il log qui sopra."


def _pc(cfg, game: dict, profile, st: dict):
    if not game.get("store"):
        return True, "", ""
    d = game.get("install_dir") or ""
    if not game.get("installed"):
        return False, "Il gioco non risulta installato.", "Usa «Installa»."
    if d and not Path(d).is_dir():
        return False, f"La cartella di installazione non esiste: {d}.", "Reinstalla il gioco o ricollega il disco."
    la = game.get("launch") or {}
    t = la.get("target")
    if not t:
        return False, "Nessun comando di avvio registrato.", "Reinstalla o riscansiona il gioco."
    if la.get("type") != "uri" and not Path(t).exists() and Path(t).name.lower() not in L.Launcher.LAUNCHER_EXES:
        return False, f"Eseguibile non trovato: {t}.", "Reinstalla il gioco o scegli l'eseguibile giusto."
    return True, "", ""


def _checks(game: dict) -> list:
    pc = bool(game.get("store"))
    if pc:
        return [("Cartella e eseguibile del gioco", _pc)]
    return [("File del gioco", _file), ("Emulatore scelto", _plan), ("Eseguibile dell'emulatore", _exe), ("BIOS richiesti", _bios),
            ("Argomenti di avvio", _args), ("Ultimo crash", _crash)]


def diagnose(cfg, game: dict, profile: dict | None = None) -> dict:
    st: dict = {}
    out = []
    for nome, fn in _checks(game):
        try:
            ok, causa, rimedio = fn(cfg, game, profile, st)
        except Exception as e:  # noqa: BLE001 - la diagnostica non deve mai sollevare
            ok, causa, rimedio = False, f"{type(e).__name__}: {e}", "Controlla i log dell'applicazione."
        out.append({"nome": nome, "ok": bool(ok), "causa": causa, "rimedio": rimedio})
    prob = next((i for i, c in enumerate(out) if not c["ok"]), None)
    return {"checks": out, "probabile": prob, "ok": prob is None}
