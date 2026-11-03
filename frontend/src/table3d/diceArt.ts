/**
 * The dice's engraving, drawn once per kind of die and cached (table3d/diceGeometry.ts lays the faces out in atlas
 * cells). One texture per kind: RGB is a tangent-space normal map of the engraving (numbers and pips cut into the
 * face, with soft walls), A is where the ink sits in it. The colours are not in it: the body colour, swirl, metal or
 * gem and the ink colour come from the material (table3d/diceLook.ts), so one atlas serves every player and look.
 *
 * Numbers are Cinzel (the table's display face, bundled), 6 and 9 underlined. A d6 has pips. A d4 has each point's
 * number at that point on all three faces, its top toward the point. A d10's numbers read toward the apex.
 * The coin has its own art: a struck relief (heads: a crowned profile; tails: a laurel round a star) and a milled rim.
 */
import * as THREE from "three";
import { dieSolid, faceText, type DieKind, type DieSolid } from "./diceGeometry";

const FONT = "Cinzel, Georgia, 'Times New Roman', serif";
const fontReady = () => {
  try {
    return typeof document === "undefined" || !document.fonts || document.fonts.check(`700 64px ${FONT}`);
  } catch {
    return true;
  }
};

/** Height map → normal map (RGB) with the ink mask in A, as a texture the GPU can mip. Rows flipped for UVs. */
function bake(ink: Uint8ClampedArray, height: Float32Array, w: number, h: number, strength: number): Uint8Array {
  const out = new Uint8Array(w * h * 4);
  const H = (x: number, y: number) => height[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))]!;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x - 1, y) - H(x - 1, y + 1)) / 4;
      const dy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x, y - 1) - H(x + 1, y - 1)) / 4;
      // tangent space: +x right, +y up (the canvas runs down, so dH/dv = −dy)
      let nx = -dx * strength;
      let ny = dy * strength;
      let nz = 1;
      const l = Math.hypot(nx, ny, nz);
      nx /= l; ny /= l; nz /= l;
      const o = ((h - 1 - y) * w + x) * 4;
      out[o] = Math.round((nx * 0.5 + 0.5) * 255);
      out[o + 1] = Math.round((ny * 0.5 + 0.5) * 255);
      out[o + 2] = Math.round((nz * 0.5 + 0.5) * 255);
      out[o + 3] = ink[(y * w + x) * 4 + 3]!;
    }
  }
  return out;
}

/** A soft copy of the ink's coverage (two box passes each way): the engraving's sloped walls. */
function soften(ink: Uint8ClampedArray, w: number, h: number, r: number): Float32Array {
  const a = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) a[i] = ink[i * 4 + 3]! / 255;
  const b = new Float32Array(w * h);
  for (let pass = 0; pass < 2; pass++) {
    for (let y = 0; y < h; y++) {
      let s = 0;
      for (let x = -r; x <= r; x++) s += a[y * w + Math.min(w - 1, Math.max(0, x))]!;
      for (let x = 0; x < w; x++) {
        b[y * w + x] = s / (2 * r + 1);
        s += a[y * w + Math.min(w - 1, x + r + 1)]! - a[y * w + Math.max(0, x - r)]!;
      }
    }
    for (let x = 0; x < w; x++) {
      let s = 0;
      for (let y = -r; y <= r; y++) s += b[Math.min(h - 1, Math.max(0, y)) * w + x]!;
      for (let y = 0; y < h; y++) {
        a[y * w + x] = s / (2 * r + 1);
        s += b[Math.min(h - 1, y + r + 1) * w + x]! - b[Math.max(0, y - r) * w + x]!;
      }
    }
  }
  return a;
}

const PIPS: Record<number, [number, number][]> = {
  1: [[0, 0]],
  2: [[-1, 1], [1, -1]],
  3: [[-1, 1], [0, 0], [1, -1]],
  4: [[-1, 1], [1, 1], [-1, -1], [1, -1]],
  5: [[-1, 1], [1, 1], [0, 0], [-1, -1], [1, -1]],
  6: [[-1, 1], [1, 1], [-1, 0], [1, 0], [-1, -1], [1, -1]],
};

