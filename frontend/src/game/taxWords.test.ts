import { describe, expect, it } from "vitest";
import { taxCasts, taxSentence } from "./seatIcons";

describe("commander tax in words", () => {
  it("counts the casts from the command zone ({2} each)", () => {
    expect([0, 2, 4, 6, 18].map(taxCasts)).toEqual([0, 1, 2, 3, 9]);
    expect(taxCasts(-2)).toBe(0);
    expect(taxCasts(3)).toBe(2); // (an odd tax set by hand: the coins round up)
  });

  it("says the tax to pay and how many casts it is", () => {
    expect(taxSentence(4)).toBe("Commander tax: +4 (cast 2 times from the command zone)");
    expect(taxSentence(2)).toBe("Commander tax: +2 (cast once from the command zone)");
    expect(taxSentence(0)).toBe("Commander tax: none yet (not cast from the command zone)");
  });
});
