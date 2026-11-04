import { describe, expect, it } from "vitest";
import { CARD_H, CARD_W, COIN, commandSlot, COMMAND_WELL, FELT_HEM, heartSpot, localToVirtual, MAT_D, MAT_W, nameplateSpot, plateDepth, pileAt, PILES, pileSpot, plateWidth, plaqueSpot, RAIL, seats, tableSize, TAX_READOUT, taxReadoutSpot, taxSpot, toLocal, toWorld, virtualToLocal, wellPiece, wellSize, WELL, type PileZone, type Seat } from "./layout";

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
    expect(a!.z - b!.z).toBeLessThan(MAT_D + 4); // a mat's depth plus at most a 4-unit aisle
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
        // each commander's tax column stands beside its own well, on the mat's side, clear of the well and of the felt
        for (const slot of [0, 1]) {
          const [cx, cz] = commandSlot(seat, slot);
          const [tx, tz] = taxSpot(seat, slot);
          expect(Math.sign(tx - cx)).toBe(-Math.sign(cx)); // toward the mat
          expect(Math.abs(tx - cx) - COIN.r).toBeGreaterThanOrEqual(COMMAND_WELL.w / 2 + 0.05);
          expect(Math.abs(tx) - COIN.r).toBeGreaterThanOrEqual(MAT_W / 2 + FELT_HEM); // off the felt
          expect(Math.abs(tz - cz)).toBeLessThan(COMMAND_WELL.h / 2); // level with its well
        }
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

/** Axis-aligned world boxes (the table's seats face along z, so every piece here is axis-aligned in the world). */
type Box = { x0: number; x1: number; z0: number; z1: number; what: string };
const boxOf = (seat: Seat, [lx, lz]: [number, number], w: number, h: number, what: string): Box => {
  const [x, z] = toWorld(seat, lx, lz);
  return { x0: x - w / 2, x1: x + w / 2, z0: z - h / 2, z1: z + h / 2, what };
};
const overlap = (a: Box, b: Box, gap = 0) => a.x0 < b.x1 + gap && b.x0 < a.x1 + gap && a.z0 < b.z1 + gap && b.z0 < a.z1 + gap;

