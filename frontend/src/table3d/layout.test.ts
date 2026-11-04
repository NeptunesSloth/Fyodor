import { describe, expect, it } from "vitest";
import { commandSlot, heartSpot, localToVirtual, MAT_D, MAT_W, pileAt, PILES, pileSpot, plaqueSpot, seats, tableSize, taxSpot, toLocal, toWorld, virtualToLocal, type Seat } from "./layout";

/** Is a world point on a seat's mat (with its edge)? */
const onMat = (seat: Seat, x: number, z: number) => {
  const [lx, lz] = toLocal(seat, x, z);
  return Math.abs(lx) <= MAT_W / 2 + 0.25 && Math.abs(lz) <= MAT_D / 2 + 0.25;
};

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

  it("three or more seats: each heart and plate in the aisle by its own mat, centred on it, the plate on the heart's left", () => {
    for (const n of [3, 4, 5, 6]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0")) {
        const [hx, hz] = toWorld(seat, ...heartSpot(seat));
        const [px, pz] = toWorld(seat, ...plaqueSpot(seat));
        expect(Math.abs(hz)).toBeLessThan(Math.abs(seat.z) - MAT_D / 2); // over the aisle side of its mat
        expect(Math.sign(hz)).toBe(Math.sign(seat.z)); // in its own half of the aisle
        expect(pz).toBeCloseTo(hz);
        expect(px).toBeLessThan(hx); // the plate left of the heart, as I see it
        expect(Math.abs((hx + px) / 2 - seat.x)).toBeLessThan(1); // the pair centred on its own mat
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

  it("mirrors the far row's piles: every library, graveyard and exile on my right, every command zone on my left", () => {
    for (const n of [2, 3, 4, 5, 6]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0")) {
        const side = (zone: "library" | "graveyard" | "exile" | "command") => Math.sign(toWorld(seat, ...pileSpot(seat, zone))[0] - seat.x);
        expect([side("library"), side("graveyard"), side("exile")]).toEqual([1, 1, 1]);
        expect(side("command")).toBe(-1);
        expect(Math.sign(toWorld(seat, ...commandSlot(seat, 1))[0] - seat.x)).toBe(-1); // a partner's slot too
        // the tax counter sits outside its slot, away from the mat
        expect(Math.abs(taxSpot(0, seat)[0])).toBeGreaterThan(Math.abs(commandSlot(seat, 0)[0]));
        // and dropping on the drawn pile finds it
        expect(pileAt(...pileSpot(seat, "graveyard"), seat)).toBe("graveyard");
        expect(pileAt(...commandSlot(seat, 1), seat)).toBe("command");
      }
    }
  });

  it("1v1: each plate and heart sits centred past its owner's own edge, off both mats and out of the aisle", () => {
    const s = seats(["a", "b"], "a");
    expect(s.every((x) => x.duel)).toBe(true);
    for (const seat of s) {
      const heart = toWorld(seat, ...heartSpot(seat));
      const plate = toWorld(seat, ...plaqueSpot(seat));
      for (const [x, z] of [heart, plate]) {
        // on the owner's side of the table, past the owner's own edge (mine below my mat, theirs beyond their far edge)
        expect(Math.sign(z)).toBe(Math.sign(seat.z));
        expect(Math.abs(z)).toBeGreaterThan(Math.abs(seat.z) + MAT_D / 2);
        for (const mat of s) expect(onMat(mat, x, z)).toBe(false);
        expect(z * z).toBeLessThan((tableSize(s).d / 2) ** 2);
      }
      // the pair is centred on the mat (the plate left of the heart, as I see it), both seats the same way round
      expect(plate[0]).toBeLessThan(heart[0]);
      expect(Math.abs((heart[0] + plate[0]) / 2 - seat.x)).toBeLessThan(1.2);
    }
  });

  it("1v1: a narrower aisle (nothing lives in it but the stack and the arrows)", () => {
    const [a, b] = seats(["a", "b"], "a");
    const four = seats(["a", "b", "c", "d"], "a");
    expect(a!.z - b!.z).toBeLessThan(four[0]!.z - four[2]!.z);
    expect(a!.z - b!.z - MAT_D).toBeGreaterThan(1); // a clear gap between the two mats
  });

  it("4 players: plates and hearts stay over the aisle (unchanged)", () => {
    for (const seat of seats(["a", "b", "c", "d"], "a")) {
      expect(seat.duel).toBeUndefined();
      const [, hz] = toWorld(seat, ...heartSpot(seat));
      const [, pz] = toWorld(seat, ...plaqueSpot(seat));
      expect(Math.abs(hz)).toBeLessThan(Math.abs(seat.z) - MAT_D / 2);
      expect(Math.abs(pz)).toBeLessThan(Math.abs(seat.z) - MAT_D / 2);
    }
  });
});
