"""Command line: `layout` places blocks, `score` reports on the current layout, `route` redraws chosen lines."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cost import Breakdown, evaluate
from .d2io import load_diagram, read_positions, write_positions
from .model import Cell, Graph, NodeId, Placement
from .route import apply_routes
from .rules import Rules, load_rules
from .solver import anneal, brute_force


def ascii_grid(p: Placement, rules: Rules, width: int = 11) -> str:
    occ = p.occupant()
    rows = []
    for r in range(rules.grid.rows):
        cells = [occ.get(Cell(r, c), "") for c in range(rules.grid.cols)]
        rows.append(" ".join((name[:width] or ".").ljust(width) for name in cells))
    return "\n".join(rows)


def report(g: Graph, b: Breakdown) -> str:
    out = [
        f"total {b.total:.1f}  direction {b.direction:.1f}  length {b.length:.1f}  "
        f"through {b.through:.1f}  crossings {b.crossings:.1f}  span {b.span:.1f}"
    ]
    for e, node in b.through_pairs:
        out.append(f"  line {e.src} -> {e.dst} passes through {node}")
    for e1, e2 in b.crossing_pairs:
        out.append(f"  {e1.src} -> {e1.dst} crosses {e2.src} -> {e2.dst}")
    return "\n".join(out)


def cmd_layout(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    source = args.diagram.read_text()
    diagram = load_diagram(args.diagram, rules)
    g = diagram.graph
    for s in diagram.skipped_edges:
        print(f"skipped edge (container or ignored node): {s}", file=sys.stderr)

    start = read_positions(source, diagram.sizes, rules) if args.refine else None
    best: Placement | None = None
    best_score = float("inf")
    for seed in args.seeds:
        p = anneal(g, rules.grid, pinned=rules.pins, start=start, iterations=args.iterations,
                   t_start=args.temperature, seed=seed)
        score = evaluate(g, p).total
        print(f"seed {seed}: {score:.1f}", file=sys.stderr)
        if score < best_score:
            best, best_score = p, score
    assert best is not None

    if args.brute:
        free = [NodeId(n) for n in args.brute.split(",")]
        fixed = Placement({n: c for n, c in best.cells.items() if n not in free})
        best = brute_force(g, rules.grid, fixed, free)

    print(ascii_grid(best, rules))
    print(report(g, evaluate(g, best)))
    out = args.output or args.diagram
    out.write_text(write_positions(source, best, diagram.sizes, rules, tala=not args.no_tala))
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    diagram = load_diagram(args.diagram, rules)
    p = read_positions(args.diagram.read_text(), diagram.sizes, rules)
    if p is None:
        print("no generated positions in this file; run `layout` first", file=sys.stderr)
        return 1
    print(ascii_grid(p, rules))
    print(report(diagram.graph, evaluate(diagram.graph, p)))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    rules = load_rules(args.rules)
    if not rules.routes:
        print("no [routes] in the rules file", file=sys.stderr)
        return 1
    out = args.output or args.svg
    out.write_text(apply_routes(args.svg.read_text(), rules.routes))
    print(f"routed {len(rules.routes)} lines into {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="d2-gridlayout", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lay = sub.add_parser("layout", help="place blocks and write top/left into the D2 file")
    lay.add_argument("diagram", type=Path)
    lay.add_argument("--rules", type=Path, required=True)
    lay.add_argument("-o", "--output", type=Path, help="default: overwrite the input")
    lay.add_argument("--seeds", type=lambda s: [int(x) for x in s.split(",")], default=[0, 1, 2, 3])
    lay.add_argument("--iterations", type=int, default=30_000)
    lay.add_argument("--temperature", type=float, default=20.0)
    lay.add_argument("--refine", action="store_true", help="start from the positions already in the file")
    lay.add_argument("--brute", help="comma-separated nodes to place exhaustively after annealing")
    lay.add_argument("--no-tala", action="store_true", help="don't set the layout engine to TALA")
    lay.set_defaults(func=cmd_layout)

    sc = sub.add_parser("score", help="report the cost of the positions in a D2 file")
    sc.add_argument("diagram", type=Path)
    sc.add_argument("--rules", type=Path, required=True)
    sc.set_defaults(func=cmd_score)

    ro = sub.add_parser("route", help="redraw the lines listed in [routes] in a rendered SVG")
    ro.add_argument("svg", type=Path)
    ro.add_argument("--rules", type=Path, required=True)
    ro.add_argument("-o", "--output", type=Path, help="default: overwrite the input")
    ro.set_defaults(func=cmd_route)

    args = ap.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
