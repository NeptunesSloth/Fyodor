import { describe, expect, it } from "vitest";
import { angleDelta, ease, HOVER_LIFT, liftFor, SELECT_LIFT } from "./motion";

describe("3D card motion", () => {
  it("turns the short way round", () => {
    expect(angleDelta(0, Math.PI / 2)).toBeCloseTo(Math.PI / 2);
    expect(angleDelta(0, -Math.PI / 2)).toBeCloseTo(-Math.PI / 2);
    expect(angleDelta(Math.PI * 0.9, -Math.PI * 0.9)).toBeCloseTo(Math.PI * 0.2);
    expect(angleDelta(1, 1 + Math.PI * 4)).toBeCloseTo(0);
  });

  it("lifts hovered and selected cards, and cards mid-tap", () => {
    expect(liftFor({ hovered: false, selected: false, turning: 0 })).toBe(0);
    expect(liftFor({ hovered: true, selected: false, turning: 0 })).toBe(HOVER_LIFT);
    expect(liftFor({ hovered: false, selected: true, turning: 0 })).toBe(SELECT_LIFT);
    expect(liftFor({ hovered: true, selected: true, turning: 0 })).toBe(HOVER_LIFT);
    const tapping = liftFor({ hovered: false, selected: false, turning: Math.PI / 2 });
    expect(tapping).toBeGreaterThan(0.2);
    expect(tapping).toBeLessThanOrEqual(0.28);
  });

  it("snaps with reduced motion", () => {
    expect(ease(0.016, 14, true)).toBe(1);
    const k = ease(0.016, 14, false);
    expect(k).toBeGreaterThan(0);
    expect(k).toBeLessThan(1);
  });
});
