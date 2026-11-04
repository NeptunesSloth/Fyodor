/**
 * Set pieces, built from primitives into a set's batches (env/kit.ts): bookcases full of varied books, a stone hearth
 * with a live fire, a tall leaded window, a floor candelabrum, a reading chair, a globe, chests, columns and arches,
 * lanterns, braziers, gravestones, shoji screens, obelisks, rocks and trees. Sizes are in table units (a card is 0.84
 * wide: about 7.5 cm to the unit). Each piece stands on its placement's origin (y = its floor), facing +z.
 */
import * as THREE from "three";
import { xf } from "./batch";
import { baked, BRASS, CLOTH, IRON, Put, STONE, vary, WOOD, type SetCtx } from "./kit";
import { PULSE } from "./roomShader";

export const LEATHERS = ["#5a1a14", "#6b2a16", "#2b3a5a", "#24402c", "#3e2a1c", "#6a4a22", "#4a1e2e", "#1e2a3a", "#7a5a2a", "#352018", "#5e3a1e", "#2e4a4a"];

/** A bookcase `w` wide, `h` tall and `d` deep, filled with books (and the odd jar or skull). */
export function bookcase(ctx: SetCtx, at: Put, w: number, h: number, d: number, wood: string, books = LEATHERS): void {
  const r = ctx.rand;
  const t = 0.35; // board thickness
  const W = baked(wood, ctx.floorY, { ao: 0.3 });
  // carcass: sides, top with a cornice, plinth, back
  at.box(t, h, d, -w / 2 + t / 2, 0, 0, W, WOOD);
  at.box(t, h, d, w / 2 - t / 2, 0, 0, W, WOOD);
  at.box(w, 1.1, d + 0.1, 0, 0, 0.05, baked(new THREE.Color(wood).multiplyScalar(0.8), ctx.floorY), WOOD);
  at.box(w + 0.6, 0.5, d + 0.5, 0, h - 0.5, 0.15, W, WOOD);
  at.box(w + 0.9, 0.3, d + 0.7, 0, h, 0.2, W, WOOD);
  at.box(w - t * 2, h - 1.1, 0.15, 0, 1.1, -d / 2 + 0.08, new THREE.Color(wood).multiplyScalar(0.45), WOOD);
  const shelves = Math.max(3, Math.round((h - 1.6) / 4.1));
  const step = (h - 1.6) / shelves;
  for (let s = 0; s < shelves; s++) {
    const y = 1.1 + s * step;
    at.box(w - t * 2, 0.22, d - 0.1, 0, y, 0.0, W, WOOD);
    // the books on this shelf, left to right: upright runs, a leaning one, the odd flat stack, gaps
    let x = -w / 2 + t + 0.1;
    const end = w / 2 - t - 0.1;
    const shelfH = step - 0.22;
    while (x < end - 0.3) {
      const roll = r();
      if (roll < 0.06) { x += 0.4 + r() * 0.8; continue; } // a gap
      if (roll < 0.12 && end - x > 2.2) {
        // a flat stack
        let y2 = y + 0.22;
        const n = 2 + Math.floor(r() * 4);
        for (let k = 0; k < n; k++) {
          const bh = 0.28 + r() * 0.2, bw = 1.6 + r() * 0.5, bd = 1.2 + r() * 0.6;
          at.box(bw, bh, bd, x + 1.0 + (r() - 0.5) * 0.2, y2, d / 2 - bd / 2 - 0.25, vary(ctx, books[Math.floor(r() * books.length)]!, 0.15), CLOTH, (r() - 0.5) * 0.2);
          y2 += bh;
        }
        x += 2.2;
        continue;
      }
      if (roll < 0.15 && end - x > 1.2) {
        // a jar or a skull between the books
        if (r() < 0.5) at.lathe([[0, 0], [0.42, 0.05], [0.5, 0.6], [0.36, 1.1], [0.3, 1.3], [0.34, 1.45], [0, 1.45]], x + 0.55, y + 0.22, 0.2, vary(ctx, "#4a5a50", 0.2), { rough: 0.3 }, 10);
        else {
          at.sphere(0.48, x + 0.55, y + 0.22 + 0.5, 0.3, "#7a705c", { rough: 0.6 }, 1, 0.9, 1.15);
          at.box(0.62, 0.28, 0.5, x + 0.55, y + 0.22, 0.55, "#6a604e", { rough: 0.6 });
        }
        x += 1.2;
        continue;
      }
      const bw = 0.24 + r() * 0.42;
      const bh = Math.min(shelfH - 0.25, shelfH * (0.62 + r() * 0.3));
      const bd = Math.min(d - 0.4, 1.5 + r() * 0.9);
      const lean = r() < 0.07 ? (r() < 0.5 ? -1 : 1) * (0.12 + r() * 0.2) : 0;
      const col = vary(ctx, books[Math.floor(r() * books.length)]!, 0.22);
      const front = d / 2 - 0.15 - r() * 0.25;
      // each spine darker toward the shelf and its top edge, as the shelf above shades it
      const y0 = y + 0.22;
      const shade = (p: THREE.Vector3, _n: THREE.Vector3, out: THREE.Color) => {
        const k = THREE.MathUtils.smoothstep(p.y, y0, y0 + bh * 0.5);
        out.copy(col).multiplyScalar(0.55 + 0.45 * k - (p.y > y0 + bh - 0.05 ? 0.1 : 0));
      };
      at.box(bw, bh, bd, x + bw / 2, y0, front - bd / 2, shade, CLOTH, 0, 0, lean);
      if (!lean) {
        // raised bands and gilt rules across the spine, a title label on some
        const style = r();
        const gilt = new THREE.Color("#a8823a").multiplyScalar(0.6 + r() * 0.3);
        if (style < 0.55) for (const by of [0.18, bh * 0.36, bh * 0.58, bh - 0.3]) at.box(bw + 0.03, 0.07, 0.05, x + bw / 2, y0 + by, front + 0.01, by < 0.2 || by > bh - 0.35 ? gilt : new THREE.Color(col).multiplyScalar(0.8), by < 0.2 || by > bh - 0.35 ? BRASS : CLOTH);
        if (style < 0.8) at.box(bw * 0.72, bh * 0.14, 0.04, x + bw / 2, y0 + bh * 0.66, front + 0.012, style < 0.4 ? new THREE.Color(col).multiplyScalar(0.4) : new THREE.Color("#8a7a5a"), CLOTH);
      }
      x += bw + 0.02 + (lean ? 0.3 : 0);
    }
  }
}

