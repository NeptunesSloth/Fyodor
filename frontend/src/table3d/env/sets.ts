/**
 * A set around the table for each plane, original and procedural, sized to the table (walls stand a fixed margin past
 * its edges): what to build, the floor and the piece under the table, its windows, practical lights and particles.
 * Seen from the seat the room shows at the table's sides and corners; orbiting or zoomed out it is a dollhouse cut
 * away on the camera's side (roomShader.ts cutaway), its far walls and floor lived in.
 */
import * as THREE from "three";
import type { PlaneId, Particles } from "../../theme/planes";
import type { TableSize } from "../layout";
import { SWAY, xf } from "./batch";
import type { CentreKind, FloorKind } from "./floors";
import { arch, bookcase, bookPile, boulder, candleBody, segments, chest, column, globe, gravestone, hearth, lantern, LEATHERS, leadedWindow, panelledWall, trunk } from "./furniture";
import { baked, BRASS, CLOTH, IRON, Put, STONE, vary, WOOD, type SetCtx } from "./kit";
import { PULSE, WINDOW } from "./roomShader";
import type { TableProp } from "./props";

export interface ParticleSpec {
  kind: Particles;
  color: string;
  /** At "high"; "medium" takes 60%. */
  count: number;
  size: number;
  opacity: number;
  base?: number;
  beam?: number;
  additive?: boolean;
  /** The volume: "room" (around the table, floor to head height), "air" (higher, over the table too) or a box. */
  where: "room" | "air" | ((r: Room) => { min: [number, number, number]; max: [number, number, number] });
}

export interface SetSpec {
  floor: FloorKind;
  floorColors: [string, string];
  /** World units each repeat of the floor texture covers. */
  floorTile: number;
  centre: CentreKind;
  /** The piece under the table, as a margin past the table's edges (x, z). */
  centreMargin: [number, number];
  props: [TableProp, TableProp];
  /** From where (distance from the table's middle, past its edge) the room fades to its dark, and how far. */
  fade: [number, number, number];
  particles: ParticleSpec[];
  build(ctx: SetCtx, room: Room): void;
}

/** The room's extents for this table (world units; the floor at y = floor). */
export interface Room { hw: number; hd: number; back: number; front: number; left: number; right: number; floor: number }

export function roomFor(size: TableSize, floor: number, margin: [number, number, number] = [13, 15, 20]): Room {
  const hw = size.w / 2, hd = size.d / 2;
  return { hw, hd, back: -(hd + margin[0]), front: hd + margin[2], left: -(hw + margin[1]), right: hw + margin[1], floor };
}

/** Placements on the floor along each wall, facing into the room. */
function walls(ctx: SetCtx, r: Room) {
  const f = r.floor;
  return {
    back: (x: number) => new Put(ctx).at(x, f, r.back),
    front: (x: number) => new Put(ctx).at(x, f, r.front, Math.PI),
    left: (z: number) => new Put(ctx).at(r.left, f, z, Math.PI / 2),
    right: (z: number) => new Put(ctx).at(r.right, f, z, -Math.PI / 2),
  };
}

/** Bookcases along a wall from a to b (skipping the gaps), each up to `maxW` wide. */
function shelvesAlong(ctx: SetCtx, place: (x: number) => Put, a: number, b: number, gaps: [number, number][], h: number, wood: string): void {
  let x = a;
  while (x < b - 3) {
    const gap = gaps.find(([g0, g1]) => x + 3 > g0 && x < g1);
    if (gap) { x = gap[1]; continue; }
    const next = gaps.filter(([g0]) => g0 > x).map(([g0]) => g0).reduce((m, v) => Math.min(m, v), b);
    const w = Math.min(10 + ctx.rand() * 3, next - x);
    if (w < 4) { x += w; continue; }
    bookcase(ctx, place(x + w / 2).at(0, 0, 1.9), w - 0.2, h, 3.6, wood);
    x += w;
  }
}

// ------------------------------------------------------------------ Dominaria: a scholar's study

const study: SetSpec = {
  floor: "planks", floorColors: ["#6a4426", "#2a170c"], floorTile: 16,
  centre: "rug", centreMargin: [5.5, 6],
  props: ["books", "candles"],
  fade: [3, 24, 0.82],
  particles: [
    { kind: "dust", color: "#ffe2b4", count: 520, size: 0.11, opacity: 0.85, base: 0.1, beam: 3.2, where: "room" },
    { kind: "embers", color: "#ffa040", count: 70, size: 0.16, opacity: 1, where: (r) => ({ min: [-r.hw - 11, r.floor + 0.8, r.back + 1.7], max: [-r.hw - 4, r.floor + 14, r.back + 4] }) },
  ],
  build(ctx, r) {
    const w = walls(ctx, r);
    const wood = "#3a2416", plaster = "#3b2c22", shelf = "#2e1c10";
    const W = r.right - r.left, D = r.front - r.back;
    // the walls: panelled, plaster above
    panelledWall(ctx, w.back(0), W + 2, 36, wood, plaster);
    panelledWall(ctx, w.left((r.back + r.front) / 2), D + 2, 36, wood, plaster);
    panelledWall(ctx, w.right((r.back + r.front) / 2), D + 2, 36, wood, plaster);
    panelledWall(ctx, w.front(0), W + 2, 36, wood, plaster);
    // the back wall: a stone hearth off to the left (clear of the table, so it shows), books the rest of the way
    const hx = -(r.hw + 7.5);
    hearth(ctx, w.back(hx).at(0, 0, 1.4), 9, 8, "#6a6058", "#3a2214");
    shelvesAlong(ctx, w.back, r.left + 0.5, r.right - 0.5, [[hx - 8.5, hx + 8.5]], 28, shelf);
    // the right wall: a tall window, a window seat with a chest under it, books either side
    const wz = -1;
    leadedWindow(ctx, w.right(wz).at(0, 0, 0.3), 7, 18, 6, wood, "#4a1a1c");
    chest(ctx, new Put(ctx).at(r.right - 3.2, r.floor, wz, -Math.PI / 2), 5, "#3a2412");
    shelvesAlong(ctx, (x) => w.right(x), r.back + 0.5, r.front - 0.5, [[wz - 7, wz + 7]], 28, shelf);
    // the left wall: books, and a writing desk with a candle burning on it
    const dz = r.back + 13;
    shelvesAlong(ctx, (x) => w.left(-x), -(r.front - 0.5), -(r.back + 0.5), [[-dz - 5.5, -dz + 5.5]], 28, shelf);
    const desk = w.left(dz).at(0, 0, 3.4);
    desk.box(9, 0.5, 4.5, 0, 6.6, 0, baked("#3a2214", r.floor), WOOD);
    for (const [lx, lz] of [[-4, -1.9], [4, -1.9], [-4, 1.9], [4, 1.9]] as const) desk.cyl(0.3, 0.24, 6.6, lx, 0, lz, baked("#2e1a0e", r.floor), WOOD, 8);
    desk.box(2.6, 0.08, 1.9, -1.2, 7.1, 0.3, "#a8987a", CLOTH, 0.2);
    desk.box(2.2, 0.08, 1.6, 1.6, 7.1, -0.4, "#9c8c6c", CLOTH, -0.3);
    bookPile(ctx, desk.at(-3, 7.1, -0.6, 0.4), 3);
    desk.lathe([[0, 0], [0.5, 0], [0.55, 0.1], [0.2, 0.2], [0, 0.2]], 3, 7.1, 1.1, "#a8823a", BRASS, 12);
    candleBody(desk, 3, 7.3, 1.1, 0.2, 1.4, ctx.rand);
    ctx.flames.add(desk.world(3, 8.75, 1.1), 0.55, ctx.rand() * 10);
    ctx.room.add(desk.world(3, 9.5, 1.1), "#ffae58", 1.0, 14, "candle", 2.2);
    // by the fire: a reading chair and a little table with a candle; a globe in the far corner; books on the floor
    // (nothing tall in front of the fire: a low footstool with a book left on it, a basket of logs)
    const stool = new Put(ctx).at(hx + 1.5, r.floor, r.back + 8.2, 0.3);
    stool.box(4.0, 1.6, 2.6, 0, 0.7, 0, baked("#2e140e", r.floor, { ao: 0.4 }), { rough: 0.55 });
    stool.geo(new THREE.SphereGeometry(1, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), xf(0, 2.3, 0, 0, 0, 0, 2.05, 0.5, 1.35), baked("#3a1810", r.floor), { rough: 0.5 });
    for (let k = 0; k < 6; k++) stool.sphere(0.09, -1.2 + (k % 3) * 1.2, 2.72, k < 3 ? -0.45 : 0.45, "#1a0806", { rough: 0.4 }, 1, 1, 1, 5);
    for (const [lx, lz] of [[-1.8, -1.1], [1.8, -1.1], [-1.8, 1.1], [1.8, 1.1]] as const) stool.lathe([[0, 0], [0.2, 0], [0.28, 0.3], [0.22, 0.7], [0, 0.7]], lx, 0, lz, "#2a1810", WOOD, 8);
    bookPile(ctx, stool.at(0.6, 2.75, 0.1, 0.5), 1);
    const basket = new Put(ctx).at(hx + 7.5, r.floor, r.back + 3.5);
    basket.lathe([[0, 0], [1.6, 0], [1.9, 1.8], [1.95, 2.0], [0, 2.0]], 0, 0, 0, baked("#5a4024", r.floor), { rough: 0.95 }, 14);
    for (let k = 0; k < 5; k++) basket.geo(new THREE.CylinderGeometry(0.4, 0.42, 3.4, 8), xf((k - 2) * 0.7, 2.2 + (k % 2) * 0.5, (ctx.rand() - 0.5) * 0.6, 0.15, 0, Math.PI / 2 + (ctx.rand() - 0.5) * 0.2), vary(ctx, "#4a3220", 0.15), { rough: 1 });
    const side = new Put(ctx).at(hx - 1, r.floor, r.back + 10);
    side.lathe([[0, 0], [1.2, 0], [0.3, 0.4], [0.25, 5.4], [1.6, 5.6], [1.6, 5.9], [0, 5.9]], 0, 0, 0, baked("#3a2214", r.floor), WOOD, 12);
    candleBody(side, 0.3, 5.9, 0.2, 0.18, 1.0, ctx.rand);
    ctx.flames.add(side.world(0.3, 6.95, 0.2), 0.5, ctx.rand() * 10);
    bookPile(ctx, side.at(-0.5, 5.9, -0.6, 1.2), 2);
    globe(ctx, new Put(ctx).at(r.right - 5.5, r.floor, r.back + 6), "#4a2a16");
    for (const [x, z, n] of [[r.left + 4.5, r.back + 5, 4], [r.right - 4, wz + 8.5, 6], [6, r.back + 4.5, 3], [-r.hw - 4, r.hd + 4, 5], [r.hw + 5, -r.hd - 2, 3]] as const) bookPile(ctx, new Put(ctx).at(x, r.floor, z, ctx.rand() * 6), n);
    // the moon high outside the window: its light falls steeply, a bright pane-patterned patch beside the table
    ctx.room.addWindow({
      centre: new THREE.Vector3(r.right - 0.2, r.floor + 15, wz), u: new THREE.Vector3(0, 0, -1), v: new THREE.Vector3(0, 1, 0),
      halfU: 3.5, halfV: 9, dir: new THREE.Vector3(-0.42, -1, 0.1), color: "#a4bcec", intensity: 0.85, pattern: WINDOW.casement,
    });
  },
};

