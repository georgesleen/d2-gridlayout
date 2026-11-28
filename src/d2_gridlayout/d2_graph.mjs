// Compile a D2 file and print its blocks and connections as JSON on stdout.
// Usage: node d2_graph.mjs diagram.d2   (or - to read stdin)
import { D2 } from '@terrastruct/d2';
import fs from 'node:fs';

const path = process.argv[2];
if (!path) {
  console.error('usage: node d2_graph.mjs diagram.d2');
  process.exit(2);
}
try {
  const d2 = new D2();
  const source = fs.readFileSync(path === '-' ? 0 : path, 'utf8');
  const r = await d2.compile(source, { layout: 'elk' });
  const shapes = r.diagram.shapes;
  const ids = new Set(shapes.map((s) => s.id));
  const out = {
    nodes: shapes.map((s) => ({
      id: s.id,
      label: s.label ?? '',
      classes: s.classes ?? [],
      width: s.width,
      height: s.height,
      container: [...ids].some((o) => o.startsWith(s.id + '.')),
    })),
    edges: r.diagram.connections.map((c) => ({
      src: c.src,
      dst: c.dst,
      srcArrow: c.srcArrow !== 'none',
      dstArrow: c.dstArrow !== 'none',
      classes: c.classes ?? [],
      label: c.label ?? '',
    })),
  };
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
} catch (e) {
  console.error(String(e?.message ?? e));
  process.exit(1);
}
