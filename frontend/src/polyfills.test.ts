import { describe, expect, it } from "vitest";
import { cornerRadii } from "./polyfills";

describe("roundRect for old browsers", () => {
  it("reads the one to four radius forms", () => {
    expect(cornerRadii(100, 100, 5)).toEqual([5, 5, 5, 5]);
    expect(cornerRadii(100, 100, [5, 10])).toEqual([5, 10, 5, 10]);
    expect(cornerRadii(100, 100, [1, 2, 3])).toEqual([1, 2, 3, 2]);
    expect(cornerRadii(100, 100, [1, 2, 3, 4])).toEqual([1, 2, 3, 4]);
    expect(cornerRadii(100, 100, { x: 7, y: 7 })).toEqual([7, 7, 7, 7]);
  });
  it("keeps the corners inside a small box", () => {
    expect(cornerRadii(10, 40, 20)).toEqual([5, 5, 5, 5]);
  });
});
