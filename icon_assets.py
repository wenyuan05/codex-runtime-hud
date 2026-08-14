"""Shared raster icon drawing for the window, tray and Windows executable."""

from __future__ import annotations


def create_icon_image(size: int = 64):
    """Return a small RGBA icon that remains legible at Windows tray sizes.

    The earlier icon used Pillow's default bitmap font for the ``C``.  That
    glyph becomes effectively invisible when Windows selects the 16px ICO
    frame, leaving only the green tile.  Drawing the mark as geometry keeps
    the same shape at every requested size and avoids font/rendering variance.
    """

    from PIL import Image, ImageDraw

    size = max(16, int(size))
    image = Image.new("RGBA", (size, size), (27, 27, 29, 255))
    draw = ImageDraw.Draw(image)

    scale = size / 256.0
    outer = max(1, round(12 * scale))
    radius = max(2, round(52 * scale))
    draw.rounded_rectangle(
        (outer, outer, size - outer - 1, size - outer - 1),
        radius=radius,
        fill=(87, 185, 126, 255),
    )

    # A deliberately broad, hand-drawn C.  It is an arc rather than a font
    # glyph so the white mark survives the 16px shell icon down to its last
    # pixels.  The right-side gap is enlarged at tiny sizes for clarity.
    left = round(size * 0.27)
    top = round(size * 0.20)
    right = round(size * 0.73)
    bottom = round(size * 0.80)
    width = max(2, round(size * 0.13))
    draw.arc((left, top, right, bottom), start=48, end=312, fill=(255, 255, 255, 255), width=width)

    # Square off the arc endpoints into a clean C opening.  The green cover
    # is intentionally narrow so the white stroke remains dominant at 16px.
    gap = max(1, round(size * 0.08))
    cover_x = right - max(1, round(width * 0.35))
    draw.rectangle((cover_x, top - gap, size, top + gap), fill=(87, 185, 126, 255))
    draw.rectangle((cover_x, bottom - gap, size, bottom + gap), fill=(87, 185, 126, 255))

    return image

