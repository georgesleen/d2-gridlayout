"""Read the graph out of a D2 file, and write grid positions back into it."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, NamedTuple

from .model import Cell, Edge, EdgeKind, Graph, NodeId, Placement
from .rules import DEFAULT_KIND, Rules

HELPER = Path(__file__).with_name("d2_graph.mjs")
BEGIN = "# --- d2-gridlayout positions (generated, edits here are overwritten) ---"
END = "# --- end d2-gridlayout ---"
OFFSET = "# offset"
TALA_PADDING = 60
"""Gap TALA puts between a container's edge and a child at top/left 0, in px."""


@dataclass(frozen=True)
class Size:
    width: float
    height: float


@dataclass(frozen=True)
class Diagram:
    graph: Graph
    sizes: Mapping[NodeId, Size]
    skipped_edges: tuple[str, ...]


def compile_d2(source: str) -> dict[str, Any]:
    """Run the Node helper on D2 source; it needs `npm install` in the repo root."""
    proc = subprocess.run(
        ["node", str(HELPER), "-"], input=source, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"D2 compile failed: {proc.stderr.strip()}")
    data: dict[str, Any] = json.loads(proc.stdout)
    return data


def build_diagram(data: Mapping[str, Any], rules: Rules) -> Diagram:
    def ignored(node_id: str) -> bool:
        return any(fnmatch.fnmatchcase(node_id, pat) for pat in rules.ignore)

    nodes: list[NodeId] = []
    sizes: dict[NodeId, Size] = {}
    for n in data["nodes"]:
        if n["container"] or ignored(n["id"]) or NodeId(n["id"]) in rules.boxes:
            continue
        nid = NodeId(n["id"])
        nodes.append(nid)
        sizes[nid] = Size(float(n["width"]), float(n["height"]))

    known = set(nodes)
    edges: list[Edge] = []
    skipped: list[str] = []
    for e in data["edges"]:
        src, dst = NodeId(e["src"]), NodeId(e["dst"])
        if e["srcArrow"] and not e["dstArrow"]:
            src, dst = dst, src  # `a <- b` is drawn from b to a
        if src not in known or dst not in known:
            skipped.append(f"{e['src']} -> {e['dst']}")
            continue
        for c in e["classes"]:
            if "," in c:
                print(f"warning: class {c!r} on {e['src']} -> {e['dst']} looks like a list; "
                      "D2 separates class lists with ';'", file=sys.stderr)
        kind = next((EdgeKind(c) for c in e["classes"] if EdgeKind(c) in rules.directions), DEFAULT_KIND)
        edges.append(Edge(src, dst, kind, rules.direction_for(kind)))

    return Diagram(Graph(tuple(nodes), tuple(edges)), sizes, tuple(skipped))


def load_diagram(path: Path, rules: Rules) -> Diagram:
    """Read a diagram, ignoring any positions block a previous run wrote."""
    return build_diagram(compile_d2(strip_positions(path.read_text())), rules)


