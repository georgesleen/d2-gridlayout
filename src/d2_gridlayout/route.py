"""Hand routes: rewrite chosen connection paths in a rendered D2 SVG."""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

END_GAP = 4
"""Gap D2 leaves between a line end and its shape, in px."""
CORNER = 10
"""Corner radius of a routed line, in px."""
LABEL_RISE = 12
"""Height of a label's baseline above its line, in px."""


class Side(Enum):
    """A side of a block where a route leaves or arrives."""

    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"

    @property
    def horizontal(self) -> bool:
        """True when a line through this side runs left or right."""
        return self in (Side.LEFT, Side.RIGHT)


@dataclass(frozen=True)
class RouteSpec:
    """How to route one edge: the side it leaves from, the side it enters, and the gap.

    `gap` is the length, in px, of the last leg into a side that is not
    parallel to the first leg. `offset` moves the line along the entry side,
    in px, so that two lines between the same blocks stay apart. `center`
    starts an L at the middle of the exit side instead, and `gap` is then unused.
    """

    exit: Side
    enter: Side
    gap: int = 40
    offset: int = 0
    center: bool = False


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


Point = tuple[float, float]


def _edge_point(r: Rect, side: Side, along: float) -> Point:
    """The point on `side` of `r`, END_GAP outside it, at coordinate `along` on that side."""
    if side is Side.LEFT:
        return (r.x - END_GAP, along)
    if side is Side.RIGHT:
        return (r.right + END_GAP, along)
    if side is Side.TOP:
        return (along, r.y - END_GAP)
    return (along, r.bottom + END_GAP)


def _span(r: Rect, side: Side) -> tuple[float, float]:
    return (r.y, r.bottom) if side.horizontal else (r.x, r.right)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def route_points(src: Rect, dst: Rect, spec: RouteSpec) -> list[Point]:
    """The corner points of an orthogonal route from `src` to `dst`.

    Parallel sides give a straight line where the blocks overlap, else a Z
    with its middle leg halfway between them. Perpendicular sides give an L
    whose last leg is `spec.gap` long, or longer when the source does not
    reach that far.

    Raises:
        ValueError: when the sides cannot be joined by an L that enters the
            chosen side from outside.
    """
    margin = 8
    if spec.exit.horizontal == spec.enter.horizontal:
        s_lo, s_hi = _span(src, spec.exit)
        d_lo, d_hi = _span(dst, spec.enter)
        s_mid = (s_lo + s_hi) / 2
        m = min(margin, (s_hi - s_lo) / 2, (d_hi - d_lo) / 2)
        lo, hi = max(s_lo, d_lo) + m, min(s_hi, d_hi) - m
        if lo <= hi:
            along = (_clamp(s_mid, lo, hi) if d_lo <= s_mid <= d_hi else (lo + hi) / 2) + spec.offset
            return [_edge_point(src, spec.exit, along), _edge_point(dst, spec.enter, along)]
        a = _edge_point(src, spec.exit, s_mid)
        b = _edge_point(dst, spec.enter, (d_lo + d_hi) / 2)
        if spec.exit.horizontal:
            mx = (a[0] + b[0]) / 2
            return [a, (mx, a[1]), (mx, b[1]), b]
        my = (a[1] + b[1]) / 2
        return [a, (a[0], my), (b[0], my), b]

    # Perpendicular: first leg leaves src along the exit axis, last leg enters dst.
    d_lo, d_hi = _span(dst, spec.enter)
    s_lo, s_hi = _span(src, spec.exit)
    end = _edge_point(dst, spec.enter, (d_lo + d_hi) / 2 + spec.offset)
    toward = {Side.TOP: -1, Side.BOTTOM: 1, Side.LEFT: -1, Side.RIGHT: 1}[spec.enter]
    s_mid = (s_lo + s_hi) / 2
    if spec.exit.horizontal:  # enter is top or bottom
        y = s_mid if spec.center else _clamp(end[1] + toward * spec.gap, s_lo + margin, s_hi - margin)
        if (y - end[1]) * toward <= 0:
            raise ValueError("source does not reach past the entry side")
        start = _edge_point(src, spec.exit, y)
        return [start, (end[0], y), end]
    x = s_mid if spec.center else _clamp(end[0] + toward * spec.gap, s_lo + margin, s_hi - margin)
    if (x - end[0]) * toward <= 0:
        raise ValueError("source does not reach past the entry side")
    start = _edge_point(src, spec.exit, x)
    return [start, (x, end[1]), end]


def _fmt(v: float) -> str:
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def path_d(points: list[Point], radius: float = CORNER) -> str:
    """An SVG path through `points` with rounded corners, in D2's style."""
    out = [f"M {_fmt(points[0][0])} {_fmt(points[0][1])}"]
    for prev, corner, nxt in zip(points, points[1:], points[2:]):
        r_in = min(radius, _dist(prev, corner) / 2)
        r_out = min(radius, _dist(corner, nxt) / 2)
        a = _toward(corner, prev, r_in)
        b = _toward(corner, nxt, r_out)
        out.append(f"L {_fmt(a[0])} {_fmt(a[1])} S {_fmt(corner[0])} {_fmt(corner[1])} {_fmt(b[0])} {_fmt(b[1])}")
    out.append(f"L {_fmt(points[-1][0])} {_fmt(points[-1][1])}")
    return " ".join(out)


def _dist(a: Point, b: Point) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _toward(origin: Point, target: Point, d: float) -> Point:
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    n = abs(dx) + abs(dy)
    return (origin[0] + dx / n * d, origin[1] + dy / n * d) if n else origin


