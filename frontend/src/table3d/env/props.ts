/**
 * The props standing on the table at its two prop spots (framing.ts propSpots: the far ends of the aisle, framed whole
 * with the table, no taller than PROP_TOP): per plane, a pair such as a brass chamberstick of dripping candles and a
 * stack of leather-bound books with one lying open. Merged into one mesh over the shared atlas (env/atlas.ts); their
 * flames join the room's (env/flames.ts) and each lit prop has a real, flickering light that falls on the table.
 */
import * as THREE from "three";
import { SWAY, xf } from "./batch";
import { ATLAS } from "./atlas";
import { candleBody } from "./furniture";
import { BRASS, CLOTH, IRON, Put, STONE, vary, WOOD, type SetCtx } from "./kit";
import { PULSE } from "./roomShader";

export type TableProp = "candles" | "books" | "lantern" | "ledger" | "tallow" | "tome" | "oillamp" | "amphora" | "hedron" | "compass" | "andon" | "teaset" | "scarab" | "coins" | "chest" | "vial" | "spikes" | "mushrooms" | "acorn";

/** A light the prop asks for: where (world), its colour and strength (TableScene-style intensity) and reach. */
export interface PropLight { pos: THREE.Vector3; color: string; intensity: number; distance: number }

/**
 * How far a prop may reach from its spot (world units, across and along the table): in 1v1 the spot is 0.6 from the
 * rail across the table and 1.6 from the nearest pile along it.
 */
export const PROP_HALF: readonly [number, number] = [0.58, 0.8];

const PAGES = { uv: ATLAS.pages, rough: 0.8 } as const;
const LEATHER = (rough = 0.62) => ({ uv: ATLAS.leather, rough });

/**
 * A closed book lying flat: boards, a page block with its edges, a rounded spine with raised bands, brass corners.
 * Local frame: its centre at the origin of `at`, spine along −x, `w` (across) × `d` (head to tail) × `h` thick.
 */
function closedBook(at: Put, w: number, d: number, h: number, leather: THREE.ColorRepresentation, corners = true): void {
  const b = 0.032; // board
  at.box(w + 0.03, b, d + 0.04, 0.015, 0, 0, leather, LEATHER());
  at.box(w + 0.03, b, d + 0.04, 0.015, h - b, 0, leather, LEATHER());
  at.box(w - 0.03, h - b * 2, d - 0.02, 0.0, b, 0, "#ffffff", PAGES);
  at.geo(new THREE.CylinderGeometry(h / 2, h / 2, d + 0.04, 10, 1, false, Math.PI, Math.PI), xf(-w / 2 + 0.01, h / 2, 0, Math.PI / 2, 0, 0, 0.55, 1, 1), leather, LEATHER());
  for (const t of [-0.32, -0.1, 0.1, 0.32]) at.geo(new THREE.CylinderGeometry(h / 2 + 0.012, h / 2 + 0.012, 0.035, 10, 1, false, Math.PI, Math.PI), xf(-w / 2 + 0.008, h / 2, t * d, Math.PI / 2, 0, 0, 0.6, 1, 1), new THREE.Color(leather).multiplyScalar(0.8), LEATHER(0.5));
  if (corners) for (const [cx, cz] of [[1, 1], [1, -1]] as const) at.geo(new THREE.CylinderGeometry(0.11, 0.11, 0.02, 3), xf(cx * (w / 2 - 0.03), h - 0.004, cz * (d / 2 - 0.035), 0, cz > 0 ? Math.PI / 6 : -Math.PI / 6 + Math.PI, 0), "#b48a3e", BRASS);
}