/** A stone hearth: its opening `w` × `h`, a live fire with logs and embers, a mantel, and its light. */
export function hearth(ctx: SetCtx, at: Put, w: number, h: number, stone: string, wood: string): THREE.Vector3 {
  const r = ctx.rand;
  const outer = w + 6;
  const S = baked(stone, ctx.floorY, { ao: 0.35 });
  // the surround: dressed blocks with joints (each a hair apart, toned)
  const block = (bx: number, by: number, bw: number, bh: number, depth: number) => at.box(bw - 0.06, bh - 0.06, depth, bx, by, 0, vary(ctx, stone, 0.12), STONE);
  for (const side of [-1, 1]) {
    let y = 0;
    while (y < h) {
      const bh = Math.min(h - y, 1.6 + r() * 0.8);
      block(side * (w / 2 + 1.5), y, 3, bh, 2.2);
      y += bh;
    }
  }
  // the lintel and the breast above, up past the camera's view
  for (let k = 0; k < 5; k++) block(-w / 2 - 3 + (k + 0.5) * (outer / 5), h, outer / 5, 2, 2.2);
  at.box(outer + 1.6, 0.7, 2.9, 0, h + 2, 0.45, baked(wood, ctx.floorY), WOOD); // mantel shelf
  at.box(outer - 1, 0.5, 2.3, 0, h + 1.5, 0.2, baked(new THREE.Color(wood).multiplyScalar(0.8), ctx.floorY), WOOD);
  at.box(outer - 1, 22, 2, 0, h + 2.7, -0.2, S, STONE);
  // firebox: sooty back and sides, a hearthstone out front
  at.box(w, h, 0.4, 0, 0, -1.5, "#120c09", STONE);
  at.box(0.3, h, 2.2, -w / 2 - 0.15, 0, -0.4, "#1d1410", STONE);
  at.box(0.3, h, 2.2, w / 2 + 0.15, 0, -0.4, "#1d1410", STONE);
  at.box(outer + 2, 0.45, 4.5, 0, 0, 2.6, baked(new THREE.Color(stone).multiplyScalar(0.85), ctx.floorY, { ao: 0.2 }), STONE);
  // andirons and logs
  for (const side of [-1, 1]) {
    at.box(0.18, 0.9, 2.2, side * w * 0.28, 0, -0.1, "#1a1a1c", IRON);
    at.cyl(0.14, 0.14, 1.4, side * w * 0.28, 0, 1.0, "#1a1a1c", IRON, 6);
    at.sphere(0.22, side * w * 0.28, 1.5, 1.0, "#3a3020", BRASS);
  }
  const logs: [number, number, number, number][] = [[-0.6, 0.95, -0.4, 0.15], [0.7, 0.95, -0.2, -0.12], [0.0, 1.55, -0.3, 0.05]];
  for (const [lx, ly, lz, rz] of logs) {
    at.geo(new THREE.CylinderGeometry(0.42, 0.48, w * 0.62, 9), xf(lx, ly, lz, 0, 0.12, Math.PI / 2 + rz), "#2a1a10", { rough: 0.95 });
    // their glowing undersides and ends
    at.glowing().geo(new THREE.CylinderGeometry(0.3, 0.34, w * 0.6, 7), xf(lx, ly - 0.16, lz + 0.12, 0, 0.12, Math.PI / 2 + rz), "#ff5a14", { glow: 1.6, pulse: PULSE.hearth });
  }
  // the ember bed
  for (let i = 0; i < 26; i++) {
    const ex = (r() - 0.5) * w * 0.7, ez = -0.8 + r() * 1.4;
    at.glowing().sphere(0.12 + r() * 0.16, ex, 0.12, ez, new THREE.Color("#ff4a10").lerp(new THREE.Color("#ffb040"), r()), { glow: 1.2 + r() * 1.2, pulse: PULSE.hearth }, 1, 0.5, 1, 6);
  }
  // the flames
  const fire = at.world(0, 0.7, -0.3);
  for (let i = 0; i < 7; i++) {
    const fx = (i / 6 - 0.5) * w * 0.55 + (r() - 0.5) * 0.4;
    const big = 1 - Math.abs(i / 6 - 0.5) * 1.2;
    ctx.flames.add(at.world(fx, 0.75 + r() * 0.5, -0.3 + (r() - 0.5) * 0.5), 1.7 + big * 1.5, r() * 10, "#ff9a3c", 0.75);
  }
  ctx.room.add(at.world(0, 2.5, 2.5), "#ff8a3a", 2.6, 34, "hearth", 0.3);
  return fire;
}

