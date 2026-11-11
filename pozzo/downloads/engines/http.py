"""Download HTTP(S): segmenti paralleli con Range, ripresa dopo interruzione, ritentativi con attesa crescente."""
from __future__ import annotations

import asyncio
import contextlib
import re
import os
import time
from pathlib import Path
from urllib.parse import unquote, urlparse, urlsplit

import httpx

from .. import hosts
from ..task import mb

RETRIES = 5
CHUNK = 256 * 1024
MIN_SEGMENT = 2 * 1024 * 1024  # sotto questa dimensione un solo flusso basta
# link che valgono una richiesta sola: ogni richiesta in piu' (anche il controllo) dà 410 Gone
ONE_TIME = ('1fichier.com',)
URL_TTL = 6 * 3600  # secondi: un link diretto risolto si riprova alla ripresa (se e' scaduto si risolve di nuovo)


class HashMismatch(ValueError):
    """Il file scaricato non ha lo SHA-256 dichiarato dal catalogo: e' in quarantena, non in libreria."""


class Bucket:
    """Limite di banda condiviso tra tutti i flussi (byte/s, 0 = illimitato)."""

    def __init__(self):
        self.rate = 0
        self._t = time.monotonic()

    async def take(self, n: int):
        if self.rate <= 0:
            return
        self._t = max(self._t, time.monotonic()) + n / self.rate
        wait = self._t - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", unquote(name)).strip(" .")
    return name or "download"


def _filename(r: httpx.Response, url: str) -> str:
    m = re.search(r"filename\*=(?:UTF-8\x27\x27)?([^;]+)|filename=\"?([^\";]+)", r.headers.get("content-disposition", ""), re.I)
    raw = (m.group(1) or m.group(2)) if m else Path(urlparse(str(r.url) or url).path).name
    return safe_name(raw)


def _meta(r: httpx.Response, url: str) -> tuple[str, int, bool, str]:
    """(nome, dimensione, accetta Range, etag) dalla risposta del primo flusso; errore se e' una pagina HTML."""
    r.raise_for_status()
    if (r.headers.get("content-type") or "").lower().startswith("text/html"):
        host = urlparse(str(r.url) or url).hostname or ""
        raise ValueError(f"Il link è una pagina, non un file ({host}): scegli un altro provider"
                         " o apri la pagina nel browser")
    if r.status_code == 206:
        m = re.search(r"/(\d+)$", r.headers.get("content-range", ""))
        total = int(m.group(1)) if m else 0
    else:
        total = int(r.headers.get("content-length") or 0)
    return _filename(r, url), total, r.status_code == 206 and total > 0,         r.headers.get("etag") or r.headers.get("last-modified") or ""


def _coherent(segs, total: int) -> bool:
    """I segmenti salvati coprono [0, total) senza buchi e ogni cursore sta dentro il suo segmento."""
    pos = 0
    for s in segs:
        if not (isinstance(s, list) and len(s) == 3 and all(type(x) is int for x in s)
                and s[0] == pos and s[0] <= s[2] <= s[1] + 1):
            return False
        pos = s[1] + 1
    return pos == total


def _sparse(f) -> None:
    """Windows: marca il file come sparso, cosi' truncate non scrive tutti gli zeri. Mai solleva."""
    if os.name != "nt":
        return
    try:
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.DeviceIoControl(msvcrt.get_osfhandle(f.fileno()), 0x900C4, None, 0, None, 0,
                                               ctypes.byref(ctypes.c_ulong()), None)
    except Exception:
        pass


async def run(task, client: httpx.AsyncClient, bucket: Bucket, segments: int, resolve, gate=None) -> None:
    """Come _run, ma se il file non ha lo SHA-256 atteso (options["sha256"]) riparte dal prossimo link di options["mirrors"]."""
    while True:
        try:
            return await _run(task, client, bucket, segments, resolve, gate)
        except HashMismatch as e:
            alts = task.options.get("mirrors") or []
            if not alts:
                raise
            task.source = alts.pop(0)
            for k in ("url", "url_at", "part", "segs", "tag"):
                task.options.pop(k, None)
            task.size = task.done = 0
            task.log(f"{e}; provo un altro mirror ({len(alts)} rimasti)", "warn")


