"""Layout rules, read from a TOML file.

Example:

    [grid]
    rows = 11
    cols = 6
    col_px = 420      # column pitch in the rendered diagram
    row_px = 140

    [directions]      # edge class -> down | right | free
    pwr = "down"
    sig = "right"
    default = "free"  # edges with none of the classes above

    [pins]            # node id -> [row, col]
    usb = [0, 1]

    [options]
    ignore = ["_*"]   # node id globs to leave out
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .model import Cell, Direction, EdgeKind, Grid, NodeId

DEFAULT_KIND = EdgeKind("default")


@dataclass(frozen=True)
class Rules:
    grid: Grid
    col_px: int
    row_px: int
    directions: Mapping[EdgeKind, Direction]
    pins: Mapping[NodeId, Cell] = field(default_factory=dict)
    ignore: tuple[str, ...] = ()

    def direction_for(self, kind: EdgeKind) -> Direction:
        return self.directions.get(kind, self.directions.get(DEFAULT_KIND, Direction.FREE))


def _int(table: Mapping[str, Any], key: str, default: int | None = None) -> int:
    v = table.get(key, default)
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise ValueError(f"[grid] {key} must be a positive integer, got {v!r}")
    return v


def parse_rules(data: Mapping[str, Any]) -> Rules:
    g = data.get("grid", {})
    grid = Grid(_int(g, "rows"), _int(g, "cols"))

    directions: dict[EdgeKind, Direction] = {}
    for k, v in data.get("directions", {}).items():
        try:
            directions[EdgeKind(k)] = Direction(v)
        except ValueError:
            raise ValueError(f"[directions] {k} = {v!r}: use down, right or free") from None

    pins: dict[NodeId, Cell] = {}
    for k, v in data.get("pins", {}).items():
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v)):
            raise ValueError(f"[pins] {k} must be [row, col]")
        cell = Cell(v[0], v[1])
        if not grid.contains(cell):
            raise ValueError(f"[pins] {k} at {v} is outside the {grid.rows}x{grid.cols} grid")
        pins[NodeId(k)] = cell

    ignore = data.get("options", {}).get("ignore", [])
    if not all(isinstance(x, str) for x in ignore):
        raise ValueError("[options] ignore must be a list of strings")

    return Rules(grid, _int(g, "col_px", 420), _int(g, "row_px", 140), directions, pins, tuple(ignore))


def load_rules(path: Path) -> Rules:
    with path.open("rb") as f:
        return parse_rules(tomllib.load(f))
