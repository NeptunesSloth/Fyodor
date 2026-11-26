import { describe, expect, it } from "vitest";
import { D4_LABEL } from "./diceArt";
import { dieSolid } from "./diceGeometry";

/** Is (x, y) inside the convex polygon (counter-clockwise or clockwise)? */
function inside(poly: [number, number][], x: number, y: number): boolean {
  let sign = 0;
  for (let i = 0; i < poly.length; i++) {
    const [ax, ay] = poly[i]!;
    const [bx, by] = poly[(i + 1) % poly.length]!;
    const c = Math.sign((bx - ax) * (y - ay) - (by - ay) * (x - ax));
    if (c && sign && c !== sign) return false;
    sign ||= c;
  }
  return true;
}

describe("the d4's numbers (diceArt.ts)", () => {
  it("are much bigger than they were, and each still sits on the flat face, clear of the other two", () => {
    // (0.86 of the inradius was too small to read from a seat away)
    expect(D4_LABEL.size).toBeGreaterThanOrEqual(0.86 * 1.3);
    const s = dieSolid("d4");
    for (const f of s.faces) {
      const inr = Math.min(...f.poly.map(([ax, ay], i) => {
        const [bx, by] = f.poly[(i + 1) % f.poly.length]!;
        return Math.abs((bx - ax) * ay - (by - ay) * ax) / Math.hypot(bx - ax, by - ay);
      }));
      // a numeral's ink: about 0.72 of the type size tall, 0.6 wide (Cinzel bold); its top toward its corner
      const h = 0.72 * D4_LABEL.size * inr;
      const w = Math.min(0.6 * D4_LABEL.size, D4_LABEL.maxW) * inr;
      f.poly.forEach(([vx, vy]) => {
        const len = Math.hypot(vx, vy);
        const ux = vx / len, uy = vy / len; // toward the corner
        const px = -uy, py = ux;
        const cx = vx * D4_LABEL.at, cy = vy * D4_LABEL.at;
        for (const [a, b] of [[-1, -1], [-1, 1], [1, -1], [1, 1]] as const) {
          const x = cx + ux * (a * h) / 2 + px * (b * w) / 2;
          const y = cy + uy * (a * h) / 2 + py * (b * w) / 2;
          expect(inside(f.poly, x, y), "on the flat face").toBe(true);
          // in its own corner's third of the face (the three never touch)
          const off = Math.acos((x * ux + y * uy) / Math.hypot(x, y));
          expect(off).toBeLessThan(Math.PI / 3);
        }
      });
    }
  });
});