// ------------------------------------------------------------------ Ravnica: a guildhall

const guildhall: SetSpec = {
  floor: "slate", floorColors: ["#2c3242", "#14171f"], floorTile: 12,
  centre: "mosaic", centreMargin: [7, 7],
  props: ["ledger", "lantern"],
  fade: [3, 24, 0.82],
  particles: [
    { kind: "motes", color: "#ffd9a0", count: 70, size: 0.12, opacity: 0.7, base: 0.2, beam: 1.2, where: "room" },
    { kind: "dust", color: "#d8e0ff", count: 260, size: 0.09, opacity: 0.8, base: 0.02, beam: 3, where: "room" },
  ],
  build(ctx, r) {
    const w = walls(ctx, r);
    const stone = "#4a5064";
    const W = r.right - r.left, D = r.front - r.back;
    // an arcade of round arches all round, a wall behind it
    for (const [place, len] of [[w.back, W], [w.front, W]] as const) {
      const n = Math.max(3, Math.round(len / 11));
      for (let k = 0; k < n; k++) arch(ctx, place(-len / 2 + (k + 0.5) * (len / n)).at(0, 0, 2.5), len / n - 3.2, 14, 2.6, stone);
      panelledWall(ctx, place(0), len + 2, 40, "#232838", "#262c3c", 4);
    }
    for (const place of [w.left, w.right]) {
      const n = Math.max(3, Math.round(D / 11));
      for (let k = 0; k < n; k++) arch(ctx, place(r.back + (k + 0.5) * (D / n)).at(0, 0, 2.5), D / n - 3.2, 14, 2.6, stone);
      panelledWall(ctx, place((r.back + r.front) / 2), D + 2, 40, "#232838", "#262c3c", 4);
    }
    // scroll racks and clerks' lecterns along the back
    // (on the side walls toward the back: out of the seat view's margins)
    for (const rack0 of [w.left(r.back + 4.8), w.right(r.back + 4.8)]) {
      const rack = rack0.at(0, 0, 1.8);
      rack.box(8.6, 11, 3.2, 0, 0, 0, baked("#241c22", r.floor), WOOD);
      rack.box(9.0, 0.5, 3.5, 0, 11, 0.1, "#2c2228", WOOD);
      for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
        const cx = -3 + i * 2, cy = 1.2 + j * 2.4;
        rack.box(1.75, 2.15, 0.3, cx, cy, 1.45, "#0c090c", WOOD); // the cubby's dark mouth
        const n = 1 + Math.floor(ctx.rand() * 3);
        for (let k = 0; k < n; k++) {
          const sx = cx - 0.45 + k * 0.45, sy = cy + 0.28 + (k % 2) * 0.32;
          rack.geo(new THREE.CylinderGeometry(0.2, 0.2, 1.4, 10), xf(sx, sy, 1.4, Math.PI / 2, 0, 0), vary(ctx, "#6a604c", 0.12), CLOTH);
          if (ctx.rand() < 0.35) rack.cyl(0.09, 0.09, 0.04, sx, sy - 0.02, 2.11, "#7a1a1e", { rough: 0.4 }, 8, Math.PI / 2);
        }
      }
    }
    // a clerks' long desk on the left: ledgers open, an inkpot, a candle burning low
    const desk = w.left(r.back + 12).at(0, 0, 3.2);
    desk.box(14, 0.5, 4, 0, 6.4, 0, baked("#2a2230", r.floor), WOOD);
    desk.box(13.4, 6.4, 0.3, 0, 0, -1.7, baked("#221c28", r.floor), WOOD);
    for (const lx of [-6.6, 6.6]) desk.box(0.5, 6.4, 3.6, lx, 0, 0, baked("#221c28", r.floor), WOOD);
    for (const [lx, lz, a] of [[-4, 0.2, 0.2], [0.5, -0.3, -0.15], [4.2, 0.4, 0.3]] as const) {
      bookPile(ctx, desk.at(lx, 6.9, lz - 0.6, a), 2);
      desk.box(2.6, 0.06, 1.8, lx + 0.2, 6.92, lz + 0.8, "#8a7c62", CLOTH, a);
    }
    desk.lathe([[0, 0], [0.4, 0], [0.45, 0.4], [0.2, 0.55], [0, 0.55]], -1.8, 6.9, 1.2, "#14141c", { rough: 0.2 }, 10);
    desk.lathe([[0, 0], [0.5, 0], [0.55, 0.1], [0.2, 0.2], [0, 0.2]], 2.4, 6.9, 1.3, "#9aa6c2", { rough: 0.3, metal: 1 }, 12);
    candleBody(desk, 2.4, 7.1, 1.3, 0.2, 0.9, ctx.rand);
    ctx.flames.add(desk.world(2.4, 8.05, 1.3), 0.5, ctx.rand() * 10);
    ctx.room.add(desk.world(2.4, 9, 1.3), "#ffcf86", 0.8, 12, "candle", 0.4);
    // a surveyor's model of the city on a round table: a crowd of slate towers and spires, a few windows lit
    const model = new Put(ctx).at(r.right - 8, r.floor, r.back + 9);
    model.lathe([[0, 0], [1.4, 0], [0.5, 0.5], [0.4, 6], [3.6, 6.2], [3.6, 6.6], [0, 6.6]], 0, 0, 0, baked("#262030", r.floor), WOOD, 18);
    for (let k = 0; k < 26; k++) {
      const a = ctx.rand() * Math.PI * 2, rr = Math.sqrt(ctx.rand()) * 2.9;
      const tx = Math.cos(a) * rr, tz = Math.sin(a) * rr;
      const tw = 0.3 + ctx.rand() * 0.35, th = 0.6 + ctx.rand() * (2.6 - rr * 0.5);
      const tone = vary(ctx, "#4a5268", 0.15);
      model.box(tw, th, tw, tx, 6.6, tz, tone, STONE, ctx.rand() * 1.5);
      model.geo(new THREE.ConeGeometry(tw * 0.75, th * 0.6 + 0.4, 4), xf(tx, 6.6 + th + (th * 0.6 + 0.4) / 2, tz, 0, Math.PI / 4), "#9aa6c2", { rough: 0.35, metal: 0.8 });
      if (ctx.rand() < 0.5) model.glowing().box(0.08, 0.1, 0.02, tx, 6.6 + th * 0.6, tz + tw / 2 + 0.01, "#ffcf7a", { glow: 2 });
    }
    ctx.room.add(model.world(0, 11, 0), "#ffcf86", 0.5, 8, "candle", 1.3);
    // a banner of the hall's own (no guild's mark): deep blue cloth with a silver ring, hanging above the back arches
    const banner = w.back(0).at(0, 0, 1.0);
    banner.box(6, 22, 0.15, 0, 10, 0, baked("#1c2a5a", r.floor, { ao: 0.2 }), CLOTH);
    banner.geo(new THREE.TorusGeometry(1.6, 0.2, 6, 24), xf(0, 22, 0.1), "#b7c3d9", { rough: 0.3, metal: 1 });
    banner.geo(new THREE.ConeGeometry(3, 2, 3), xf(0, 9, 0, 0, 0, Math.PI), "#1c2a5a", CLOTH);
    // hanging lanterns in the arches (they sway)
    const spots: [number, number][] = [];
    for (const x of [-W / 3, 0, W / 3]) spots.push([x, r.back + 5]);
    for (const z of [r.back + D * 0.3, r.back + D * 0.62]) { spots.push([r.left + 5, z]); spots.push([r.right - 5, z]); }
    for (const [x, z] of spots) hangingLantern(ctx, new THREE.Vector3(x, r.floor + 15, z), "#c8803a");
    ctx.room.addWindow({
      centre: new THREE.Vector3(r.left + 0.2, r.floor + 16, -1), u: new THREE.Vector3(0, 0, 1), v: new THREE.Vector3(0, 1, 0),
      halfU: 4, halfV: 8, dir: new THREE.Vector3(0.45, -1, -0.1), color: "#9fb2ff", intensity: 0.6, pattern: WINDOW.arch,
    });
  },
};

