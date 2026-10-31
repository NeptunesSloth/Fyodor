import { describe, expect, it } from "vitest";
import { battlefieldCardWidth, groupPositions, toPixels } from "./geometry";

describe("battlefield geometry", () => {
  it("mirrors opponent battlefields vertically", () => {
    expect(toPixels(500, 0, 1000, 600, 100, false)).toEqual([500, 0]);
    expect(toPixels(500, 0, 1000, 600, 100, true)).toEqual([500, 500]);
  });

  it("scales card width to fit both dimensions", () => {
    expect(battlefieldCardWidth(1000, 1000)).toBe(84);
    expect(battlefieldCardWidth(2000, 300)).toBeLessThan(84);
    expect(battlefieldCardWidth(100, 50)).toBe(36);
  });

  it("draws a small mat's cards readable, never past the mat", () => {
    // three opponents across 1920px: ~54px by share, drawn at the readable width
    expect(battlefieldCardWidth(640, 250)).toBeLessThan(56);
    expect(battlefieldCardWidth(640, 250, true)).toBe(74);
    // at most 1.45x the share
    expect(battlefieldCardWidth(500, 250, true)).toBeCloseTo((500 / 1000) * 84 * 1.45);
    // never taller than the mat, never smaller than without the boost
    expect(battlefieldCardWidth(640, 90, true)).toBeLessThanOrEqual((90 - 8) / (88 / 63) + 1e-9);
    expect(battlefieldCardWidth(640, 40, true)).toBe(battlefieldCardWidth(640, 40));
    // big mats are unchanged
    expect(battlefieldCardWidth(1800, 500, true)).toBe(battlefieldCardWidth(1800, 500));
  });

  it("keeps relative offsets when moving a group within a battlefield", () => {
    const current = { a: { x: 100, y: 100 }, b: { x: 150, y: 120 } };
    expect(groupPositions(["a", "b"], "a", { x: 300, y: 50 }, current, true)).toEqual({ a: [300, 50], b: [350, 70] });
  });

  it("fans cards arriving from another zone", () => {
    expect(groupPositions(["a", "b"], "a", { x: 10, y: 10 }, {}, false)).toEqual({ a: [10, 10], b: [28, 28] });
  });
});