/** A book lying open, pages curling up from the gutter, a ribbon trailing. Its spine along z. */
function openBook(at: Put, w: number, d: number, leather: THREE.ColorRepresentation, rand: () => number): void {
  const half = w / 2;
  at.box(w + 0.08, 0.03, d + 0.05, 0, 0, 0, leather, LEATHER());
  for (const s of [-1, 1]) {
    // the leaves under the open page: a block thinning toward the outer edge
    at.box(half - 0.04, 0.07, d - 0.02, s * (half / 2 + 0.005), 0.03, 0, "#ffffff", PAGES);
    // the page: a sheet curving up from the gutter and settling flat
    const g = new THREE.PlaneGeometry(half, d, 10, 1);
    const p = g.getAttribute("position");
    const uv = g.getAttribute("uv");
    for (let i = 0; i < p.count; i++) {
      const u = (p.getX(i) + half / 2) / half; // 0 at the gutter, 1 at the outer edge
      const y = 0.16 * Math.sin(Math.min(1, u * 1.5) * Math.PI * 0.5) * (1 - u * 0.6) + 0.025 * u;
      p.setXYZ(i, s * (u * half), p.getY(i), y);
      if (s < 0) uv.setX(i, 1 - uv.getX(i));
    }
    // (the plane's +z face turns up; the left page is mirrored in x, which turns it face down: flip its winding)
    if (s < 0 && g.index) g.setIndex(Array.from(g.index.array).reverse());
    g.computeVertexNormals();
    // shaded into the gutter, where the page curls away from the light
    const paper = new THREE.Color("#cdbf9f");
    at.geo(g, xf(0, 0.1, 0, -Math.PI / 2, 0, 0), (_p, n, out) => out.copy(paper).multiplyScalar(0.45 + 0.55 * Math.pow(Math.max(0, n.y), 6)), { uv: ATLAS.parchment, rough: 0.85 });
  }
  // a ribbon marker trailing over the tail
  at.box(0.04, 0.006, d * 0.45, half * 0.15, 0.115, d * 0.42, "#7a1a1a", { rough: 0.5 }, 0.1);
  at.box(0.04, 0.12, 0.006, half * 0.17, 0.0, d / 2 + 0.05, "#7a1a1a", { rough: 0.5 }, 0.1, 0.2);
  void rand;
}

/** A brass chamberstick with three dripping candles (heights fitted under PROP_TOP). Returns the flames' tips. */
function candles(ctx: SetCtx, at: Put, wax: string, metal: string, metalSurf = BRASS, tallow = false): THREE.Vector3[] {
  const r = ctx.rand;
  // the dish: a shallow tray with a rolled rim, a finger ring
  at.lathe([[0, 0], [0.44, 0], [0.5, 0.025], [0.52, 0.07], [0.49, 0.085], [0.44, 0.05], [0.0, 0.05]], 0, 0, 0, metal, metalSurf, 24);
  at.geo(new THREE.TorusGeometry(0.1, 0.024, 6, 14), xf(0.1, 0.06, 0.6, Math.PI / 2, 0, 0), metal, metalSurf);
  // wax pooled on the dish, and a spent stub
  at.lathe([[0, 0], [0.28, 0], [0.33, 0.012], [0.2, 0.03], [0, 0.03]], -0.06, 0.05, 0.04, wax, { rough: 0.5 }, 16, 1.3, 1, 1);
  const tops: THREE.Vector3[] = [];
  const set: [number, number, number, number][] = [[0.04, -0.13, 0.13, 0.86], [-0.2, 0.12, 0.11, 0.62], [0.22, 0.15, 0.1, 0.44]];
  for (const [cx, cz, rad, hh] of set) {
    // a socket cup under each candle
    at.lathe([[0, 0], [rad + 0.05, 0], [rad + 0.06, 0.05], [rad + 0.02, 0.06], [0, 0.06]], cx, 0.05, cz, metal, metalSurf, 14);
    candleBody(at, cx, 0.1, cz, rad, hh, r, tallow ? "#e4d6b0" : wax);
    if (tallow) for (let k = 0; k < 3; k++) {
      // tallow runs long and pools at the foot
      const a = r() * Math.PI * 2;
      at.sphere(rad * 0.35, cx + Math.cos(a) * rad * 1.1, 0.12, cz + Math.sin(a) * rad * 1.1, "#e4d6b0", { rough: 0.5 }, 1, 0.45, 1, 8);
    }
    tops.push(at.world(cx, 0.1 + hh + 0.03, cz));
  }
  return tops;
}

