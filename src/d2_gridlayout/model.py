"""Core types: graph, grid cells and placements."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, NewType

NodeId = NewType("NodeId", str)
EdgeKind = NewType("EdgeKind", str)


class Direction(Enum):
    """Preferred direction for an edge, from its arrow tail to its head."""

    DOWN = "down"
    RIGHT = "right"
    FREE = "free"


@dataclass(frozen=True, order=True)
class Cell:
    row: int
    col: int

    def __post_init__(self) -> None:
        if self.row < 0 or self.col < 0:
            raise ValueError(f"cell coordinates must be non-negative: {self}")


@dataclass(frozen=True)
class Edge:
    src: NodeId
    dst: NodeId
    kind: EdgeKind
    direction: Direction


@dataclass(frozen=True)
class Graph:
    nodes: tuple[NodeId, ...]
    edges: tuple[Edge, ...]

    def __post_init__(self) -> None:
        known = set(self.nodes)
        if len(known) != len(self.nodes):
            raise ValueError("duplicate node ids")
        for e in self.edges:
            if e.src not in known or e.dst not in known:
                raise ValueError(f"edge references unknown node: {e}")


@dataclass(frozen=True)
class Grid:
    rows: int
    cols: int

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("grid must have at least one row and column")

    def cells(self) -> list[Cell]:
        return [Cell(r, c) for r in range(self.rows) for c in range(self.cols)]

    def contains(self, cell: Cell) -> bool:
        return cell.row < self.rows and cell.col < self.cols


@dataclass(frozen=True)
class Placement:
    """One cell per node; no two nodes share a cell."""

    cells: Mapping[NodeId, Cell] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(set(self.cells.values())) != len(self.cells):
            raise ValueError("two nodes share a cell")

    def occupant(self) -> dict[Cell, NodeId]:
        return {c: n for n, c in self.cells.items()}
