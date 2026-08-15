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

    if size == 16:
        # Explorer's "Small icons" view uses the native 16px ICO frame.  A
        # downsampled vector mark turns into the blocky shape seen in that
        # view, so draw this one frame on the pixel grid.  The open right side
        # is deliberately wide enough to read as a C at 100% scale.
        image = Image.new("RGBA", (16, 16), (27, 27, 29, 255))
        draw = ImageDraw.Draw(image)
        green = (87, 185, 126, 255)
        white = (255, 255, 255, 255)
        draw.rounded_rectangle((2, 2, 13, 13), radius=3, fill=green)
        for y, start, end in (
            (4, 7, 9),
            (5, 5, 6),
            (6, 4, 4),
            (7, 4, 4),
            (8, 4, 4),
            (9, 4, 4),
            (10, 5, 6),
            (11, 7, 9),
        ):
            draw.line((start, y, end, y), fill=white, width=2)
        return image

    # Render large and downsample so the curved C keeps a stable, centered
    # silhouette at all non-native shell sizes.
    canvas_size = max(64, size * 4)
    image = Image.new("RGBA", (canvas_size, canvas_size), (27, 27, 29, 255))
    draw = ImageDraw.Draw(image)

    scale = canvas_size / 256.0
    outer = max(1, round(12 * scale))
    radius = max(2, round(52 * scale))
    draw.rounded_rectangle(
        (outer, outer, canvas_size - outer - 1, canvas_size - outer - 1),
        radius=radius,
        fill=(87, 185, 126, 255),
    )

    # Build the C from concentric ellipses instead of a low-resolution arc.
    # This gives Windows a stable, symmetric shape to sample at 32px and up.
    left = round(canvas_size * 0.27)
    top = round(canvas_size * 0.20)
    right = round(canvas_size * 0.73)
    bottom = round(canvas_size * 0.80)
    stroke = max(2, round(canvas_size * 0.13))
    green = (87, 185, 126, 255)
    white = (255, 255, 255, 255)
    draw.ellipse((left, top, right, bottom), fill=white)
    draw.ellipse(
        (left + stroke, top + stroke, right - stroke, bottom - stroke),
        fill=green,
    )

    # Remove a mirrored wedge on the right.  Its diagonal edges become the
    # two clean C terminals while preserving equal top/bottom spacing.
    center_y = (top + bottom) / 2.0
    cut_x = round((left + right) / 2.0 - stroke * 0.15)
    cut_top = round(center_y - canvas_size * 0.18)
    cut_bottom = round(center_y + canvas_size * 0.18)
    wedge_top = round(center_y - canvas_size * 0.37)
    wedge_bottom = round(center_y + canvas_size * 0.37)
    draw.polygon(
        ((cut_x, cut_top), (right + 1, wedge_top),
         (right + 1, wedge_bottom), (cut_x, cut_bottom)),
        fill=green,
    )

    return image.resize((size, size), Image.Resampling.LANCZOS)
