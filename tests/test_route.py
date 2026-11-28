import base64
import shutil
import subprocess
from pathlib import Path

import pytest

from d2_gridlayout.route import (
    END_GAP, Rect, RouteSpec, Side, apply_routes, edge_id, label_anchor, path_d, route_points, shapes,
)
from d2_gridlayout.rules import parse_rules

A = Rect(0, 0, 100, 60)  # cy 30


def test_overlapping_blocks_get_a_straight_line_at_the_source_centre() -> None:
    b = Rect(300, -100, 50, 400)
    assert route_points(A, b, RouteSpec(Side.RIGHT, Side.LEFT)) == [(100 + END_GAP, 30), (300 - END_GAP, 30)]


def test_disjoint_blocks_get_a_z_with_a_middle_leg_halfway() -> None:
    b = Rect(300, 200, 50, 60)  # cy 230
    pts = route_points(A, b, RouteSpec(Side.RIGHT, Side.LEFT))
    assert pts == [(104, 30), (200, 30), (200, 230), (296, 230)]


def test_l_route_enters_the_top_after_the_gap() -> None:
    src = Rect(500, 0, 50, 600)
    dst = Rect(100, 300, 80, 100)  # cx 140, top 300
    pts = route_points(src, dst, RouteSpec(Side.LEFT, Side.TOP, gap=40))
    assert pts == [(496, 256), (140, 256), (140, 296)]


def test_l_route_into_the_bottom() -> None:
    src = Rect(500, 0, 50, 600)
    dst = Rect(100, 300, 80, 100)
    assert route_points(src, dst, RouteSpec(Side.LEFT, Side.BOTTOM))[1] == (140, 444)


def test_l_route_that_cannot_reach_is_rejected() -> None:
    src = Rect(500, 200, 50, 100)  # wholly below the target's top
    dst = Rect(100, 50, 80, 100)
    with pytest.raises(ValueError):
        route_points(src, dst, RouteSpec(Side.LEFT, Side.TOP))


def test_path_rounds_corners() -> None:
    d = path_d([(0, 0), (100, 0), (100, 50)])
    assert d == "M 0 0 L 90 0 S 100 0 100 10 L 100 50"


def test_label_sits_above_the_longest_horizontal_leg() -> None:
    assert label_anchor([(0, 0), (10, 0), (10, 100), (210, 100)]) == (110, 88)


def test_edge_keys_normalise_to_d2_ids() -> None:
    assert edge_id("a -> b") == ("(a -> b)[0]", "a", "b")
    assert edge_id("(a <-> b)[2]") == ("(a <-> b)[2]", "a", "b")
    with pytest.raises(ValueError):
        edge_id("a b")


def test_rules_parse_routes() -> None:
    r = parse_rules({"grid": {"rows": 1, "cols": 1}, "routes": {"a -> b": {"exit": "left", "enter": "top"}}})
    assert r.routes["a -> b"] == RouteSpec(Side.LEFT, Side.TOP, 40)
    with pytest.raises(ValueError):
        parse_rules({"grid": {"rows": 1, "cols": 1}, "routes": {"a -> b": {"exit": "up", "enter": "top"}}})


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


SVG = (
    f'<g class="{_b64("a")} x"><g class="shape" ><rect x="0" y="0" width="100" height="60" /></g></g>'
    f'<g class="{_b64("b")} x"><g class="shape" ><rect x="300" y="-100" width="50" height="400" /></g></g>'
    f'<g class="{_b64("(a -&gt; b)[0]")} sig"><path d="M 1 2 L 3 4" stroke="blue" />'
    '<text x="50" y="100" fill="blue">lbl</text></g>'
    '<mask><rect x="35" y="80" width="30" height="26" fill="rgba(0,0,0,0.75)"></rect></mask>'
)


def test_apply_routes_rewrites_path_label_and_mask() -> None:
    out = apply_routes(SVG, {"a -> b": RouteSpec(Side.RIGHT, Side.LEFT)})
    assert 'd="M 104 30 L 296 30"' in out
    assert '<text x="200" y="18"' in out
    assert 'x="185" y="-2" width="30"' in out


def test_shapes_and_missing_edge() -> None:
    assert shapes(SVG)["b"] == Rect(300, -100, 50, 400)
    with pytest.raises(ValueError):
        apply_routes(SVG, {"b -> a": RouteSpec(Side.LEFT, Side.RIGHT)})


@pytest.mark.skipif(shutil.which("d2") is None, reason="needs the d2 CLI")
def test_routes_a_real_d2_render(tmp_path: Path) -> None:
    f = tmp_path / "t.d2"
    f.write_text(
        "vars: {d2-config: {layout-engine: tala}}\n"
        'a: "A" {top: 0; left: 0; width: 100; height: 60}\n'
        'b: "B" {top: 0; left: 400; width: 100; height: 400}\n'
        'a -> b: "x"\n'
    )
    svg = tmp_path / "t.svg"
    subprocess.run(["d2", str(f), str(svg)], check=True, capture_output=True)
    out = apply_routes(svg.read_text(), {"a -> b": RouteSpec(Side.RIGHT, Side.LEFT)})
    assert 'd="M 104 30 L 396 30"' in out


def test_offset_moves_a_straight_line_along_the_entry_side() -> None:
    b = Rect(300, -100, 50, 400)
    assert route_points(A, b, RouteSpec(Side.RIGHT, Side.LEFT, offset=10))[0] == (104, 40)


def test_centered_l_leaves_the_middle_of_the_exit_side() -> None:
    src = Rect(0, 200, 100, 60)  # cx 50
    dst = Rect(300, 0, 100, 60)  # cy 30
    pts = route_points(src, dst, RouteSpec(Side.TOP, Side.LEFT, center=True))
    assert pts == [(50, 196), (50, 30), (296, 30)]


def test_shapes_reads_circles_as_their_bounding_box() -> None:
    svg = f'<g class="{_b64("j")} x"><g class="shape" ><ellipse rx="7" ry="7" cx="100" cy="50" /></g></g>'
    assert shapes(svg)["j"] == Rect(93, 43, 14, 14)


def test_small_block_still_gets_a_straight_line() -> None:
    dot = Rect(0, 23, 14, 14)  # cy 30
    tall = Rect(300, 0, 50, 400)
    assert route_points(dot, tall, RouteSpec(Side.RIGHT, Side.LEFT)) == [(18, 30), (296, 30)]