/** The largest circle round the cell centre inside the face polygon (cell units). */
function inRadius(poly: [number, number][]): number {
  let r = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const [ax, ay] = poly[i]!;
    const [bx, by] = poly[(i + 1) % poly.length]!;
    const ex = bx - ax, ey = by - ay;
    r = Math.min(r, Math.abs(ex * ay - ey * ax) / Math.hypot(ex, ey));
  }
  return r;
}

/** Draw a number centred at (x, y), `px` tall, turned by `angle`, underlined if it is 6 or 9. */
function number(g: CanvasRenderingContext2D, text: string, x: number, y: number, px: number, angle: number, maxW: number): void {
  g.save();
  g.translate(x, y);
  g.rotate(angle);
  g.font = `700 ${px}px ${FONT}`;
  const w = g.measureText(text).width;
  const k = w > maxW ? maxW / w : 1;
  g.scale(k, k);
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, 0, px * 0.04);
  if (text === "6" || text === "9") g.fillRect(-px * 0.24, px * 0.44, px * 0.48, Math.max(2, px * 0.075));
  g.restore();
}

/** The ink for every face of a die, in its atlas cells (white on transparent). */
function drawInk(g: CanvasRenderingContext2D, s: DieSolid, kind: DieKind, cell: number): void {
  g.fillStyle = "#fff";
  s.faces.forEach((f, fi) => {
    const cx = (fi % s.cols + 0.5) * cell;
    const cy = (Math.floor(fi / s.cols) + 0.5) * cell;
    const at = (x: number, y: number) => [cx + x * cell, cy - y * cell] as const;
    const inr = inRadius(f.poly);
    if (kind === "d6") {
      const v = f.value;
      const step = inr * 0.56;
      for (const [px, py] of PIPS[v]!) {
        const [x, y] = at(px * step, py * step);
        g.beginPath();
        g.arc(x, y, cell * inr * (v === 1 ? 0.27 : 0.17), 0, Math.PI * 2);
        g.fill();
      }
      return;
    }
    if (kind === "d4") {
      // each corner's number near that corner, its top toward it
      for (let k = 0; k < f.verts.length; k++) {
        const [vx, vy] = f.poly[k]!;
        const [x, y] = at(vx * 0.52, vy * 0.52);
        const angle = Math.atan2(vx, vy);
        number(g, String(s.pointValues[f.verts[k]!]), x, y, cell * inr * 0.86, angle, cell * inr * 1.0);
      }
      return;
    }
    if (kind === "dx") return; // no real face for this number: plain faces, the chip carries it
    const text = faceText(kind, f.value);
    const ten = kind === "d10" || kind === "d10x10";
    // a kite's number sits in its wide part, a little toward the apex
    const [x, y] = at(0, ten ? -0.02 : 0);
    const tall = text.length > 1 ? (ten ? 0.95 : 1.12) : ten ? 1.1 : 1.3;
    number(g, text, x, y, cell * inr * tall, 0, cell * inr * (text.length > 1 ? 1.75 : 1.3));
  });
}

interface Baked { texture: THREE.DataTexture; size: [number, number] }
const atlases = new Map<string, Baked>();

