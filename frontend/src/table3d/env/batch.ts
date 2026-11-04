/**
 * Merging a set's many small parts into a few meshes: every part is added with its transform, colour and surface
 * (roughness, metalness, self-light, pulse channel; see roomShader.ts), and the batch comes out as one geometry, one
 * draw call however many books, stones or posts it holds.
 */
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

export interface Surface {
  rough?: number;
  metal?: number;
  /** Self-light, as a share of the part's own colour. */
  glow?: number;
  /** roomShader PULSE channel. */
  pulse?: number;
  /** Self-light varying over the part (world position after the transform): e.g. wax lit from within near the flame. */
  glowAt?: (p: THREE.Vector3) => number;
  /** Where the part's own 0–1 UVs land in the material's atlas (env/atlas.ts): [u, v, width, height]. */
  uv?: readonly [number, number, number, number];
  /** Moves on the GPU (roomShader.ts swayPos): its pivot (world) and code (SWAY kind × 100 + phase). */
  sway?: readonly [number, number, number, number];
  /** Where the piece this part belongs to stands (world x, z): the cutaway hides a piece whole (roomShader.ts). */
  anchor?: readonly [number, number];
}

/** GPU motion kinds for `Surface.sway`: a lantern swinging on its chain, a big stone adrift, a small one hovering. */
export const SWAY = { swing: 1, drift: 2, hover: 3 } as const;

const tmpColor = new THREE.Color();
/** The atlas's plain white cell (env/atlas.ts), for parts with no texture of their own. */
export const NEUTRAL_UV = [0.77, 0.77, 0.2, 0.2] as const;

export class Batch {
  private parts: THREE.BufferGeometry[] = [];
  /** Triangles so far (diagnostics). */
  tris = 0;

  /**
   * Add a part: `geo` is consumed (transformed in place). `color` may be one colour, or a function of the vertex's
   * world position and normal (baked shading: soot, wear, dust on the top faces).
   */
  add(geo: THREE.BufferGeometry, m: THREE.Matrix4 | null, color: THREE.ColorRepresentation | ((p: THREE.Vector3, n: THREE.Vector3, out: THREE.Color) => void), s: Surface = {}): this {
    // (kept indexed, so a merged set shades each shared corner once: the software renderer felt every copy)
    const g = geo;
    if (!g.index) g.setIndex(Array.from({ length: g.getAttribute("position").count }, (_, i) => i));
    if (m) g.applyMatrix4(m);
    if (!g.getAttribute("normal")) g.computeVertexNormals();
    for (const name of Object.keys(g.attributes)) if (name !== "position" && name !== "normal" && name !== "uv") g.deleteAttribute(name);
    if (!g.getAttribute("uv")) g.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(g.getAttribute("position").count * 2), 2));
    const uv = g.getAttribute("uv") as THREE.BufferAttribute;
    const r = s.uv ?? NEUTRAL_UV;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, r[0] + THREE.MathUtils.clamp(uv.getX(i), 0, 1) * r[2], r[1] + THREE.MathUtils.clamp(uv.getY(i), 0, 1) * r[3]);
    const pos = g.getAttribute("position");
    const nor = g.getAttribute("normal");
    const n = pos.count;
    const col = new Float32Array(n * 3);
    const surf = new Float32Array(n * 4);
    const sway = new Float32Array(n * 4);
    const anchor = new Float32Array(n * 2);
    const sw = s.sway ?? [0, 0, 0, -1];
    // a part placed without a piece of its own stands where its middle is (the cutaway takes it whole)
    let own = s.anchor;
    if (!own) {
      g.computeBoundingBox();
      const c = g.boundingBox!.getCenter(new THREE.Vector3());
      own = [c.x, c.z];
    }
    const p = new THREE.Vector3();
    const q = new THREE.Vector3();
    const fixed = typeof color === "function" ? null : tmpColor.set(color).clone();
    for (let i = 0; i < n; i++) {
      if (fixed) col.set([fixed.r, fixed.g, fixed.b], i * 3);
      else {
        p.fromBufferAttribute(pos, i);
        q.fromBufferAttribute(nor, i);
        (color as (p: THREE.Vector3, n: THREE.Vector3, out: THREE.Color) => void)(p, q, tmpColor);
        col.set([tmpColor.r, tmpColor.g, tmpColor.b], i * 3);
      }
      if (s.glowAt) p.fromBufferAttribute(pos, i);
      surf.set([s.rough ?? 0.85, s.metal ?? 0, s.glowAt ? s.glowAt(p) : s.glow ?? 0, s.pulse ?? 0], i * 4);
      sway.set(sw, i * 4);
      anchor.set(own, i * 2);
    }
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    g.setAttribute("aSurf", new THREE.BufferAttribute(surf, 4));
    g.setAttribute("aSway", new THREE.BufferAttribute(sway, 4));
    g.setAttribute("aAnchor", new THREE.BufferAttribute(anchor, 2));
    this.parts.push(g);
    this.tris += g.index!.count / 3;
    return this;
  }

  get empty(): boolean {
    return this.parts.length === 0;
  }

  /** The merged geometry (null when nothing was added). The parts are released. */
  build(): THREE.BufferGeometry | null {
    if (!this.parts.length) return null;
    // (last added first: furniture is added after the walls it stands against, so drawn first it hides them from
    // the depth test instead of being shaded over them)
    const merged = mergeGeometries(this.parts.slice().reverse(), false);
    for (const p of this.parts) p.dispose();
    this.parts = [];
    merged?.computeBoundingSphere();
    return merged;
  }
}

const M = new THREE.Matrix4();
const Q = new THREE.Quaternion();
const E = new THREE.Euler();
const S = new THREE.Vector3();
const P = new THREE.Vector3();

/** A transform from a position, rotation (x, y, z radians) and scale. */
export function xf(x: number, y: number, z: number, rx = 0, ry = 0, rz = 0, sx = 1, sy = sx, sz = sx): THREE.Matrix4 {
  return M.clone().compose(P.set(x, y, z), Q.setFromEuler(E.set(rx, ry, rz)), S.set(sx, sy, sz));
}
