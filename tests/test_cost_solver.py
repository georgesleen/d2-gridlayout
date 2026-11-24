import itertools

import pytest

from d2_gridlayout.cost import Weights, direction_cost, evaluate
from d2_gridlayout.model import Cell, Direction, Edge, EdgeKind, Graph, Grid, NodeId, Placement
from d2_gridlayout.solver import anneal, brute_force

A, B, C, D = (NodeId(x) for x in "abcd")
PWR, SIG = EdgeKind("pwr"), EdgeKind("sig")


def down(s: NodeId, d: NodeId) -> Edge:
    return Edge(s, d, PWR, Direction.DOWN)


def right(s: NodeId, d: NodeId) -> Edge:
    return Edge(s, d, SIG, Direction.RIGHT)


W = Weights()


@pytest.mark.parametrize(
    "dst,expected",
    [
        (Cell(2, 1), 0.0),
        (Cell(0, 1), W.aligned_backwards),
        (Cell(2, 2), W.diagonal_forward),
        (Cell(1, 2), W.perpendicular),
        (Cell(0, 2), W.diagonal_backwards),
    ],
)
def test_down_edge_direction_cost(dst: Cell, expected: float) -> None:
    p = Placement({A: Cell(1, 1), B: dst})
    assert direction_cost(down(A, B), p, W) == expected


def test_right_edge_uses_columns() -> None:
    p = Placement({A: Cell(1, 1), B: Cell(1, 3)})
    assert direction_cost(right(A, B), p, W) == 0.0


def test_x_layout_reports_one_crossing() -> None:
    g = Graph((A, B, C, D), (down(A, D), down(B, C)))
    p = Placement({A: Cell(0, 0), B: Cell(0, 1), C: Cell(1, 0), D: Cell(1, 1)})
    assert len(evaluate(g, p).crossing_pairs) == 1


def test_line_through_block_is_reported() -> None:
    g = Graph((A, B, C), (down(A, C),))
    p = Placement({A: Cell(0, 0), B: Cell(1, 0), C: Cell(2, 0)})
    assert evaluate(g, p).through_pairs == ((g.edges[0], B),)


def test_anneal_finds_straight_power_column_and_signal_row() -> None:
    # a -> b -> c should stack vertically; b -> d should sit to b's right.
    g = Graph((A, B, C, D), (down(A, B), down(B, C), right(B, D)))
    p = anneal(g, Grid(4, 4), iterations=8000, seed=1)
    a, b, c, d = (p.cells[n] for n in (A, B, C, D))
    assert a.col == b.col == c.col and a.row + 1 == b.row and b.row + 1 == c.row
    assert d.row == b.row and d.col == b.col + 1


def test_anneal_respects_pins() -> None:
    g = Graph((A, B, C), (down(A, B), down(B, C)))
    p = anneal(g, Grid(3, 3), pinned={A: Cell(0, 2)}, iterations=3000, seed=2)
    assert p.cells[A] == Cell(0, 2)


def test_brute_force_matches_exhaustive_minimum() -> None:
    g = Graph((A, B, C, D), (down(A, B), right(B, C), down(C, D)))
    grid = Grid(3, 3)
    fixed = Placement({A: Cell(0, 0)})
    got = brute_force(g, grid, fixed, [B, C, D])
    free_cells = [c for c in grid.cells() if c != Cell(0, 0)]
    best = min(
        evaluate(g, Placement({A: Cell(0, 0), B: b, C: c, D: d})).total
        for b, c, d in itertools.permutations(free_cells, 3)
    )
    assert evaluate(g, got).total == best


def test_brute_force_rejects_unplaced_nodes() -> None:
    g = Graph((A, B), (down(A, B),))
    with pytest.raises(ValueError):
        brute_force(g, Grid(2, 2), Placement({}), [A])
