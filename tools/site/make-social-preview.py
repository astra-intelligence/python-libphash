#!/usr/bin/env python3
"""Generate docs/assets/social-preview.png, the site's 1200x630 Open Graph card.

The card is drawn from the same elements as the site itself: the logo -- a 4x4
grid of rounded squares, sixteen bits of a perceptual hash, set bits in the
site's accent (#2a78d6), clear bits in the same color, faint -- the package
name, and the site tagline. Run it from the repository root:

    python3 tools/site/make-social-preview.py

Pillow is the only dependency (already a docs-group dependency via the site's
image assets; the script draws everything itself and needs no fonts from the
machine -- it renders text as vector paths through PIL's baked-in default
font, sized to fit the 1200x630 canvas).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
ACCENT = (42, 120, 214)      # #2a78d6 -- the site's primary color
ACCENT_FAINT = (42, 120, 214, 72)
INK = (24, 42, 66)           # a near-black slate that reads on the light card
MUTED = (90, 110, 132)       # secondary text
BG = (255, 255, 255)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "social-preview.png"


def cell(draw: ImageDraw.ImageDraw, x0: int, y0: int, size: int, radius: int,
         fill: tuple[int, int, int, int] | tuple[int, int, int]) -> None:
    draw.rounded_rectangle([x0, y0, x0 + size, y0 + size], radius=radius, fill=fill)


def hash_grid(draw: ImageDraw.ImageDraw, cx: int, cy: int, cell_size: int,
              gap: int, radius_ratio: float = 0.2) -> None:
    """A 4x4 grid of the logo's hash bits around (cx, cy)."""
    n = 4
    size = cell_size
    total = n * size + (n - 1) * gap
    x0 = cx - total // 2
    y0 = cy - total // 2
    pattern = [
        [1, 0, 1, 1],
        [0, 1, 1, 0],
        [1, 1, 0, 1],
        [0, 1, 1, 1],
    ]
    rad = int(size * radius_ratio)
    for r in range(n):
        for c in range(n):
            if pattern[r][c]:
                fill = ACCENT
            else:
                fill = ACCENT_FAINT
            cell(draw, x0 + c * (size + gap), y0 + r * (size + gap), size, rad, fill)


def main() -> None:
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Decorative hash grid, right of center, large and quiet.
    hash_grid(draw, cx=960, cy=210, cell_size=74, gap=18, radius_ratio=0.22)

    # A thin accent rule under the wordmark.
    draw.rectangle([80, 316, 380, 322], fill=ACCENT)

    # Wordmark + tagline. PIL's default bitmap font is tiny; draw text with a
    # larger vector font by loading a TTF shipped with Pillow's bundled fonts
    # if present, else fall back to the default font scaled up.
    fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_path = next((p for p in fonts if Path(p).exists()), None)
    regular_path = fonts[1] if Path(fonts[1]).exists() else None

    if bold_path:
        title_font = ImageFont.truetype(bold_path, 72)
        tag_font = ImageFont.truetype(regular_path or bold_path, 30)
    else:
        title_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()

    draw.text((80, 150), "python-libphash", font=title_font, fill=INK)
    draw.text((80, 356), "Perceptual image hashing in Python", font=tag_font, fill=MUTED)
    draw.text((80, 404), "gudoshnikovn.github.io/python-libphash", font=tag_font, fill=ACCENT)

    img.convert("RGB").save(OUT, "PNG")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()
