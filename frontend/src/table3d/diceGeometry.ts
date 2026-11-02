/**
 * Real dice, as pure geometry (no DOM, no WebGL: unit-tested). Each die is its true polyhedron (the physics hull,
 * table3d/physics.ts) and a rounded mesh of it for the eye: the solid shrunk by the bevel radius and grown back by a
 * sphere (flat faces, cylindrical edge strips, spherical corner caps), so edges catch the light like a tumbled
 * resin die. Faces carry their standard numbers:
 *
 * - d6, d8, d12, d20: opposite faces sum to n + 1 (d6 with pips, 1-2-3 counter-clockwise around their corner);
 * - d10: 0–9, evens around one apex and odds around the other, opposite faces summing to 9; the percentile tens die
 *   is the same die reading 00–90;
 * - d4: numbered at its points; each face shows its three corners' numbers, and the roll is the point on top;
 * - a coin: heads up or tails up.
 *
 * The server decides the number (game/dice.ts). The physics decides how the die tumbles and which face lands up;
 * `faceTurn` then gives the rotation of the die's own symmetry group that carries the face showing the server's
 * number onto the landed face. The visual mesh is drawn turned by it for the whole throw: the shape is unchanged
 * (a symmetry maps the solid onto itself), so it tumbles exactly as simulated and lands showing the right number.
 */
import * as THREE from "three";

export type DieKind = "d4" | "d6" | "d8" | "d10" | "d12" | "d20" | "d10x10" | "d3" | "dx" | "coin";

/** The die a roll of `sides` is thrown with (d100: a tens die plus a d10; d2: a coin with 1 and 2). */
export function kindsFor(sides: number, coin: boolean): DieKind[] {
  if (coin || sides === 2) return ["coin"];
  if (sides === 100) return ["d10x10", "d10"];
  if (sides === 3) return ["d3"];
  if ([4, 6, 8, 10, 12, 20].includes(sides)) return [`d${sides}` as DieKind];
  return ["dx"];
}

/** A d100 result as its two dice: tens (00–90, as 0–9) and units (0–9); 100 reads "00" and "0". */
export function percentile(v: number): [number, number] {
  const m = ((v % 100) + 100) % 100;
  return [Math.floor(m / 10), m % 10];
}

/** Face value → the number written on it. */
export function faceText(kind: DieKind, value: number): string {
  if (kind === "d10x10") return value === 0 ? "00" : String(value * 10);
  return String(value);
}

export interface FaceInfo {
  /** Outward unit normal, die frame. */
  normal: THREE.Vector3;
  /** Centre of the flat face on the rounded die. */
  center: THREE.Vector3;
  /** In-plane unit vectors: the number reads upright with `up` pointing up (right × up = normal). */
  right: THREE.Vector3;
  up: THREE.Vector3;
  /** Half-size of the face's square atlas cell, in die units. */
  half: number;
  /** The flat face's corners in cell coordinates (−0.5…0.5, y up). */
  poly: [number, number][];
  /** Which solid vertex each corner is (d4 numbers its points). */
  verts: number[];
  /** The value this face shows (d4: unused, see `pointValues`). */
  value: number;
}

export interface DieSolid {
  kind: DieKind;
  /** The sharp polyhedron (physics hull), centre of mass at the origin. */
  verts: THREE.Vector3[];
  /** Hull faces, counter-clockwise seen from outside. */
  polys: number[][];
  faces: FaceInfo[];
  /** d4: the number at each point. */
  pointValues: number[];
  /** Bounding radius and the distance from centre to a face (the resting height). */
  radius: number;
  inradius: number;
  /** The rounded mesh, with atlas cells laid out `cols` × `rows` (the last cell is left blank for the edges). */
  geometry: THREE.BufferGeometry;
  cols: number;
  rows: number;
  /** The rotations that map the solid onto itself. */
  symmetries: THREE.Quaternion[];
}

const PHI = (1 + Math.sqrt(5)) / 2;

/** Circumradius per die (world units: a card is 0.84 wide). Bigger than life, so they read at seat distance. */
const RADIUS: Record<Exclude<DieKind, "coin">, number> = {
  d4: 0.7, d6: 0.58, d8: 0.63, d10: 0.63, d10x10: 0.63, d12: 0.64, d20: 0.67, d3: 0.58, dx: 0.67,
};
/** Edge rounding as a fraction of the inradius. */
const BEVEL: Record<Exclude<DieKind, "coin">, number> = {
  d4: 0.1, d6: 0.17, d8: 0.11, d10: 0.1, d10x10: 0.1, d12: 0.1, d20: 0.085, d3: 0.17, dx: 0.085,
};