/** A tall leaded window (`w` × `h`, its sill at `sill`) in a wall facing +z, with curtains drawn back. */
export function leadedWindow(ctx: SetCtx, at: Put, w: number, h: number, sill: number, wood: string, curtain: string): void {
  const F = baked(wood, ctx.floorY);
  at.box(w + 1.4, 0.6, 1.8, 0, sill - 0.6, 0.5, F, WOOD); // sill
  at.box(w + 1.2, 0.8, 0.9, 0, sill + h, 0.2, F, WOOD); // head
  for (const side of [-1, 1]) at.box(0.7, h, 0.9, side * (w / 2 + 0.25), sill, 0.2, F, WOOD);
  at.box(0.35, h, 0.6, 0, sill, 0.1, F, WOOD); // mullion
  for (const ty of [0.25, 0.5, 0.75]) at.box(w, 0.25, 0.5, 0, sill + h * ty, 0.1, F, WOOD);
  // the moonlit glass behind (faintly lit), leaded in small panes
  at.glowing().box(w, h, 0.05, 0, sill, -0.15, "#9fb4dc", { glow: 0.55, rough: 0.2 });
  // the window bay below: panelled
  at.box(w + 1.4, sill - 0.6, 0.5, 0, 0, 0.1, baked(new THREE.Color(wood).multiplyScalar(0.85), ctx.floorY), WOOD);
  // curtains: heavy folds drawn to each side
  for (const side of [-1, 1]) {
    const folds = 5;
    for (let k = 0; k < folds; k++) {
      const fx = side * (w / 2 + 0.6 + k * 0.42);
      at.geo(new THREE.CylinderGeometry(0.3, 0.42, h + sill - 1, 8, 1, false, 0, Math.PI), xf(fx, (h + sill - 1) / 2 + 1, 1.0, 0, side > 0 ? 0 : Math.PI, 0), baked(vary(ctx, curtain, 0.1), ctx.floorY, { ao: 0.5, reach: 8 }), CLOTH);
    }
    at.box(1.0, 0.4, 0.6, side * (w / 2 + 1.3), sill + h * 0.45, 1.3, "#8a6a2a", BRASS); // tie-back
  }
  at.cyl(0.18, 0.18, w + 6, 0, sill + h + 1.2, 1.1, "#5a4020", BRASS, 8, 0, 0, Math.PI / 2);
}

