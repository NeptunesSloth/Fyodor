import { describe, expect, it } from "vitest";
import { flicker, hash1, hearth, noise1, sway } from "./flicker";

const times = Array.from({ length: 4000 }, (_, i) => i * 0.013);

describe("the room's living light", () => {
  it("noise stays in [0, 1] and moves smoothly", () => {
    for (const t of times) {
      const n = noise1(t * 3.7);
      expect(n).toBeGreaterThanOrEqual(0);
      expect(n).toBeLessThanOrEqual(1);
      expect(Math.abs(noise1(t * 3.7 + 0.001) - n)).toBeLessThan(0.01);
    }
    expect(hash1(3)).not.toBe(hash1(4));
  });

  it("a flame flickers about 1, never past its amount, and neighbours don't flicker in step", () => {
    const a = times.map((t) => flicker(t, 0.3, 0.25));
    for (const v of a) {
      expect(v).toBeGreaterThanOrEqual(0.75 - 1e-9);
      expect(v).toBeLessThanOrEqual(1.25 + 1e-9);
    }
    // it really moves (not a constant), and is about 1 on average
    expect(Math.max(...a) - Math.min(...a)).toBeGreaterThan(0.15);
    expect(Math.abs(a.reduce((s, v) => s + v, 0) / a.length - 1)).toBeLessThan(0.08);
    const b = times.map((t) => flicker(t, 7.9, 0.25));
    const same = a.filter((v, i) => Math.abs(v - b[i]!) < 0.01).length;
    expect(same / a.length).toBeLessThan(0.2);
    // amount 0: steady
    expect(flicker(12.3, 1, 0)).toBe(1);
  });

  it("a flame's flutter is subtle frame to frame (no strobing at 60 fps)", () => {
    for (const t of times) expect(Math.abs(flicker(t + 1 / 60, 2, 0.25) - flicker(t, 2, 0.25))).toBeLessThan(0.12);
  });

  it("a hearth breathes within its amount", () => {
    for (const t of times) {
      const v = hearth(t, 0.4, 0.3);
      expect(v).toBeGreaterThanOrEqual(0.7 - 1e-9);
      expect(v).toBeLessThanOrEqual(1.3 + 1e-9);
    }
  });

  it("a hanging lantern sways gently: within its amplitude, smoothly", () => {
    let prev = sway(0, 1.2, 0.055);
    for (const t of times) {
      const [ax, az] = sway(t, 1.2, 0.055);
      expect(Math.abs(ax)).toBeLessThanOrEqual(0.055 + 1e-9);
      expect(Math.abs(az)).toBeLessThanOrEqual(0.055 * 0.6 + 1e-9);
      expect(Math.abs(ax - prev[0])).toBeLessThan(0.002);
      prev = [ax, az];
    }
  });
});
