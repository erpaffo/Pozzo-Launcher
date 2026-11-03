"""Immagini in WebP (pozzo/imgopt.py): risparmio, trasparenza, animate, file corrotto, mai ingrandire.

Esegui: PYTHONUTF8=1 python tests/test_imgopt.py   (o pytest tests/test_imgopt.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from pozzo import imgopt  # noqa: E402


def _foto(path: Path, size=(2400, 1600)) -> Path:
    """Immagine "fotografica" (rumore) che in PNG pesa molto."""
    im = Image.effect_noise(size, 60).convert("RGB")
    im.save(path, "PNG")
    return path


def test_optimize_risparmia(tmp: Path):
    src = _foto(tmp / "cover.png")
    prima = src.stat().st_size
    out = imgopt.optimize(src)
    assert out.suffix == ".webp" and out.exists(), out
    assert out.stat().st_size < prima, (out.stat().st_size, prima)
    with Image.open(out) as im:
        assert max(im.size) <= 1600, im.size
    assert not src.exists(), "con un risparmio l'originale viene tolto"
    print(f"ok  optimize: {prima:,} byte di PNG -> {out.stat().st_size:,} byte di WebP "
          f"({100 - out.stat().st_size * 100 // prima}% in meno)")


def test_originale_se_non_conviene(tmp: Path):
    """Se il WebP viene piu' grosso resta l'originale (qui forzato: con le immagini vere il WebP e' sempre minore)."""
    src = tmp / "cover.png"
    Image.effect_noise((300, 300), 50).convert("RGB").save(src, "PNG")
    prima = src.stat().st_size
    salva = imgopt._salva
    imgopt._salva = lambda im, dest, quality: dest.write_bytes(b"x" * (prima + 10))
    try:
        out = imgopt.optimize(src)
    finally:
        imgopt._salva = salva
    assert out == src and src.exists(), out
    assert not (tmp / "cover.webp").exists(), "il WebP piu' grosso viene tolto"
    print("ok  se il WebP non e' piu' piccolo resta l'originale")


def test_trasparenza(tmp: Path):
    src = tmp / "logo.png"
    im = Image.new("RGBA", (1200, 1200), (255, 0, 0, 0))
    im.paste((0, 0, 255, 255), (100, 100, 1100, 1100))
    im.save(src, "PNG")
    out = imgopt.optimize(src)
    with Image.open(out) as letto:
        assert letto.mode == "RGBA" and letto.getpixel((5, 5))[3] == 0, letto.mode
    print("ok  trasparenza mantenuta (angolo ancora trasparente)")


def _gif(path: Path, size=(64, 64)) -> Path:
    """GIF davvero animata: fotogrammi diversi (con lo stesso disegno Pillow ne scrive uno solo)."""
    frames = []
    for i in (0, 40, 80):
        im = Image.new("RGB", size, (255, 255, 255))
        im.paste((i, 0, 0), (0, 0, size[0] // 2, size[1]))
        frames.append(im.convert("P"))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return path


def test_animata_non_si_tocca(tmp: Path):
    src = _gif(tmp / "animata.gif")
    with Image.open(src) as im:
        assert im.is_animated, "la fixture deve essere animata"
    prima = src.read_bytes()
    assert imgopt.optimize(src) == src and src.read_bytes() == prima, "la GIF animata resta com'era"
    print("ok  animata: non convertita, il file resta identico")


def test_file_corrotto(tmp: Path):
    src = tmp / "rotto.jpg"
    src.write_bytes(b"questo non e' un'immagine")
    try:
        imgopt.optimize(src)
    except ValueError as e:
        assert "illeggibile" in str(e) and "rotto.jpg" in str(e), e
    else:
        raise AssertionError("ci si aspetta ValueError")
    assert sorted(p.name for p in tmp.iterdir()) == ["rotto.jpg"], "nessun file parziale lasciato"
    print("ok  file corrotto: errore chiaro e nessun file a meta'")


def test_thumb(tmp: Path):
    src = _foto(tmp / "grande.png", (1000, 800))
    out = imgopt.thumb(src, 200)
    with Image.open(out) as im:
        assert max(im.size) == 200 and im.format == "WEBP", (im.size, im.format)
    assert out.stat().st_size < src.stat().st_size
    assert out.name == "grande_200.webp"
    print(f"ok  thumb: {out.stat().st_size:,} byte a 200 px")


def test_thumb_dest_e_tall(tmp: Path):
    """Come _thumb delle rotte: file in una cartella di cache e copertine alte fino a 3x la larghezza."""
    src = _foto(tmp / "alta.png", (600, 1800))
    dest = tmp / "cache" / "300" / "x.webp"
    out = imgopt.thumb(src, 300, quality=82, dest=dest, tall=3)
    assert out == dest
    with Image.open(out) as im:
        assert im.size == (300, 900), im.size
    print("ok  thumb con dest e tall")


def test_thumb_mai_ingrandisce(tmp: Path):
    src = _foto(tmp / "piccola.png", (50, 40))
    out = imgopt.thumb(src, 400)
    with Image.open(out) as im:
        assert im.size == (50, 40), im.size
    print("ok  thumb: un'immagine piccola non viene ingrandita")


def test_thumb_di_animata(tmp: Path):
    src = _gif(tmp / "animata.gif", (300, 300))
    out = imgopt.thumb(src, 100)
    with Image.open(out) as im:
        assert im.size == (100, 100) and not getattr(im, "is_animated", False), im.size
    print("ok  thumb di un'animata: primo fotogramma")


def _white_contrast(color: str) -> float:
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    luminance = sum(w * v for w, v in zip((0.2126, 0.7152, 0.0722), linear))
    return 1.05 / (luminance + 0.05)


def test_accent_dominante_e_contrasto(tmp: Path):
    red = Image.new("RGB", (64, 64), "#d82020")
    ImageDraw.Draw(red).rectangle((48, 0, 63, 63), fill="#2040d8")
    red_path = tmp / "red.png"
    red.save(red_path)

    blue = Image.new("RGB", (64, 64), "#2040d8")
    ImageDraw.Draw(blue).rectangle((48, 0, 63, 63), fill="#d82020")
    blue_path = tmp / "blue.png"
    blue.save(blue_path)

    red_accent, blue_accent = imgopt.accent_color(red_path), imgopt.accent_color(blue_path)
    assert red_accent and int(red_accent[1:3], 16) > int(red_accent[5:7], 16) * 2, red_accent
    assert blue_accent and int(blue_accent[5:7], 16) > int(blue_accent[1:3], 16) * 2, blue_accent
    assert _white_contrast(red_accent) >= imgopt.ACCENT_TEXT_CONTRAST
    assert _white_contrast(blue_accent) >= imgopt.ACCENT_TEXT_CONTRAST

    gray = tmp / "gray.png"
    Image.new("RGB", (32, 32), "#888888").save(gray)
    assert imgopt.accent_color(gray) is None
    print("ok  accent dominante rosso/blu e contrasto testo bianco 4.5:1; grigio senza accent")


def test_accent_esclude_bianco_e_preferisce_saturazione(tmp: Path):
    near_white = tmp / "near-white.png"
    Image.new("RGB", (32, 32), "#fefdfc").save(near_white)
    assert imgopt.accent_color(near_white) is None

    # Counts are close; saturation takes precedence over frequency.
    pixels = ([(119, 119, 160)] * 2040) + ([(224, 32, 32)] * 2000) + ([(255, 255, 255)] * 56)
    cover = Image.new("RGB", (64, 64))
    cover.putdata(pixels)
    path = tmp / "saturation.png"
    cover.save(path)
    accent = imgopt.accent_color(path)
    assert accent and int(accent[1:3], 16) > int(accent[5:7], 16) * 2, accent
    assert _white_contrast(accent) >= imgopt.ACCENT_TEXT_CONTRAST
    print("ok  near-white escluso; a frequenze simili prevale il colore piu' saturo")


def test_accent_cache_disco_e_invalidazione(tmp: Path):
    src = tmp / "cover.png"
    Image.new("RGB", (32, 32), "#d82020").save(src)
    cached = imgopt._accent_color_cached
    cached.cache_clear()
    red = imgopt.accent_color(src)
    sidecar = src.with_name(src.name + ".accent")
    assert red and sidecar.exists(), sidecar

    cached.cache_clear()  # elimina la cache RAM: il risultato deve provenire dal sidecar
    imgopt._accent_color_cached = lambda *args: (_ for _ in ()).throw(AssertionError("cache disco ignorata"))
    try:
        assert imgopt.accent_color(src) == red
    finally:
        imgopt._accent_color_cached = cached

    old_mtime = src.stat().st_mtime_ns
    Image.new("RGB", (32, 32), "#2040d8").save(src)
    os.utime(src, ns=(old_mtime + 2_000_000_000, old_mtime + 2_000_000_000))
    cached.cache_clear()
    blue = imgopt.accent_color(src)
    assert blue and blue != red and int(blue[5:7], 16) > int(blue[1:3], 16) * 2, blue
    assert sidecar.read_text(encoding="ascii").startswith(f"{src.stat().st_mtime_ns} {src.stat().st_size} ")
    print("ok  cache su disco riusata e invalidata su cambio mtime")


def test_accent_file_mancante_o_illeggibile(tmp: Path):
    assert imgopt.accent_color(tmp / "missing.png") is None
    broken = tmp / "broken.png"
    broken.write_bytes(b"not an image")
    assert imgopt.accent_color(broken) is None
    print("ok  accent nullo per file mancante o illeggibile")


def test_api_cover_accent_override(tmp: Path):
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pozzo.app.routes import images

    base = tmp / "base.png"
    override = tmp / "override.png"
    Image.new("RGB", (32, 32), "#d82020").save(base)
    Image.new("RGB", (32, 32), "#2040d8").save(override)
    remote_url = "https://covers.test/game.png"
    remote_path = tmp / "media" / "net" / f"{hashlib.sha1(remote_url.encode()).hexdigest()}.png"
    remote_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), "#2040d8").save(remote_path)
    overrides = {"cover": "override.png"}
    game = {"id": 1, "key": "test:1", "media": {"cover": "base.png"}}
    ctx = SimpleNamespace(
        cfg=SimpleNamespace(cache=tmp),
        lib=SimpleNamespace(get=lambda gid: game),
        state={},
        thumbs_dir=tmp / "thumbs",
        user=SimpleNamespace(media_overrides=lambda key: overrides),
    )

    class NoThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

    with patch.object(images.threading, "Thread", NoThread):
        app = FastAPI()
        app.include_router(images.build_router(ctx))
    with TestClient(app) as client:
        response = client.get("/api/game/1/cover-accent")
        accent = response.json()["accent"]
        assert response.status_code == 200 and accent
        assert int(accent[5:7], 16) > int(accent[1:3], 16) * 2, accent
        overrides["cover"] = f"url:{remote_url}"
        remote = client.get("/api/game/1/cover-accent")
        assert remote.status_code == 200 and remote.json()["accent"] == accent, remote.json()
        overrides.clear()
        game["media"].clear()
        missing = client.get("/api/game/1/cover-accent")
        assert missing.status_code == 200 and missing.json() == {"accent": None}, missing.json()
    print("ok  endpoint onora override, cache remota esistente e cover mancante")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_optimize_risparmia, test_originale_se_non_conviene, test_trasparenza, test_animata_non_si_tocca,
                   test_file_corrotto, test_thumb, test_thumb_dest_e_tall, test_thumb_mai_ingrandisce,
                   test_thumb_di_animata, test_accent_dominante_e_contrasto,
                   test_accent_esclude_bianco_e_preferisce_saturazione, test_accent_cache_disco_e_invalidazione,
                   test_accent_file_mancante_o_illeggibile, test_api_cover_accent_override):
            sub = Path(t) / fn.__name__
            sub.mkdir()
            fn(sub)
    print("TUTTI I TEST OK")