/** A floor-standing brass candelabrum with `arms` lit candles, and its light. */
export function candelabrum(ctx: SetCtx, at: Put, height: number, arms: number, brass = "#a8823a"): void {
  const B = brass;
  at.lathe([[0, 0], [1.5, 0], [1.6, 0.25], [1.1, 0.5], [0.5, 0.9], [0.32, 1.6], [0.26, height - 2], [0.4, height - 1.7], [0.3, height - 1.5], [0, height - 1.5]], 0, 0, 0, B, BRASS, 14);
  const cups: THREE.Vector3[] = [new THREE.Vector3(0, height - 1.5, 0)];
  for (let k = 0; k < arms - 1; k++) {
    const a = (k / (arms - 1)) * Math.PI * 2;
    const rr = 1.6;
    const x = Math.cos(a) * rr, z = Math.sin(a) * rr;
    at.geo(new THREE.TorusGeometry(rr / 2, 0.09, 6, 10, Math.PI), xf(x / 2, height - 2.2, z / 2, Math.PI / 2, -a + Math.PI, 0), B, BRASS);
    cups.push(new THREE.Vector3(x, height - 2.2, z));
  }
  for (const c of cups) {
    at.lathe([[0, 0], [0.3, 0], [0.42, 0.2], [0.24, 0.3], [0, 0.3]], c.x, c.y, c.z, B, BRASS, 10);
    const ch = 1.0 + ctx.rand() * 1.2;
    candleBody(at, c.x, c.y + 0.25, c.z, 0.18, ch, ctx.rand);
    ctx.flames.add(at.world(c.x, c.y + 0.25 + ch + 0.05, c.z), 0.55, ctx.rand() * 10);
  }
  ctx.room.add(at.world(0, height + 0.5, 0), "#ffae58", 1.2, 16, "candle", ctx.rand() * 10);
}

/** A candle's wax with a melted rim and a few drips, its wick, standing at (x, y, z). */
export function candleBody(at: Put, x: number, y: number, z: number, r: number, h: number, rand: () => number, wax = "#ead9b8"): void {
  const top = at.world(x, y + h, z).y;
  const foot = top - h;
  const W = new THREE.Color(wax);
  // wax: a little uneven, its melted rim, shaded toward the foot and lit from within near the flame
  const shade = (p: THREE.Vector3, _n: THREE.Vector3, out: THREE.Color) => out.copy(W).multiplyScalar(0.72 + 0.28 * THREE.MathUtils.smoothstep(p.y, foot, foot + h * 0.7));
  at.lathe([[0, 0], [r * 1.03, 0], [r * 0.99, h * 0.35], [r * 1.01, h * 0.7], [r * 0.98, h - 0.06], [r * 0.92, h - 0.005], [r * 0.6, h - 0.045], [0.0, h - 0.065]], x, y, z, shade, { rough: 0.5, glowAt: (p) => Math.max(0, 1 - (top - p.y) / (h * 0.45)) * 0.4, pulse: PULSE.candle }, 16);
  const drips = 2 + Math.floor(rand() * 3);
  for (let k = 0; k < drips; k++) {
    const a = rand() * Math.PI * 2, len = h * (0.25 + rand() * 0.45);
    const dr = r * (0.16 + rand() * 0.1);
    at.geo(new THREE.CapsuleGeometry(dr, len, 3, 6), xf(x + Math.cos(a) * r * 0.97, y + h - len / 2 - dr - 0.01, z + Math.sin(a) * r * 0.97, 0, -a, 0, 1, 1, 0.55), shade, { rough: 0.45, glowAt: (p) => Math.max(0, 1 - (top - p.y) / (h * 0.45)) * 0.3, pulse: PULSE.candle });
    // the bead it ends in
    at.sphere(dr * 1.25, x + Math.cos(a) * r * 0.99, y + h - len - dr * 1.2, z + Math.sin(a) * r * 0.99, shade, { rough: 0.45 }, 1, 1.2, 1, 6);
  }
  // the wick, bent and charred, its tip a glowing coal
  at.cyl(0.016, 0.02, 0.15, x, y + h - 0.07, z, "#1a1410", { rough: 0.9 }, 5, 0, 0, 0.14);
  at.sphere(0.018, x + 0.012, y + h + 0.075, z, "#ff7a2a", { glow: 2.5, pulse: PULSE.candle }, 1, 1, 1, 5);
}

