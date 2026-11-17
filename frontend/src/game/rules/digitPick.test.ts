import { describe, expect, it } from "vitest";
import { digitPick } from "./RulesHud";

describe("digits pick a choice's list (playtest nov 17: digits 2-6 moved the camera instead)", () => {
  it("1-9 are the first nine options and 0 the tenth; other keys aren't picks", () => {
    expect(digitPick("1")).toBe(0);
    expect(digitPick("6")).toBe(5);
    expect(digitPick("0")).toBe(9);
    for (const k of ["a", "Enter", "F1", "12", ""]) expect(digitPick(k)).toBeNull();
  });
});
