import shutil
from pathlib import Path
from typing import Any

import pytest

from d2_gridlayout.d2io import (
    BEGIN, Size, build_diagram, load_diagram, read_positions, strip_positions, write_positions,
)
from d2_gridlayout.model import Cell, Direction, NodeId, Placement
from d2_gridlayout.rules import parse_rules

RULES = parse_rules({
    "grid": {"rows": 3, "cols": 3, "col_px": 400, "row_px": 120},
    "directions": {"pwr": "down", "sig": "right"},
    "pins": {"a": [0, 0]},
    "options": {"ignore": ["_*"]},
})


def raw(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "nodes": [
            {"id": "a", "width": 300, "height": 60, "container": False},
            {"id": "b", "width": 200, "height": 60, "container": False},
            {"id": "grp", "width": 500, "height": 200, "container": True},
            {"id": "grp.c", "width": 100, "height": 40, "container": False},
            {"id": "_spacer", "width": 10, "height": 10, "container": False},
        ],
        "edges": [
            {"src": "a", "dst": "b", "srcArrow": False, "dstArrow": True, "classes": ["pwr"]},
            {"src": "a", "dst": "b", "srcArrow": True, "dstArrow": False, "classes": ["sig"]},
            {"src": "a", "dst": "grp", "srcArrow": False, "dstArrow": True, "classes": []},
        ],
    }
    data.update(overrides)
    return data


def test_containers_and_ignored_nodes_are_left_out() -> None:
    d = build_diagram(raw(), RULES)
    assert d.graph.nodes == (NodeId("a"), NodeId("b"), NodeId("grp.c"))
    assert d.skipped_edges == ("a -> grp",)


def test_reverse_arrow_is_flipped_and_classes_map_to_directions() -> None:
    e1, e2 = build_diagram(raw(), RULES).graph.edges
    assert (e1.src, e1.dst, e1.direction) == ("a", "b", Direction.DOWN)
    assert (e2.src, e2.dst, e2.direction) == ("b", "a", Direction.RIGHT)


def test_positions_round_trip_and_replace_old_block() -> None:
    sizes = {NodeId("a"): Size(300, 60), NodeId("b"): Size(200, 60)}
    p = Placement({NodeId("a"): Cell(0, 0), NodeId("b"): Cell(2, 1)})
    once = write_positions("a\nb\n", p, sizes, RULES)
    twice = write_positions(once, p, sizes, RULES)
    assert twice == once and twice.count(BEGIN) == 1
    assert "b.left: 500" in once and "b.top: 270" in once  # centred in its cell
    assert read_positions(once, sizes, RULES) == p
    assert strip_positions(once) == "a\nb\n"


def test_bad_direction_rejected() -> None:
    with pytest.raises(ValueError):
        parse_rules({"grid": {"rows": 1, "cols": 1}, "directions": {"pwr": "up"}})


def test_pin_outside_grid_rejected() -> None:
    with pytest.raises(ValueError):
        parse_rules({"grid": {"rows": 1, "cols": 1}, "pins": {"a": [3, 0]}})


HELPER_READY = shutil.which("node") is not None and (
    Path(__file__).parents[1] / "node_modules" / "@terrastruct" / "d2"
).exists()


@pytest.mark.skipif(not HELPER_READY, reason="needs node and `npm install`")
def test_reads_a_real_d2_file(tmp_path: Path) -> None:
    f = tmp_path / "t.d2"
    f.write_text('a: "A"\nb: "B"\na <- b: {class: sig}\nclasses: {sig: {style.stroke: blue}}\n')
    (edge,) = load_diagram(f, RULES).graph.edges
    assert (edge.src, edge.dst, edge.direction) == ("b", "a", Direction.RIGHT)


@pytest.mark.skipif(not HELPER_READY, reason="needs node and `npm install`")
def test_written_file_still_compiles(tmp_path: Path) -> None:
    f = tmp_path / "t.d2"
    f.write_text('a: "A"\nb: "B"\na -> b\n')
    d = load_diagram(f, RULES)
    p = Placement({NodeId("a"): Cell(0, 0), NodeId("b"): Cell(1, 0)})
    f.write_text(write_positions(f.read_text(), p, d.sizes, RULES))
    assert load_diagram(f, RULES).graph.nodes == (NodeId("a"), NodeId("b"))


def test_comma_class_list_warns(capsys: pytest.CaptureFixture[str]) -> None:
    data = raw(edges=[{"src": "a", "dst": "b", "srcArrow": False, "dstArrow": True, "classes": ["pwr, sig"]}])
    build_diagram(data, RULES)
    assert "separates class lists with ';'" in capsys.readouterr().err