/** A lantern hanging on a chain from the dark above, swinging gently (on the GPU). */
function hangingLantern(ctx: SetCtx, at: THREE.Vector3, glass: string): void {
  const phase = ctx.rand() * 6;
  const put = new Put(ctx).at(at.x, at.y - 2.4, at.z).swaying(at, SWAY.swing, phase);
  // (frosted glass, lit from within: from across the room it reads as a lit lantern without its flame)
  lantern(ctx, put, 1.4, glass);
  for (let k = 0; k < 8; k++) put.geo(new THREE.TorusGeometry(0.16, 0.05, 4, 8), xf(0, 3 + k * 0.42, 0, 0, (k % 2) * Math.PI / 2, 0), "#1c1a18", IRON);
  ctx.room.add(at.clone().add(new THREE.Vector3(0, -1.6, 0)), "#ffc070", 0.9, 14, "candle", ctx.rand() * 10);
}

// ------------------------------------------------------------------ Innistrad: a chapel crypt

const chapel: SetSpec = {
  floor: "flagstone", floorColors: ["#4a4c52", "#1c1d21"], floorTile: 13,
  centre: "ritual", centreMargin: [6, 7],
  props: ["tome", "tallow"],
  fade: [3, 22, 0.84],
  particles: [
    { kind: "fog", color: "#7a889e", count: 60, size: 9, opacity: 0.07, base: 1, beam: 0.15, additive: false, where: (r) => ({ min: [r.left, r.floor, r.back], max: [r.right, r.floor + 2.5, r.front] }) },
    { kind: "dust", color: "#d8e4ff", count: 380, size: 0.1, opacity: 0.9, base: 0.06, beam: 3.4, where: "room" },
  ],
  build(ctx, r) {
    const w = walls(ctx, r);
    const stone = "#4e525a";
    const W = r.right - r.left, D = r.front - r.back;
    // stone walls with pointed blind arcading
    for (const [place, len] of [[w.back, W], [w.front, W]] as const) {
      stoneWall(ctx, place(0), len + 2, 40, stone);
      const n = Math.max(3, Math.round(len / 9));
      for (let k = 0; k < n; k++) arch(ctx, place(-len / 2 + (k + 0.5) * (len / n)).at(0, 0, 1.3), len / n - 3.4, 12, 1.4, "#5a5e66", true);
    }
    for (const place of [w.left, w.right]) {
      stoneWall(ctx, place((r.back + r.front) / 2), D + 2, 40, stone);
      const n = Math.max(3, Math.round(D / 9));
      for (let k = 0; k < n; k++) arch(ctx, place(r.back + (k + 0.5) * (D / n)).at(0, 0, 1.3), D / n - 3.4, 12, 1.4, "#5a5e66", true);
    }
    // the altar at the back under the window: a stone table, a cloth, candles crowding it
    const altar = w.back(0).at(0, 0, 5);
    altar.box(12, 6.5, 4, 0, 0, 0, baked("#5e6068", r.floor), STONE);
    altar.box(12.6, 0.5, 4.6, 0, 6.5, 0, "#6a6c74", STONE);
    altar.box(4, 0.08, 4.7, 0, 7.0, 0, "#6a1e22", CLOTH);
    altar.box(4, 3.0, 0.08, 0, 4.0, 2.36, "#6a1e22", CLOTH);
    for (let i = 0; i < 9; i++) {
      const cx = -5 + i * 1.25 + (ctx.rand() - 0.5) * 0.4, cz = (ctx.rand() - 0.5) * 2.4;
      const ch = 0.8 + ctx.rand() * 2.2;
      candleBody(altar, cx, 7.0, cz, 0.22, ch, ctx.rand, "#e4d6b0");
      ctx.flames.add(altar.world(cx, 7.05 + ch, cz), 0.5, ctx.rand() * 10);
    }
    ctx.room.add(altar.world(0, 10, 2), "#ffb060", 1.4, 22, "candle", 0.7);
    // ledger stones and tombs, gravestones leaning by the walls
    for (const [x, z, a] of [[r.left + 5, r.back + 7, 0.1], [r.right - 6, r.back + 8, -0.15], [r.left + 6, 4, 0.05]] as const) {
      const tomb = new Put(ctx).at(x, r.floor, z, a);
      const T = baked("#4e5056", r.floor, { ao: 0.45, reach: 2 });
      tomb.box(5, 0.6, 8.8, 0, 0, 0, T, STONE); // plinth
      tomb.box(4.4, 2.6, 8.2, 0, 0.6, 0, T, STONE);
      for (let k = 0; k < 3; k++) tomb.box(1.0, 1.8, 0.12, -1.3 + k * 1.3, 0.95, 4.11, "#3e4046", STONE); // carved panels
      tomb.box(4.9, 0.35, 8.7, 0, 3.2, 0, "#585a60", STONE); // the lid, its edge chamfered
      tomb.box(4.5, 0.25, 8.3, 0, 3.55, 0, "#5e6066", STONE);
      // a sword carved on the lid, its pommel at the head
      tomb.box(0.28, 0.1, 5.2, 0, 3.8, 0.6, "#6a6c72", STONE);
      tomb.box(1.8, 0.1, 0.3, 0, 3.8, -1.6, "#6a6c72", STONE);
      tomb.sphere(0.3, 0, 3.85, -2.6, "#6a6c72", STONE, 1, 0.4, 1, 8);
    }
    for (let k = 0; k < 9; k++) {
      const side = k % 2 ? 1 : -1;
      const z = r.back + 14 + (k >> 1) * 5 + ctx.rand() * 2;
      if (z > r.front - 4) continue;
      gravestone(ctx, new Put(ctx).at(side * (r.hw + 9 + ctx.rand() * 3), r.floor, z, side * -Math.PI / 2 + (ctx.rand() - 0.5) * 0.5, (ctx.rand() - 0.5) * 0.18, (ctx.rand() - 0.5) * 0.2), 4 + ctx.rand() * 3, "#5a5e66", k % 3);
    }
    // iron candle stands, and candle clusters guttering on the floor
    for (const [x, z] of [[r.left + 8, r.back + 3.5], [r.right - 8, r.back + 3.5], [-r.hw - 4, -r.hd - 3], [r.hw + 4, -r.hd - 3]] as const) {
      const stand = new Put(ctx).at(x, r.floor, z);
      stand.lathe([[0, 0], [1.2, 0], [0.9, 0.3], [0.2, 0.6], [0.16, 11], [0.6, 11.2], [0.62, 11.5], [0, 11.5]], 0, 0, 0, baked("#24262a", r.floor), IRON, 8);
      for (let i = 0; i < 3; i++) {
        const a = i * 2.1 + ctx.rand(), cx = Math.cos(a) * 0.3, cz = Math.sin(a) * 0.3, ch = 0.6 + ctx.rand() * 1.4;
        candleBody(stand, cx, 11.5, cz, 0.18, ch, ctx.rand, "#e4d6b0");
        ctx.flames.add(stand.world(cx, 11.55 + ch, cz), 0.48, ctx.rand() * 10);
      }
      ctx.room.add(stand.world(0, 13.5, 0), "#ffa850", 0.8, 13, "candle", ctx.rand() * 10);
    }
    // (beyond the table's far corners and out to the sides: in the room's view, never in the seat's margins)
    for (const [x, z] of [[-r.hw - 9, -r.hd - 6], [r.hw + 9, -r.hd - 6], [-r.hw - 12, r.hd - 2], [r.hw + 12, r.hd - 2]] as const) {
      const cl = new Put(ctx).at(x, r.floor, z);
      for (let i = 0; i < 5; i++) {
        const cx = (ctx.rand() - 0.5) * 1.8, cz = (ctx.rand() - 0.5) * 1.8, ch = 0.5 + ctx.rand() * 2.2;
        candleBody(cl, cx, 0, cz, 0.24 + ctx.rand() * 0.1, ch, ctx.rand, "#bfae86");
        ctx.flames.add(cl.world(cx, ch + 0.05, cz), 0.5, ctx.rand() * 10);
      }
      // the wax that has run off them onto the stones
      cl.lathe([[0, 0], [1.3, 0], [1.1, 0.06], [0, 0.08]], 0, 0, 0, "#a89874", { rough: 0.5 }, 12);
      ctx.room.add(cl.world(0, 3, 0), "#ffa850", 0.7, 11, "candle", ctx.rand() * 10);
    }
    // the moon through the tracery, falling across the floor on the left of the table
    ctx.room.addWindow({
      centre: new THREE.Vector3(r.left + 0.2, r.floor + 20, -2), u: new THREE.Vector3(0, 0, 1), v: new THREE.Vector3(0, 1, 0),
      halfU: 3.6, halfV: 9, dir: new THREE.Vector3(0.45, -1, 0.12), color: "#b0c4ff", intensity: 0.5, pattern: WINDOW.tracery,
    });
    const win = w.left(-2).at(0, 0, 0.6);
    win.glowing().box(9, 20, 0.05, 0, 10, -0.3, "#9fb4e0", { glow: 0.6 });
    for (const s of [-1, 1]) win.box(1, 26, 1.2, s * 5, 4, 0, baked("#5a5e66", r.floor), STONE);
    win.box(11, 4, 1.4, 0, 0, 0, baked("#555960", r.floor), STONE);
  },
};