/** A wingback reading chair, a little turned. */
export function armchair(ctx: SetCtx, at: Put, leather: string, wood: string): void {
  // a deep club chair: a rounded seat cushion, rolled arms, a curved back, button-tufted, on short turned feet
  const L = baked(leather, ctx.floorY, { ao: 0.4, reach: 4 });
  const dark = new THREE.Color(leather).multiplyScalar(0.72);
  at.box(6.2, 2.4, 5.8, 0, 0.7, 0, baked(dark, ctx.floorY, { ao: 0.5 }), CLOTH);
  at.geo(new THREE.SphereGeometry(1, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), xf(0, 3.05, 0.4, 0, 0, 0, 2.5, 0.75, 2.35), L, { rough: 0.55 });
  // the back: a curved shell, outer and inner skins, its top rolled
  for (const [rad, sh] of [[3.2, 1], [2.75, 0.9]] as const) {
    at.geo(new THREE.CylinderGeometry(rad, rad, 6.4, 18, 1, true, Math.PI * 0.62, Math.PI * 0.76), xf(0, 3.1 + 3.2, 0.9, 0, Math.PI, 0, 1, 1, 0.85), sh === 1 ? L : new THREE.Color(leather).multiplyScalar(0.9), { rough: 0.55 });
  }
  at.geo(new THREE.TorusGeometry(2.98, 0.24, 8, 22, Math.PI * 0.76), xf(0, 9.5, 0.9, Math.PI / 2, 0, Math.PI * 0.12, 1, 0.85, 1), L, { rough: 0.5 });
  for (const sd of [-1, 1]) {
    at.box(1.0, 3.3, 5.0, sd * 2.75, 2.4, 0.5, L, { rough: 0.55 });
    at.geo(new THREE.CylinderGeometry(0.72, 0.72, 5.3, 12), xf(sd * 2.85, 5.7, 0.55, Math.PI / 2, 0, 0), L, { rough: 0.5 });
    at.geo(new THREE.SphereGeometry(0.72, 10, 8), xf(sd * 2.85, 5.7, 3.2, 0, 0, 0, 1, 1, 0.3), new THREE.Color(leather).multiplyScalar(0.85), { rough: 0.5 });
  }
  for (const [lx, lz] of [[-2.7, -2.4], [2.7, -2.4], [-2.7, 2.6], [2.7, 2.6]] as const) at.lathe([[0, 0], [0.22, 0], [0.32, 0.3], [0.26, 0.7], [0, 0.7]], lx, 0, lz, wood, WOOD, 8);
  // tufting buttons across the inside of the back
  for (let i = 0; i < 10; i++) {
    const a = Math.PI * (0.38 + (i % 5) * 0.06) * (i % 2 ? 1 : 1);
    const t = (i % 5) / 4 - 0.5;
    at.sphere(0.12, Math.sin(t * 1.8) * 2.55, 5.4 + Math.floor(i / 5) * 2.0, 0.9 - Math.cos(t * 1.8) * 2.2 + 0.05, "#1a0806", { rough: 0.4 }, 1, 1, 1, 6);
    void a;
  }
}