def label_anchor(points: list[Point]) -> Point:
    """Where a route's label goes: above the middle of its longest horizontal leg.

    A route with no horizontal leg gets its label beside its longest leg.
    """
    legs = list(zip(points, points[1:]))
    flat = [(a, b) for a, b in legs if a[1] == b[1]]
    a, b = max(flat or legs, key=lambda ab: _dist(*ab))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    return (mx, my - LABEL_RISE) if flat else (mx + 2 * LABEL_RISE, my)


_SHAPE = re.compile(
    r'<g class="(?P<id>[A-Za-z0-9+/=]+)[^"]*"><g class="shape" ><(?:rect|image)[^>]*?'
    r' x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)" width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)"'
)
_ELLIPSE = re.compile(
    r'<g class="(?P<id>[A-Za-z0-9+/=]+)[^"]*"><g class="shape" ><ellipse[^>]*?'
    r' rx="(?P<rx>[\d.]+)" ry="(?P<ry>[\d.]+)" cx="(?P<cx>[-\d.]+)" cy="(?P<cy>[-\d.]+)"'
)
_GROUP = re.compile(r'<g class="(?P<id>[A-Za-z0-9+/=]+)[^"]*">(?P<body>(?:(?!</g>).)*?<path d="[^"]*".*?)</g>', re.S)
_TEXT = re.compile(r'<text x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)"')


def _decode(b64: str) -> str | None:
    try:
        return html.unescape(base64.b64decode(b64).decode())
    except (ValueError, UnicodeDecodeError):
        return None


def shapes(svg: str) -> dict[str, Rect]:
    """The bounding rectangle of every rect, image, circle or oval shape in a D2 SVG, by D2 id."""
    out: dict[str, Rect] = {}
    for m in _SHAPE.finditer(svg):
        name = _decode(m["id"])
        if name is not None:
            out[name] = Rect(float(m["x"]), float(m["y"]), float(m["w"]), float(m["h"]))
    for m in _ELLIPSE.finditer(svg):
        name = _decode(m["id"])
        if name is not None:
            rx, ry = float(m["rx"]), float(m["ry"])
            out[name] = Rect(float(m["cx"]) - rx, float(m["cy"]) - ry, 2 * rx, 2 * ry)
    return out


_EDGE_KEY = re.compile(r"^\(?\s*(?P<src>\S+)\s+(?P<op><->|->|<-|--)\s+(?P<dst>[^)\s\[]+)\s*\)?(?:\[(?P<i>\d+)\])?$")


def edge_id(key: str) -> tuple[str, str, str]:
    """Normalise a route key such as `a -> b` or `a -> b[1]` to D2's id, source and target.

    Raises:
        ValueError: for a key that is not an edge.
    """
    m = _EDGE_KEY.match(key.strip())
    if m is None:
        raise ValueError(f"[routes] {key!r} is not an edge like 'a -> b' or 'a -> b[1]'")
    return f"({m['src']} {m['op']} {m['dst']})[{m['i'] or 0}]", m["src"], m["dst"]


def apply_routes(svg: str, routes: Mapping[str, RouteSpec]) -> str:
    """Rewrite the paths, labels and label masks of the routed edges in a D2 SVG.

    Raises:
        ValueError: when a routed edge or one of its blocks is not in the SVG.
    """
    rects = shapes(svg)
    wanted = {edge_id(k)[0]: (edge_id(k), spec) for k, spec in routes.items()}
    found: set[str] = set()
    mask_moves: list[tuple[Point, Point]] = []

    def rewrite(m: re.Match[str]) -> str:
        name = _decode(m["id"])
        if name not in wanted:
            return m.group(0)
        (_, src, dst), spec = wanted[name]
        if src not in rects or dst not in rects:
            raise ValueError(f"[routes] {name}: block {src if src not in rects else dst} not found")
        found.add(name)
        pts = route_points(rects[src], rects[dst], spec)
        body = re.sub(r'<path d="[^"]*"', f'<path d="{path_d(pts)}"', m["body"], count=1)
        t = _TEXT.search(body)
        if t is not None:
            ax, ay = label_anchor(pts)
            old_x, old_y = float(t["x"]), float(t["y"])
            body = body[: t.start()] + f'<text x="{_fmt(ax)}" y="{_fmt(ay)}"' + body[t.end():]
            mask_moves.append(((old_x, old_y), (ax, ay)))
        return m.group(0).replace(m["body"], body, 1)

    out = _GROUP.sub(rewrite, svg)
    missing = set(wanted) - found
    if missing:
        present = [n for n in (_decode(m["id"]) for m in _GROUP.finditer(svg)) if n and n.startswith("(")]
        raise ValueError(
            f"[routes] not in the SVG: {', '.join(sorted(missing))}. "
            f"D2 numbers <-> edges across both orders; edges present: {', '.join(present)}"
        )
    for old, new in mask_moves:
        out = _move_mask(out, old, new)
    return out


_MASK_RECT = re.compile(r'<rect x="(?P<x>[-\d.]+)" y="(?P<y>[-\d.]+)" width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)" fill="rgba\(0,0,0,0.75\)"></rect>')


def _move_mask(svg: str, old: Point, new: Point) -> str:
    """Move the mask hole under a label from its old text anchor to a new one."""
    (ox, oy), (nx, ny) = old, new
    for m in _MASK_RECT.finditer(svg):
        x, y, w = float(m["x"]), float(m["y"]), float(m["w"])
        if abs(x + w / 2 - ox) <= 1 and abs(y + 20 - oy) <= 1:
            moved = m.group(0).replace(f'x="{m["x"]}"', f'x="{_fmt(nx - w / 2)}"', 1)
            moved = moved.replace(f'y="{m["y"]}"', f'y="{_fmt(ny - 20)}"', 1)
            return svg[: m.start()] + moved + svg[m.end():]
    return svg
