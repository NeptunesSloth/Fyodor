/**
 * The set builder's toolkit: a context carrying the batches a set is merged into (solid parts, self-lit parts), the
 * room's flames and light, and small helpers to add primitives at a placement with baked shading (darker toward the
 * floor and underneath, a little lighter on top, as dust and bounce light would leave them).
 */
import * as THREE from "three";
import { Batch, xf, type Surface } from "./batch";
import type { Flames } from "./flames";
import type { RoomLight } from "./roomShader";

export interface SetCtx {
  /** Solid parts of the room (one draw call). */
  set: Batch;
  /** Self-lit parts: embers, lit glass, lantern paper (one draw call). */
  glow: Batch;
  flames: Flames;
  room: RoomLight;
  rand: () => number;
  floorY: number;
  /** "medium" builds a lighter set than "high". */
  rich: boolean;
}

export type Shade = THREE.ColorRepresentation | ((p: THREE.Vector3, n: THREE.Vector3, out: THREE.Color) => void);

/** Baked shading: darker toward the floor and on undersides, a hair lighter on top faces. */
export function baked(color: THREE.ColorRepresentation, floorY: number, opts: { ao?: number; reach?: number; top?: number } = {}): Shade {
  const base = new THREE.Color(color);
  const ao = opts.ao ?? 0.45;
  const reach = opts.reach ?? 3;
  const top = opts.top ?? 1.08;
  return (p, n, out) => {
    const k = THREE.MathUtils.smoothstep(p.y, floorY, floorY + reach);
    out.copy(base).multiplyScalar((1 - ao) + ao * k);
    if (n.y > 0.6) out.multiplyScalar(top);
    else if (n.y < -0.6) out.multiplyScalar(0.55);
  };
}

/** A tone of `color` varied by ±`amount` (multiplicative), from the context's random stream. */
export function vary(ctx: SetCtx, color: THREE.ColorRepresentation, amount: number): THREE.Color {
  return new THREE.Color(color).multiplyScalar(1 + (ctx.rand() - 0.5) * 2 * amount);
}

/** Placement helpers: everything is added at `parent × local`. */
export class Put {
  constructor(private ctx: SetCtx, private parent: THREE.Matrix4 = new THREE.Matrix4(), private into: "set" | "glow" = "set", private sway?: readonly [number, number, number, number], private anchor?: readonly [number, number]) {}

  /**
   * A child placement (local transform composed onto this one). The first placement off the room's origin is where its
   * piece stands (its anchor: the cutaway takes the piece away whole when it stands between the camera and the table).
   */
  at(x: number, y: number, z: number, ry = 0, rx = 0, rz = 0, s = 1): Put {
    const m = this.parent.clone().multiply(xf(x, y, z, rx, ry, rz, s));
    const p = new THREE.Vector3().setFromMatrixPosition(m);
    return new Put(this.ctx, m, this.into, this.sway, this.anchor ?? [p.x, p.z]);
  }

  glowing(): Put {
    return new Put(this.ctx, this.parent, "glow", this.sway, this.anchor);
  }

  /** Everything added through this placement moves on the GPU about `pivot` (world): batch.ts SWAY kind, a phase. */
  swaying(pivot: THREE.Vector3, kind: number, phase: number): Put {
    return new Put(this.ctx, this.parent, this.into, [pivot.x, pivot.y, pivot.z, kind * 100 + (phase % 6.28)], this.anchor);
  }

  /** The same placement as a piece of its own (the cutaway judges it by its own place, not its parent's). */
  piece(): Put {
    const p = new THREE.Vector3().setFromMatrixPosition(this.parent);
    return new Put(this.ctx, this.parent, this.into, this.sway, [p.x, p.z]);
  }

  /** The motion code of this placement (for a flame riding along). */
  get swayCode(): readonly [number, number, number, number] | undefined {
    return this.sway;
  }

  /** The world position of a local point. */
  world(x: number, y: number, z: number): THREE.Vector3 {
    return new THREE.Vector3(x, y, z).applyMatrix4(this.parent);
  }

  geo(g: THREE.BufferGeometry, local: THREE.Matrix4 | null, color: Shade, s: Surface = {}): this {
    const m = local ? this.parent.clone().multiply(local) : this.parent.clone();
    (this.into === "glow" ? this.ctx.glow : this.ctx.set).add(g, m, color, { ...s, ...(this.sway ? { sway: this.sway } : {}), ...(this.anchor ? { anchor: this.anchor } : {}) });
    return this;
  }

  /** A box with its base at y (not its centre). */
  box(w: number, h: number, d: number, x: number, y: number, z: number, color: Shade, s: Surface = {}, ry = 0, rx = 0, rz = 0): this {
    return this.geo(new THREE.BoxGeometry(w, h, d), xf(x, y + h / 2, z, rx, ry, rz), color, s);
  }

  /** A cylinder standing on y. */
  cyl(rTop: number, rBot: number, h: number, x: number, y: number, z: number, color: Shade, s: Surface = {}, seg = 12, rx = 0, ry = 0, rz = 0): this {
    return this.geo(new THREE.CylinderGeometry(rTop, rBot, h, seg), xf(x, y + h / 2, z, rx, ry, rz), color, s);
  }

  /** A lathe (profile points [radius, height]) standing on y. */
  lathe(profile: [number, number][], x: number, y: number, z: number, color: Shade, s: Surface = {}, seg = 16, sx = 1, sy = 1, sz = 1): this {
    const g = new THREE.LatheGeometry(profile.map(([r, h]) => new THREE.Vector2(Math.max(0, r), h)), seg);
    return this.geo(g, xf(x, y, z, 0, 0, 0, sx, sy, sz), color, s);
  }

  sphere(r: number, x: number, y: number, z: number, color: Shade, s: Surface = {}, sx = 1, sy = 1, sz = 1, seg = 12): this {
    return this.geo(new THREE.SphereGeometry(r, seg, Math.max(6, Math.round(seg * 0.6))), xf(x, y, z, 0, 0, 0, sx, sy, sz), color, s);
  }
}

/** Common palettes and surfaces. */
export const BRASS: Surface = { rough: 0.38, metal: 1 };
export const IRON: Surface = { rough: 0.55, metal: 0.85 };
export const WOOD: Surface = { rough: 0.7 };
export const STONE: Surface = { rough: 0.92 };
export const CLOTH: Surface = { rough: 0.95 };
