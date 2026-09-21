/** Wireframe platonic solids + sacred geometry. Stroke only, no fill. */

export type SolidKind = "tetra" | "cube" | "octa" | "dodeca" | "icosa" | "merkaba";

export const SOLID_CYCLE: SolidKind[] = ["tetra", "cube", "octa", "icosa", "dodeca", "merkaba"];

const PHI = (1 + Math.sqrt(5)) / 2;
const INV = 1 / PHI;

type V = [number, number, number];
type E = [number, number];

function edgesByMin(verts: V[], slack = 1.12): E[] {
  const n = verts.length;
  let min = Infinity;
  const dist: number[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const a = verts[i]!;
      const b = verts[j]!;
      const d = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
      dist.push(d);
      if (d > 1e-6 && d < min) min = d;
    }
  }
  const out: E[] = [];
  let k = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (dist[k]! <= min * slack) out.push([i, j]);
      k++;
    }
  }
  return out;
}

function tetra(): { verts: V[]; edges: E[] } {
  const verts: V[] = [
    [1, 1, 1],
    [1, -1, -1],
    [-1, 1, -1],
    [-1, -1, 1],
  ];
  return { verts, edges: edgesByMin(verts, 1.05) };
}

function cube(): { verts: V[]; edges: E[] } {
  const verts: V[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) verts.push([x, y, z]);
  return { verts, edges: edgesByMin(verts, 1.05) };
}

function octa(): { verts: V[]; edges: E[] } {
  const verts: V[] = [
    [1, 0, 0],
    [-1, 0, 0],
    [0, 1, 0],
    [0, -1, 0],
    [0, 0, 1],
    [0, 0, -1],
  ];
  return { verts, edges: edgesByMin(verts, 1.05) };
}

function icosa(): { verts: V[]; edges: E[] } {
  const verts: V[] = [];
  for (const s of [-1, 1]) for (const t of [-1, 1]) {
    verts.push([0, s, t * PHI]);
    verts.push([s, t * PHI, 0]);
    verts.push([t * PHI, 0, s]);
  }
  return { verts, edges: edgesByMin(verts, 1.08) };
}

function dodeca(): { verts: V[]; edges: E[] } {
  const verts: V[] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) verts.push([x, y, z]);
  for (const s of [-1, 1]) for (const t of [-1, 1]) {
    verts.push([0, s * INV, t * PHI]);
    verts.push([s * INV, t * PHI, 0]);
    verts.push([t * PHI, 0, s * INV]);
  }
  return { verts, edges: edgesByMin(verts, 1.08) };
}

function merkaba(): { verts: V[]; edges: E[] } {
  const a = tetra();
  const b: V[] = a.verts.map((v) => [-v[0], -v[1], -v[2]]);
  const verts = [...a.verts, ...b];
  const edges: E[] = [
    ...a.edges,
    ...a.edges.map(([i, j]) => [i + 4, j + 4] as E),
  ];
  return { verts, edges };
}

const MESH: Record<SolidKind, { verts: V[]; edges: E[] }> = {
  tetra: tetra(),
  cube: cube(),
  octa: octa(),
  dodeca: dodeca(),
  icosa: icosa(),
  merkaba: merkaba(),
};

export function rotate3(v: V, ax: number, ay: number, az: number): V {
  const cx = Math.cos(ax);
  const sx = Math.sin(ax);
  const cy = Math.cos(ay);
  const sy = Math.sin(ay);
  const cz = Math.cos(az);
  const sz = Math.sin(az);
  let [x, y, z] = v;
  let y1 = y * cx - z * sx;
  let z1 = y * sx + z * cx;
  y = y1;
  z = z1;
  let x1 = x * cy + z * sy;
  z1 = -x * sy + z * cy;
  x = x1;
  z = z1;
  x1 = x * cz - y * sz;
  y1 = x * sz + y * cz;
  return [x1, y1, z1];
}

export function project(v: V, cx: number, cy: number, radius: number): [number, number] {
  const z = v[2] + 3.2;
  const f = radius / z;
  return [cx + v[0] * f, cy + v[1] * f];
}

export function strokeSolid(
  ctx: CanvasRenderingContext2D,
  kind: SolidKind,
  cx: number,
  cy: number,
  radius: number,
  ax: number,
  ay: number,
  az: number,
) {
  const mesh = MESH[kind];
  const pts = mesh.verts.map((v) => project(rotate3(v, ax, ay, az), cx, cy, radius));
  ctx.beginPath();
  for (const [i, j] of mesh.edges) {
    const a = pts[i]!;
    const b = pts[j]!;
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
  }
  ctx.stroke();
}

export function flowerCenters(cx: number, cy: number, R: number): [number, number][] {
  const pts: [number, number][] = [[cx, cy]];
  for (let ring = 1; ring <= 2; ring++) {
    const n = ring === 1 ? 6 : 12;
    const rad = ring * R;
    const off = ring === 2 ? Math.PI / 12 : 0;
    for (let i = 0; i < n; i++) {
      const a = off + (i * Math.PI * 2) / n;
      pts.push([cx + Math.cos(a) * rad, cy + Math.sin(a) * rad]);
    }
  }
  return pts;
}

export function fruitCenters(cx: number, cy: number, R: number): [number, number][] {
  const pts: [number, number][] = [[cx, cy]];
  for (const ring of [1, 2]) {
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3;
      pts.push([cx + Math.cos(a) * ring * R, cy + Math.sin(a) * ring * R]);
    }
  }
  return pts;
}
