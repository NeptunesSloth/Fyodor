import { describe, expect, it } from "vitest";
import { handCardWidth, handLayout, handRoom, minSliver, rowWidth, STRIP_AT, stripRange } from "./handLayout";

const SCREENS = [1920, 1366, 1024] as const;
const COUNTS = [1, 7, 20, 21, 30, 77, 200] as const;

describe("my hand's layout", () => {
  for (const three of [true, false]) {
    const style = three ? "arc" : "row";
    for (const screen of SCREENS) {
      const avail = handRoom(screen, three);
      const w = handCardWidth(screen, three);
      it(`${three ? "3D" : "2D"} at ${screen}px: a fan fits the width, a strip scrolls, every card keeps a sliver`, () => {
        for (const n of COUNTS) {
          const l = handLayout(n, avail, w, style);
          expect(l.cardW).toBe(w);
          expect(l.step).toBeGreaterThanOrEqual(Math.min(w, minSliver(w)) - 1e-9);
          expect(l.contentW).toBeCloseTo(rowWidth(n, w, l.step), 6);
          if (l.mode === "fan") {
            expect(l.contentW).toBeLessThanOrEqual(Math.max(avail, w) + 1e-6);
            expect(l.boxW).toBe(l.contentW);
          } else {
            expect(l.boxW).toBeCloseTo(avail, 6); // the strip is the room's width…
            expect(l.contentW).toBeGreaterThan(l.boxW); // …and scrolls
            expect(l.spread).toBe(0);
          }
        }
      });
    }
  }

  it("7 and 20 cards fan; 77 and 200 are a strip, on every screen and both tables", () => {
    for (const three of [true, false]) {
      for (const screen of SCREENS) {
        const lay = (n: number) => handLayout(n, handRoom(screen, three), handCardWidth(screen, three), three ? "arc" : "row");
        expect(lay(7).mode).toBe("fan");
        expect(lay(20).mode).toBe("fan");
        expect(lay(77).mode).toBe("strip");
        expect(lay(200).mode).toBe("strip");
      }
    }
  });

  it("past STRIP_AT cards it becomes a strip, unless the fan still shows wide slivers", () => {
    expect(handLayout(STRIP_AT, 1000, 160).mode).toBe("fan");
    expect(handLayout(STRIP_AT + 1, 1000, 160).mode).toBe("strip");
    // a very wide screen: 24 cards still show more than the strip's sliver each
    expect(handLayout(24, 4000, 160).mode).toBe("fan");
  });

  it("a hand too big for its slivers is a strip at any count (a narrow window)", () => {
    const l = handLayout(12, 300, 112);
    expect(l.mode).toBe("strip");
  });

  it("overlap grows with the count: the step never grows as cards are added", () => {
    let last = Infinity;
    for (let n = 2; n <= STRIP_AT; n++) {
      const l = handLayout(n, 1240, 161);
      expect(l.step).toBeLessThanOrEqual(last + 1e-9);
      last = l.step;
    }
  });

  it("a few cards sit as before: 3D overlaps them a little, 2D not at all", () => {
    expect(handLayout(3, 1240, 161, "arc").step).toBeCloseTo(161 * 0.88, 6);
    expect(handLayout(7, 1600, 104, "row").step).toBe(104);
  });

  it("the arc is gentle: at most 4.5° between cards, 34° across the hand", () => {
    for (let n = 2; n <= STRIP_AT; n++) {
      const l = handLayout(n, 1240, 161, "arc");
      expect(l.spread).toBeLessThanOrEqual(4.5);
      expect(l.spread * n).toBeLessThanOrEqual(34 + 1e-9);
    }
    expect(handLayout(7, 1240, 104, "row").spread).toBe(0);
  });

  it("an empty hand and a single card", () => {
    expect(handLayout(0, 1240, 161)).toMatchObject({ mode: "fan", contentW: 0 });
    expect(handLayout(1, 1240, 161)).toMatchObject({ mode: "fan", contentW: 161 });
    expect(handLayout(1, 50, 161).mode).toBe("fan"); // never a strip of one
  });

  it("the strip's range reads 1–N of 77 and ends on the last card", () => {
    const l = handLayout(77, 1240, 161);
    const start = stripRange(77, l, 0);
    expect(start.first).toBe(1);
    expect(start.last).toBeGreaterThan(10);
    const end = stripRange(77, l, l.contentW - l.boxW);
    expect(end.last).toBe(77);
    expect(end.first).toBeGreaterThan(50);
  });
});
