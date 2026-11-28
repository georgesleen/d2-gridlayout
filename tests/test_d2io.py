import shutil
from pathlib import Path
from typing import Any

import pytest

from d2_gridlayout.d2io import (
    BEGIN, Pos, Size, build_diagram, load_diagram, nest, read_positions, strip_positions, unnest,
    write_positions,
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


def test_nest_places_containers_around_children_and_round_trips() -> None:
    absolute = {"a": Pos(0, 0), "g.b": Pos(200, 300), "g.h.c": Pos(400, 500)}
    rel, shift = nest(absolute)
    assert rel["g"] == Pos(140, 240)  # TALA_PADDING above and left of g.b
    assert rel["g.b"] == Pos(0, 0)
    assert rel["g.h"] == Pos(140, 140)
    assert rel["g.h.c"] == Pos(0, 0)
    assert shift == Pos(0, 0)
    assert {k: v for k, v in unnest(rel, shift).items() if k in absolute} == absolute


def test_nest_shifts_negative_positions_and_unnest_restores_them() -> None:
    absolute = {"g.b": Pos(10, 20), "c": Pos(-5, 0)}
    rel, shift = nest(absolute)
    assert shift == Pos(50, 40)
    assert min(v.top for k, v in rel.items() if "." not in k) == 0
    assert {k: v for k, v in unnest(rel, shift).items() if k in absolute} == absolute


def test_positions_in_containers_round_trip() -> None:
    sizes = {NodeId("a"): Size(300, 60), NodeId("grp.c"): Size(100, 40)}
    p = Placement({NodeId("a"): Cell(0, 0), NodeId("grp.c"): Cell(0, 1)})
    out = write_positions("a\ngrp: {c}\n", p, sizes, RULES)
    assert "grp.c.top: 0" in out and "grp.top:" in out
    assert read_positions(out, sizes, RULES) == p


@pytest.mark.skipif(not HELPER_READY, reason="needs node and `npm install`")
def test_nested_file_compiles_with_d2(tmp_path: Path) -> None:
    if shutil.which("d2") is None:
        pytest.skip("needs the d2 CLI")
    import subprocess
    f = tmp_path / "t.d2"
    f.write_text('a: "A"\ng: {b: "B"}\na -> g.b\n')
    d = load_diagram(f, RULES)
    p = Placement({NodeId("a"): Cell(0, 0), NodeId("g.b"): Cell(0, 1)})
    f.write_text(write_positions(f.read_text(), p, d.sizes, RULES))
    subprocess.run(["d2", str(f), str(tmp_path / "t.svg")], check=True, capture_output=True)


@pytest.mark.skipif(not HELPER_READY, reason="needs node and `npm install`")
def test_stale_invalid_positions_block_is_ignored(tmp_path: Path) -> None:
    f = tmp_path / "t.d2"
    f.write_text(f'a: "A"\n{BEGIN}\na.top: -5\na.left: 0\n# --- end d2-gridlayout ---\n')
    assert load_diagram(f, RULES).graph.nodes == (NodeId("a"),)


BOX_RULES = parse_rules({
    "grid": {"rows": 3, "cols": 3, "col_px": 400, "row_px": 120},
    "boxes": {"bg": ["a", "b"]},
    "options": {"box_padding": 20, "box_label_px": 30},
})


def test_box_is_left_out_of_placement() -> None:
    data = raw()
    data["nodes"].append({"id": "bg", "width": 10, "height": 10, "container": False})
    assert NodeId("bg") not in build_diagram(data, BOX_RULES).graph.nodes


def test_box_encloses_members_with_padding_and_label_room() -> None:
    sizes = {NodeId("a"): Size(300, 60), NodeId("b"): Size(200, 60)}
    p = Placement({NodeId("a"): Cell(0, 0), NodeId("b"): Cell(1, 1)})
    out = write_positions("a\nb\nbg\n", p, sizes, BOX_RULES)
    # a spans left 50..350, top 30..90; b spans left 500..700, top 150..210.
    # The box top is 30 - 20 - 30 = -20, so everything shifts down by 20.
    assert "bg.top: 0" in out and "bg.left: 30" in out
    assert "bg.width: 690" in out and "bg.height: 250" in out
    assert "a.top: 50" in out
    assert read_positions(out, sizes, BOX_RULES) == p


def test_box_with_no_members_rejected() -> None:
    rules = parse_rules({"grid": {"rows": 1, "cols": 1}, "boxes": {"bg": ["zzz"]}})
    with pytest.raises(ValueError):
        write_positions("a\n", Placement({NodeId("a"): Cell(0, 0)}), {NodeId("a"): Size(10, 10)}, rules)


def test_nested_box_id_rejected() -> None:
    with pytest.raises(ValueError):
        parse_rules({"grid": {"rows": 1, "cols": 1}, "boxes": {"g.bg": ["a"]}})


def test_box_can_enclose_another_box() -> None:
    rules = parse_rules({
        "grid": {"rows": 3, "cols": 3, "col_px": 400, "row_px": 120},
        "boxes": {"outer": ["inner", "b"], "inner": ["a"]},
        "options": {"box_padding": 20, "box_label_px": 30},
    })
    sizes = {NodeId("a"): Size(300, 60), NodeId("b"): Size(200, 60)}
    p = Placement({NodeId("a"): Cell(1, 0), NodeId("b"): Cell(1, 1)})
    out = write_positions("a\nb\n", p, sizes, rules)
    # inner: a at top 150, left 50 -> inner top 100, left 30; outer is another 50 up and 20 left.
    assert "inner.top: 100" in out and "outer.top: 50" in out and "outer.left: 10" in out


def test_boxes_that_enclose_each_other_are_rejected() -> None:
    rules = parse_rules({"grid": {"rows": 1, "cols": 1}, "boxes": {"x": ["y"], "y": ["x"]}})
    with pytest.raises(ValueError):
        write_positions("a\n", Placement({NodeId("a"): Cell(0, 0)}), {NodeId("a"): Size(10, 10)}, rules)
