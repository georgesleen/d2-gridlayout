"""Straight-line geometry between cell centres, in cell units."""

from __future__ import annotations

from .model import Cell

# A line counts as passing through a block when it comes this close to the
# block's centre, in cell units. Blocks are wider than tall, hence the asymmetry.
THROUGH_DX = 0.5
THROUGH_DY = 0.45

Point = tuple[float, float]


def centre(cell: Cell) -> Point:
    """(x, y) of a cell centre: x is the column, y is the row."""
    return (float(cell.col), float(cell.row))


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segments_cross(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Proper crossing only: touching or collinear overlap does not count."""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def passes_through(a: Cell, b: Cell, other: Cell) -> bool:
    """True if the segment from a to b runs through the block in `other`."""
    (x1, y1), (x2, y2) = centre(a), centre(b)
    x, y = centre(other)
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return False
    t = ((x - x1) * dx + (y - y1) * dy) / length_sq
    if not 0 < t < 1:
        return False
    px, py = x1 + t * dx, y1 + t * dy
    return abs(px - x) < THROUGH_DX and abs(py - y) < THROUGH_DY
