"""Server-side raster reconstruction of a page. Geometry equality, not pixels, is the contract."""

import io
from typing import Any

from PIL import Image, ImageDraw


def render_png(width: int, height: int, strokes: list[dict[str, Any]], scale: float = 0.4) -> bytes:
    image = Image.new("RGB", (round(width * scale), round(height * scale)), "#ffffff")
    draw = ImageDraw.Draw(image)
    for stroke in strokes:
        line = [(x * scale, y * scale) for x, y, _t, _p in stroke["points"]]
        line_width = max(1, round(stroke["width"] * scale))
        if len(line) == 1:
            x, y = line[0]
            radius = line_width / 2
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=stroke["color"])
        else:
            draw.line(line, fill=stroke["color"], width=line_width, joint="curve")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
