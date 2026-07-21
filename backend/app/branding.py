"""Brand icon, drawn with PIL so no SVG renderer / bundled asset is needed.

Reproduces ``frontend/public/logo.svg``: an open (right-gap) ring in faded
brand blue plus a solid blue checkmark, on a transparent background. Used for
the system-tray icon and, at build time, to generate the ``.ico`` embedded in
the packaged executable.
"""

from PIL import Image, ImageDraw

_BLUE = (59, 130, 246, 255)  # #3B82F6
_BLUE_FADED = (59, 130, 246, 77)  # ring at ~0.3 opacity


def make_icon(size: int = 256) -> "Image.Image":
    scale = size / 100.0  # logo is authored in a 100x100 viewBox
    width = max(2, round(10 * scale))  # stroke-width: 10

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def pt(x: float, y: float) -> "tuple[float, float]":
        return (x * scale, y * scale)

    # Open ring (the system / "Q"), faded. Circle r=30 centred at (50, 50),
    # drawn clockwise from ~32deg to ~332deg leaving a gap on the right.
    x0, y0 = pt(20, 20)
    x1, y1 = pt(80, 80)
    draw.arc([x0, y0, x1, y1], start=32, end=332, fill=_BLUE_FADED, width=width)

    # Checkmark (the answer), solid, with round caps/joints.
    points = [pt(38, 52), pt(52, 66), pt(82, 30)]
    draw.line(points, fill=_BLUE, width=width, joint="curve")
    radius = width / 2
    for cx, cy in (points[0], points[2]):
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=_BLUE)

    return img


def save_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256)) -> None:
    """Write a multi-resolution Windows ``.ico`` at ``path``."""
    make_icon(256).save(path, format="ICO", sizes=[(s, s) for s in sizes])
