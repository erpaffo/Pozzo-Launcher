"""Immagini: WebP al posto di PNG/JPG pesanti, e miniature, con Pillow (gia' in requirements.txt).

Solo WebP: AVIF escluso perche' Pillow non garantisce il codec su tutte le piattaforme (servirebbe
un plugin in piu') e senza dipendenze nuove. Funzioni pure sul filesystem: ricevono un file e
restituiscono il file da usare (puo' essere l'originale, se convertirlo non conviene).

Regole:
- scrittura atomica (file .tmp nella stessa cartella e poi os.replace): chi legge non vede mai un'immagine a meta';
- se il WebP non e' piu' piccolo dell'originale, resta l'originale (e si restituisce quello);
- mai ingrandire: le immagini gia' piccole si ridimensionano o restano come sono;
- immagini animate (GIF/WebP animati) non si convertono: si restituisce l'originale cosi' com'e';
- file corrotto: ValueError con il nome del file, senza lasciare file parziali.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

LANCZOS = Image.Resampling.LANCZOS


def _trasparente(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)


def _salva(im: Image.Image, dest: Path, quality: int) -> None:
    """WebP atomico: chi legge non vede mai un'immagine a meta'."""
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        im.save(tmp, "WEBP", quality=quality, method=4)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _apri(src: Path) -> Image.Image:
    try:
        im = Image.open(src)
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError(f"immagine illeggibile: {src.name}") from e
    im.load()
    return im


def optimize(path, quality: int = 82, max_side: int = 1600) -> Path:
    """Converte e ridimensiona un'immagine scaricata in WebP; restituisce il file da usare.

    Se l'originale e' piu' leggero del WebP (capita con le immagini piccole o gia' compresse) resta
    l'originale; altrimenti il WebP prende il suo posto e l'originale viene tolto.
    """
    src = Path(path)
    with _apri(src) as im:
        if getattr(im, "is_animated", False):
            return src  # animata: convertirla la rovinerebbe
        if src.suffix.lower() == ".webp" and max(im.size) <= max_side:
            return src  # gia' WebP e abbastanza piccola
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side), LANCZOS)
        lavoro = im.convert("RGBA" if _trasparente(im) else "RGB")
    # il file e' chiuso: su Windows si puo' sostituire o togliere
    dest = src.with_suffix(".webp")
    _salva(lavoro, dest, quality)
    if dest.stat().st_size >= src.stat().st_size:
        dest.unlink(missing_ok=True)
        return src
    src.unlink(missing_ok=True)
    return dest


def thumb(path, size: int, quality: int = 78, dest=None, tall: int = 1) -> Path:
    """Miniatura WebP con larghezza/altezza al massimo `size` x `size*tall`.

    Va in `dest` (se dato; la cartella viene creata) oppure in <nome>_<size>.webp accanto all'originale.
    """
    src = Path(path)
    size = max(1, int(size))
    with _apri(src) as im:
        gia_piccola = max(im.size) <= size
        if gia_piccola and src.suffix.lower() == ".webp" and not getattr(im, "is_animated", False):
            return src  # gia' una miniatura WebP: ricodificarla la peggiorerebbe
        if getattr(im, "is_animated", False):
            im.seek(0)  # di un'animata si tiene il primo fotogramma
        im.thumbnail((size, size * tall), LANCZOS)  # thumbnail non ingrandisce mai
        lavoro = im.convert("RGBA" if _trasparente(im) else "RGB")
    dest = Path(dest) if dest else src.with_name(f"{src.stem}_{size}.webp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _salva(lavoro, dest, quality)
    if gia_piccola and dest.stat().st_size >= src.stat().st_size:
        dest.unlink(missing_ok=True)
        return src
    return dest
