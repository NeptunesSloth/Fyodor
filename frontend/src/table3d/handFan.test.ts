import { describe, expect, it } from "vitest";
import { easeFan, fanAxes, fanCorners, FAN_LAYER, FAN_LEAN, FAN_MAX, fanTag, handFan, insideRail, refanFrom, showsFan } from "./handFan";
import { CARD_H, CARD_W, MAT_D, seats, tableSize, type Seat } from "./layout";

/** Every seat but mine at every table (two facing rows), plus a lone seat turned each way round. */
function tables(): { seat: Seat; all: Seat[] }[] {
  const out: { seat: Seat; all: Seat[] }[] = [];
  for (const n of [2, 3, 4, 5, 6]) {
    const all = seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0");
    for (const seat of all.slice(1)) out.push({ seat, all });
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

/** Distance from a seat's mat centre toward its owner (mat-local z). */
function along(seat: Seat, x: number, z: number): number {
  return (x - seat.x) * Math.sin(seat.rot) + (z - seat.z) * Math.cos(seat.rot);
}

describe("another player's hand, held up at their edge", () => {
  it("one card per hand card, up to FAN_MAX", () => {
    const seat = seats(["a", "b"], "a")[1]!;
    expect(handFan(seat, 0)).toEqual([]);
    for (let n = 1; n <= 15; n++) expect(handFan(seat, n).length).toBe(Math.min(n, FAN_MAX));
  });

  it("is real card size", () => {
    for (const c of handFan(seats(["a", "b", "c", "d"], "a")[2]!, 7)) {
      const [bl, br, , tl] = fanCorners(c);
      expect(bl!.distanceTo(br!)).toBeCloseTo(CARD_W, 5);
      expect(bl!.distanceTo(tl!)).toBeCloseTo(CARD_H, 5);
    }
  });

  it("stands nearly upright: every card leans FAN_LEAN (15–25°) back from vertical, its top above its bottom", () => {
    expect(FAN_LEAN).toBeGreaterThanOrEqual((15 * Math.PI) / 180);
    expect(FAN_LEAN).toBeLessThanOrEqual((25 * Math.PI) / 180);
    for (const { seat } of tables()) {
      for (const c of handFan(seat, 9)) {
        const { normal } = fanAxes(c);
        // the card's plane leans back FAN_LEAN: its normal is that far up from level (the fan's turn is in the plane)
        expect(Math.asin(normal.y)).toBeCloseTo(FAN_LEAN, 5);
        const [bl, br, tr, tl] = fanCorners(c);
        expect((tl!.y + tr!.y) / 2).toBeGreaterThan((bl!.y + br!.y) / 2 + CARD_H * 0.75);
      }
    }
  });

  it("stays inside the table top's rail and above the felt, for 1 to 15 cards and every seat", () => {
    for (const { seat, all } of tables()) {
      const { hx, hz } = insideRail(tableSize(all));
      for (let n = 1; n <= 15; n++) {
        for (const card of handFan(seat, n)) {
          for (const p of fanCorners(card)) {
            expect(Math.abs(p.x)).toBeLessThanOrEqual(hx);
            expect(Math.abs(p.z)).toBeLessThanOrEqual(hz);
            expect(p.y).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  it("stands at its owner's own edge: its foot past the mat's edge; the far row's whole fan off the mat", () => {
    for (const { seat } of tables()) {
      for (const card of handFan(seat, 7)) {
        const [bl, br, tr, tl] = fanCorners(card);
        for (const p of [bl!, br!]) expect(along(seat, p.x, p.z)).toBeGreaterThan(MAT_D / 2);
        // across the table it leans back toward its owner; in my row it leans over its mat's edge, but held high there
        if (seat.side === "north") for (const p of [tr!, tl!]) expect(along(seat, p.x, p.z)).toBeGreaterThan(MAT_D / 2);
        else for (const p of [tr!, tl!]) expect(along(seat, p.x, p.z)).toBeGreaterThan(MAT_D / 2 - 0.3);
      }
    }
  });

  it("the far row's backs face the table's middle, and every fan's seen side faces my side of the table", () => {
    for (const n of [2, 3, 4, 5, 6]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0").slice(1)) {
        for (const c of handFan(seat, 5)) {
          const { normal } = fanAxes(c);
          expect(normal.z).toBeGreaterThan(0.85); // toward me (my row is at +z) and only a little up
          if (seat.side === "north") expect(Math.sign(normal.z)).toBe(-Math.sign(seat.z)); // toward the middle
        }
      }
    }
  });

  it("is fanned in an arc: left to right as I see it, each turned out a little more, the outer ones lower", () => {
    for (const n of [2, 4, 5, 6]) {
      for (const seat of seats(Array.from({ length: n }, (_, i) => `p${i}`), "p0").slice(1)) {
        const fan = handFan(seat, 8);
        const tops = fan.map((c) => fanAxes(c).up);
        for (let i = 1; i < fan.length; i++) {
          expect(fan[i]!.pos.x).toBeGreaterThan(fan[i - 1]!.pos.x + 0.15);
          expect(tops[i]!.x).toBeGreaterThan(tops[i - 1]!.x);
        }
        expect(fan[0]!.pos.y).toBeLessThan(fan[3]!.pos.y);
        expect(fan[7]!.pos.y).toBeLessThan(fan[4]!.pos.y);
      }
    }
  });

  it("layers its cards far enough apart not to fight in depth from across the table", () => {
    expect(FAN_LAYER).toBeGreaterThanOrEqual(0.01);
    const [a, b] = handFan(seats(["a", "b"], "a")[1]!, 2);
    expect(a!.pos.distanceTo(b!.pos)).toBeGreaterThan(0.01);
  });

  it("a count tag floats just over the top of the fan", () => {
    const fan = handFan(seats(["a", "b", "c", "d"], "a")[3]!, 15);
    const at = fanTag(fan)!;
    const top = Math.max(...fan.flatMap(fanCorners).map((p) => p.y));
    expect(at.y).toBeGreaterThan(top - 0.1);
    expect(at.y).toBeLessThan(top + 0.6);
    expect(fanTag([])).toBeNull();
  });

  it("re-fans from where the cards are: kept cards stay put, a drawn card starts behind the last one, never shared", () => {
    const seat = seats(["a", "b"], "a")[1]!;
    const five = handFan(seat, 5);
    const six = handFan(seat, 6);
    const from = refanFrom(five, six);
    expect(from.length).toBe(6);
    for (let i = 0; i < 5; i++) expect(from[i]!.pos.distanceTo(five[i]!.pos)).toBeLessThan(1e-9);
    expect(from[5]!.pos.distanceTo(five[4]!.pos)).toBeLessThan(1e-9);
    expect(from[5]!.pos).not.toBe(five[4]!.pos); // copies: easing them leaves the old fan alone
    // fewer cards: the ones left ease from where they were; into an empty hand: already in place
    expect(refanFrom(six, five).map((c) => c.pos.x)).toEqual(six.slice(0, 5).map((c) => c.pos.x));
    expect(refanFrom([], five).map((c) => c.pos.x)).toEqual(five.map((c) => c.pos.x));
  });

  it("eases a re-fan to rest exactly, in well under a second at 60 fps, and at once under reduced motion", () => {
    const seat = seats(["a", "b", "c", "d"], "a")[2]!;
    const goal = handFan(seat, 9);
    const cur = refanFrom(handFan(seat, 4), goal);
    let frames = 0;
    while (!easeFan(cur, goal, 1 - Math.exp(-9 / 60)) && frames < 1000) frames++;
    expect(frames).toBeLessThan(200);
    for (const [i, c] of cur.entries()) {
      expect(c.pos.equals(goal[i]!.pos)).toBe(true); // exactly: a settled fan never redraws differently
      expect(c.quat.equals(goal[i]!.quat)).toBe(true);
    }
    const snap = refanFrom(handFan(seat, 4), goal);
    expect(easeFan(snap, goal, 1)).toBe(true);
    expect(snap[8]!.pos.equals(goal[8]!.pos)).toBe(true);
  });

  it("shows at every seat but mine", () => {
    expect(showsFan({ player: "b" }, "a")).toBe(true);
    expect(showsFan({ player: "a" }, "a")).toBe(false);
  });
});
