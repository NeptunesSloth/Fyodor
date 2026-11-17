import { describe, expect, it } from "vitest";
import { landsClearance } from "./landsClear";

describe("my land row's clearance (second pass nov 17: prompts and the draw notice lay over the lands)", () => {
  it("is the space from the window's bottom to just above my highest land", () => {
    expect(landsClearance([772, 790, 780], 1080, 150)).toBe(1080 - 772 + 8);
  });
  it("doesn't apply with no lands, lands already clear of the docked plaques, or lands far up the mat", () => {
    expect(landsClearance([], 1080, 150)).toBeNull();
    expect(landsClearance([950], 1080, 150)).toBeNull(); // (under the plaques' own spot already)
    expect(landsClearance([300], 1080, 150)).toBeNull(); // (free placement in the middle: every prompt would leave the screen)
  });
});
