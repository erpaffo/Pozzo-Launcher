from __future__ import annotations

import io
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SIZE = 1024
LANCZOS = Image.Resampling.LANCZOS


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def point(cx: float, cy: float, rx: float, ry: float, angle: float) -> tuple[float, float]:
    rad = math.radians(angle)
    return cx + rx * math.cos(rad), cy + ry * math.sin(rad)


def render_icon() -> Image.Image:
    # The 1024px master is the supersampled drawing surface for every output size.
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, 1016, 1016), radius=205, fill=255)

    bg = Image.new("RGBA", (SIZE, SIZE))
    draw = ImageDraw.Draw(bg)
    top, bottom = (30, 37, 57), (12, 16, 25)
    for y in range(SIZE):
        draw.line((0, y, SIZE, y), fill=(*mix(top, bottom, y / (SIZE - 1)), 255))

    halo = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((225, 250, 799, 800), fill=(42, 105, 204, 76))
    bg = Image.alpha_composite(bg, halo.filter(ImageFilter.GaussianBlur(105)))
    bg.putalpha(mask)

    # Stone rim: alternating masonry blocks preserve a bold well silhouette at 16–32px.
    cx, cy = 512, 518
    outer_rx, outer_ry = 382, 348
    inner_rx, inner_ry = 245, 213
    draw = ImageDraw.Draw(bg)
    draw.ellipse((cx - outer_rx, cy - outer_ry + 17, cx + outer_rx, cy + outer_ry + 17),
                 fill=(4, 7, 13, 165))
    colors = [(76, 84, 103, 255), (91, 99, 118, 255), (67, 76, 95, 255), (83, 91, 109, 255)]
    for i in range(12):
        start, end = i * 30 + 1.75, (i + 1) * 30 - 1.75
        poly = [point(cx, cy, outer_rx, outer_ry, start),
                point(cx, cy, outer_rx, outer_ry, end),
                point(cx, cy, inner_rx, inner_ry, end),
                point(cx, cy, inner_rx, inner_ry, start)]
        draw.polygon(poly, fill=colors[i % len(colors)], outline=(43, 51, 67, 255), width=8)
        # A restrained top-edge glint gives the stones depth without adding small-detail noise.
        mid = (start + end) / 2
        if 190 < mid < 350:
            a = point(cx, cy, outer_rx - 10, outer_ry - 10, start + 5)
            b = point(cx, cy, outer_rx - 10, outer_ry - 10, end - 5)
            draw.line((a, b), fill=(128, 143, 166, 115), width=5)

    draw.ellipse((cx - outer_rx, cy - outer_ry, cx + outer_rx, cy + outer_ry),
                 outline=(116, 127, 150, 255), width=9)
    draw.ellipse((cx - inner_rx, cy - inner_ry, cx + inner_rx, cy + inner_ry),
                 fill=(8, 12, 20, 255), outline=(38, 56, 83, 255), width=12)

    # Blue light pooled inside the dark opening.
    opening = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(opening).ellipse((cx - inner_rx + 12, cy - inner_ry + 12,
                                     cx + inner_rx - 12, cy + inner_ry - 12), fill=255)
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((337, 535, 687, 714), fill=(45, 122, 235, 155))
    glow = glow.filter(ImageFilter.GaussianBlur(42))
    glow.putalpha(Image.composite(glow.getchannel("A"), Image.new("L", (SIZE, SIZE), 0), opening))
    bg = Image.alpha_composite(bg, glow)
    draw = ImageDraw.Draw(bg)

    # A suspended bucket and taut rope make the mark read as a working well, not a portal.
    draw.line((512, 319, 512, 470), fill=(193, 207, 228, 255), width=12)
    draw.line((518, 326, 518, 466), fill=(91, 140, 255, 180), width=4)
    draw.arc((432, 430, 592, 558), start=180, end=360, fill=(177, 195, 220, 255), width=13)
    bucket = [(438, 488), (586, 488), (566, 610), (458, 610)]
    draw.polygon(bucket, fill=(37, 69, 97, 255), outline=(110, 169, 255, 255))
    draw.line((447, 500, 577, 500), fill=(164, 206, 255, 255), width=12)
    draw.line((466, 518, 466, 579), fill=(91, 140, 255, 155), width=8)
    draw.line((492, 601, 532, 601), fill=(139, 192, 255, 210), width=8)

    bg.putalpha(Image.composite(bg.getchannel("A"), Image.new("L", (SIZE, SIZE), 0), mask))
    return bg


def resized(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), LANCZOS)


def save_ico(master: Image.Image, path: Path) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    entries: list[tuple[int, bytes]] = []
    for size in sizes:
        stream = io.BytesIO()
        resized(master, size).save(stream, format="PNG", optimize=True)
        entries.append((size, stream.getvalue()))

    offset = 6 + 16 * len(entries)
    header = struct.pack("<HHH", 0, 1, len(entries))
    directory = bytearray()
    payload = bytearray()
    for size, data in entries:
        dimension = 0 if size == 256 else size
        directory.extend(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32,
                                     len(data), offset))
        payload.extend(data)
        offset += len(data)
    path.write_bytes(header + directory + payload)


def main() -> None:
    master = render_icon()
    (ROOT / "packaging" / "icon.png").write_bytes(_png(master, 1024))
    save_ico(master, ROOT / "packaging" / "icon.ico")

    static = ROOT / "pozzo" / "app" / "static" / "m"
    for filename, size in (("icon.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)):
        (static / filename).write_bytes(_png(master, size))

    icns_images = [resized(master, size) for size in (32, 64, 128, 256, 512)]
    master.save(ROOT / "packaging" / "icon.icns", format="ICNS", append_images=icns_images)


def _png(master: Image.Image, size: int) -> bytes:
    stream = io.BytesIO()
    resized(master, size).save(stream, format="PNG", optimize=True)
    return stream.getvalue()


if __name__ == "__main__":
    main()
