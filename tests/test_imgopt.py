"""Immagini in WebP (pozzo/imgopt.py): risparmio, trasparenza, animate, file corrotto, mai ingrandire.

Esegui: PYTHONUTF8=1 python tests/test_imgopt.py   (o pytest tests/test_imgopt.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

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


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_optimize_risparmia, test_originale_se_non_conviene, test_trasparenza, test_animata_non_si_tocca,
                   test_file_corrotto, test_thumb, test_thumb_dest_e_tall, test_thumb_mai_ingrandisce, test_thumb_di_animata):
            sub = Path(t) / fn.__name__
            sub.mkdir()
            fn(sub)
    print("TUTTI I TEST OK")