async def _run(task, client: httpx.AsyncClient, bucket: Bucket, segments: int, resolve, gate=None) -> None:
    """Scarica `task` fino alla fine. Lo stato per riprendere sta in task.options (segs, tag, url): il manager lo salva."""
    url = task.options.get("url")
    gated = False  # gate (coda per lo scaricamento) una volta sola in tutto run
    if url and time.time() - float(task.options.get("url_at") or 0) < URL_TTL:
        # ripresa: il link diretto di prima evita di rifare tutti i passaggi (pubblicita', pagina dell'host...)
        task.log("Riprovo il link già risolto")
        try:
            if gate:
                gated = True
                await gate()
            return await _fetch(task, client, bucket, segments, url, time.time())
        except HashMismatch:
            raise
        except (httpx.HTTPStatusError, httpx.TransportError, ValueError) as e:
            task.log(f"Link di prima non più valido ({type(e).__name__}): lo risolvo di nuovo", "warn")
        task.options.pop("url", None)
    task.log("Risolvo il link")
    t0 = time.time()
    url = await asyncio.to_thread(resolve, task.source)  # senza tetto: l'attesa dei lock del browser non conta
    task.log(f"Link risolto in {time.time() - t0:.1f} s")
    if url != task.source:  # uscito da pagine di terzi: mai verso la rete locale (l'utente puo' scrivere a mano un link LAN)
        await asyncio.to_thread(hosts.assert_public, url)
    host = urlsplit(url).hostname or ""
    if not any(host == h or host.endswith("." + h) for h in ONE_TIME):  # un link monouso non si riusa
        task.options.update(url=url, url_at=time.time())
    if gate and not gated:
        await gate()
    await _fetch(task, client, bucket, segments, url, t0)


async def _fetch(task, client, bucket, segments, url, t0):
    task.phase = "Preparo il download (nome e dimensione)"  # resta scritto se qualcosa va storto qui
    headers = task.options.get("headers") or {}
    # la prima richiesta e' anche il primo flusso: un link monouso non sopporta un controllo in piu'
    async with client.stream("GET", url, headers={**headers, "Range": "bytes=0-"}) as first:
        meta = _meta(first, url)
        host = urlsplit(url).hostname or ""
        if any(host == h or host.endswith("." + h) for h in ONE_TIME):
            meta = (meta[0], meta[1], False, meta[3])  # un solo flusso: niente richieste parallele allo stesso link
            task.log("Link monouso: un solo flusso")
        task.log(f"Il server ha risposto dopo {time.time() - t0:.1f} s in tutto")
        task.log(f"Controllo: {meta[0]}, {mb(meta[1]) if meta[1] else 'dimensione ignota'}, "
                 f"Range {'sì' if meta[2] else 'no'} (HTTP {first.status_code})")
        task.phase = ""  # da qui è il download vero: la riga mostra avanzamento e velocità
        await _download(task, client, bucket, segments, url, headers, first, meta)


