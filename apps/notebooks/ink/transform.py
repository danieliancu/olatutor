"""Physical device coordinates to logical page units (spec section 3).

The transform runs once, at capture. Stored integers are the truth afterwards, so the +/-1 unit
rounding differences between runtimes can never reach replay or hashing.
"""

import math

Matrix = tuple[float, float, float, float, float, float]


def build_matrix(
    *,
    viewport: tuple[float, float],
    dpr: float,
    rotation_deg: int,
    page_width: int,
    scroll: tuple[float, float] = (0.0, 0.0),
    zoom: float = 1.0,
) -> Matrix:
    """Return (a, b, c, d, e, f) with x' = a*x + c*y + e and y' = b*x + d*y + f.

    `viewport` is in physical pixels as the device reports it, before undoing rotation. The page
    is fitted to the view's width at zoom 1. `scroll` is the logical unit shown at the view origin.
    """
    width, height = viewport[0] / dpr, viewport[1] / dpr
    if rotation_deg == 0:
        rotation = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        view_width = width
    elif rotation_deg == 90:
        rotation = (0.0, -1.0, 1.0, 0.0, 0.0, width)
        view_width = height
    elif rotation_deg == 180:
        rotation = (-1.0, 0.0, 0.0, -1.0, width, height)
        view_width = width
    elif rotation_deg == 270:
        rotation = (0.0, 1.0, -1.0, 0.0, height, 0.0)
        view_width = height
    else:
        raise ValueError("rotation must be 0, 90, 180 or 270")

    units_per_css_px = page_width / view_width / zoom
    scale = units_per_css_px / dpr
    a, b, c, d, e, f = rotation
    return (
        a * scale,
        b * scale,
        c * scale,
        d * scale,
        e * units_per_css_px + scroll[0],
        f * units_per_css_px + scroll[1],
    )


def round_half_away(value: float) -> int:
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def to_logical(matrix: Matrix, x: float, y: float) -> tuple[int, int]:
    a, b, c, d, e, f = matrix
    return round_half_away(a * x + c * y + e), round_half_away(b * x + d * y + f)


def matrix_micro(matrix: Matrix) -> list[int]:
    return [round_half_away(value * 1_000_000) for value in matrix]