/** A wall of coursed stone blocks (only the courses low down, where the camera sees them, are cut). */
function stoneWall(ctx: SetCtx, at: Put, w: number, h: number, stone: string): void {
  segments(at, w, 8, (seg, len) => {
    seg.box(len, h, 0.8, 0, 0, -0.4, baked(stone, ctx.floorY, { ao: 0.4, reach: 8 }), STONE);
    let y = 0;
    let row = 0;
    while (y < 14) {
      const bh = 1.4 + ctx.rand() * 0.5;
      let x = -len / 2 - (row % 2) * 1.2;
      while (x < len / 2) {
        const bw = Math.min(len / 2 - x, 2.4 + ctx.rand() * 1.8);
        const x0 = Math.max(x, -len / 2);
        if (x + bw - x0 > 0.4) seg.box(x + bw - x0 - 0.12, bh - 0.12, 0.25, (x0 + x + bw) / 2, y, 0.05, vary(ctx, stone, 0.14), STONE);
        x += bw;
      }
      y += bh;
      row++;
    }
  });
}

// ------------------------------------------------------------------ Theros: a temple under Nyx

const temple: SetSpec = {
  floor: "marble", floorColors: ["#d8d0c0", "#8f8574"], floorTile: 20,
  centre: "meander", centreMargin: [6, 6],
  props: ["oillamp", "amphora"],
  fade: [4, 28, 0.78],
  particles: [
    { kind: "stars", color: "#e6dcff", count: 420, size: 0.16, opacity: 0.95, base: 0.8, where: "air" },
    { kind: "motes", color: "#ffd27a", count: 80, size: 0.12, opacity: 0.7, base: 0.5, where: "room" },
  ],
  build(ctx, r) {
    const W = r.right - r.left, D = r.front - r.back;
    // a peristyle of fluted columns on a stepped platform
    const R = new THREE.Vector2(W / 2 - 2, D / 2 - 2);
    const n = 16;
    for (let k = 0; k < n; k++) {
      const a = (k / n) * Math.PI * 2;
      const x = Math.cos(a) * R.x, z = (r.back + r.front) / 2 + Math.sin(a) * R.y;
      column(ctx, new Put(ctx).at(x, r.floor, z), 1.2, 26, "#d9d3c6", true);
    }
    // a low parapet joining the columns' plinths, and a laurel frieze of gilt bosses along it
    for (let k = 0; k < n; k++) {
      const a0 = (k / n) * Math.PI * 2, a1 = ((k + 1) / n) * Math.PI * 2;
      const x0 = Math.cos(a0) * R.x, z0 = (r.back + r.front) / 2 + Math.sin(a0) * R.y;
      const x1 = Math.cos(a1) * R.x, z1 = (r.back + r.front) / 2 + Math.sin(a1) * R.y;
      const len = Math.hypot(x1 - x0, z1 - z0);
      const mid = new Put(ctx).at((x0 + x1) / 2, r.floor, (z0 + z1) / 2, -Math.atan2(z1 - z0, x1 - x0));
      mid.box(len - 3, 2.2, 1.0, 0, 0, 0, baked("#cfc6b3", r.floor, { ao: 0.3 }), STONE);
      mid.box(len - 2.6, 0.35, 1.3, 0, 2.2, 0, "#ddd5c4", STONE);
      for (let b = 0; b < 3; b++) mid.sphere(0.22, -len / 4 + b * len / 4, 1.2, 0.52, "#c9a24a", BRASS, 1, 1, 0.5, 8);
    }
    // bronze braziers on tripods, burning
    for (const [x, z] of [[-r.hw - 5, -r.hd - 4], [r.hw + 5, -r.hd - 4], [-r.hw - 5, r.hd + 6], [r.hw + 5, r.hd + 6]] as const) {
      const b = new Put(ctx).at(x, r.floor, z);
      for (let k = 0; k < 3; k++) {
        const a = (k / 3) * Math.PI * 2;
        b.geo(new THREE.CylinderGeometry(0.12, 0.16, 8.5, 6), xf(Math.cos(a) * 0.9, 4.2, Math.sin(a) * 0.9, Math.sin(a) * 0.12, 0, -Math.cos(a) * 0.12), "#7a5a2a", BRASS);
      }
      b.lathe([[0, 0], [0.8, 0], [1.9, 0.9], [2.0, 1.3], [1.8, 1.3], [0.7, 0.3], [0, 0.3]], 0, 8.2, 0, "#8a6a2e", BRASS, 18);
      b.glowing().sphere(1.5, 0, 9.3, 0, "#ff7a2a", { glow: 1.6, pulse: PULSE.hearth }, 1, 0.25, 1, 10);
      for (let i = 0; i < 4; i++) ctx.flames.add(b.world((ctx.rand() - 0.5) * 1.6, 9.4, (ctx.rand() - 0.5) * 1.6), 1.2 + ctx.rand() * 0.5, ctx.rand() * 10, "#ff9a3c", 0.75);
      ctx.room.add(b.world(0, 11, 0), "#ffb060", 1.3, 18, "hearth", ctx.rand() * 10);
    }
    // a statue on a plinth at the back, robed (an original figure: draped cloth and a raised arm)
    for (const x of [-W * 0.28, W * 0.28]) {
      const st = new Put(ctx).at(x, r.floor, r.back + 5.5);
      st.box(4, 4, 4, 0, 0, 0, baked("#cfc6b3", r.floor), STONE);
      st.lathe([[0, 0], [1.5, 0], [1.3, 3], [1.0, 6], [1.15, 7.5], [0.7, 8.2], [0.4, 8.6], [0, 8.6]], 0, 4, 0, "#e2dccf", STONE, 16);
      st.sphere(0.7, 0, 13.2, 0, "#e2dccf", STONE);
      st.geo(new THREE.CylinderGeometry(0.25, 0.3, 4, 8), xf(x > 0 ? -1.1 : 1.1, 12.6, 0.3, 0, 0, x > 0 ? 0.5 : -0.5), "#e2dccf", STONE);
    }
    // offerings at the columns' feet: amphorae
    // (only behind the table: in the seat's margins they would loom)
    for (let k = 0; k < 6; k++) {
      const a = Math.PI * (1.1 + (k / 5) * 0.8);
      const p = new Put(ctx).at(Math.cos(a) * (R.x - 2.5), r.floor, (r.back + r.front) / 2 + Math.sin(a) * (R.y - 2.5));
      p.lathe([[0, 0], [0.4, 0], [1.1, 0.8], [1.2, 1.8], [0.9, 2.6], [0.35, 3], [0.35, 3.5], [0.5, 3.6], [0, 3.6]], 0, 0, 0, vary(ctx, "#9a4a24", 0.12), { rough: 0.7 }, 14);
    }
  },
};