/** The engraving of a kind of die (normal map + ink mask), cached; redrawn once the display font arrives. */
export function dieAtlas(kind: Exclude<DieKind, "coin">, cell = 160): THREE.DataTexture {
  const key = `${kind}:${cell}`;
  const known = atlases.get(key);
  if (known) return known.texture;
  const s = dieSolid(kind);
  const w = s.cols * cell;
  const h = s.rows * cell;
  const draw = (): Uint8Array => {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const g = c.getContext("2d", { willReadFrequently: true })!;
    drawInk(g, s, kind, cell);
    const ink = g.getImageData(0, 0, w, h).data;
    const height = soften(ink, w, h, Math.max(1, Math.round(cell / 90)));
    for (let i = 0; i < height.length; i++) height[i] = 1 - height[i]!; // cut in: the ink lies at the bottom
    return bake(ink, height, w, h, cell / 22);
  };
  const tex = new THREE.DataTexture(draw(), w, h, THREE.RGBAFormat);
  tex.colorSpace = THREE.NoColorSpace;
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  atlases.set(key, { texture: tex, size: [w, h] });
  if (!fontReady()) {
    void document.fonts?.load(`700 64px ${FONT}`).then(() => {
      if (atlases.get(key)?.texture !== tex) return;
      tex.image.data = draw();
      tex.needsUpdate = true;
    }, () => undefined);
  }
  return tex;
}

// -- the coin ---------------------------------------------------------------------------------------------------------

/**
 * The coin's atlas: heads in the left half, tails in the right (each a disc filling its half), the milled rim along
 * a strip at the bottom. RGB normal, A where the field is (sunk, enamelled in the seat colour); the relief stands
 * proud in the metal.
 */
export function coinAtlas(size = 512): THREE.DataTexture {
  const key = `coin:${size}`;
  const known = atlases.get(key);
  if (known) return known.texture;
  const w = size * 2;
  const h = size + size / 8;
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true })!;
  // relief height in white (raised), drawn as a mask; the field (enamel) is everything inside the bead ring that isn't relief
  const R = size / 2;
  const face = (ox: number, heads: boolean) => {
    const cx = ox + R;
    const cy = R;
    g.save();
    g.translate(cx, cy);
    g.fillStyle = "#fff";
    g.strokeStyle = "#fff";
    // the rim and a beaded ring
    g.lineWidth = R * 0.07;
    g.beginPath();
    g.arc(0, 0, R * 0.93, 0, Math.PI * 2);
    g.stroke();
    for (let i = 0; i < 64; i++) {
      const a = (i / 64) * Math.PI * 2;
      g.beginPath();
      g.arc(Math.cos(a) * R * 0.8, Math.sin(a) * R * 0.8, R * 0.022, 0, Math.PI * 2);
      g.fill();
    }
    if (heads) {
      // a crowned profile, facing left
      g.beginPath();
      g.moveTo(-0.06 * R, -0.42 * R);
      g.bezierCurveTo(-0.34 * R, -0.42 * R, -0.42 * R, -0.18 * R, -0.36 * R, -0.04 * R); // brow
      g.lineTo(-0.46 * R, 0.08 * R); // nose
      g.lineTo(-0.36 * R, 0.12 * R);
      g.bezierCurveTo(-0.38 * R, 0.18 * R, -0.34 * R, 0.22 * R, -0.3 * R, 0.24 * R); // lips
      g.bezierCurveTo(-0.34 * R, 0.32 * R, -0.26 * R, 0.4 * R, -0.16 * R, 0.38 * R); // chin
      g.bezierCurveTo(-0.14 * R, 0.5 * R, -0.18 * R, 0.6 * R, -0.24 * R, 0.66 * R); // throat
      g.lineTo(0.3 * R, 0.66 * R); // the bust's cut
      g.bezierCurveTo(0.26 * R, 0.5 * R, 0.3 * R, 0.36 * R, 0.4 * R, 0.24 * R); // nape
      g.bezierCurveTo(0.46 * R, 0.0, 0.36 * R, -0.36 * R, -0.06 * R, -0.42 * R); // the back of the head
      g.fill();
      // the crown
      g.beginPath();
      g.moveTo(-0.3 * R, -0.4 * R);
      for (let i = 0; i <= 4; i++) {
        const x = -0.3 * R + i * 0.15 * R;
        g.lineTo(x, -0.64 * R + (i % 2 ? 0.08 * R : 0));
        g.lineTo(x + 0.075 * R, -0.46 * R);
      }
      g.lineTo(0.32 * R, -0.4 * R);
      g.closePath();
      g.fill();
      for (let i = 0; i <= 4; i += 2) {
        g.beginPath();
        g.arc(-0.3 * R + i * 0.15 * R, -0.68 * R, R * 0.035, 0, Math.PI * 2);
        g.fill();
      }
    } else {
      // a laurel wreath round a five-pointed star
      for (const side of [-1, 1]) {
        for (let i = 0; i < 9; i++) {
          const a = Math.PI / 2 + side * (0.35 + i * 0.27);
          const x = Math.cos(a) * R * 0.6;
          const y = Math.sin(a) * R * 0.6;
          g.save();
          g.translate(x, y);
          g.rotate(a + side * 0.9);
          g.beginPath();
          g.ellipse(0, 0, R * 0.1, R * 0.04, 0, 0, Math.PI * 2);
          g.fill();
          g.restore();
        }
      }
      g.beginPath();
      for (let i = 0; i < 10; i++) {
        const a = -Math.PI / 2 + (i / 10) * Math.PI * 2;
        const rr = i % 2 ? R * 0.15 : R * 0.36;
        g.lineTo(Math.cos(a) * rr, Math.sin(a) * rr);
      }
      g.closePath();
      g.fill();
    }
    g.restore();
  };
  face(0, true);
  face(size, false);
  const relief = g.getImageData(0, 0, w, h).data;
  const height = soften(relief, w, h, 2);
  // the field: inside the rim and outside the relief takes the enamel
  const ink = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < w; x++) {
    const ox = x < size ? R : size + R;
    const d = Math.hypot(x - ox, y - R) / R;
    const i = y * w + x;
    const field = d < 0.89 ? 1 - relief[i * 4 + 3]! / 255 : 0;
    ink[i * 4 + 3] = Math.round(field * 255);
  }
  // the milled edge: fine vertical ridges along the strip (u runs round the coin)
  for (let y = size; y < h; y++) for (let x = 0; x < w; x++) height[y * w + x] = 0.5 + 0.5 * Math.cos((x / w) * Math.PI * 2 * 120);
  const tex = new THREE.DataTexture(bake(ink, height, w, h, 6), w, h, THREE.RGBAFormat);
  tex.colorSpace = THREE.NoColorSpace;
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  atlases.set(key, { texture: tex, size: [w, h] });
  return tex;
}

