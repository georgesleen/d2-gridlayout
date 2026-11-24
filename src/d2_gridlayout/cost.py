"""Layout cost: how well a placement follows the direction rules and stays clean."""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import centre, passes_through, segments_cross
from .model import Direction, Edge, Graph, NodeId, Placement


@dataclass(frozen=True)
class Weights:
    """Penalty for each kind of defect. Tune per diagram if needed."""

    aligned_backwards: float = 30.0  # straight, but pointing the wrong way
    diagonal_forward: float = 4.0  # diagonal that still heads the right way
    perpendicular: float = 12.0  # straight, but across the preferred axis
    diagonal_backwards: float = 25.0
    free_diagonal: float = 6.0  # FREE edges prefer straight lines
    length: float = 1.0  # per cell beyond adjacent
    through_block: float = 60.0
    crossing: float = 12.0
    span: float = 6.0  # per row or column the layout occupies


@dataclass(frozen=True)
class Breakdown:
    direction: float
    length: float
    through: float
    crossings: float
    span: float
    through_pairs: tuple[tuple[Edge, NodeId], ...] = field(default=())
    crossing_pairs: tuple[tuple[Edge, Edge], ...] = field(default=())

    @property
    def total(self) -> float:
        return self.direction + self.length + self.through + self.crossings + self.span


def direction_cost(e: Edge, p: Placement, w: Weights) -> float:
    a, b = p.cells[e.src], p.cells[e.dst]
    dr, dc = b.row - a.row, b.col - a.col
    if e.direction is Direction.FREE:
        return 0.0 if dr == 0 or dc == 0 else w.free_diagonal
    # Express the move along the preferred axis (along) and across it.
    along, across = (dr, dc) if e.direction is Direction.DOWN else (dc, dr)
    if across == 0:
        return 0.0 if along > 0 else w.aligned_backwards
    if along > 0:
        return w.diagonal_forward
    if along == 0:
        return w.perpendicular
    return w.diagonal_backwards


def length_cost(e: Edge, p: Placement, w: Weights) -> float:
    a, b = p.cells[e.src], p.cells[e.dst]
    return w.length * (abs(a.row - b.row) + abs(a.col - b.col) - 1)


def evaluate(g: Graph, p: Placement, w: Weights = Weights()) -> Breakdown:
    occupant = p.occupant()
    direction = sum(direction_cost(e, p, w) for e in g.edges)
    length = sum(length_cost(e, p, w) for e in g.edges)

    through: list[tuple[Edge, NodeId]] = []
    for e in g.edges:
        a, b = p.cells[e.src], p.cells[e.dst]
        for cell, node in occupant.items():
            if node not in (e.src, e.dst) and passes_through(a, b, cell):
                through.append((e, node))

    crossings: list[tuple[Edge, Edge]] = []
    es = g.edges
    for i in range(len(es)):
        for j in range(i + 1, len(es)):
            e1, e2 = es[i], es[j]
            if {e1.src, e1.dst} & {e2.src, e2.dst}:
                continue
            if segments_cross(
                centre(p.cells[e1.src]), centre(p.cells[e1.dst]),
                centre(p.cells[e2.src]), centre(p.cells[e2.dst]),
            ):
                crossings.append((e1, e2))

    rows = [c.row for c in p.cells.values()]
    cols = [c.col for c in p.cells.values()]
    span = w.span * ((max(rows) - min(rows)) + (max(cols) - min(cols))) if rows else 0.0

    return Breakdown(
        direction=direction,
        length=length,
        through=w.through_block * len(through),
        crossings=w.crossing * len(crossings),
        span=span,
        through_pairs=tuple(through),
        crossing_pairs=tuple(crossings),
    )