export const COIN_RADIUS = 0.37;
export const COIN_THICK = 0.095;

function baseVerts(kind: Exclude<DieKind, "coin">): THREE.Vector3[] {
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
  switch (kind) {
    case "d4":
      return [v(1, 1, 1), v(1, -1, -1), v(-1, 1, -1), v(-1, -1, 1)];
    case "d6":
    case "d3": {
      const out: THREE.Vector3[] = [];
      for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) out.push(v(x, y, z));
      return out;
    }
    case "d8":
      return [v(1, 0, 0), v(-1, 0, 0), v(0, 1, 0), v(0, -1, 0), v(0, 0, 1), v(0, 0, -1)];
    case "d10":
    case "d10x10": {
      // a pentagonal trapezohedron with planar kites: apex height h for ring offset z0
      const z0 = 0.105;
      const c36 = Math.cos(Math.PI / 5);
      const h = (z0 * (1 + c36)) / (1 - c36);
      const out = [v(0, h, 0), v(0, -h, 0)];
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2;
        const b = ((k + 0.5) / 5) * Math.PI * 2;
        out.push(v(Math.cos(a), z0, Math.sin(a)), v(Math.cos(b), -z0, Math.sin(b)));
      }
      return out;
    }
    case "d12": {
      const out: THREE.Vector3[] = [];
      for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) out.push(v(x, y, z));
      for (const a of [-1, 1]) for (const b of [-1, 1]) {
        out.push(v(0, a / PHI, b * PHI), v(a / PHI, b * PHI, 0), v(a * PHI, 0, b / PHI));
      }
      return out;
    }
    case "d20":
    case "dx": {
      const out: THREE.Vector3[] = [];
      for (const a of [-1, 1]) for (const b of [-1, 1]) out.push(v(0, a, b * PHI), v(a, b * PHI, 0), v(a * PHI, 0, b));
      return out;
    }
  }
}

/** The faces of a convex point set: planes through three points with every point on one side, coplanar points merged. */
export function hullFaces(pts: THREE.Vector3[]): number[][] {
  const found: { n: THREE.Vector3; d: number; idx: number[] }[] = [];
  const eps = 1e-6;
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) for (let k = j + 1; k < pts.length; k++) {
    const n = pts[j]!.clone().sub(pts[i]!).cross(pts[k]!.clone().sub(pts[i]!));
    if (n.lengthSq() < 1e-12) continue;
    n.normalize();
    let d = n.dot(pts[i]!);
    if (d < 0) { n.negate(); d = -d; }
    if (pts.some((p) => n.dot(p) > d + eps)) continue;
    if (found.some((f) => f.n.dot(n) > 1 - 1e-9)) continue;
    const idx = pts.map((p, q) => (Math.abs(n.dot(p) - d) < eps ? q : -1)).filter((q) => q >= 0);
    found.push({ n, d, idx });
  }
  // order each face's corners counter-clockwise seen from outside
  return found.map(({ n, idx }) => {
    const c = idx.reduce((a, q) => a.add(pts[q]!), new THREE.Vector3()).divideScalar(idx.length);
    const u = pts[idx[0]!]!.clone().sub(c).normalize();
    const w = n.clone().cross(u);
    return [...idx].sort((p, q) => {
      const a = pts[p]!.clone().sub(c);
      const b = pts[q]!.clone().sub(c);
      return Math.atan2(a.dot(w), a.dot(u)) - Math.atan2(b.dot(w), b.dot(u));
    });
  });
}

const normalOf = (pts: THREE.Vector3[], f: number[]) => {
  const c = f.reduce((a, q) => a.add(pts[q]!), new THREE.Vector3()).divideScalar(f.length);
  const n = pts[f[1]!]!.clone().sub(pts[f[0]!]!).cross(pts[f[2]!]!.clone().sub(pts[f[0]!]!)).normalize();
  return n.dot(c) < 0 ? n.negate() : n;
};

