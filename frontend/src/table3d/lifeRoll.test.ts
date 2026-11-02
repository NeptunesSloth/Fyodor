import { describe, expect, it } from "vitest";
import { lifeRollAt } from "./seatProps";

describe("the 3D heart's life roll", () => {
  const roll = { from: 40, to: 35, start: 1000, dur: 400 };
  it("starts at the old total, eases toward the new one and lands exactly on it", () => {
    expect(lifeRollAt(roll, 1000)).toBe(40);
    const mid = lifeRollAt(roll, 1200);
    expect(mid).toBeLessThan(40);
    expect(mid).toBeGreaterThan(35);
    expect(lifeRollAt(roll, 1400)).toBe(35);
    expect(lifeRollAt(roll, 9999)).toBe(35);
  });
  it("counts up as well, and a zero duration (instant) shows the new total at once", () => {
    expect(lifeRollAt({ from: 10, to: 13, start: 0, dur: 300 }, 150)).toBeGreaterThanOrEqual(11);
    expect(lifeRollAt({ from: 10, to: 13, start: 0, dur: 0 }, 0)).toBe(13);
  });
  it("eases out: most of the change shows early", () => {
    expect(lifeRollAt({ from: 0, to: 100, start: 0, dur: 1000 }, 300)).toBeGreaterThan(50);
  });
});
