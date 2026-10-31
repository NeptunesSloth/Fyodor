import { describe, expect, it } from "vitest";
import { heartSpot, localToVirtual, pileAt, PILES, seats, tableSize, toLocal, toWorld, virtualToLocal } from "./layout";

describe("3D table layout", () => {
  it("seats two facing rows, the viewer's row south, clockwise (along my row to my left, then back across)", () => {
    const s = seats(["p1", "p2", "p3", "p4"], "p3");
    expect(s.map((x) => [x.player, x.side])).toEqual([["p3", "south"], ["p4", "south"], ["p1", "north"], ["p2", "north"]]);
    const [me, left, across, right] = s;
    expect(left!.x).toBeLessThan(me!.x); // my left neighbour sits to my left in my row
    expect(across!.x).toBeLessThan(right!.x); // then the far row, west to east
    expect(right!.x).toBeCloseTo(me!.x); // the last player sits straight across from me
  });

  it("keeps every mat upright for its owner (no sideways seats)", () => {
    for (const n of [1, 2, 3, 4, 5, 6]) {
      const s = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
      for (const seat of s) expect(["south", "north"]).toContain(seat.side);
      expect(s[0]!.side).toBe("south");
      // the viewer sits in the middle of their row
      const row = s.filter((x) => x.side === "south").map((x) => x.x);
      expect(Math.abs(s[0]!.x)).toBeLessThanOrEqual(Math.max(...row.map(Math.abs)));
    }
  });

  it("floats every life heart toward the middle of the table, over the aisle", () => {
    for (const n of [2, 4, 6]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0")) {
        const [hx, hz] = toWorld(seat, ...heartSpot(seat));
        if (Math.abs(seat.x) > 0.01) expect(Math.abs(hx)).toBeLessThan(Math.abs(seat.x)); // nearer the middle than its mat
        expect(Math.abs(hz)).toBeLessThan(Math.abs(seat.z)); // out over the aisle side
      }
    }
  });

  it("1v1: two mats face each other across a narrow aisle", () => {
    const [a, b] = seats(["a", "b"], "a");
    expect(a!.x).toBe(0);
    expect(b!.x).toBe(0);
    expect(a!.z - b!.z).toBeLessThan(10); // mat depth 6 plus a 3-unit aisle
  });

  it("round-trips mat-local and world coordinates for every side", () => {
    for (const seat of seats(["a", "b", "c", "d"], "a")) {
      const [wx, wz] = toWorld(seat, 1.5, -2);
      const [lx, lz] = toLocal(seat, wx, wz);
      expect(lx).toBeCloseTo(1.5);
      expect(lz).toBeCloseTo(-2);
    }
  });

  it("points each mat's near edge (local +z) at its owner", () => {
    for (const seat of seats(["a", "b", "c", "d"], "a")) {
      const [wx, wz] = toWorld(seat, 0, 1);
      // the near edge is farther from the table centre than the mat centre
      expect(Math.hypot(wx, wz)).toBeGreaterThan(Math.hypot(seat.x, seat.z));
    }
  });

  it("round-trips battlefield virtual positions", () => {
    const [lx, lz] = virtualToLocal(320, 180);
    const [x, y] = localToVirtual(lx, lz);
    expect(x).toBeCloseTo(320);
    expect(y).toBeCloseTo(180);
  });

  it("keeps mats inside the table and apart from each other", () => {
    for (const n of [2, 3, 4, 5, 6]) {
      const order = Array.from({ length: n }, (_, i) => `p${i}`);
      const s = seats(order, "p0");
      const size = tableSize(s);
      for (const seat of s) {
        expect(Math.abs(seat.x)).toBeLessThan(size.w / 2);
        expect(Math.abs(seat.z)).toBeLessThan(size.d / 2);
      }
      for (let i = 0; i < s.length; i++) for (let j = i + 1; j < s.length; j++) {
        expect(Math.hypot(s[i]!.x - s[j]!.x, s[i]!.z - s[j]!.z)).toBeGreaterThan(6);
      }
    }
  });

  it("finds piles", () => {
    expect(pileAt(...PILES.library)).toBe("library");
    expect(pileAt(...PILES.command)).toBe("command");
    expect(pileAt(0, 0)).toBeNull();
  });
});
