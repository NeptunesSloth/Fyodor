import { describe, expect, it } from "vitest";
import { fanCorners, FAN_LAYER, FAN_MAX, handFan, insideRail } from "./handFan";
import { MAT_D, seats, tableSize, type Seat } from "./layout";

/** Every seat of every table (two facing rows), plus a lone seat turned each way round. */
function tables(): { seat: Seat; all: Seat[] }[] {
  const out: { seat: Seat; all: Seat[] }[] = [];
  for (const n of [2, 3, 4, 5, 6]) {
    const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
    for (const seat of all) out.push({ seat, all });
  }
  const sides = ["south", "west", "north", "east"] as const;
  for (const [i, rot] of [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].entries()) {
    for (const duel of [false, true]) {
      const seat: Seat = { player: "x", x: 0, z: 0, rot, side: sides[i]!, ...(duel ? { duel: true } : {}) };
      out.push({ seat, all: [seat] });
    }
  }
  return out;
}

describe("another player's hand fan", () => {
  it("stays inside the table top's rail and above the felt, for 1 to 15 cards and every seat", () => {
    for (const { seat, all } of tables()) {
      const { hx, hz } = insideRail(tableSize(all));
      for (let n = 1; n <= 15; n++) {
        const fan = handFan(seat, n);
        expect(fan.length).toBe(Math.min(n, FAN_MAX));
        for (const card of fan) {
          for (const p of fanCorners(card)) {
            expect(Math.abs(p.x)).toBeLessThanOrEqual(hx);
            expect(Math.abs(p.z)).toBeLessThanOrEqual(hz);
            expect(p.y).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  it("stands past its own mat's edge, off the mat", () => {
    for (const { seat } of tables()) {
      for (const card of handFan(seat, 7)) {
        for (const p of fanCorners(card)) {
          const dx = p.x - seat.x;
          const dz = p.z - seat.z;
          // distance from the mat's centre along the seat's own direction (local +z)
          const along = dx * Math.sin(seat.rot) + dz * Math.cos(seat.rot);
          expect(along).toBeGreaterThan(MAT_D / 2);
        }
      }
    }
  });

  it("layers its cards far enough apart not to fight in depth from across the table", () => {
    expect(FAN_LAYER).toBeGreaterThanOrEqual(0.01);
    const [a, b] = handFan(seats(["a", "b"], "a")[1]!, 2);
    expect(a!.pos.distanceTo(b!.pos)).toBeGreaterThan(0.01);
  });
});