/** A terrestrial globe on a turned stand. */
export function globe(ctx: SetCtx, at: Put, wood: string): void {
  at.lathe([[0, 0], [2.2, 0], [2.0, 0.4], [0.6, 0.8], [0.45, 4], [0.7, 5], [0.4, 8.5], [0, 8.5]], 0, 0, 0, baked(wood, ctx.floorY), WOOD, 12);
  for (const a of [0, 2.1, 4.2]) at.box(0.35, 0.3, 2.6, Math.cos(a) * 1.3, 0.2, Math.sin(a) * 1.3, wood, WOOD, -a + Math.PI / 2);
  at.geo(new THREE.TorusGeometry(2.9, 0.12, 6, 28), xf(0, 11.4, 0, 0, 0.4, 0.4), "#a8823a", BRASS);
  // the sphere: seas and lands painted as vertex colours
  const g = new THREE.SphereGeometry(2.7, 24, 16);
  const sea = new THREE.Color("#2c4a5a"), land = new THREE.Color("#a88a52");
  at.geo(g, xf(0, 11.4, 0, 0, 0, 0.41), (_p, n, out) => {
    const v = Math.sin(n.x * 4.1 + n.y * 2.3) * Math.cos(n.z * 3.7 - n.y * 1.3) + Math.sin(n.y * 6 + n.x * 2) * 0.4;
    out.copy(v > 0.25 ? land : sea);
  }, { rough: 0.45 });
}

/** A brass-bound chest. */
export function chest(ctx: SetCtx, at: Put, w: number, wood: string): void {
  const d = w * 0.6, h = w * 0.55;
  at.box(w, h, d, 0, 0, 0, baked(wood, ctx.floorY, { ao: 0.3 }), WOOD);
  at.geo(new THREE.CylinderGeometry(d / 2, d / 2, w, 12, 1, false, 0, Math.PI), xf(0, h, 0, 0, 0, Math.PI / 2), baked(wood, ctx.floorY), WOOD);
  for (const bx of [-w * 0.35, 0, w * 0.35]) {
    at.box(0.28, h + 0.02, d + 0.06, bx, 0, 0, "#8a6a2a", BRASS);
    at.geo(new THREE.CylinderGeometry(d / 2 + 0.04, d / 2 + 0.04, 0.28, 12, 1, true, 0, Math.PI), xf(bx, h, 0, 0, 0, Math.PI / 2), "#8a6a2a", BRASS);
  }
  at.box(0.7, 0.8, 0.12, 0, h - 0.9, d / 2 + 0.04, "#a8823a", BRASS);
}

/** A pile of books lying on the floor. */
export function bookPile(ctx: SetCtx, at: Put, n: number): void {
  let y = 0;
  for (let k = 0; k < n; k++) {
    const bh = 0.35 + ctx.rand() * 0.3, bw = 2.2 + ctx.rand() * 0.8, bd = 1.6 + ctx.rand() * 0.6;
    at.box(bw, bh, bd, (ctx.rand() - 0.5) * 0.3, y, (ctx.rand() - 0.5) * 0.3, vary(ctx, LEATHERS[Math.floor(ctx.rand() * LEATHERS.length)]!, 0.15), CLOTH, (ctx.rand() - 0.5) * 0.6);
    at.box(bw - 0.12, bh - 0.12, 0.04, (ctx.rand() - 0.5) * 0.02, y + 0.06, bd / 2 + 0.0, "#9a8c6c", CLOTH);
    y += bh;
  }
}

/** A wall: `w` wide, `h` tall, its inner face toward +z; panelled wainscot below, plaster above, a skirting board. */
export function panelledWall(ctx: SetCtx, at: Put, w: number, h: number, wood: string, plaster: string, wainscot = 7): void {
  at.box(w, h, 0.6, 0, 0, -0.3, baked(plaster, ctx.floorY, { ao: 0.5, reach: 10 }), { rough: 0.95 });
  const W = baked(wood, ctx.floorY, { ao: 0.3 });
  at.box(w, 0.9, 0.5, 0, 0, 0.1, new THREE.Color(wood).multiplyScalar(0.7), WOOD); // skirting
  at.box(w, wainscot, 0.25, 0, 0, -0.05, new THREE.Color(wood).multiplyScalar(0.75), WOOD);
  at.box(w, 0.45, 0.55, 0, wainscot, 0.05, W, WOOD); // dado rail
  const panels = Math.max(1, Math.round(w / 4));
  const pw = w / panels;
  for (let k = 0; k < panels; k++) {
    const px = -w / 2 + (k + 0.5) * pw;
    at.box(pw - 1.0, wainscot - 2.4, 0.2, px, 1.4, 0.12, vary(ctx, wood, 0.06), WOOD);
    at.box(0.3, wainscot - 1, 0.32, -w / 2 + k * pw, 0.9, 0.08, W, WOOD);
  }
  at.box(w, 0.7, 0.6, 0, h - 0.7, 0.05, W, WOOD); // cornice
}