/** A small iron lantern with lit glass and a flame inside. Returns the flame's base. */
function tableLantern(ctx: SetCtx, at: Put, glass: string, iron: string): THREE.Vector3 {
  const s = 0.5;
  at.box(s * 1.1, 0.06, s * 1.1, 0, 0, 0, iron, IRON);
  at.box(s * 1.2, 0.05, s * 1.2, 0, 0.06 + s * 1.3, 0, iron, IRON);
  at.geo(new THREE.ConeGeometry(s * 0.72, s * 0.45, 4), xf(0, 0.11 + s * 1.3 + s * 0.22, 0, 0, Math.PI / 4), iron, IRON);
  at.geo(new THREE.TorusGeometry(s * 0.17, 0.02, 5, 12), xf(0, 0.11 + s * 1.3 + s * 0.5, 0), iron, IRON);
  for (const [cx, cz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) at.box(0.045, s * 1.3, 0.045, cx * s * 0.52, 0.06, cz * s * 0.52, iron, IRON);
  for (const t of [0.35, 0.75]) for (const [ax, az, ry] of [[0, 1, 0], [0, -1, 0], [1, 0, Math.PI / 2], [-1, 0, Math.PI / 2]] as const) at.box(s * 1.04, 0.02, 0.02, ax * s * 0.52, 0.06 + s * 1.3 * t, az * s * 0.52, iron, IRON, ry);
  // clear glass (unseen but for the flame and its light on the frame), a stub of candle inside on a drip tray
  at.lathe([[0, 0], [0.16, 0], [0.17, 0.02], [0, 0.02]], 0, 0.06, 0, glass === "" ? iron : "#8a6a2a", BRASS, 12);
  candleBody(at, 0, 0.08, 0, 0.08, 0.22, ctx.rand);
  return at.world(0, 0.08 + 0.24, 0);
}

/** Gold coins in a slumped pile. */
function coinPile(ctx: SetCtx, at: Put, n: number, gold: string): void {
  for (let i = 0; i < n; i++) {
    const a = ctx.rand() * Math.PI * 2, rr = Math.sqrt(ctx.rand()) * 0.42;
    const y = Math.max(0, (0.42 - rr) * 0.45) + ctx.rand() * 0.02;
    at.geo(new THREE.CylinderGeometry(0.09, 0.09, 0.022, 14), xf(Math.cos(a) * rr, y + 0.011, Math.sin(a) * rr, (ctx.rand() - 0.5) * 0.6, 0, (ctx.rand() - 0.5) * 0.6), vary(ctx, gold, 0.08), { rough: 0.28, metal: 1 });
  }
}

/** A faceted floating stone with glowing seams (it bobs: returned as a mover-ready group by the caller). */
function hedronGeo(len: number, r: number): THREE.BufferGeometry {
  const g = new THREE.OctahedronGeometry(1, 0);
  g.scale(r, len / 2, r);
  return g;
}

/** Build one table prop at `at` (its spot, on the table top). Returns the lights it asks for. */
export function buildTableProp(ctx: SetCtx, at: Put, kind: TableProp, glow: string): PropLight[] {
  const r = ctx.rand;
  const lights: PropLight[] = [];
  const flame = (p: THREE.Vector3, size = 0.46, tint = "#ffb45a", h = 0.62) => ctx.flames.add(p, size, r() * 10, tint, h);
  switch (kind) {
    case "candles":
    case "tallow": {
      const tallow = kind === "tallow";
      const tops = candles(ctx, at.at(0, 0, 0, (r() - 0.5) * 0.4), tallow ? "#d8c8a0" : "#e8d6b2", tallow ? "#5a5e66" : "#a8823a", tallow ? IRON : BRASS, tallow);
      for (const t of tops) flame(t, 0.44);
      const c = tops[0]!;
      // (from a little above the flames: the wax right under it would burn white)
      lights.push({ pos: new THREE.Vector3(c.x, c.y + 1.0, c.z), color: glow, intensity: 6.5, distance: 16 });
      break;
    }
    case "books":
    case "ledger":
    case "tome": {
      const pal = kind === "ledger" ? ["#22304a", "#2e3446", "#3a2a40"] : kind === "tome" ? ["#1a1a1e", "#3a1418", "#2a2622"] : ["#5a1a14", "#24402c", "#2b3a5a", "#6a4a22"];
      // (the books' long side along the table, where the spot has room)
      const ry = (r() - 0.5) * 0.2;
      const base = at.at(0, 0, 0, ry);
      const w = kind === "tome" ? 0.8 : 0.74, d = kind === "tome" ? 1.1 : 1.0;
      closedBook(base.at(0.02, 0, 0.02, 0.06), w, d, 0.16, pal[0]!);
      closedBook(base.at(-0.03, 0.16, -0.02, -0.12), w * 0.94, d * 0.94, 0.13, pal[1]!, kind !== "ledger");
      if (kind === "ledger") {
        closedBook(base.at(0.0, 0.29, 0.0, 0.2), w * 0.9, d * 0.88, 0.11, pal[2]!);
        // a silver seal stamp on top, and a stick of sealing wax
        base.lathe([[0, 0], [0.13, 0], [0.13, 0.04], [0.06, 0.06], [0.05, 0.2], [0.09, 0.26], [0.06, 0.32], [0, 0.32]], 0.12, 0.4, 0.05, "#b7c3d9", { rough: 0.3, metal: 1 }, 14);
        base.box(0.05, 0.05, 0.42, -0.2, 0.4, -0.1, "#8a1a22", { rough: 0.4 }, 0.5);
      } else {
        // the top book lies open; a ribbon over its tail
        // (its spine toward me: the pages open left and right as I would read them)
        openBook(base.at(0.0, 0.29, 0.02, 0.08 + (kind === "tome" ? -0.06 : 0)), 0.96, 0.72, pal[2] ?? pal[0]!, r);
        if (kind === "tome") {
          // a silver clasp and a pewter holy symbol beside
          base.box(0.08, 0.05, 0.14, w / 2 + 0.02, 0.06, 0.0, "#c3ccd8", { rough: 0.25, metal: 1 });
        }
      }
      break;
    }
    case "lantern": {
      const f = tableLantern(ctx, at.at(0, 0, 0, r()), "#ffcf86", "#1c1e24");
      flame(f, 0.3, "#ffc070", 0.7);
      lights.push({ pos: f.clone().setY(f.y + 0.3), color: glow, intensity: 5, distance: 15 });
      break;
    }
    case "oillamp": {
      // a terracotta (or bronze) oil lamp on a low stand, its wick at the nozzle
      const bronze = glow === "#ffcf6a";
      const col = bronze ? "#8a6a2e" : "#a4532c";
      const surf = bronze ? BRASS : { rough: 0.7 };
      at.lathe([[0, 0], [0.32, 0], [0.34, 0.04], [0.12, 0.12], [0.1, 0.5], [0.2, 0.56], [0.0, 0.56]], 0, 0, 0, col, surf, 18);
      const lamp = at.at(0, 0.56, 0, r() * 6);
      lamp.sphere(0.24, 0, 0.1, 0, col, surf, 1, 0.5, 1.15, 16);
      lamp.geo(new THREE.CylinderGeometry(0.05, 0.08, 0.3, 10), xf(0, 0.12, 0.3, Math.PI / 2 - 0.25, 0, 0), col, surf);
      lamp.geo(new THREE.TorusGeometry(0.07, 0.02, 6, 12), xf(0, 0.2, -0.24, 0, 0, 0), col, surf);
      lamp.cyl(0.06, 0.09, 0.03, 0, 0.18, 0, "#2a1a10", { rough: 0.6 }, 10);
      if (!bronze) for (let k = 0; k < 8; k++) lamp.box(0.02, 0.04, 0.02, Math.cos(k * 0.8) * 0.19, 0.14, Math.sin(k * 0.8) * 0.19, "#d8a070", { rough: 0.8 });
      const tip = lamp.world(0, 0.2, 0.44);
      flame(tip, 0.42, "#ffb050", 0.7);
      lights.push({ pos: tip.clone().setY(tip.y + 0.3), color: glow, intensity: 5, distance: 15 });
      break;
    }
    case "amphora": {
      at.lathe([[0, 0], [0.12, 0], [0.14, 0.04], [0.28, 0.22], [0.31, 0.45], [0.24, 0.7], [0.09, 0.82], [0.08, 0.95], [0.12, 1.0], [0.0, 1.0]], 0, 0, 0, "#9a4a24", { rough: 0.7 }, 20);
      for (const s of [-1, 1]) at.geo(new THREE.TorusGeometry(0.12, 0.022, 6, 12, Math.PI), xf(s * 0.16, 0.82, 0, 0, 0, s * -1.1), "#9a4a24", { rough: 0.7 });
      // black-figure bands
      at.cyl(0.3, 0.315, 0.06, 0, 0.42, 0, "#1a120c", { rough: 0.6 }, 20);
      at.cyl(0.285, 0.3, 0.04, 0, 0.56, 0, "#1a120c", { rough: 0.6 }, 20);
      // a laurel wreath beside it
      const wreath = at.at(0.22, 0.02, 0.42);
      for (let k = 0; k < 14; k++) {
        const a = (k / 14) * Math.PI * 1.8;
        wreath.sphere(0.06, Math.cos(a) * 0.22, 0, Math.sin(a) * 0.22, "#c9a24a", { rough: 0.35, metal: 1 }, 1, 0.4, 2.2);
      }
      break;
    }
    case "hedron": {
      // a small hedron hovering over a stone cradle, turning, its seams aglow
      at.lathe([[0, 0], [0.34, 0], [0.38, 0.06], [0.2, 0.14], [0, 0.14]], 0, 0, 0, "#5a5446", STONE, 6);
      const base = at.world(0, 0.66, 0);
      const h = new Put(ctx).at(base.x, base.y, base.z, 0, 0.12, 0.1).swaying(base, SWAY.hover, r() * 6);
      h.geo(hedronGeo(0.74, 0.19), null, "#7a7462", { rough: 0.75 });
      for (const t of [-0.11, 0.11]) h.glowing().geo(new THREE.CylinderGeometry(0.19 * (1 - Math.abs(t) * 2.6) * 0.74, 0.19 * (1 - Math.abs(t) * 2.6) * 0.74, 0.03, 4), xf(0, t, 0), "#7dffc0", { glow: 1.6 });
      lights.push({ pos: base.clone(), color: "#7dffc0", intensity: 2.5, distance: 8 });
      break;
    }
    case "compass": {
      // a rolled map and a brass compass on it
      at.geo(new THREE.CylinderGeometry(0.1, 0.1, 0.95, 12), xf(0, 0.1, 0, 0, 0.5, Math.PI / 2), "#ffffff", { uv: ATLAS.parchment, rough: 0.85 });
      at.geo(new THREE.CylinderGeometry(0.11, 0.11, 0.06, 12), xf(Math.cos(0.5) * 0.48, 0.1, -Math.sin(0.5) * 0.48, 0, 0.5, Math.PI / 2), "#8a5a2a", WOOD);
      at.lathe([[0, 0], [0.24, 0], [0.26, 0.05], [0.22, 0.07], [0, 0.06]], 0.18, 0, 0.32, "#b48a3e", BRASS, 22);
      at.box(0.03, 0.01, 0.34, 0.18, 0.07, 0.32, "#8a1a1a", { rough: 0.4 }, r() * 3);
      break;
    }
    case "andon": {
      // a paper floor lantern in miniature: a wooden frame round glowing paper
      const s = 0.42;
      for (const [cx, cz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) at.box(0.05, 1.12, 0.05, cx * s, 0, cz * s, "#2a1a12", WOOD);
      for (const y of [0.08, 1.06]) for (const [ax, az, ry] of [[0, 1, 0], [0, -1, 0], [1, 0, Math.PI / 2], [-1, 0, Math.PI / 2]] as const) at.box(s * 2 + 0.05, 0.05, 0.05, ax * s, y, az * s, "#2a1a12", WOOD, ry);
      at.glowing().box(s * 1.92, 0.94, s * 1.92, 0, 0.12, 0, "#d8a46a", { glow: 0.7, pulse: PULSE.lantern, uv: ATLAS.parchment, rough: 0.9 });
      for (const y of [0.42, 0.74]) for (const [ax, az, ry] of [[0, 1, 0], [0, -1, 0], [1, 0, Math.PI / 2], [-1, 0, Math.PI / 2]] as const) at.box(s * 2 + 0.02, 0.03, 0.03, ax * (s + 0.005), y, az * (s + 0.005), "#2a1a12", WOOD, ry);
      const f = at.world(0, 0.4, 0);
      flame(f, 0.22, "#ffb060");
      lights.push({ pos: f.clone().setY(f.y + 0.3), color: glow, intensity: 6, distance: 15 });
      break;
    }
    case "teaset": {
      at.cyl(0.54, 0.54, 0.04, 0, 0, 0, "#1a0c0a", { rough: 0.3 }, 24); // a lacquer tray
      at.lathe([[0, 0], [0.16, 0], [0.24, 0.1], [0.25, 0.2], [0.18, 0.3], [0.08, 0.32], [0.0, 0.32]], -0.18, 0.04, -0.05, "#3a4a3e", { rough: 0.25 }, 18);
      at.geo(new THREE.CylinderGeometry(0.025, 0.04, 0.22, 8), xf(0.06, 0.2, -0.05, 0, 0, -1.0), "#3a4a3e", { rough: 0.25 });
      at.geo(new THREE.TorusGeometry(0.16, 0.02, 6, 14, Math.PI), xf(-0.18, 0.36, -0.05, 0, 0, 0), "#2a1a12", WOOD);
      for (const [cx, cz] of [[0.28, 0.2], [0.05, 0.36]] as const) {
        at.lathe([[0, 0], [0.06, 0], [0.1, 0.12], [0.1, 0.13], [0.0, 0.13]], cx, 0.04, cz, "#e8e0d0", { rough: 0.2 }, 16);
        at.cyl(0.085, 0.085, 0.005, cx, 0.15, cz, "#5a7a3a", { rough: 0.1 }, 14);
      }
      break;
    }
    case "scarab": {
      at.box(0.5, 0.18, 0.5, 0, 0, 0, "#b8925c", STONE);
      at.box(0.56, 0.05, 0.56, 0, 0.18, 0, "#24479a", { rough: 0.3 });
      at.sphere(0.2, 0, 0.3, 0, "#1d3a8a", { rough: 0.2, metal: 0.4 }, 1, 0.55, 1.3, 14);
      at.sphere(0.09, 0, 0.3, 0.24, "#e3b04b", BRASS, 1, 0.7, 0.8, 10);
      at.box(0.02, 0.02, 0.4, 0, 0.4, 0, "#e3b04b", BRASS);
      // and a canopic jar beside it
      at.lathe([[0, 0], [0.12, 0], [0.16, 0.2], [0.14, 0.42], [0.1, 0.46], [0.0, 0.46]], 0.05, 0, 0.56, "#d8c8a0", STONE, 16);
      at.sphere(0.12, 0.05, 0.52, 0.56, "#e3b04b", BRASS, 1, 0.9, 1, 12);
      break;
    }
    case "coins":
      coinPile(ctx, at, 46, "#e8b53a");
      at.box(0.5, 0.02, 0.36, 0.25, 0, -0.3, "#ffffff", { uv: ATLAS.parchment, rough: 0.9 }, 0.4);
      break;
    case "chest": {
      const c = at.at(0, 0, 0, r() - 0.5);
      c.box(0.8, 0.34, 0.5, 0, 0, 0, "#4a2c18", WOOD);
      for (const bx of [-0.3, 0, 0.3]) c.box(0.06, 0.35, 0.52, bx, 0, 0, "#8a6a2a", BRASS);
      // the lid open, gold heaped inside
      c.geo(new THREE.CylinderGeometry(0.25, 0.25, 0.8, 12, 1, false, 0, Math.PI), xf(0, 0.34 + 0.18, -0.38, -1.2, 0, Math.PI / 2), "#4a2c18", WOOD);
      coinPile(ctx, c.at(0, 0.3, 0, 0, 0, 0, 0.85), 22, "#e8b53a");
      break;
    }
    case "vial": {
      // a vial of glistening oil in a cradle of bone, glowing faintly
      at.lathe([[0, 0], [0.3, 0], [0.34, 0.06], [0.2, 0.12], [0.0, 0.12]], 0, 0, 0, "#d8dcd0", { rough: 0.35 }, 16);
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2;
        at.geo(new THREE.ConeGeometry(0.035, 0.75, 6), xf(Math.cos(a) * 0.22, 0.45, Math.sin(a) * 0.22, Math.sin(a) * 0.25, 0, -Math.cos(a) * 0.25), "#e4e8dc", { rough: 0.3 });
      }
      at.glowing().lathe([[0, 0], [0.11, 0], [0.13, 0.3], [0.06, 0.45], [0.05, 0.6], [0, 0.6]], 0, 0.12, 0, "#4aff6a", { glow: 0.9, pulse: PULSE.lantern, rough: 0.05 }, 16);
      lights.push({ pos: at.world(0, 0.6, 0), color: "#9aff6a", intensity: 3, distance: 10 });
      break;
    }
    case "spikes":
      at.lathe([[0, 0], [0.4, 0], [0.42, 0.08], [0.0, 0.1]], 0, 0, 0, "#1a1c1a", { rough: 0.4, metal: 0.9 }, 8);
      for (let k = 0; k < 7; k++) {
        const a = r() * Math.PI * 2, rr = r() * 0.25;
        const h = 0.5 + r() * 0.75;
        at.geo(new THREE.ConeGeometry(0.05 + r() * 0.04, h, 6), xf(Math.cos(a) * rr, 0.08 + h / 2, Math.sin(a) * rr, (r() - 0.5) * 0.5, 0, (r() - 0.5) * 0.5), "#d8dcd0", { rough: 0.3 });
      }
      break;
    case "mushrooms": {
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2 + r(), rr = 0.08 + r() * 0.2;
        const h = 0.25 + r() * 0.55, cap = 0.13 + r() * 0.12;
        const x = Math.cos(a) * rr, z = Math.sin(a) * rr;
        at.cyl(0.035, 0.05, h, x, 0, z, "#e8e0c8", { rough: 0.8 }, 8);
        at.glowing().geo(new THREE.SphereGeometry(cap, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2), xf(x, h, z, 0, 0, 0, 1, 0.75, 1), vary(ctx, "#b84a7a", 0.15), { glow: 0.6, pulse: PULSE.lantern, rough: 0.5 });
        for (let s = 0; s < 4; s++) at.sphere(0.018, x + Math.cos(s * 1.6) * cap * 0.5, h + cap * 0.62, z + Math.sin(s * 1.6) * cap * 0.5, "#fff0d0", { glow: 0.8 });
      }
      at.lathe([[0, 0], [0.5, 0], [0.42, 0.06], [0, 0.07]], 0, 0, 0, "#3a4a26", { rough: 1 }, 10); // moss
      lights.push({ pos: at.world(0, 0.8, 0), color: "#e0a0ff", intensity: 3, distance: 10 });
      break;
    }
    case "acorn": {
      at.sphere(0.2, 0, 0.25, 0, "#8a5a2a", { rough: 0.5 }, 1, 1.25, 1, 14);
      at.geo(new THREE.SphereGeometry(0.22, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2), xf(0, 0.41, 0, 0, 0, 0, 1, 0.7, 1), "#5a4024", { rough: 1 });
      at.cyl(0.02, 0.03, 0.12, 0, 0.55, 0, "#5a4024", { rough: 1 }, 6);
      // a fallen leaf and a dewdrop
      const leaf = new THREE.CircleGeometry(0.3, 10);
      leaf.scale(1, 0.5, 1);
      leaf.rotateX(-Math.PI / 2);
      leaf.rotateY(1.3);
      at.geo(leaf, xf(0.12, 0.02, 0.42), "#b8862a", CLOTH);
      at.sphere(0.04, 0.16, 0.06, 0.46, "#cfe8ff", { rough: 0.05, glow: 0.2 });
      break;
    }
  }
  return lights;
}