/** The rotations mapping the point set onto itself (found by matching face frames). */
function symmetryGroup(pts: THREE.Vector3[], polys: number[][]): THREE.Quaternion[] {
  const frame = (f: number[], k: number) => {
    const n = normalOf(pts, f);
    const c = f.reduce((a, q) => a.add(pts[q]!), new THREE.Vector3()).divideScalar(f.length);
    const x = pts[f[k]!]!.clone().sub(c).normalize();
    return new THREE.Matrix4().makeBasis(x, n.clone().cross(x), n);
  };
  const f0 = polys[0]!;
  const inv = frame(f0, 0).clone().invert();
  const out: THREE.Quaternion[] = [];
  const scale = Math.max(...pts.map((p) => p.length()));
  for (const g of polys) {
    if (g.length !== f0.length) continue;
    for (let k = 0; k < g.length; k++) {
      const m = frame(g, k).multiply(inv);
      const q = new THREE.Quaternion().setFromRotationMatrix(m).normalize();
      const ok = pts.every((p) => {
        const r = p.clone().applyQuaternion(q);
        return pts.some((s) => s.distanceTo(r) < 1e-6 * scale);
      });
      if (ok && !out.some((o) => Math.abs(o.dot(q)) > 1 - 1e-9)) out.push(q);
    }
  }
  return out;
}

/** Deterministic little generator for the layout search (not the throw: that's physics.ts `seeded`). */
function lcg(seed: number): () => number {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}

/**
 * Numbers for a die whose opposite faces pair up: each pair gets v and n + 1 − v (or 9 − v on a d10), then a short
 * seeded search spreads the high numbers around the die (every corner's faces add up to about the same).
 */
function numberFaces(kind: DieKind, normals: THREE.Vector3[], polys: number[][], nVerts: number): number[] {
  const n = normals.length;
  const opposite = normals.map((a) => normals.findIndex((b) => a.dot(b) < -0.999));
  const pairs: [number, number][] = [];
  for (let i = 0; i < n; i++) if (opposite[i]! > i) pairs.push([i, opposite[i]!]);
  const isTen = kind === "d10" || kind === "d10x10";
  const low = (k: number) => (isTen ? 2 * k : k + 1); // a d10's upper ring gets the evens
  const pairOf = (v: number) => (isTen ? 9 - v : n + 1 - v);
  // d10: the upper faces (around the +y apex) take the evens
  if (isTen) for (const p of pairs) if (normals[p[0]]!.y < 0) p.reverse();
  const around: number[][] = Array.from({ length: nVerts }, () => []);
  polys.forEach((f, fi) => f.forEach((v) => around[v]!.push(fi)));
  const score = (vals: number[]) => {
    const sums = around.filter((a) => a.length).map((a) => a.reduce((s, fi) => s + vals[fi]!, 0) / a.length);
    const mean = sums.reduce((a, b) => a + b, 0) / sums.length;
    return sums.reduce((a, b) => a + (b - mean) ** 2, 0);
  };
  const assign = (order: number[], flip: boolean[]) => {
    const vals = new Array<number>(n).fill(0);
    order.forEach((pi, k) => {
      const [a, b] = pairs[pi]!;
      const [lo, hi] = flip[pi] && !isTen ? [b, a] : [a, b];
      vals[lo] = low(k);
      vals[hi] = pairOf(low(k));
    });
    return vals;
  };
  const rnd = lcg(n * 7919 + (isTen ? 1 : 0));
  let order = pairs.map((_, i) => i);
  let flip = pairs.map(() => false);
  let best = assign(order, flip);
  let bestScore = score(best);
  for (let it = 0; it < 4000; it++) {
    const o = [...order];
    const f = [...flip];
    const i = Math.floor(rnd() * o.length);
    const j = Math.floor(rnd() * o.length);
    [o[i], o[j]] = [o[j]!, o[i]!];
    if (rnd() < 0.5) f[Math.floor(rnd() * f.length)] = !f[Math.floor(rnd() * f.length)];
    const vals = assign(o, f);
    const sc = score(vals);
    if (sc <= bestScore) {
      order = o;
      flip = f;
      best = vals;
      bestScore = sc;
    }
  }
  return best;
}

/** A d6's numbers: 1 up, 6 down, 2 toward +z, 5 −z, 3 toward +x, 4 −x (1-2-3 counter-clockwise round their corner). */
function d6Values(normals: THREE.Vector3[]): number[] {
  return normals.map((nm) => {
    if (nm.y > 0.9) return 1;
    if (nm.y < -0.9) return 6;
    if (nm.z > 0.9) return 2;
    if (nm.z < -0.9) return 5;
    if (nm.x > 0.9) return 3;
    return 4;
  });
}