/** A plain stone or plaster column with a base and capital (fluted: Theros). */
export function column(ctx: SetCtx, at: Put, r: number, h: number, color: string, fluted = false): void {
  const C = baked(color, ctx.floorY, { ao: 0.3, reach: 4 });
  at.box(r * 2.6, 0.8, r * 2.6, 0, 0, 0, C, STONE);
  at.lathe([[0, 0], [r * 1.25, 0], [r * 1.25, 0.3], [r * 1.05, 0.6], [r, 0.9], [0, 0.9]], 0, 0.8, 0, C, STONE, 18);
  if (fluted) {
    const n = 16;
    for (let k = 0; k < n; k++) {
      const a = (k / n) * Math.PI * 2;
      at.cyl(r * 0.2, r * 0.22, h - 3.4, Math.cos(a) * r * 0.86, 1.7, Math.sin(a) * r * 0.86, C, STONE, 5);
    }
    at.cyl(r * 0.88, r * 0.94, h - 3.4, 0, 1.7, 0, C, STONE, 16);
  } else at.cyl(r * 0.92, r, h - 3.4, 0, 1.7, 0, C, STONE, 16);
  at.lathe([[0, 0], [r * 0.95, 0], [r * 1.3, 0.6], [r * 1.35, 0.9], [0, 0.9]], 0, h - 1.7, 0, C, STONE, 18);
  at.box(r * 2.8, 0.8, r * 2.8, 0, h - 0.8, 0, C, STONE);
}

/** A round or pointed arch between two piers (span `w`, spring height `h`), in the x–y plane. */
export function arch(ctx: SetCtx, at: Put, w: number, h: number, depth: number, color: string, pointed = false): void {
  const C = baked(color, ctx.floorY, { ao: 0.35, reach: 5 });
  for (const s of [-1, 1]) at.box(1.6, h, depth, s * (w / 2 + 0.8), 0, 0, C, STONE);
  const n = 11;
  const R = w / 2 + 0.8;
  for (let k = 0; k < n; k++) {
    const a0 = (k / n) * Math.PI, a1 = ((k + 1) / n) * Math.PI;
    const am = (a0 + a1) / 2;
    const lift = pointed ? Math.sin(am) * w * 0.25 : 0;
    const x = Math.cos(am) * R * (pointed ? 0.85 : 1), y = h + Math.sin(am) * R * (pointed ? 1.1 : 1) + lift * 0.3;
    at.box(1.6, R * (a1 - a0) * 1.12, depth, x, y - R * (a1 - a0) * 0.56, 0, C, STONE, 0, 0, am);
  }
  at.box(w + 3.2, 0.6, depth + 0.2, 0, h - 0.6, 0, C, STONE);
}

