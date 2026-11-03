import { describe, expect, it } from "vitest";
import { slide, type SlideCard } from "./cardPhysics";

const card = (id: string, x: number, z: number, extra: Partial<SlideCard> = {}): SlideCard => ({ id, x, z, w: 0.84, d: 1.17, ...extra });
const HW = 5.7;
const HD = 4;

describe("card physics (cannon-es flicks)", () => {
  it("slides a flicked card on, slowing to a stop on the felt", () => {
    const { rest } = slide([card("a", -3, 0, { vx: 8 })], HW, HD);
    const [x, z] = rest.get("a")!;
    expect(x).toBeGreaterThan(-1); // went a good way
    expect(x).toBeLessThan(HW); // and stopped on the mat
    expect(z).toBeCloseTo(0, 5); // straight, square to the mat
  });

  it("knocks a card in its way aside, and leaves the rest alone", () => {
    const { rest } = slide([card("a", -3, 0, { vx: 9 }), card("b", 0, 0), card("far", 0, 3)], HW, HD);
    expect(rest.get("b")![0]).toBeGreaterThan(0.3); // pushed along
    expect(rest.has("far")).toBe(false); // untouched
  });

  it("keeps piles: cards under the flicked one, and cards overlapping each other, don't burst apart", () => {
    const pile = [card("p1", 2, 2), card("p2", 2.16, 2), card("p3", 2.32, 2)];
    const { rest } = slide([card("a", -2, 0, { vx: 6 }), card("under", -2, 0.1), ...pile], HW, HD);
    expect(rest.has("under")).toBe(false);
    for (const p of pile) expect(rest.has(p.id)).toBe(false);
  });

  it("stops at the edge of the mat", () => {
    const { rest } = slide([card("a", 3, 0, { vx: 40 })], HW, HD);
    expect(rest.get("a")![0]).toBeLessThanOrEqual(HW - 0.42 + 1e-3);
  });
});
