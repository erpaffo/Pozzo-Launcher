import re, sys, json, pathlib
ROOT = pathlib.Path("C:/Users/paffe/OneDrive/Desktop/GameScraper/pozzo/app/static")
CATP = pathlib.Path("C:/Users/paffe/OneDrive/Desktop/GameScraper/scratch/i18n/h.it.json")
LOC = re.compile(r'toLocale(?:Date|Time)?String\("it"')

def fixloc(x):
    return LOC.sub(lambda m: m.group(0).replace('"it"', 'GSI18n.lang'), x)

def apply(rel, pairs, cat):
    p = ROOT / rel
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    s = fixloc(raw.replace("\r\n", "\n"))
    pairs = [(fixloc(o.replace(chr(92) + chr(34), chr(34))), n.replace(chr(92) + chr(34), chr(34)), c) for o, n, c in pairs]
    for old, new, cnt in pairs:
        n = s.count(old)
        if n != cnt:
            sys.exit(f"{rel}: count {n} != {cnt}: {old[:80]!r}")
        s = s.replace(old, new)
    s = fixloc(s)
    p.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))
    cur = json.loads(CATP.read_text("utf-8")) if CATP.exists() else {}
    for k, v in cat.items():
        if k in cur and cur[k] != v:
            sys.exit(f"dup key with different value: {k}")
        cur[k] = v
    CATP.write_text(json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(rel, "ok", len(pairs), "replacements,", len(cat), "keys")