async def _download(task, client, bucket, segments, url, headers, first, meta):
    name, total, ranged, tag = meta
    dest = Path(task.save_path).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    task.name = task.name or name
    final = (dest / safe_name(task.name)).resolve()
    if final.parent != dest:  # path traversal
        raise ValueError("Nome file non valido")
    part = final.with_name(final.name + ".part")
    if task.options.get("part") != str(part):  # primo avvio: non si tocca un file esistente ne' il .part di un altro task
        stem, ext, i = final.stem, final.suffix, 1
        while final.exists() or part.exists():
            final = dest / f"{stem} ({i}){ext}"
            part, i = final.with_name(final.name + ".part"), i + 1
        task.name = final.name
    # stesso file anche con un etag diverso: host come datanodes danno a ogni risoluzione un server (e un etag) nuovo
    same = task.options.get("tag") == tag or (total > 0 and task.size == total)
    task.size = total
    task.options["part"] = str(part)

    old = task.options.get("segs") or []
    # stato salvato rovinato (segmenti che non coprono il file): non ci si fida, si riparte da capo
    if not (part.exists() and same and old and (ranged or len(old) == 1) and (not ranged or _coherent(old, total))):
        n = max(1, min(segments, total // MIN_SEGMENT)) if ranged else 1
        step = -(-total // n) if ranged else 0
        task.options["segs"] = [[i * step, min((i + 1) * step, total) - 1, i * step] for i in range(n)] if ranged \
            else [[0, total - 1 if total else -1, 0]]  # -1: dimensione ignota, si legge fino alla fine
        task.options["tag"] = tag
        with open(part, "wb") as f:
            if total:
                _sparse(f)
                f.truncate(total)
        task.log(f"Nuovo download: {n} segment{'o' if n == 1 else 'i'}")
    else:
        have = part.stat().st_size
        for i, s in enumerate(old if ranged else []):
            if s[2] > have:  # il .part e' piu' corto di quanto il segmento dice di avere: quei byte non ci sono
                task.log(f"Segmento {i + 1}: il file parziale non ha i dati attesi, riparte dall'inizio", "warn")
                s[2] = s[0]
        if ranged and have != total:
            with open(part, "r+b") as f:
                f.truncate(total)
        task.log(f"Ripresa: {mb(sum(s[2] - s[0] for s in old))} già scaricati, {len(old)} segment{'o' if len(old) == 1 else 'i'}")
    segs = task.options["segs"]
    if not ranged:
        if segs[0][2]:
            task.log("Il server non supporta Range: riparto dall'inizio", "warn")
        segs[0][2] = 0  # senza Range non si riprende: si riparte dall'inizio

    mile = [None]  # ultima decina di percento scritta nel registro (la prima chiamata parte da dove si e' ripreso)

    def sync_done():
        task.done = sum(s[2] - s[0] for s in segs)
        m = task.done * 10 // task.size if task.size else 0
        if mile[0] is None or m < mile[0]:
            mile[0] = m
        elif m > mile[0]:
            mile[0] = m
            task.log(f"Avanzamento {m * 10}% ({mb(task.done)} di {mb(task.size)})")

    async def worker(i, first_resp=None):
        seg, fails, why = segs[i], 0, ""
        with open(part, "r+b") as f:
            while seg[1] < 0 or seg[2] <= seg[1]:
                if not ranged:
                    seg[2] = 0  # senza Range il server rimanda dall'inizio: anche dopo un errore a meta'
                h = dict(headers)
                if ranged:
                    h["Range"] = f"bytes={seg[2]}-{seg[1]}"
                src = first_resp  # la risposta gia' aperta si usa una volta sola
                first_resp = None
                cm = contextlib.nullcontext(src) if src is not None else client.stream("GET", url, headers=h)
                try:
                    async with cm as resp:
                        resp.raise_for_status()
                        if ranged and resp.status_code != 206:
                            raise httpx.TransportError("il server ignora Range")
                        f.seek(seg[2])
                        async for chunk in resp.aiter_bytes(CHUNK):
                            if seg[1] >= 0:
                                chunk = chunk[: seg[1] - seg[2] + 1]
                            await bucket.take(len(chunk))
                            f.write(chunk)
                            seg[2] += len(chunk)
                            fails = 0
                            sync_done()
                            if seg[1] >= 0 and seg[2] > seg[1]:
                                break
                    if seg[1] < 0:
                        seg[1] = seg[2] - 1  # dimensione ignota: fine del flusso
                        task.size = seg[2]
                except httpx.HTTPStatusError as e:
                    if e.response.status_code < 500 and e.response.status_code != 429:
                        raise
                    fails, why = fails + 1, f"HTTP {e.response.status_code}"
                except httpx.TransportError as e:
                    fails, why = fails + 1, f"{type(e).__name__}: {e}"
                if fails > RETRIES:
                    task.log(f"Segmento {i + 1}: {why}; tentativi esauriti", "error")
                    raise httpx.TransportError("troppi tentativi falliti")
                if fails:
                    wait = min(2 ** fails, 30)
                    task.log(f"Segmento {i + 1}: {why}; tentativo {fails}/{RETRIES}, riprovo tra {wait} s", "warn")
                    await asyncio.sleep(wait)

    sync_done()
    # il primo flusso riusa la risposta del controllo solo se parte dall'inizio (download nuovo)
    reuse = first if segs[0][2] == 0 else None
    await asyncio.gather(worker(0, reuse), *(worker(i) for i in range(1, len(segs))))
    sync_done()
    want = (task.options.get("sha256") or "").lower()
    if want:  # nessun hash dichiarato = nessun blocco
        from ... import ports  # import qui: ports e' pesante
        if await asyncio.to_thread(ports._sha256, part) != want:
            q = dest / ".quarantena"
            q.mkdir(exist_ok=True)
            part.replace(q / f"{int(time.time())}-{final.name}")
            raise HashMismatch(f"SHA-256 diverso da quello atteso: {final.name} messo in quarantena")
    final.unlink(missing_ok=True)
    part.replace(final)
    for k in ("segs", "url", "url_at"):
        task.options.pop(k, None)
    task.name = final.name
    task.size = task.size or task.done
