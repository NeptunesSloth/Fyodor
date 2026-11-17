import { describe, expect, it } from "vitest";
import { STACK_FAN, stackLift } from "./TableScene";

describe("the 3D stack of a long chain (playtest nov 17: 95 triggers rose as one ramp over both battlefields)", () => {
  it("stays low: the piled cards share a thin pile, only the last few fan out", () => {
    const n = 95;
    const piled = n - STACK_FAN;
    const heights = Array.from({ length: n }, (_, i) => stackLift(i, piled));
    expect(Math.max(...heights)).toBeLessThan(0.4); // (it was 0.3 + 94 × 0.02 = 2.18 over the base)
    for (let i = 1; i < n; i++) expect(heights[i]!).toBeGreaterThan(heights[i - 1]!); // (each card over the last: no z-fighting)
  });

  it("a short stack fans as before", () => {
    expect([0, 1, 2].map((i) => stackLift(i, 0))).toEqual([0, 0.02, 0.04]);
  });
});
