"""Genera pozzo/data/bios_hashes.json dagli hash ufficiali di libretro (dat/System.dat).

E' l'unico punto in cui si scarica qualcosa: l'app e i test leggono il JSON gia' generato. Si tiene solo
cio' che `pozzo/bios.py` chiede davvero (nomi di REQUISITI), con dimensione, crc, md5 e sha1 del DAT.

Uso: python tools/update_bios_hashes.py [--dat System.dat]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

URL = "https://raw.githubusercontent.com/libretro/libretro-database/master/dat/System.dat"
OUT = ROOT / "pozzo" / "data" / "bios_hashes.json"

GAME = re.compile(r'^\s*game \(')
COMMENT = re.compile(r'^\s*comment "(.*)"\s*$')
VERSION = re.compile(r"^\s*version (\S+)\s*$", re.M)
ROM = re.compile(r'rom \( name (?:"([^"]+)"|(\S+)) size (\d+)(?: crc ([0-9A-Fa-f]+))?(?: md5 ([0-9A-Fa-f]+))?'
                 r'(?: sha1 ([0-9A-Fa-f]+))? \)')


def parse_dat(text: str) -> list[dict]:
    """Righe `rom ( ... )` del DAT, con il gruppo (`comment`) in cui compaiono.

    Il nome puo' avere un prefisso di cartella ("dc/dc_boot.bin"): si tiene anche il nome semplice, perche'
    e' quello che si trova nella cartella dei BIOS.
    """
    out, gruppo = [], ""
    for line in text.splitlines():
        if GAME.match(line):
            gruppo = ""
            continue
        m = COMMENT.match(line)
        if m:
            gruppo = m.group(1)
            continue
        m = ROM.search(line)
        if not m:
            continue
        nome = (m.group(1) or m.group(2)).replace("\\", "/")
        out.append({"group": gruppo, "path": nome, "name": nome.rsplit("/", 1)[-1].lower(),
                    "size": int(m.group(3)), "crc": (m.group(4) or "").upper(),
                    "md5": (m.group(5) or "").lower(), "sha1": (m.group(6) or "").lower()})
    return out


def version_of(text: str) -> str:
    m = VERSION.search(text)
    return m.group(1) if m else ""


def build(text: str, wanted: list[str]) -> tuple[dict, int]:
    """{nome: {size, crc, md5, sha1}} per i soli nomi richiesti; ritorna anche quante varianti si sono perse."""
    voluti = {n.lower() for n in wanted}
    files, doppioni = {}, 0
    for rec in parse_dat(text):
        if rec["name"] not in voluti or not rec["sha1"]:
            continue
        if rec["name"] in files:  # shortcut: varianti regionali con lo stesso nome, si tiene la prima
            doppioni += 1
            continue
        files[rec["name"]] = {"size": rec["size"], "crc": rec["crc"], "md5": rec["md5"], "sha1": rec["sha1"]}
    return files, doppioni


def wanted_names() -> list[str]:
    """I nomi che pozzo/bios.py elenca: sono i soli che vale la pena tenere nel JSON."""
    from pozzo import bios

    return [nome for spec in bios.REQUISITI.values() for nome, _obbligatorio, _gruppo in spec["files"]
            if "." in nome]  # «firmware» e' una cartella, non ha hash


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dat", help="usa un System.dat gia' scaricato invece della rete")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)

    if args.dat:
        text = Path(args.dat).read_text(encoding="utf-8", errors="replace")
    else:
        import httpx
        r = httpx.get(URL, timeout=60, follow_redirects=True)
        r.raise_for_status()
        text = r.text

    nomi = wanted_names()
    files, doppioni = build(text, nomi)
    payload = {"fonte": URL if not args.dat else str(args.dat), "versione": version_of(text),
               "generato": date.today().isoformat(), "files": files}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    senza = sorted({n.lower() for n in nomi} - set(files))
    print(f"{out}: {len(files)} file, versione DAT {payload['versione'] or '?'}"
          + (f", {doppioni} varianti doppie ignorate" if doppioni else ""))
    if senza:
        print("senza hash nel DAT (restano «hash non noto»): " + ", ".join(senza))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
