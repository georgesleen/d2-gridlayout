import pytest

from d2_gridlayout.geometry import passes_through, segments_cross
from d2_gridlayout.model import Cell, Edge, EdgeKind, Graph, Direction, NodeId, Placement


def test_x_shape_crosses() -> None:
    assert segments_cross((0, 0), (2, 2), (0, 2), (2, 0))


def test_shared_endpoint_does_not_cross() -> None:
    assert not segments_cross((0, 0), (2, 2), (2, 2), (4, 0))


def test_parallel_lines_do_not_cross() -> None:
    assert not segments_cross((0, 0), (2, 0), (0, 1), (2, 1))


def test_straight_line_through_middle_block() -> None:
    assert passes_through(Cell(0, 0), Cell(0, 2), Cell(0, 1))


def test_line_misses_block_in_other_row() -> None:
    assert not passes_through(Cell(0, 0), Cell(0, 2), Cell(1, 1))


def test_endpoints_are_not_through() -> None:
    assert not passes_through(Cell(0, 0), Cell(0, 2), Cell(0, 2))


def test_shallow_diagonal_near_block() -> None:
    # (0,0) -> (1,4) passes y=0.25 at x=1: close enough to the block at (0,1).
    assert passes_through(Cell(0, 0), Cell(1, 4), Cell(0, 1))


def test_negative_cell_rejected() -> None:
    with pytest.raises(ValueError):
        Cell(-1, 0)


def test_shared_cell_rejected() -> None:
    with pytest.raises(ValueError):
        Placement({NodeId("a"): Cell(0, 0), NodeId("b"): Cell(0, 0)})


def test_edge_to_unknown_node_rejected() -> None:
    with pytest.raises(ValueError):
        Graph(
            (NodeId("a"),),
            (Edge(NodeId("a"), NodeId("b"), EdgeKind("x"), Direction.FREE),),
        )