// ------------------------------------------------------------------ Zendikar: the wilds, hedrons adrift

const wilds: SetSpec = {
  floor: "rock", floorColors: ["#6a6252", "#3a352b"], floorTile: 22,
  centre: "none", centreMargin: [0, 0],
  props: ["hedron", "compass"],
  fade: [4, 30, 0.75],
  particles: [{ kind: "motes", color: "#b9ffd9", count: 220, size: 0.13, opacity: 0.85, base: 0.4, where: "air" }],
  build(ctx, r) {
    // standing hedrons (huge, half sunk, leaning), broken ones lying, and a few adrift (they bob)
    const stoneC = "#6a6456";
    for (let k = 0; k < 10; k++) {
      const a = (k / 10) * Math.PI * 2 + ctx.rand() * 0.3;
      const rx = r.hw + 8 + ctx.rand() * 10, rz = r.hd + 8 + ctx.rand() * 10;
      const p = new Put(ctx).at(Math.cos(a) * rx, r.floor, Math.sin(a) * rz, ctx.rand() * 6, (ctx.rand() - 0.5) * 0.5, (ctx.rand() - 0.5) * 0.5);
      hedron(ctx, p, 8 + ctx.rand() * 9, 1.6 + ctx.rand() * 1.2, stoneC);
    }
    for (let k = 0; k < 7; k++) {
      const a = ctx.rand() * Math.PI * 2;
      boulder(ctx, new Put(ctx).at(Math.cos(a) * (r.hw + 6 + ctx.rand() * 12), r.floor, Math.sin(a) * (r.hd + 6 + ctx.rand() * 12)), 1.5 + ctx.rand() * 3, "#5a5446", "#4a6a3a");
    }
    for (let k = 0; k < 5; k++) {
      const a = (k / 5) * Math.PI * 2 + 0.6;
      trunk(ctx, new Put(ctx).at(Math.cos(a) * (r.hw + 16), r.floor, Math.sin(a) * (r.hd + 15)), 30, 1.4, "#3a3024");
    }
    // roots and vines snaking over the rock
    for (let k = 0; k < 10; k++) {
      const a = ctx.rand() * Math.PI * 2, rr = r.hw + 4 + ctx.rand() * 14;
      const pts: THREE.Vector3[] = [];
      for (let i = 0; i < 6; i++) pts.push(new THREE.Vector3(Math.cos(a + i * 0.12) * (rr + i * 1.5), r.floor + 0.3 + Math.abs(Math.sin(i * 1.7)) * 0.6, Math.sin(a + i * 0.12) * (rr + i * 1.5)));
      new Put(ctx).geo(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 18, 0.3 + ctx.rand() * 0.2, 6), null, "#3a3a24", { rough: 1 });
    }
    for (let k = 0; k < 6; k++) {
      const a = (k / 6) * Math.PI * 2 + 0.25;
      const base = new THREE.Vector3(Math.cos(a) * (r.hw + 10), r.floor + 12 + ctx.rand() * 8, Math.sin(a) * (r.hd + 10));
      floatingHedron(ctx, base, 3 + ctx.rand() * 3);
    }
    ctx.room.add(new THREE.Vector3(0, r.floor + 14, r.back + 2), "#7dffc0", 0.8, 30, "steady");
  },
};

function hedron(ctx: SetCtx, at: Put, len: number, rad: number, stone: string): void {
  const g = new THREE.OctahedronGeometry(1, 0);
  g.scale(rad, len / 2, rad);
  at.geo(g, xf(0, len * 0.3, 0), baked(stone, ctx.floorY, { ao: 0.4 }), STONE);
  // its glowing seams: thin bright bands round the girth
  for (const t of [-0.15, 0.15]) at.glowing().geo(new THREE.CylinderGeometry(rad * (1 - Math.abs(t) * 2) * 0.72, rad * (1 - Math.abs(t) * 2) * 0.72, 0.12, 4), xf(0, len * 0.3 + t * len, 0), "#3ad08a", { glow: 1.2 });
}

function floatingHedron(ctx: SetCtx, base: THREE.Vector3, len: number): void {
  const put = new Put(ctx).at(base.x, base.y, base.z, ctx.rand() * 6, ctx.rand() * 0.6, ctx.rand() * 0.6).swaying(base, SWAY.drift, ctx.rand() * 6);
  const g = new THREE.OctahedronGeometry(1, 0);
  g.scale(len * 0.2, len / 2, len * 0.2);
  put.geo(g, null, "#6a6456", STONE);
  for (const t of [-0.15, 0.15]) put.glowing().geo(new THREE.CylinderGeometry(len * 0.2 * (1 - Math.abs(t) * 2) * 0.74, len * 0.2 * (1 - Math.abs(t) * 2) * 0.74, 0.14, 4), xf(0, t * len, 0), "#3ad08a", { glow: 1.3 });
}

// ------------------------------------------------------------------ Kamigawa: a shrine hall, neon beyond the screens