describe("zone wells, nameplates and the commander tax", () => {
  const ZONES: PileZone[] = ["library", "graveyard", "exile", "command"];
  /** Every piece by a seat: its wells and their plates (a partner's well and the third slot too), its tax columns and tags. */
  const pieces = (seat: Seat, duel: boolean): Box[] => {
    const out: Box[] = [];
    const spots: [PileZone, [number, number], string][] = [
      ...ZONES.map((z) => [z, pileSpot(seat, z), z] as [PileZone, [number, number], string]),
      ["command", commandSlot(seat, 1), "partner"], ["command", commandSlot(seat, 2), "third"],
    ];
    for (const [zone, at, name] of spots) {
      const { w, h } = wellSize(zone);
      out.push(boxOf(seat, at, w, h, `${name} well`));
      out.push(boxOf(seat, nameplateSpot(seat, at, zone), plateWidth(zone, duel), plateDepth(seat), `${name} plate`));
    }
    for (const slot of [0, 1]) out.push(boxOf(seat, taxSpot(seat, slot), COIN.r * 2, COIN.r * 2, `tax ${slot}`));
    return out;
  };

  it("a well is a little larger than a card (the command zone's larger still), and its plate is its caption, nearest me", () => {
    expect(WELL.w).toBeGreaterThan(CARD_W);
    expect(WELL.h).toBeGreaterThan(CARD_H);
    expect(COMMAND_WELL.w).toBeGreaterThanOrEqual(WELL.w);
    expect(COMMAND_WELL.h).toBeGreaterThan(WELL.h);
    for (const seat of seats(["a", "b", "c", "d"], "a")) {
      const lib = pileSpot(seat, "library");
      const [, pz] = toWorld(seat, ...nameplateSpot(seat, lib, "library"));
      const [, wz] = toWorld(seat, ...lib);
      expect(pz).toBeGreaterThan(wz); // world +z is toward me: under the well on my screen, whatever the seat
      // one plane covers the well and its plate
      const piece = wellPiece(seat, lib, "library");
      const [, cz] = toWorld(seat, ...piece.at);
      expect(Math.abs(cz - (wz - WELL.h / 2 + piece.h / 2))).toBeLessThan(1e-9);
    }
  });

  for (const n of [2, 3, 4, 5, 6]) {
    it(`${n} seats: every well, plate, tax column and tag lies on the table's wood, off every mat, and none overlaps another`, () => {
      const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
      const size = tableSize(all);
      const boxes = all.flatMap((s) => pieces(s, n === 2));
      for (const b of boxes) {
        // inside the rail
        expect(Math.max(Math.abs(b.x0), Math.abs(b.x1)), b.what).toBeLessThanOrEqual(size.w / 2 - RAIL);
        expect(Math.max(Math.abs(b.z0), Math.abs(b.z1)), b.what).toBeLessThanOrEqual(size.d / 2 - RAIL);
        // off every mat's felt
        for (const s of all) {
          const felt = boxOf(s, [0, 0], MAT_W + 2 * FELT_HEM, MAT_D + 2 * FELT_HEM, "felt");
          expect(overlap(b, { ...felt, x0: felt.x0 + 1e-6, x1: felt.x1 - 1e-6, z0: felt.z0 + 1e-6, z1: felt.z1 - 1e-6 }), `${b.what} on ${s.player}'s mat`).toBe(false);
        }
      }
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
        expect(overlap(boxes[i]!, boxes[j]!), `${boxes[i]!.what} / ${boxes[j]!.what}`).toBe(false);
      }
    });
  }

  it("the tax's number lies on its command well's plate, at its end toward the mat", () => {
    for (const n of [2, 4]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0")) {
        for (const slot of [0, 1]) {
          const at = commandSlot(seat, slot);
          const plate = boxOf(seat, nameplateSpot(seat, at, "command"), plateWidth("command", n === 2), plateDepth(seat), "plate");
          const num = boxOf(seat, taxReadoutSpot(seat, slot), TAX_READOUT.w, TAX_READOUT.h, "number");
          expect(num.x0).toBeGreaterThanOrEqual(plate.x0 - 1e-9);
          expect(num.x1).toBeLessThanOrEqual(plate.x1 + 1e-9);
          expect(num.z0).toBeGreaterThanOrEqual(plate.z0 - 1e-9);
          expect(num.z1).toBeLessThanOrEqual(plate.z1 + 1e-9);
          // toward the mat: nearer the mat's middle than the plate's middle is
          const [wx] = toWorld(seat, ...taxReadoutSpot(seat, slot));
          expect(Math.abs(wx - seat.x)).toBeLessThan(Math.abs((plate.x0 + plate.x1) / 2 - seat.x));
        }
      }
    }
  });

  it("the tax column never overlaps the command card, and my tax pieces stay clear of my seat buttons' row", () => {
    for (const n of [2, 4]) {
      const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
      const mine = all[0]!;
      const card = boxOf(mine, commandSlot(mine, 0), CARD_W, CARD_H, "card");
      expect(overlap(boxOf(mine, taxSpot(mine, 0), COIN.r * 2, COIN.r * 2, "coins"), card, 0.05)).toBe(false);
      // the buttons' row (seatProps: from DUEL_ROW_X in 1v1, from x0 = 0.7 − span at more seats; both right of the command column)
      const rowZ = n === 2 ? MAT_D / 2 + 1.05 : MAT_D / 2 + 0.44;
      const [x0, x1] = n === 2 ? [-7.8 - 0.26, 3.45 + 0.64 + 0.26] : [0.7 - 4.2 - 0.26, 0.7 + 0.26];
      const row = boxOf(mine, [(x0 + x1) / 2, rowZ], x1 - x0, 0.52, "buttons");
      for (const b of pieces(mine, n === 2)) expect(overlap(b, row, 0.1), b.what).toBe(false);
    }
  });
});
