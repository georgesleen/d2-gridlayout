"""Placement search: simulated annealing, and brute force for a few nodes.

Lesson from use: annealing from a random start often settles on layouts that
score well but read badly. Pin the nodes you care about (inputs at the top,
the main chain in a row) and let the solver place the rest.
"""

from __future__ import annotations

import itertools
import math
import random
from typing import Mapping, Sequence

from .cost import Weights, evaluate
from .model import Cell, Graph, Grid, NodeId, Placement

BRUTE_FORCE_LIMIT = 2_000_000


def _check_pins(g: Graph, grid: Grid, pinned: Mapping[NodeId, Cell]) -> None:
    for n, c in pinned.items():
        if n not in g.nodes:
            raise ValueError(f"pinned node not in graph: {n}")
        if not grid.contains(c):
            raise ValueError(f"pin outside grid: {n} at {c}")
    if len(set(pinned.values())) != len(pinned):
        raise ValueError("two pins share a cell")
    if len(g.nodes) > grid.rows * grid.cols:
        raise ValueError("grid has fewer cells than nodes")


def random_start(g: Graph, grid: Grid, pinned: Mapping[NodeId, Cell], rng: random.Random) -> Placement:
    taken = set(pinned.values())
    free_cells = [c for c in grid.cells() if c not in taken]
    rng.shuffle(free_cells)
    cells: dict[NodeId, Cell] = dict(pinned)
    for n in g.nodes:
        if n not in cells:
            cells[n] = free_cells.pop()
    return Placement(cells)


def anneal(
    g: Graph,
    grid: Grid,
    *,
    pinned: Mapping[NodeId, Cell] | None = None,
    start: Placement | None = None,
    weights: Weights = Weights(),
    iterations: int = 30_000,
    t_start: float = 20.0,
    seed: int = 0,
) -> Placement:
    pins = dict(pinned or {})
    _check_pins(g, grid, pins)
    rng = random.Random(seed)
    cells = dict((start or random_start(g, grid, pins, rng)).cells)
    for n, c in pins.items():
        if cells.get(n) != c:
            raise ValueError(f"start placement disagrees with pin for {n}")
    movable = [n for n in g.nodes if n not in pins]
    if not movable:
        return Placement(cells)
    all_cells = grid.cells()

    cur = evaluate(g, Placement(cells), weights).total
    best, best_cells = cur, dict(cells)
    for i in range(iterations):
        t = t_start * (1 - i / iterations) + 0.05
        n = rng.choice(movable)
        old, target = cells[n], rng.choice(all_cells)
        other = next((k for k, v in cells.items() if v == target), None)
        if other is not None and other in pins:
            continue
        cells[n] = target
        if other is not None:
            cells[other] = old
        new = evaluate(g, Placement(cells), weights).total
        if new <= cur or rng.random() < math.exp((cur - new) / t):
            cur = new
            if cur < best:
                best, best_cells = cur, dict(cells)
        else:
            cells[n] = old
            if other is not None:
                cells[other] = target
    return Placement(best_cells)


def best_of(
    g: Graph, grid: Grid, seeds: Sequence[int], **kwargs: object
) -> Placement:
    """Run anneal once per seed and keep the lowest-cost result."""
    weights = kwargs.get("weights", Weights())
    assert isinstance(weights, Weights)
    results = [anneal(g, grid, seed=s, **kwargs) for s in seeds]  # type: ignore[arg-type]
    return min(results, key=lambda p: evaluate(g, p, weights).total)


def brute_force(
    g: Graph,
    grid: Grid,
    fixed: Placement,
    free: Sequence[NodeId],
    *,
    candidates: Sequence[Cell] | None = None,
    weights: Weights = Weights(),
) -> Placement:
    """Try every assignment of `free` nodes to the remaining candidate cells."""
    missing = set(g.nodes) - set(fixed.cells) - set(free)
    if missing:
        raise ValueError(f"nodes neither fixed nor free: {sorted(missing)}")
    taken = set(fixed.cells.values())
    pool = [c for c in (candidates or grid.cells()) if c not in taken and grid.contains(c)]
    count = math.perm(len(pool), len(free))
    if count > BRUTE_FORCE_LIMIT:
        raise ValueError(f"{count} combinations; narrow candidates or free fewer nodes")
    best: tuple[float, Placement] | None = None
    for combo in itertools.permutations(pool, len(free)):
        p = Placement({**fixed.cells, **dict(zip(free, combo))})
        score = evaluate(g, p, weights).total
        if best is None or score < best[0]:
            best = (score, p)
    if best is None:
        raise ValueError("not enough free cells")
    return best[1]