const shrine: SetSpec = {
  floor: "tatami", floorColors: ["#6e6242", "#3e3420"], floorTile: 14,
  centre: "mat", centreMargin: [5, 5],
  props: ["teaset", "andon"],
  fade: [3, 24, 0.8],
  particles: [{ kind: "petals", color: "#ffc0d8", count: 200, size: 0.26, opacity: 0.9, base: 0.7, beam: 0.5, additive: false, where: "air" }],
  build(ctx, r) {
    const w = walls(ctx, r);
    const W = r.right - r.left, D = r.front - r.back;
    for (const [place, len, mid] of [[w.back, W, 0], [w.front, W, 0], [w.left, D, (r.back + r.front) / 2], [w.right, D, (r.back + r.front) / 2]] as const) shoji(ctx, place(mid), len + 2, 26);
    // posts at the corners and along the walls, a lintel, an engawa step
    for (const [x, z] of [[r.left, r.back], [r.right, r.back], [r.left, r.front], [r.right, r.front]] as const) new Put(ctx).at(x, r.floor, z).box(1.6, 30, 1.6, 0, 0, 0, baked("#2a1a12", r.floor), WOOD);
    // a tokonoma alcove at the back: a hanging scroll and an arrangement of branches
    const toko = w.back(0).at(0, 0, 0.6);
    toko.box(12, 1.2, 4, 0, 0, 1.6, baked("#3a2418", r.floor), WOOD);
    toko.box(3.5, 14, 0.1, 0, 6, 0.2, "#e8dcc0", { uv: [0.02, 0.02, 0.46, 0.46] });
    toko.lathe([[0, 0], [0.8, 0], [1.1, 1.2], [0.6, 2.4], [0.7, 2.8], [0, 2.8]], 3.6, 1.2, 1.6, "#2a3a4a", { rough: 0.2 }, 14);
    for (let k = 0; k < 5; k++) toko.geo(new THREE.CylinderGeometry(0.05, 0.1, 6, 5), xf(3.6 + (ctx.rand() - 0.5) * 2, 6 + ctx.rand() * 2, 1.6, 0, 0, (ctx.rand() - 0.5) * 1.2), "#3a2a1a", WOOD);
    for (let k = 0; k < 12; k++) toko.sphere(0.35, 3.6 + (ctx.rand() - 0.5) * 4, 7 + ctx.rand() * 3, 1.6, "#f0b0c8", { glow: 0.15, rough: 0.8 });
    // a six-panel folding screen behind the far seat: gold leaf, a pine bough brushed across it
    const byobu = w.back(0).at(0, 0, 4.5);
    const panelsN = 6, pwid = 2.7;
    for (let k = 0; k < panelsN; k++) {
      const ang = k % 2 ? 0.38 : -0.38;
      const px = (k - (panelsN - 1) / 2) * pwid * Math.cos(0.38);
      const panel = byobu.at(px, 0, k % 2 ? 0.5 : 0, ang);
      panel.box(pwid, 11, 0.18, 0, 0.3, 0, "#1a0c0a", { rough: 0.3 });
      panel.box(pwid - 0.3, 10.4, 0.04, 0, 0.6, 0.1, "#a8823a", { rough: 0.35, metal: 0.7 });
      // the bough: a dark branch and clusters of needles, crossing the panels at a slant
      const by = 6.5 + Math.sin(k * 0.9) * 1.6;
      panel.box(pwid - 0.2, 0.22, 0.03, 0, by, 0.13, "#3a2414", { rough: 0.8 }, 0, 0, (k % 2 ? 1 : -1) * 0.12);
      for (let n = 0; n < 4; n++) panel.sphere(0.5 + ctx.rand() * 0.3, -1 + n * 0.7, by + 0.4 + (ctx.rand() - 0.5) * 0.8, 0.14, "#24402a", { rough: 0.8 }, 1.4, 0.7, 0.1, 8);
    }
    // a lacquered tansu chest against each side wall, cushions by the table
    for (const t0 of [w.left(r.back + 9), w.right(r.back + 9)]) {
      const t = t0.at(0, 0, 1.8);
      t.box(7, 4.5, 3.2, 0, 0, 0, baked("#2a120c", r.floor), { rough: 0.3 });
      t.box(4.5, 3.5, 3.2, -1.25, 4.5, 0, baked("#2a120c", r.floor), { rough: 0.3 });
      for (const [dx, dy] of [[-2, 1.2], [1.8, 1.2], [-2, 3.2], [1.8, 3.2], [-1.3, 6]] as const) {
        t.box(2.6, 0.05, 0.05, dx, dy, 1.62, "#3a2a1c", WOOD);
        t.geo(new THREE.TorusGeometry(0.3, 0.05, 5, 10, Math.PI), xf(dx, dy - 0.2, 1.68, 0, 0, Math.PI), "#1a1a1a", IRON);
      }
    }
    for (const [x, z] of [[-r.hw - 3, -3], [-r.hw - 3, 3], [r.hw + 3, -3], [r.hw + 3, 3]] as const) {
      const c = new Put(ctx).at(x, r.floor, z, (ctx.rand() - 0.5) * 0.3);
      // a zabuton: a square cushion, plump in the middle, piped at its edge
      c.box(3.6, 0.35, 3.6, 0, 0, 0, "#141a30", CLOTH);
      c.geo(new THREE.SphereGeometry(1, 20, 8, 0, Math.PI * 2, 0, Math.PI / 2), xf(0, 0.3, 0, 0, Math.PI / 4, 0, 2.45, 0.35, 2.45), baked("#232c4e", r.floor, { ao: 0.2, reach: 1 }), CLOTH);
      for (const [ex, ez, ry] of [[0, 1.8, 0], [0, -1.8, 0], [1.8, 0, Math.PI / 2], [-1.8, 0, Math.PI / 2]] as const) c.box(3.6, 0.1, 0.1, ex, 0.3, ez, "#8a6a3a", CLOTH, ry);
    }
    // andon floor lanterns, glowing paper
    for (const [x, z] of [[-r.hw - 5, -r.hd - 5], [r.hw + 5, -r.hd - 5], [-r.hw - 5, r.hd + 5], [r.hw + 5, r.hd + 5], [r.left + 4, 0], [r.right - 4, 0]] as const) {
      const a = new Put(ctx).at(x, r.floor, z, Math.PI / 4);
      for (const [cx, cz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) a.box(0.25, 7, 0.25, cx * 1.3, 0, cz * 1.3, "#1e140e", WOOD);
      a.glowing().box(2.4, 4.5, 2.4, 0, 2, 0, "#c88a4a", { glow: 0.75, pulse: PULSE.lantern, rough: 0.9, uv: [0.02, 0.02, 0.46, 0.46] });
      for (const y of [2, 6.5]) a.box(2.9, 0.25, 2.9, 0, y, 0, "#1e140e", WOOD);
      for (const y of [3.5, 5]) a.box(2.5, 0.08, 2.5, 0, y, 0, "#2a1a10", WOOD);
      ctx.room.add(a.world(0, 4, 0), "#ffb070", 0.55, 10, "candle", ctx.rand() * 10);
    }
    // red paper lanterns hanging along the eaves (they sway), neon beyond
    for (const x of [-W / 3, 0, W / 3]) paperLantern(ctx, new THREE.Vector3(x, r.floor + 18, r.back + 3));
    for (const z of [r.back + D * 0.35, r.back + D * 0.7]) { paperLantern(ctx, new THREE.Vector3(r.left + 3, r.floor + 18, z)); paperLantern(ctx, new THREE.Vector3(r.right - 3, r.floor + 18, z)); }
    // a thread of neon along the foot of the far screens: the city's glow coming in under them
    for (const [x0, z0, x1, z1, c] of [[r.left + 1, r.back + 0.7, r.right - 1, r.back + 0.7, "#ff5fc8"], [r.left + 0.7, r.back + 1, r.left + 0.7, r.front - 1, "#5fe8ff"], [r.right - 0.7, r.back + 1, r.right - 0.7, r.front - 1, "#5fe8ff"]] as const) {
      const len = Math.hypot(x1 - x0, z1 - z0);
      new Put(ctx).at((x0 + x1) / 2, r.floor, (z0 + z1) / 2).glowing().geo(new THREE.BoxGeometry(len, 0.12, 0.12), xf(0, 1.15, 0, 0, -Math.atan2(z1 - z0, x1 - x0)), c, { glow: 2.4 });
    }
    ctx.room.addWindow({
      centre: new THREE.Vector3(r.left + 0.3, r.floor + 14, -2), u: new THREE.Vector3(0, 0, 1), v: new THREE.Vector3(0, 1, 0),
      halfU: 8, halfV: 9, dir: new THREE.Vector3(0.5, -1, 0.05), color: "#d8c8ff", intensity: 0.35, pattern: WINDOW.shoji,
    });
  },
};

function shoji(ctx: SetCtx, at: Put, w: number, h: number): void {
  const frame = "#2a1a12";
  segments(at, w, 6, (p, pw) => {
    p.box(pw, 1, 0.6, 0, 0, 0, baked(frame, ctx.floorY), WOOD); // sill
    p.box(pw, 0.8, 0.6, 0, h, 0, frame, WOOD); // lintel
    p.box(0.5, h, 0.7, -pw / 2, 0, 0, frame, WOOD);
    // paper, lit from beyond, and its lattice
    p.glowing().box(pw - 0.5, h - 1, 0.08, 0, 1, -0.2, "#8a7c62", { glow: 0.35, pulse: PULSE.steady, rough: 0.9 });
    for (let i = 1; i < 3; i++) p.box(0.14, h - 1, 0.2, -pw / 2 + (i * pw) / 3, 1, 0, frame, WOOD);
    for (let j = 1; j < 7; j++) p.box(pw - 0.5, 0.14, 0.2, 0, 1 + (j * (h - 1)) / 7, 0, frame, WOOD);
    p.box(pw - 0.5, 3.4, 0.22, 0, 1, 0.05, "#3a2418", WOOD); // the solid kick panel
  });
}

function paperLantern(ctx: SetCtx, at: THREE.Vector3): void {
  const put = new Put(ctx).at(at.x, at.y, at.z).swaying(at, SWAY.swing, ctx.rand() * 6);
  put.glowing().sphere(1.2, 0, -3, 0, "#e0402a", { glow: 1.2, pulse: PULSE.lantern, rough: 0.8 }, 1, 1.35, 1, 14);
  for (const y of [-4.7, -1.3]) put.cyl(0.62, 0.62, 0.3, 0, y - 0.15, 0, "#1a0c08", WOOD, 12);
  put.cyl(0.05, 0.05, 2.6, 0, -1.3, 0, "#1a0c08", WOOD, 4);
  for (let k = 0; k < 6; k++) put.geo(new THREE.TorusGeometry(1.21 * Math.sin(((k + 1) / 7) * Math.PI), 0.025, 4, 18), xf(0, -3 - 1.35 * 1.2 * Math.cos(((k + 1) / 7) * Math.PI), 0, Math.PI / 2, 0, 0), "#7a1a10", WOOD);
  ctx.room.add(at.clone().add(new THREE.Vector3(0, -3, 0)), "#ff7050", 0.6, 10, "candle", ctx.rand() * 10);
}

// ------------------------------------------------------------------ Amonkhet: the trial grounds

const trials: SetSpec = {
  floor: "sand", floorColors: ["#8a6a42", "#4e3a22"], floorTile: 24,
  centre: "dais", centreMargin: [5, 5],
  props: ["oillamp", "scarab"],
  fade: [4, 30, 0.72],
  particles: [{ kind: "sand", color: "#ffdca0", count: 380, size: 0.08, opacity: 0.6, base: 0.8, where: "room" }],
  build(ctx, r) {
    // obelisks at the corners, a low carved wall at the back, braziers, jars
    for (const [x, z] of [[-r.hw - 6, -r.hd - 6], [r.hw + 6, -r.hd - 6], [-r.hw - 6, r.hd + 9], [r.hw + 6, r.hd + 9]] as const) {
      const o = new Put(ctx).at(x, r.floor, z, ctx.rand() * 0.3);
      o.box(4, 1.5, 4, 0, 0, 0, baked("#a07a48", r.floor), STONE);
      o.geo(new THREE.CylinderGeometry(0.9, 1.4, 22, 4), xf(0, 12.5, 0, 0, Math.PI / 4), baked("#b8925c", r.floor, { ao: 0.25, reach: 6 }), STONE);
      o.geo(new THREE.ConeGeometry(1.05, 2, 4), xf(0, 24.5, 0, 0, Math.PI / 4), "#e3b04b", BRASS);
      for (let k = 0; k < 6; k++) o.box(0.9, 0.25, 0.08, 0, 4 + k * 2.6, 1.15 - k * 0.025, "#24479a", { rough: 0.3 });
    }
    const W = r.right - r.left;
    segments(new Put(ctx).at(0, r.floor, r.back), W, 9, (wallP, seg) => {
      wallP.box(seg, 9, 2.4, 0, 0, 0, baked("#a8844e", r.floor, { ao: 0.3, reach: 4 }), STONE);
      for (let k = 0; k < Math.floor(seg / 3); k++) {
        const x = -seg / 2 + 1.5 + k * 3;
        // carved figures: original glyph panels, raised
        wallP.box(2.2, 5.5, 0.2, x, 1.6, 1.25, "#b8925c", STONE);
        wallP.box(0.8, 0.8, 0.15, x, 5.2 + (k % 3) * 0.3, 1.4, "#24479a", { rough: 0.3 });
        wallP.box(1.4, 0.2, 0.15, x, 3 + (k % 2) * 0.9, 1.4, "#8a6a3e", STONE);
      }
      wallP.box(seg, 0.6, 2.8, 0, 9, 0, "#c9a26a", STONE);
    });
    for (const [x, z] of [[-r.hw - 4, r.hd + 2], [r.hw + 4, r.hd + 2], [r.left + 8, r.back + 5], [r.right - 8, r.back + 5]] as const) {
      const b = new Put(ctx).at(x, r.floor, z);
      b.lathe([[0, 0], [1.4, 0], [0.6, 0.8], [0.5, 6], [1.8, 7], [2, 7.6], [0, 7.6]], 0, 0, 0, baked("#8a6a2e", r.floor), BRASS, 12);
      b.glowing().sphere(1.4, 0, 7.6, 0, "#ff7a2a", { glow: 1.5, pulse: PULSE.hearth }, 1, 0.25, 1, 10);
      for (let i = 0; i < 3; i++) ctx.flames.add(b.world((ctx.rand() - 0.5) * 1.2, 7.7, (ctx.rand() - 0.5) * 1.2), 1.1 + ctx.rand() * 0.4, ctx.rand() * 10, "#ff9a3c", 0.78);
      ctx.room.add(b.world(0, 9.5, 0), "#ffb050", 1.2, 18, "hearth", ctx.rand() * 10);
    }
    for (let k = 0; k < 12; k++) {
      const a = ctx.rand() * Math.PI * 2;
      const p = new Put(ctx).at(Math.cos(a) * (r.hw + 7 + ctx.rand() * 8), r.floor, Math.sin(a) * (r.hd + 7 + ctx.rand() * 8), 0, (ctx.rand() - 0.5) * 0.3);
      if (k % 3 === 0) boulder(ctx, p, 1.5 + ctx.rand() * 2, "#a8844e");
      else p.lathe([[0, 0], [0.8, 0], [1.4, 1.4], [1.3, 2.8], [0.6, 3.4], [0.7, 3.8], [0, 3.8]], 0, 0, 0, vary(ctx, "#c49a62", 0.12), { rough: 0.8 }, 12);
    }
  },
};

// ------------------------------------------------------------------ Ixalan: a jungle temple, gold in the green

const jungle: SetSpec = {
  floor: "mossy", floorColors: ["#6a6a50", "#2a2c1e"], floorTile: 18,
  centre: "calendar", centreMargin: [6, 6],
  props: ["coins", "chest"],
  fade: [3, 24, 0.82],
  particles: [{ kind: "fireflies", color: "#fff08a", count: 120, size: 0.18, opacity: 1, base: 0.6, where: "room" }],
  build(ctx, r) {
    const w = walls(ctx, r);
    // stepped stone walls at the back and sides, carved, overgrown
    for (const [place, len, mid] of [[w.back, r.right - r.left, 0], [w.left, r.front - r.back, (r.back + r.front) / 2], [w.right, r.front - r.back, (r.back + r.front) / 2]] as const) {
      segments(place(mid), len + 2, 8, (p, seg) => {
        for (let s = 0; s < 4; s++) p.box(seg, 4, 3, 0, s * 4, -s * 2.5, baked("#5e604a", r.floor, { ao: 0.3, reach: 6 }), STONE);
        for (let k = 0; k < Math.floor(seg / 4); k++) p.box(2.6, 2.6, 0.3, -seg / 2 + 2 + k * 4, 0.7, 1.55, vary(ctx, "#6a6c54", 0.1), STONE);
      });
    }
    // vines down the walls, ferns and big leaves at their feet, trees
    for (let k = 0; k < 16; k++) {
      const a = ctx.rand() * Math.PI * 2;
      const x = Math.cos(a) * (r.hw + 9 + ctx.rand() * 6), z = Math.sin(a) * (r.hd + 9 + ctx.rand() * 6);
      fern(ctx, new Put(ctx).at(x, r.floor, z, ctx.rand() * 6), 3 + ctx.rand() * 3);
    }
    for (let k = 0; k < 4; k++) trunk(ctx, new Put(ctx).at((k % 2 ? 1 : -1) * (r.hw + 12), r.floor, r.back + 6 + k * 7), 32, 1.6, "#3a3426");
    for (let k = 0; k < 14; k++) {
      const x = r.left + 2 + ctx.rand() * (r.right - r.left - 4);
      const pts: THREE.Vector3[] = [];
      for (let i = 0; i < 5; i++) pts.push(new THREE.Vector3(x + Math.sin(i * 1.3) * 1.2, r.floor + 16 - i * 4, r.back + 1.6 + i * 0.6));
      new Put(ctx).geo(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 16, 0.18, 5), null, "#2c4a24", { rough: 1 });
    }
    // torches on poles
    for (const [x, z] of [[-r.hw - 5, -r.hd - 4], [r.hw + 5, -r.hd - 4], [-r.hw - 6, r.hd + 6], [r.hw + 6, r.hd + 6]] as const) {
      const t = new Put(ctx).at(x, r.floor, z);
      t.cyl(0.25, 0.35, 10, 0, 0, 0, baked("#3a2a1a", r.floor), WOOD, 6);
      t.lathe([[0, 0], [0.5, 0], [0.8, 1], [0, 1]], 0, 10, 0, "#2a1a10", { rough: 1 }, 8);
      for (let i = 0; i < 3; i++) ctx.flames.add(t.world((ctx.rand() - 0.5) * 0.5, 10.9, (ctx.rand() - 0.5) * 0.5), 1.0 + ctx.rand() * 0.3, ctx.rand() * 10, "#ff9a3c", 0.78);
      ctx.room.add(t.world(0, 12, 0), "#ffa850", 1.1, 16, "hearth", ctx.rand() * 10);
    }
    // gold: spilled coins and an idol on a plinth
    const idol = w.back(-r.hw - 8).at(0, 0, 5);
    idol.box(5, 4, 5, 0, 0, 0, baked("#5e604a", r.floor), STONE);
    idol.lathe([[0, 0], [1.8, 0], [1.6, 2], [2.0, 3.4], [1.2, 5], [1.5, 6], [0, 6.5]], 0, 4, 0, "#e8b53a", { rough: 0.25, metal: 1 }, 8);
    for (let k = 0; k < 120; k++) {
      const a = ctx.rand() * Math.PI * 2, rr = 2 + ctx.rand() * 6;
      new Put(ctx).geo(new THREE.CylinderGeometry(0.25, 0.25, 0.06, 10), xf(-r.hw - 8 + Math.cos(a) * rr, r.floor + 0.05 + ctx.rand() * 0.1, r.back + 9 + Math.sin(a) * rr * 0.6, (ctx.rand() - 0.5) * 0.8, 0, (ctx.rand() - 0.5) * 0.8), vary(ctx, "#e8b53a", 0.1), { rough: 0.3, metal: 1 });
    }
  },
};