/** The coin mesh: a thick disc with rounded edges and a raised lip, UVs into the coin atlas. Cached. */
let coinGeo: THREE.BufferGeometry | null = null;
export function coinGeometry(radius: number, thick: number): THREE.BufferGeometry {
  if (coinGeo) return coinGeo;
  const seg = 64;
  const bevel = thick * 0.28;
  const pos: number[] = [];
  const nor: number[] = [];
  const uv: number[] = [];
  const atlasH = 1 + 1 / 8; // the atlas: two discs side by side over the rim strip
  const faceUv = (heads: boolean, x: number, z: number): [number, number] => {
    // heads seen from above (+y): x right, −z up on the canvas; tails seen from below is mirrored in x
    const u = (heads ? 0.5 : 1.5) + (heads ? x : -x) / (2 * radius) * 0.98;
    const v = 0.5 - z / (2 * radius) * 0.98;
    return [u / 2, 1 - (1 - v) / atlasH];
  };
  const rimV = (t: number) => (1 / 8) * (1 - t) / atlasH; // the strip at the bottom of the atlas
  type V3 = [number, number, number];
  type Corner = [V3, V3, [number, number]];
  /** One triangle, wound counter-clockwise seen from outside (its normals say which side is out). */
  const tri = (a: Corner, b: Corner, c: Corner) => {
    const e1 = [b[0][0] - a[0][0], b[0][1] - a[0][1], b[0][2] - a[0][2]];
    const e2 = [c[0][0] - a[0][0], c[0][1] - a[0][1], c[0][2] - a[0][2]];
    const n = [e1[1]! * e2[2]! - e1[2]! * e2[1]!, e1[2]! * e2[0]! - e1[0]! * e2[2]!, e1[0]! * e2[1]! - e1[1]! * e2[0]!];
    const out = n[0]! * (a[1][0] + b[1][0] + c[1][0]) + n[1]! * (a[1][1] + b[1][1] + c[1][1]) + n[2]! * (a[1][2] + b[1][2] + c[1][2]);
    for (const k of out < 0 ? [a, c, b] : [a, b, c]) {
      pos.push(...k[0]);
      nor.push(...k[1]);
      uv.push(...k[2]);
    }
  };
  for (let i = 0; i < seg; i++) {
    const a0 = (i / seg) * Math.PI * 2;
    const a1 = ((i + 1) / seg) * Math.PI * 2;
    const c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
    for (const heads of [true, false]) {
      const y = heads ? thick / 2 : -thick / 2;
      const n: V3 = [0, heads ? 1 : -1, 0];
      const r = radius - bevel;
      const p0: V3 = [0, y, 0];
      const p1: V3 = [c0 * r, y, s0 * r];
      const p2: V3 = [c1 * r, y, s1 * r];
      tri([p0, n, faceUv(heads, 0, 0)], [p1, n, faceUv(heads, p1[0], p1[2])], [p2, n, faceUv(heads, p2[0], p2[2])]);
    }
    // the rounded edge: a quarter round top and bottom, the milled band between
    const ring = (t: number): { r: number; y: number; nr: number; ny: number } => {
      // t: 0 at the top face's edge, 1 at the bottom face's edge
      const k = 5;
      const steps = 2 * k + 1;
      const j = t * steps;
      if (j <= k) {
        const ang = (j / k) * (Math.PI / 2);
        return { r: radius - bevel + Math.sin(ang) * bevel, y: thick / 2 - bevel + Math.cos(ang) * bevel, nr: Math.sin(ang), ny: Math.cos(ang) };
      }
      if (j >= k + 1) {
        const ang = ((j - k - 1) / k) * (Math.PI / 2);
        return { r: radius - bevel + Math.cos(ang) * bevel, y: -thick / 2 + bevel - Math.sin(ang) * bevel, nr: Math.cos(ang), ny: -Math.sin(ang) };
      }
      const m = j - k;
      return { r: radius, y: thick / 2 - bevel - m * (thick - 2 * bevel), nr: 1, ny: 0 };
    };
    const steps = 11;
    for (let j = 0; j < steps; j++) {
      const A = ring(j / steps), B = ring((j + 1) / steps);
      const u0 = i / seg, u1 = (i + 1) / seg;
      const P = (q: typeof A, c: number, s: number): V3 => [c * q.r, q.y, s * q.r];
      const N = (q: typeof A, c: number, s: number): V3 => [c * q.nr, q.ny, s * q.nr];
      const vA = rimV(j / steps), vB = rimV((j + 1) / steps);
      tri([P(A, c0, s0), N(A, c0, s0), [u0, vA]], [P(A, c1, s1), N(A, c1, s1), [u1, vA]], [P(B, c0, s0), N(B, c0, s0), [u0, vB]]);
      tri([P(B, c0, s0), N(B, c0, s0), [u0, vB]], [P(A, c1, s1), N(A, c1, s1), [u1, vA]], [P(B, c1, s1), N(B, c1, s1), [u1, vB]]);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  g.computeBoundingSphere();
  coinGeo = g;
  return g;
}

/** Forget the cached atlases (their GPU copies are freed by the renderers that used them). */
export function disposeDiceArt(): void {
  for (const a of atlases.values()) a.texture.dispose();
  atlases.clear();
  coinGeo?.dispose();
  coinGeo = null;
}
