"""Read the graph out of a D2 file, and write grid positions back into it."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .model import Cell, Edge, EdgeKind, Graph, NodeId, Placement
from .rules import DEFAULT_KIND, Rules

HELPER = Path(__file__).with_name("d2_graph.mjs")
BEGIN = "# --- d2-gridlayout positions (generated, edits here are overwritten) ---"
END = "# --- end d2-gridlayout ---"


@dataclass(frozen=True)
class Size:
    width: float
    height: float


@dataclass(frozen=True)
class Diagram:
    graph: Graph
    sizes: Mapping[NodeId, Size]
    skipped_edges: tuple[str, ...]


def compile_d2(path: Path) -> dict[str, Any]:
    """Run the Node helper; it needs `npm install` in the repo root."""
    proc = subprocess.run(
        ["node", str(HELPER), str(path)], capture_output=True, text=True, check=False
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
        if n["container"] or ignored(n["id"]):
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
    return build_diagram(compile_d2(path), rules)


def strip_positions(source: str) -> str:
    pattern = re.compile(rf"\n*{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.S)
    return pattern.sub("\n", source).rstrip("\n") + "\n"


def write_positions(
    source: str, placement: Placement, sizes: Mapping[NodeId, Size], rules: Rules, *, tala: bool = True
) -> str:
    """Append a generated block of `top`/`left` settings, replacing any old one.

    Blocks are centred in their grid cell, so blocks of different sizes still
    line up and the lines between them stay straight.
    """
    lines = [BEGIN, f"# grid {rules.grid.rows}x{rules.grid.cols}, pitch {rules.col_px}x{rules.row_px} px"]
    if tala:
        lines.append("vars: {d2-config: {layout-engine: tala}}")
    for node in sorted(placement.cells, key=lambda n: (placement.cells[n], n)):
        cell, size = placement.cells[node], sizes[node]
        left = round(cell.col * rules.col_px + (rules.col_px - size.width) / 2)
        top = round(cell.row * rules.row_px + (rules.row_px - size.height) / 2)
        lines.append(f"{node}.top: {max(top, 0)}")
        lines.append(f"{node}.left: {max(left, 0)}")
    lines.append(END)
    return strip_positions(source) + "\n" + "\n".join(lines) + "\n"


def read_positions(source: str, sizes: Mapping[NodeId, Size], rules: Rules) -> Placement | None:
    """Recover the grid placement from a generated block, if there is one."""
    m = re.search(rf"{re.escape(BEGIN)}(.*?){re.escape(END)}", source, re.S)
    if m is None:
        return None
    tops: dict[str, int] = {}
    lefts: dict[str, int] = {}
    for node, attr, value in re.findall(r"^(\S+)\.(top|left): (\d+)$", m.group(1), re.M):
        (tops if attr == "top" else lefts)[node] = int(value)
    cells: dict[NodeId, Cell] = {}
    for node, size in sizes.items():
        if node not in tops or node not in lefts:
            print(f"warning: no saved position for {node}", file=sys.stderr)
            return None
        col = round((lefts[node] + size.width / 2) / rules.col_px - 0.5)
        row = round((tops[node] + size.height / 2) / rules.row_px - 0.5)
        cells[node] = Cell(row, col)
    return Placement(cells)