function fern(ctx: SetCtx, at: Put, size: number): void {
  const n = 7;
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2 + ctx.rand() * 0.4;
    const leaf = new THREE.PlaneGeometry(size * 0.45, size, 1, 4);
    const p = leaf.getAttribute("position");
    for (let i = 0; i < p.count; i++) {
      const t = (p.getY(i) + size / 2) / size;
      p.setX(i, p.getX(i) * Math.sin(t * Math.PI) * 1.1);
      p.setZ(i, -t * t * size * 0.6);
    }
    leaf.computeVertexNormals();
    at.geo(leaf, xf(Math.cos(a) * size * 0.25, size * 0.42, Math.sin(a) * size * 0.25, -0.9, -a + Math.PI / 2, 0), vary(ctx, "#2f5a26", 0.25), { rough: 0.7 });
  }
}

// ------------------------------------------------------------------ New Phyrexia: a cathedral of ribs

const machine: SetSpec = {
  floor: "plates", floorColors: ["#2a302c", "#0c0e0d"], floorTile: 16,
  centre: "grate", centreMargin: [5, 5],
  props: ["vial", "spikes"],
  fade: [3, 24, 0.82],
  particles: [{ kind: "oil", color: "#2a3a2a", count: 120, size: 0.14, opacity: 0.9, base: 0.6, additive: false, where: "room" }, { kind: "spores", color: "#b8ffb0", count: 140, size: 0.1, opacity: 0.7, base: 0.6, where: "room" }],
  build(ctx, r) {
    // great ribs of porcelain bone arching from the floor round the table
    const W = r.right - r.left, D = r.front - r.back;
    for (let k = 0; k < 8; k++) {
      const z = r.back + 2 + (k / 7) * (D - 4);
      for (const s of [-1, 1]) {
        const pts = [new THREE.Vector3(s * (W / 2 - 1), r.floor, z), new THREE.Vector3(s * (W / 2 - 3), r.floor + 14, z), new THREE.Vector3(s * (W / 2 - 9), r.floor + 26, z), new THREE.Vector3(s * (W / 2 - 16), r.floor + 32, z)];
        new Put(ctx).geo(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 20, 0.9 - k * 0.03, 8), null, baked("#d8dcd0", r.floor, { ao: 0.35, reach: 5 }), { rough: 0.35 });
      }
    }
    // pipes along the back, veins of glowing oil
    for (let k = 0; k < 6; k++) {
      const y = r.floor + 1 + k * 1.6;
      new Put(ctx).geo(new THREE.CylinderGeometry(0.6, 0.6, W, 10), xf(0, y, r.back + 1 + (k % 2) * 1.2, 0, 0, Math.PI / 2), "#1e2420", { rough: 0.35, metal: 0.8 });
      if (k % 2) new Put(ctx).glowing().geo(new THREE.CylinderGeometry(0.2, 0.2, W, 6), xf(0, y + 0.55, r.back + 1.7, 0, 0, Math.PI / 2), "#5aff6a", { glow: 1.2, pulse: PULSE.lantern });
    }
    // vats of oil with a sickly glow, spikes, cables
    for (const [x, z] of [[-r.hw - 6, -r.hd - 3], [r.hw + 6, -r.hd - 3], [-r.hw - 7, r.hd + 6], [r.hw + 7, r.hd + 6]] as const) {
      const v = new Put(ctx).at(x, r.floor, z);
      v.lathe([[0, 0], [2.4, 0], [2.6, 0.5], [2.6, 4.5], [2.8, 4.8], [2.5, 5], [2.3, 4.6]], 0, 0, 0, baked("#1c201e", r.floor), { rough: 0.4, metal: 0.85 }, 18);
      v.glowing().cyl(2.35, 2.35, 0.1, 0, 4.4, 0, "#3ac84a", { glow: 0.9, pulse: PULSE.lantern }, 18);
      for (let k = 0; k < 4; k++) v.box(0.3, 5.2, 0.3, Math.cos(k * 1.57 + 0.4) * 2.65, 0, Math.sin(k * 1.57 + 0.4) * 2.65, "#d8dcd0", { rough: 0.35 });
      ctx.room.add(v.world(0, 7, 0), "#7aff6a", 1.0, 14, "candle", ctx.rand() * 10);
    }
    for (let k = 0; k < 20; k++) {
      const a = ctx.rand() * Math.PI * 2, h = 3 + ctx.rand() * 9;
      new Put(ctx).at(Math.cos(a) * (r.hw + 6 + ctx.rand() * 10), r.floor, Math.sin(a) * (r.hd + 6 + ctx.rand() * 10), 0, (ctx.rand() - 0.5) * 0.4, (ctx.rand() - 0.5) * 0.4).geo(new THREE.ConeGeometry(0.4 + ctx.rand() * 0.5, h, 6), xf(0, h / 2, 0), baked("#d8dcd0", r.floor), { rough: 0.3 });
    }
    ctx.room.add(new THREE.Vector3(0, r.floor + 2, 0), "#5aff6a", 0.6, 26, "steady");
  },
};