def strip_positions(source: str) -> str:
    pattern = re.compile(rf"\n*{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.S)
    return pattern.sub("\n", source).rstrip("\n") + "\n"


class Pos(NamedTuple):
    """A block's top-left corner in px."""

    top: int
    left: int


def _parent(node: str) -> str | None:
    return node.rsplit(".", 1)[0] if "." in node else None


def nest(absolute: Mapping[str, Pos]) -> tuple[dict[str, Pos], Pos]:
    """Convert absolute block positions to the parent-relative ones TALA reads.

    Each container gets a position TALA_PADDING above and left of its
    children. Top-level positions are shifted so none is negative; the second
    value is that shift, which `unnest` takes back.
    """
    out = dict(absolute)
    ancestors = {".".join(n.split(".")[:i]) for n in absolute for i in range(1, n.count(".") + 1)}
    for c in sorted(ancestors, key=lambda c: -c.count(".")):
        kids = [v for k, v in out.items() if _parent(k) == c]
        out[c] = Pos(min(k.top for k in kids) - TALA_PADDING, min(k.left for k in kids) - TALA_PADDING)
    top_level = [v for k, v in out.items() if _parent(k) is None]
    shift = Pos(max(0, -min(v.top for v in top_level)), max(0, -min(v.left for v in top_level)))
    rel: dict[str, Pos] = {}
    for node, pos in out.items():
        parent = _parent(node)
        if parent is None:
            rel[node] = Pos(pos.top + shift.top, pos.left + shift.left)
        else:
            rel[node] = Pos(pos.top - out[parent].top - TALA_PADDING, pos.left - out[parent].left - TALA_PADDING)
    return rel, shift


def unnest(relative: Mapping[str, Pos], shift: Pos) -> dict[str, Pos]:
    """Undo `nest`: absolute positions of every block and container."""
    out: dict[str, Pos] = {}

    def resolve(node: str) -> Pos:
        if node not in out:
            pos, parent = relative[node], _parent(node)
            if parent is None:
                out[node] = Pos(pos.top - shift.top, pos.left - shift.left)
            else:
                p = resolve(parent)
                out[node] = Pos(p.top + TALA_PADDING + pos.top, p.left + TALA_PADDING + pos.left)
        return out[node]

    for node in relative:
        resolve(node)
    return out


def box_rects(
    absolute: Mapping[str, Pos], sizes: Mapping[NodeId, Size], rules: Rules
) -> dict[str, tuple[Pos, Size]]:
    """The position and size of each background box, enclosing its members.

    A member is a placed top-level block or another box.

    Raises:
        ValueError: for a box with no members, a nested member, or boxes that enclose each other.
    """
    rects: dict[str, tuple[Pos, Size]] = {n: (p, sizes[NodeId(n)]) for n, p in absolute.items()}
    out: dict[str, tuple[Pos, Size]] = {}
    pending = dict(rules.boxes)
    while pending:
        progressed = False
        for box, patterns in list(pending.items()):
            def match(n: str, patterns: tuple[str, ...] = patterns) -> bool:
                return any(fnmatch.fnmatchcase(n, p) for p in patterns)
            if any(match(b) for b in pending if b != box):
                continue  # wait for the boxes inside this one
            members = [n for n in rects if match(n)]
            if not members:
                raise ValueError(f"[boxes] {box} matches no placed block or box")
            if any("." in m for m in members):
                raise ValueError(f"[boxes] {box}: members must be top-level blocks")
            pad, label = rules.box_padding, rules.box_label_px
            top = min(rects[m][0].top for m in members) - pad - label
            left = min(rects[m][0].left for m in members) - pad
            bottom = max(rects[m][0].top + rects[m][1].height for m in members) + pad
            right = max(rects[m][0].left + rects[m][1].width for m in members) + pad
            rect = (Pos(round(top), round(left)), Size(round(right - left), round(bottom - top)))
            out[box] = rects[box] = rect
            del pending[box]
            progressed = True
        if not progressed:
            raise ValueError(f"[boxes] these boxes enclose each other: {', '.join(sorted(pending))}")
    return out


def write_positions(
    source: str, placement: Placement, sizes: Mapping[NodeId, Size], rules: Rules, *, tala: bool = True
) -> str:
    """Append a generated block of `top`/`left` settings, replacing any old one.

    Blocks are centred in their grid cell, so blocks of different sizes still
    line up and the lines between them stay straight. Blocks inside containers
    get container-relative positions, and the containers are placed around them.
    Each background box from the rules is sized to enclose its member blocks.
    """
    absolute: dict[str, Pos] = {}
    for node, cell in placement.cells.items():
        size = sizes[node]
        absolute[node] = Pos(
            round(cell.row * rules.row_px + (rules.row_px - size.height) / 2),
            round(cell.col * rules.col_px + (rules.col_px - size.width) / 2),
        )
    boxes = box_rects(absolute, sizes, rules)
    rel, shift = nest({**absolute, **{b: pos for b, (pos, _) in boxes.items()}})
    lines = [BEGIN, f"# grid {rules.grid.rows}x{rules.grid.cols}, pitch {rules.col_px}x{rules.row_px} px"]
    if shift != Pos(0, 0):
        lines.append(f"{OFFSET} {shift.top} {shift.left}")
    if tala:
        lines.append("vars: {d2-config: {layout-engine: tala}}")
    for name in sorted(rel, key=lambda n: (n.count("."), absolute.get(n, rel[n]), n)):
        lines.append(f"{name}.top: {rel[name].top}")
        lines.append(f"{name}.left: {rel[name].left}")
        if name in boxes:
            lines.append(f"{name}.width: {int(boxes[name][1].width)}")
            lines.append(f"{name}.height: {int(boxes[name][1].height)}")
    lines.append(END)
    return strip_positions(source) + "\n" + "\n".join(lines) + "\n"


def read_positions(source: str, sizes: Mapping[NodeId, Size], rules: Rules) -> Placement | None:
    """Recover the grid placement from a generated block, if there is one."""
    m = re.search(rf"{re.escape(BEGIN)}(.*?){re.escape(END)}", source, re.S)
    if m is None:
        return None
    tops: dict[str, int] = {}
    lefts: dict[str, int] = {}
    for name, attr, value in re.findall(r"^(\S+)\.(top|left): (\d+)$", m.group(1), re.M):
        (tops if attr == "top" else lefts)[name] = int(value)
    off = re.search(rf"^{re.escape(OFFSET)} (\d+) (\d+)$", m.group(1), re.M)
    shift = Pos(int(off.group(1)), int(off.group(2))) if off else Pos(0, 0)
    absolute = unnest({n: Pos(tops[n], lefts[n]) for n in tops if n in lefts}, shift)
    cells: dict[NodeId, Cell] = {}
    for node, size in sizes.items():
        if node not in absolute:
            print(f"warning: no saved position for {node}", file=sys.stderr)
            return None
        pos = absolute[node]
        col = round((pos.left + size.width / 2) / rules.col_px - 0.5)
        row = round((pos.top + size.height / 2) / rules.row_px - 0.5)
        cells[node] = Cell(row, col)
    return Placement(cells)
