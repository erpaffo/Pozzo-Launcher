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

import colorsys
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, UnidentifiedImageError

LANCZOS = Image.Resampling.LANCZOS
ACCENT_TEXT_CONTRAST = 4.5


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


@lru_cache(maxsize=512)
def _accent_color_cached(path: str, _mtime_ns: int, _size: int) -> str | None:
    try:
        with Image.open(path) as im:
            sample = im.convert("RGB")
            sample.thumbnail((64, 64), LANCZOS)
            quantized = sample.quantize(colors=16)
            palette = quantized.getpalette()
            colors = quantized.getcolors(64 * 64) or []
    except (OSError, ValueError):
        return None

    saturated = []
    for count, index in colors:
        rgb = tuple(palette[index * 3:index * 3 + 3])
        if len(rgb) == 3:
            _, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
            if min(rgb) >= 240 or saturation < 0.25 or value < 0.12:
                continue
            saturated.append((saturation, count, rgb))
    if not saturated:
        return None
    _, _, rgb = max(saturated, key=lambda item: (item[0], item[1]))
    red, green, blue = (channel / 255 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)

    def white_contrast(lightness: float) -> float:
        adjusted = colorsys.hls_to_rgb(hue, lightness, saturation)
        luminance = sum(weight * (channel / 12.92 if channel <= 0.04045 else
                                  ((channel + 0.055) / 1.055) ** 2.4)
                        for weight, channel in zip((0.2126, 0.7152, 0.0722), adjusted))
        return 1.05 / (luminance + 0.05)

    target = ACCENT_TEXT_CONTRAST + 0.05  # margin for RGB rounding after HLS conversion
    if white_contrast(lightness) < target:
        low, high = 0.0, lightness
        for _ in range(24):
            mid = (low + high) / 2
            if white_contrast(mid) >= target:
                low = mid
            else:
                high = mid
        lightness = low
    rgb = tuple(round(channel * 255) for channel in colorsys.hls_to_rgb(hue, lightness, saturation))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def accent_color(path) -> str | None:
    """Return a cached saturated accent contrasting with white text by at least 4.5:1."""
    src = Path(path)
    try:
        stat = src.stat()
    except OSError:
        return None
    sidecar = src.with_name(src.name + ".accent")
    try:
        mtime, size, color = sidecar.read_text(encoding="ascii").strip().split(" ", 2)
        valid = color == "-" or (len(color) == 7 and color[0] == "#"
                                 and all(c in "0123456789abcdef" for c in color[1:]))
        if valid and int(mtime) == stat.st_mtime_ns and int(size) == stat.st_size:
            return None if color == "-" else color
    except (OSError, ValueError):
        pass

    color = _accent_color_cached(str(src.resolve()), stat.st_mtime_ns, stat.st_size)
    tmp = sidecar.with_name(sidecar.name + ".tmp")
    try:
        tmp.write_text(f"{stat.st_mtime_ns} {stat.st_size} {color or '-'}\n", encoding="ascii")
        os.replace(tmp, sidecar)
    except OSError:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    return color


def optimize(path, quality: int = 82, max_side: int = 1600) -> Path:
    """Converte e ridimensiona un'immagine scaricata in WebP; restituisce il file da usare.

    Se l'originale e' piu' leggero del WebP (capita con le immagini piccole o gia' compresse) resta
    l'originale; altrimenti il WebP prende il suo posto e l'originale viene tolto.
    """
    src = Path(path)
    with _apri(src) as im:
        if getattr(im, "is_animated", False):
            accent_color(src)
            return src  # animata: convertirla la rovinerebbe
        if src.suffix.lower() == ".webp" and max(im.size) <= max_side:
            accent_color(src)
            return src  # gia' WebP e abbastanza piccola
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side), LANCZOS)
        lavoro = im.convert("RGBA" if _trasparente(im) else "RGB")
    # il file e' chiuso: su Windows si puo' sostituire o togliere
    dest = src.with_suffix(".webp")
    _salva(lavoro, dest, quality)
    if dest.stat().st_size >= src.stat().st_size:
        dest.unlink(missing_ok=True)
        out = src
    else:
        src.unlink(missing_ok=True)
        out = dest
    accent_color(out)
    return out


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