// ------------------------------------------------------------------ Lorwyn: a meadow at dusk

const meadow: SetSpec = {
  floor: "grass", floorColors: ["#6a8a3a", "#2e3e1c"], floorTile: 14,
  centre: "none", centreMargin: [0, 0],
  props: ["mushrooms", "acorn"],
  fade: [4, 30, 0.76],
  particles: [{ kind: "pollen", color: "#fff2b0", count: 240, size: 0.12, opacity: 0.85, base: 0.6, where: "air" }, { kind: "fireflies", color: "#d8ff8a", count: 70, size: 0.16, opacity: 1, base: 0.6, where: "room" }],
  build(ctx, r) {
    // willows: trunks, their curtains of hanging leaves
    for (let k = 0; k < 6; k++) {
      const a = (k / 6) * Math.PI * 2 + 0.3;
      const x = Math.cos(a) * (r.hw + 14), z = Math.sin(a) * (r.hd + 13);
      const t = new Put(ctx).at(x, r.floor, z, ctx.rand() * 6);
      trunk(ctx, t, 16, 1.3, "#4a3c2a");
      // its hanging curtain of leafy strands, thinning to their tips
      for (let s = 0; s < 40; s++) {
        const b = (s / 40) * Math.PI * 2 + ctx.rand() * 0.1, rr = 3.5 + ctx.rand() * 3.5;
        const len = 7 + ctx.rand() * 8;
        t.geo(new THREE.CylinderGeometry(0.16, 0.04, len, 4), xf(Math.cos(b) * rr, 17 + ctx.rand() * 2 - len / 2, Math.sin(b) * rr, (ctx.rand() - 0.5) * 0.1, 0, (ctx.rand() - 0.5) * 0.1), vary(ctx, "#36502a", 0.2), CLOTH);
      }
    }
    // mossy stones, a ring of glowing mushrooms, flowers in the grass
    for (let k = 0; k < 9; k++) {
      const a = ctx.rand() * Math.PI * 2;
      boulder(ctx, new Put(ctx).at(Math.cos(a) * (r.hw + 6 + ctx.rand() * 10), r.floor, Math.sin(a) * (r.hd + 6 + ctx.rand() * 10)), 1 + ctx.rand() * 2.5, "#6a6a5a", "#5a7a34");
    }
    const ring = 24;
    for (let k = 0; k < ring; k++) {
      const a = (k / ring) * Math.PI * 2;
      const p = new Put(ctx).at(Math.cos(a) * (r.hw + 4), r.floor, Math.sin(a) * (r.hd + 4));
      const h = 0.4 + ctx.rand() * 0.7, cap = 0.25 + ctx.rand() * 0.3;
      p.cyl(0.07, 0.11, h, 0, 0, 0, "#b8b098", { rough: 0.8 }, 6);
      p.glowing().geo(new THREE.SphereGeometry(cap, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), xf(0, h, 0, 0, 0, 0, 1, 0.7, 1), vary(ctx, "#7a3a62", 0.2), { glow: 0.45, pulse: PULSE.lantern });
    }
    for (let k = 0; k < 160; k++) {
      const a = ctx.rand() * Math.PI * 2, rr = Math.max(r.hw, r.hd) + 2 + ctx.rand() * 18;
      const p = new Put(ctx).at(Math.cos(a) * rr, r.floor, Math.sin(a) * rr * 0.85);
      const h = 0.6 + ctx.rand() * 1.2;
      p.cyl(0.03, 0.04, h, 0, 0, 0, "#3a5a24", CLOTH, 4);
      p.sphere(0.18, 0, h, 0, ["#f0e0a0", "#e8a0c0", "#b0a0f0", "#fff0f0"][k % 4]!, { rough: 0.8, glow: 0.12 }, 1, 0.6, 1, 6);
    }
    ctx.room.add(new THREE.Vector3(0, r.floor + 1.5, 0), "#e0a0ff", 0.7, 24, "steady");
    // fae lanterns on crooked poles
    for (const [x, z] of [[-r.hw - 5, -r.hd - 5], [r.hw + 5, -r.hd - 5], [-r.hw - 6, r.hd + 6], [r.hw + 6, r.hd + 6]] as const) {
      const l = new Put(ctx).at(x, r.floor, z);
      l.geo(new THREE.CylinderGeometry(0.12, 0.2, 9, 6), xf(0, 4.5, 0, 0, 0, 0.08), "#4a3c2a", WOOD);
      l.glowing().sphere(0.7, 0.35, 9.3, 0, "#ffe7a0", { glow: 1.6, pulse: PULSE.lantern });
      ctx.room.add(l.world(0.35, 9.3, 0), "#ffd890", 0.9, 14, "candle", ctx.rand() * 10);
    }
  },
};

export const SETS: Record<PlaneId, SetSpec> = {
  dominaria: study, ravnica: guildhall, innistrad: chapel, theros: temple, zendikar: wilds,
  kamigawa: shrine, amonkhet: trials, ixalan: jungle, phyrexia: machine, lorwyn: meadow,
};

void LEATHERS;
void CLOTH;
