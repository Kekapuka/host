"""Generate the application icon (assets/icon.ico, assets/icon.png) from the logo geometry.

Requires Pillow (dev only):  python scripts/make_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

# Exact rectangles of the original 1080x1080 logo (x, y, width, height).
RECTS = [
    (97, 255, 114, 88),
    (281, 414, 113, 167),
    (493, 414, 111, 167),
    (387, 572, 112, 89),
    (281, 657, 113, 167),
    (493, 657, 111, 167),
    (869, 735, 113, 89),
]
VIEW = (97, 255, 885, 569)  # bounding box of all rectangles

ROOT = Path(__file__).resolve().parent.parent


def render(size: int, padding: float = 0.16) -> Image.Image:
    scale_up = 4  # supersample for crisp edges
    s = size * scale_up
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.2), fill=(255, 255, 255, 255))
    vx, vy, vw, vh = VIEW
    k = (s * (1 - 2 * padding)) / max(vw, vh)
    ox = (s - vw * k) / 2
    oy = (s - vh * k) / 2
    for x, y, w, h in RECTS:
        x0 = ox + (x - vx) * k
        y0 = oy + (y - vy) * k
        d.rectangle((x0, y0, x0 + w * k, y0 + h * k), fill=(10, 10, 10, 255))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    big = render(256)
    big.save(assets / "icon.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.save(assets / "icon.ico", sizes=[(n, n) for n in sizes])
    print("icons written to", assets)


if __name__ == "__main__":
    main()
