"""Brand icon, drawn with PIL so no SVG renderer / bundled asset is needed.

Reproduces ``frontend/public/logo.svg``: an open (right-gap) ring in faded
brand colour plus a solid checkmark, on a transparent background. Used for
the system-tray icon and, at build time, to generate the ``.ico`` embedded in
the packaged executable (and the installer).

The preview channel uses the same shape in an amber palette.
"""

from typing import Optional, Tuple

from PIL import Image, ImageDraw

RGBA = Tuple[int, int, int, int]

_STABLE = (47, 122, 107)  # #2F7A6B, keep in sync with frontend/public/logo.svg
_PREVIEW = (180, 83, 9)  # #B45309 (Tailwind amber-700)
_RING_ALPHA = 77  # ring at ~0.3 opacity


def _palette(preview: bool) -> Tuple[RGBA, RGBA]:
    r, g, b = _PREVIEW if preview else _STABLE
    return (r, g, b, 255), (r, g, b, _RING_ALPHA)


def _resolve(preview: Optional[bool]) -> bool:
    if preview is None:
        from app.channel import PREVIEW

        return PREVIEW
    return preview


def make_icon(size: int = 256, preview: Optional[bool] = None) -> "Image.Image":
    """Draw the logo; ``preview`` defaults to the running channel (``app.channel.PREVIEW``)."""
    preview = _resolve(preview)
    solid, faded = _palette(preview)
    scale = size / 100.0  # logo is authored in a 100x100 viewBox
    width = max(2, round(10 * scale))  # stroke-width: 10

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def pt(x: float, y: float) -> "tuple[float, float]":
        return (x * scale, y * scale)

    def dot(cx: float, cy: float, radius: float) -> None:
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=solid)

    # Open ring (the system / "Q"), faded. Circle r=30 centred at (50, 50),
    # drawn clockwise from ~32deg to ~332deg leaving a gap on the right.
    x0, y0 = pt(20, 20)
    x1, y1 = pt(80, 80)
    draw.arc([x0, y0, x1, y1], start=32, end=332, fill=faded, width=width)

    # Checkmark (the answer), solid, with round caps/joints.
    points = [pt(38, 52), pt(52, 66), pt(82, 30)]
    draw.line(points, fill=solid, width=width, joint="curve")
    for cx, cy in (points[0], points[2]):
        dot(cx, cy, width / 2)

    return img


def save_ico(path: str, sizes=(16, 24, 32, 48, 64, 128, 256), preview: Optional[bool] = None) -> None:
    """Write a multi-resolution Windows ``.ico`` at ``path``.

    Each size is drawn natively (not downscaled from 256px) so strokes keep
    their minimum pixel width at small tray/taskbar sizes.
    """
    preview = _resolve(preview)
    images = [make_icon(s, preview) for s in sorted(sizes, reverse=True)]
    images[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])


def save_splash(path: str, width: int = 460, height: int = 200, preview: Optional[bool] = None) -> None:
    """Write the startup splash background (logo on white); the text is drawn by the bootloader."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    logo = make_icon(96, preview)
    img.paste(logo, ((width - 96) // 2, 28), logo)
    img.save(path, format="PNG")
