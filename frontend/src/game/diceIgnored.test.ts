import { describe, expect, it } from "vitest";
import { keptRolls, rollSummary } from "./dice";

describe("rolls the rules ignored (Barbarian Class: one more die, ignore the lowest)", () => {
  it("counts only the kept rolls and says which were ignored", () => {
    expect(keptRolls({ results: [17, 7], ignored: [1] })).toEqual([17]);
    expect(rollSummary({ results: [17, 7], coin: false, ignored: [1] })).toBe("17 (ignored 7)");
    expect(rollSummary({ results: [3, 1, 6], coin: false, ignored: [1] })).toBe("3 + 6 = 9 (ignored 1)");
  });
  it("leaves an ordinary roll as it was", () => {
    expect(rollSummary({ results: [3, 6], coin: false })).toBe("3 + 6 = 9");
    expect(rollSummary({ results: [14], coin: false, ignored: [] })).toBe("14");
  });
});
