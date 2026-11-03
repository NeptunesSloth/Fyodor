import { describe, expect, it } from "vitest";
import { bagAnchor, clearOf } from "./bagAnchor";

const screen = { width: 1440, height: 900 };

describe("where a drawer's bag chits stack", () => {
  it("under an opponent's plaque at the top of the table", () => {
    expect(bagAnchor({ left: 12, top: 80, right: 170, bottom: 130 }, screen)).toEqual({ left: 12, top: 138 });
  });
  it("beside your own plaque in the rail", () => {
    expect(bagAnchor({ left: 10, top: 460, right: 180, bottom: 560 }, screen)).toEqual({ left: 190, top: 460 });
  });
  it("always on screen", () => {
    const at = bagAnchor({ left: 1400, top: 20, right: 1500, bottom: 30 }, screen);
    expect(at.left).toBeLessThanOrEqual(1440 - 260 - 8);
    expect(at.top).toBeGreaterThanOrEqual(52);
  });
});

describe("a drawer's chits keep clear of what is already showing", () => {
  it("move down past a dice result line they would cover", () => {
    expect(clearOf({ left: 12, top: 150 }, 230, 90, [{ left: 215, top: 189, right: 415, bottom: 216 }])).toEqual({ left: 12, top: 222 });
  });
  it("stay put when nothing is in the way, and pass several obstacles in turn", () => {
    expect(clearOf({ left: 12, top: 150 }, 230, 40, [{ left: 600, top: 150, right: 700, bottom: 200 }])).toEqual({ left: 12, top: 150 });
    const taken = [{ left: 0, top: 160, right: 100, bottom: 180 }, { left: 0, top: 200, right: 100, bottom: 230 }];
    expect(clearOf({ left: 12, top: 150 }, 230, 40, taken)).toEqual({ left: 12, top: 236 });
  });
});
