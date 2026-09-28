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

  it("keeps relative offsets when moving a group within a battlefield", () => {
    const current = { a: { x: 100, y: 100 }, b: { x: 150, y: 120 } };
    expect(groupPositions(["a", "b"], "a", { x: 300, y: 50 }, current, true)).toEqual({ a: [300, 50], b: [350, 70] });
  });

  it("fans cards arriving from another zone", () => {
    expect(groupPositions(["a", "b"], "a", { x: 10, y: 10 }, {}, false)).toEqual({ a: [10, 10], b: [28, 28] });
  });
});