/** Which way each face's number reads: toward the apex (d10), the nearest pole (d8), else toward a corner. */
function upFor(kind: DieKind, pts: THREE.Vector3[], f: number[], n: THREE.Vector3, c: THREE.Vector3): THREE.Vector3 {
  const inPlane = (v: THREE.Vector3) => v.clone().sub(n.clone().multiplyScalar(v.dot(n))).normalize();
  if (kind === "d10" || kind === "d10x10") {
    const apex = f.reduce((best, q) => (Math.abs(pts[q]!.y) > Math.abs(pts[best]!.y) ? q : best), f[0]!);
    return inPlane(pts[apex]!.clone().sub(c));
  }
  if (kind === "d6" || kind === "d3") {
    // the pips and numbers sit square to the edges: up along a world axis in the face's plane
    const axis = Math.abs(n.y) > 0.9 ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0, 1, 0);
    return inPlane(axis);
  }
  // point toward the corner that is highest along a fixed tilted axis (a consistent, even-looking layout)
  const ref = new THREE.Vector3(0.21, 1, 0.37).normalize();
  const corner = f.reduce((best, q) => (pts[q]!.clone().sub(c).dot(ref) > pts[best]!.clone().sub(c).dot(ref) ? q : best), f[0]!);
  return inPlane(pts[corner]!.clone().sub(c));
}

const solids = new Map<string, DieSolid>();

/** Edge strips and corner caps get this many segments (more on the high graphics setting). */
export function dieSolid(kind: Exclude<DieKind, "coin">, segments = 4): DieSolid {
  const key = `${kind}:${segments}`;
  const known = solids.get(key);
  if (known) return known;
  const raw = baseVerts(kind);
  const scale = RADIUS[kind] / Math.max(...raw.map((p) => p.length()));
  const pts = raw.map((p) => p.multiplyScalar(scale));
  const polys = hullFaces(pts);
  const normals = polys.map((f) => normalOf(pts, f));
  const inradius = Math.min(...polys.map((f, i) => normals[i]!.dot(pts[f[0]!]!)));
  const radius = Math.max(...pts.map((p) => p.length()));
  const r = inradius * BEVEL[kind];
  const s = (inradius - r) / inradius;
  const core = pts.map((p) => p.clone().multiplyScalar(s));

  let values: number[];
  if (kind === "d6") values = d6Values(normals);
  else if (kind === "d3") values = d6Values(normals).map((v) => ((v - 1) % 3) + 1); // a d3: 1–3 twice, opposite faces sum to 4
  else if (kind === "d4" || kind === "dx") values = polys.map(() => 0);
  else values = numberFaces(kind, normals, polys, pts.length);
  // d4: the points 1–4
  const pointValues = kind === "d4" ? pts.map((_, i) => i + 1) : [];

  const cols = Math.ceil(Math.sqrt(polys.length + 1));
  const rows = Math.ceil((polys.length + 1) / cols);
  const faces: FaceInfo[] = polys.map((f, fi) => {
    const n = normals[fi]!;
    const c = f.reduce((a, q) => a.add(core[q]!), new THREE.Vector3()).divideScalar(f.length).addScaledVector(n, r);
    const up = upFor(kind, pts, f, n, c);
    const right = up.clone().cross(n).normalize();
    const flat = f.map((q) => core[q]!.clone().addScaledVector(n, r));
    const half = Math.max(...flat.map((p) => Math.max(Math.abs(p.clone().sub(c).dot(right)), Math.abs(p.clone().sub(c).dot(up))))) * 1.02;
    const poly = flat.map((p) => [p.clone().sub(c).dot(right) / (2 * half), p.clone().sub(c).dot(up) / (2 * half)] as [number, number]);
    return { normal: n, center: c, right, up, half, poly, verts: f, value: values[fi]! };
  });

  const geometry = roundedMesh(core, polys, normals, faces, r, segments, cols, rows);
  const solid: DieSolid = {
    kind, verts: pts, polys, faces, pointValues, radius, inradius, geometry, cols, rows,
    symmetries: symmetryGroup(pts, polys),
  };
  solids.set(key, solid);
  return solid;
}

/** UV of a point in face `fi`'s atlas cell; the blank cell (the last) for edges and corners. */
function cellUv(fi: number, cols: number, rows: number, x: number, y: number): [number, number] {
  const col = fi % cols;
  const row = Math.floor(fi / cols);
  return [(col + 0.5 + x) / cols, 1 - (row + 0.5 - y) / rows];
}