/** An iron lantern with lit glass; `hanging` adds a chain above it. Returns the flame's local position. */
export function lantern(_ctx: SetCtx, at: Put, size: number, glass: string, iron = "#1c1a18"): THREE.Vector3 {
  const s = size;
  at.box(s * 1.1, s * 0.15, s * 1.1, 0, 0, 0, iron, IRON);
  at.box(s * 1.2, s * 0.12, s * 1.2, 0, s * 1.35, 0, iron, IRON);
  at.geo(new THREE.ConeGeometry(s * 0.75, s * 0.55, 4), xf(0, s * 1.47 + s * 0.27, 0, 0, Math.PI / 4), iron, IRON);
  at.geo(new THREE.TorusGeometry(s * 0.18, s * 0.04, 5, 10), xf(0, s * 2.1, 0), iron, IRON);
  for (const [cx, cz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) at.box(s * 0.08, s * 1.25, s * 0.08, cx * s * 0.5, s * 0.12, cz * s * 0.5, iron, IRON);
  at.glowing().box(s * 0.95, s * 1.2, s * 0.95, 0, s * 0.14, 0, glass, { glow: 0.85, pulse: PULSE.lantern, rough: 0.2 });
  return new THREE.Vector3(0, s * 0.35, 0);
}

/** A gravestone: rounded or cross-topped, tilted with age. */
export function gravestone(ctx: SetCtx, at: Put, h: number, color: string, kind: number): void {
  const C = baked(vary(ctx, color, 0.15), ctx.floorY, { ao: 0.5, reach: 2 });
  const w = h * 0.55;
  if (kind === 0) {
    at.box(w, h - w / 2, 0.45, 0, 0, 0, C, STONE);
    at.geo(new THREE.CylinderGeometry(w / 2, w / 2, 0.45, 14, 1, false, -Math.PI / 2, Math.PI), xf(0, h - w / 2, 0, Math.PI / 2, 0, 0), C, STONE);
    at.box(w * 0.5, 0.06, 0.05, 0, h * 0.62, 0.24, new THREE.Color(color).multiplyScalar(0.5), STONE);
  } else if (kind === 1) {
    at.box(0.5, h, 0.45, 0, 0, 0, C, STONE);
    at.box(w * 1.1, 0.5, 0.45, 0, h * 0.62, 0, C, STONE);
  } else {
    at.box(w * 1.2, h * 0.5, 0.5, 0, 0, 0, C, STONE);
    at.geo(new THREE.ConeGeometry(w * 0.85, h * 0.4, 4), xf(0, h * 0.5 + h * 0.2, 0, 0, Math.PI / 4, 0, 1, 1, 0.35), C, STONE);
  }
  at.box(w * 1.3, 0.3, 1.2, 0, 0, 0.2, baked(new THREE.Color(color).multiplyScalar(0.7), ctx.floorY), STONE);
}

/** A rough boulder (a squashed, jittered icosahedron). */
export function boulder(ctx: SetCtx, at: Put, r: number, color: string, moss?: string): void {
  const g = new THREE.IcosahedronGeometry(r, 1);
  const p = g.getAttribute("position");
  // (the same jitter for every copy of a corner, so the faces stay joined: a lump, not shards)
  const seed = ctx.rand() * 100;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const h = Math.sin(x * 12.9898 / r + y * 78.233 / r + z * 37.719 / r + seed) * 43758.5453;
    const k = 0.8 + (h - Math.floor(h)) * 0.35;
    p.setXYZ(i, x * k, Math.max(-r * 0.2, y * k * 0.7), z * k);
  }
  g.computeVertexNormals();
  const base = new THREE.Color(color), m = moss ? new THREE.Color(moss) : null;
  at.geo(g, xf(0, r * 0.15, 0, 0, ctx.rand() * 6), (pp, n, out) => {
    out.copy(base).multiplyScalar(0.8 + ((pp.x * 7.1 + pp.z * 3.3) % 1 + 1) % 1 * 0.3);
    if (m && n.y > 0.45) out.lerp(m, 0.7);
  }, STONE);
}

/** A tree: a tapering, leaning trunk with a few boughs (leaves are the set's own business). */
export function trunk(ctx: SetCtx, at: Put, h: number, r: number, bark: string): void {
  const B = baked(bark, ctx.floorY, { ao: 0.3, reach: 4 });
  at.cyl(r * 0.6, r, h, 0, 0, 0, B, { rough: 1 }, 9, (ctx.rand() - 0.5) * 0.15, 0, (ctx.rand() - 0.5) * 0.15);
  for (let k = 0; k < 4; k++) {
    const a = ctx.rand() * Math.PI * 2;
    at.geo(new THREE.CylinderGeometry(r * 0.15, r * 0.35, h * 0.4, 6), xf(Math.cos(a) * r, h * (0.55 + ctx.rand() * 0.3), Math.sin(a) * r, Math.sin(a) * 0.8, 0, -Math.cos(a) * 0.8), B, { rough: 1 });
  }
  // roots
  for (let k = 0; k < 5; k++) {
    const a = (k / 5) * Math.PI * 2 + ctx.rand();
    at.geo(new THREE.ConeGeometry(r * 0.35, r * 2.2, 5), xf(Math.cos(a) * r * 0.9, 0.2, Math.sin(a) * r * 0.9, Math.sin(a) * 1.25, 0, -Math.cos(a) * 1.25), B, { rough: 1 });
  }
}
