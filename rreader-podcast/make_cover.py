#!/usr/bin/env python3
"""
One-off: generate a placeholder square cover image for the podcast feed.

Apple Podcasts requires square artwork between 1400x1400 and 3000x3000 px,
JPG or PNG, RGB (no alpha, no CMYK). This draws a simple solid-color square
with the site name so the RSS feed is valid from day one. Swap
assets/cover.jpg for real artwork whenever you have one -- see
DISTRIBUTION-GUIDE.md.

Run once: uv run python make_cover.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 1400
ACCENT = (236, 140, 111)  # matches rreader-web's ACCENT (#ec8c6f)
OUT = Path(__file__).parent / "assets" / "cover.jpg"


def main():
    img = Image.new("RGB", (SIZE, SIZE), ACCENT)
    draw = ImageDraw.Draw(img)

    # Try a bundled system font (DejaVu ships with Pillow's font dir on most
    # platforms); fall back to Pillow's built-in bitmap font if unavailable.
    try:
        font_big = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 120
        )
        font_small = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 48
        )
    except Exception:
        try:
            from PIL import ImageFont as _IF

            font_big = _IF.load_default(size=120)
            font_small = _IF.load_default(size=48)
        except Exception:
            font_big = ImageFont.load_default()
            font_small = ImageFont.load_default()

    title = "news.coroke.net"
    subtitle = "PODCAST"

    bbox = draw.textbbox((0, 0), title, font=font_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((SIZE - tw) / 2 - bbox[0], SIZE / 2 - th - 20 - bbox[1]),
        title,
        font=font_big,
        fill=(255, 255, 255),
    )

    bbox2 = draw.textbbox((0, 0), subtitle, font=font_small)
    sw, sh = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
    draw.text(
        ((SIZE - sw) / 2 - bbox2[0], SIZE / 2 + 30 - bbox2[1]),
        subtitle,
        font=font_small,
        fill=(255, 255, 255),
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "JPEG", quality=90)
    print(f"Wrote {OUT} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