function roundedMesh(core: THREE.Vector3[], polys: number[][], normals: THREE.Vector3[], faces: FaceInfo[], r: number, seg: number, cols: number, rows: number): THREE.BufferGeometry {
  const pos: number[] = [];
  const nor: number[] = [];
  const uv: number[] = [];
  const blank = cellUv(cols * rows - 1, cols, rows, 0, 0);
  const push = (p: THREE.Vector3, n: THREE.Vector3, t: [number, number]) => {
    pos.push(p.x, p.y, p.z);
    nor.push(n.x, n.y, n.z);
    uv.push(t[0], t[1]);
  };
  type Corner = [THREE.Vector3, THREE.Vector3, [number, number]];
  /** One triangle, wound counter-clockwise seen from outside (its normals say which side is out). */
  const tri3 = (a: Corner, b: Corner, c: Corner) => {
    const n = b[0].clone().sub(a[0]).cross(c[0].clone().sub(a[0]));
    const out = a[1].clone().add(b[1]).add(c[1]);
    for (const k of n.dot(out) < 0 ? [a, c, b] : [a, b, c]) push(k[0], k[1], k[2]);
  };
  const dir = (a: THREE.Vector3, b: THREE.Vector3, t: number) => a.clone().multiplyScalar(1 - t).addScaledVector(b, t).normalize();
  // flat faces (fans from the centre: every face is convex)
  faces.forEach((f, fi) => {
    const corners = polys[fi]!.map((q) => core[q]!.clone().addScaledVector(f.normal, r));
    const cuv = cellUv(fi, cols, rows, 0, 0);
    for (let i = 0; i < corners.length; i++) {
      const a = corners[i]!;
      const b = corners[(i + 1) % corners.length]!;
      const [ax, ay] = f.poly[i]!;
      const [bx, by] = f.poly[(i + 1) % corners.length]!;
      tri3([f.center, f.normal, cuv], [a, f.normal, cellUv(fi, cols, rows, ax, ay)], [b, f.normal, cellUv(fi, cols, rows, bx, by)]);
    }
  });
  // edge strips: each edge once, between its two faces
  const edgeFaces = new Map<string, number[]>();
  polys.forEach((f, fi) => f.forEach((a, i) => {
    const b = f[(i + 1) % f.length]!;
    const k = a < b ? `${a}-${b}` : `${b}-${a}`;
    edgeFaces.set(k, [...(edgeFaces.get(k) ?? []), fi]);
  }));
  for (const [k, [f1, f2]] of edgeFaces) {
    if (f2 === undefined) continue;
    const [a, b] = k.split("-").map(Number) as [number, number];
    const n1 = normals[f1!]!;
    const n2 = normals[f2]!;
    for (let i = 0; i < seg; i++) {
      const na = dir(n1, n2, i / seg);
      const nb = dir(n1, n2, (i + 1) / seg);
      const sa = core[a]!.clone().addScaledVector(na, r);
      const ea = core[b]!.clone().addScaledVector(na, r);
      const sb = core[a]!.clone().addScaledVector(nb, r);
      const eb = core[b]!.clone().addScaledVector(nb, r);
      tri3([ea, na, blank], [sa, na, blank], [sb, nb, blank]);
      tri3([ea, na, blank], [sb, nb, blank], [eb, nb, blank]);
    }
  }
  // corner caps: a spherical patch between the faces meeting at each corner, in their cyclic order
  for (let v = 0; v < core.length; v++) {
    const around = polys.map((f, fi) => (f.includes(v) ? fi : -1)).filter((fi) => fi >= 0);
    if (around.length < 3) continue;
    // order the faces around the corner: next face shares the edge leaving v on the current face
    const ordered = [around[0]!];
    while (ordered.length < around.length) {
      const f = polys[ordered[ordered.length - 1]!]!;
      const prev = f[(f.indexOf(v) - 1 + f.length) % f.length]!; // the edge (prev → v) belongs to the next face
      const next = around.find((fi) => !ordered.includes(fi) && polys[fi]!.includes(prev));
      if (next === undefined) break;
      ordered.push(next);
    }
    const m = ordered.reduce((a, fi) => a.add(normals[fi]!), new THREE.Vector3()).normalize();
    const c = core[v]!;
    for (let k = 0; k < ordered.length; k++) {
      const na = normals[ordered[k]!]!;
      const nb = normals[ordered[(k + 1) % ordered.length]!]!;
      const at = (i: number, j: number) => {
        if (i === 0) return m.clone();
        const edge = dir(na, nb, j / i);
        return m.clone().multiplyScalar(1 - i / seg).addScaledVector(edge, i / seg).normalize();
      };
      const tri = (d1: THREE.Vector3, d2: THREE.Vector3, d3: THREE.Vector3) =>
        tri3([c.clone().addScaledVector(d1, r), d1, blank], [c.clone().addScaledVector(d2, r), d2, blank], [c.clone().addScaledVector(d3, r), d3, blank]);
      for (let i = 0; i < seg; i++) {
        for (let j = 0; j <= i; j++) {
          tri(at(i, j), at(i + 1, j), at(i + 1, j + 1));
          if (j < i) tri(at(i, j), at(i + 1, j + 1), at(i, j + 1));
        }
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.computeBoundingSphere();
  return g;
}

// -- which face is up, and the turn that shows the server's number there ----------------------------------------

const UP = new THREE.Vector3(0, 1, 0);

/** The face of `solid` pointing most nearly up when the die is turned by `q`. */
export function topFace(solid: DieSolid, q: THREE.Quaternion): number {
  let best = 0;
  let bestY = -Infinity;
  solid.faces.forEach((f, i) => {
    const y = f.normal.clone().applyQuaternion(q).y;
    if (y > bestY) { bestY = y; best = i; }
  });
  return best;
}

/** The d4's point on top when turned by `q`. */
export function topPoint(solid: DieSolid, q: THREE.Quaternion): number {
  let best = 0;
  let bestY = -Infinity;
  solid.verts.forEach((p, i) => {
    const y = p.clone().applyQuaternion(q).y;
    if (y > bestY) { bestY = y; best = i; }
  });
  return best;
}

/** How far the die is from lying flat when turned by `q` (1 − the bottom face's alignment with down; 0 = flat). */
export function tilt(solid: DieSolid, q: THREE.Quaternion): number {
  return 1 - Math.max(...solid.faces.map((f) => -f.normal.clone().applyQuaternion(q).y));
}

/** The face(s) showing `value` (d4: the point). For dice with no real face for it (dx), none. */
export function facesShowing(solid: DieSolid, value: number): number[] {
  if (solid.kind === "d4") return solid.pointValues.map((v, i) => (v === value ? i : -1)).filter((i) => i >= 0);
  return solid.faces.map((f, i) => (f.value === value ? i : -1)).filter((i) => i >= 0);
}

/**
 * The symmetry S that carries a face showing `value` onto the face that landed up (`landed`: a face index; for a d4
 * the point on top). Drawing the die turned by body × S shows `value` on top. Identity when no face shows it.
 */
export function faceTurn(solid: DieSolid, landed: number, value: number): THREE.Quaternion {
  const targets = facesShowing(solid, value);
  if (!targets.length) return new THREE.Quaternion();
  if (targets.includes(landed)) return new THREE.Quaternion();
  const point = solid.kind === "d4";
  const want = point ? solid.verts[landed]!.clone().normalize() : solid.faces[landed]!.normal;
  for (const t of targets) {
    const from = point ? solid.verts[t]!.clone().normalize() : solid.faces[t]!.normal;
    const s = solid.symmetries.find((q) => from.clone().applyQuaternion(q).dot(want) > 0.9999);
    if (s) return s.clone();
  }
  return new THREE.Quaternion();
}

/** The value shown on top by a die drawn turned by `q` (tests and the 2D fallback). */
export function shownValue(solid: DieSolid, q: THREE.Quaternion): number {
  return solid.kind === "d4" ? solid.pointValues[topPoint(solid, q)]! : solid.faces[topFace(solid, q)]!.value;
}

/** The coin: heads (+y) or tails up; S flips it over when the server's call is the other side. */
export function coinTurn(bodyQ: THREE.Quaternion, heads: boolean): THREE.Quaternion {
  const up = UP.clone().applyQuaternion(bodyQ).y > 0;
  return up === heads ? new THREE.Quaternion() : new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
}

/** Free the cached rounded meshes (the last dice tray going away). */
export function disposeSolids(): void {
  for (const s of solids.values()) s.geometry.dispose();
  solids.clear();
}
