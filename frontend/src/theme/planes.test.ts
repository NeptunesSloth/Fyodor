import { describe, expect, it } from "vitest";
import { accentLow, contrast, PLANES, textFaint } from "./planes";

describe("plane tokens", () => {
  it("measures contrast like WCAG", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5);
  });

  it("keeps dark ink readable on every stop of every plane's brass buttons", () => {
    for (const p of PLANES) {
      for (const stop of [p.ui.accent2, p.ui.accent, accentLow(p)]) {
        expect(contrast(stop, p.ui.accentInk), `${p.id} ${stop}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("keeps primary text readable on every plane's background", () => {
    for (const p of PLANES) {
      expect(contrast(p.ui.text, p.ui.bg), p.id).toBeGreaterThanOrEqual(7);
      expect(contrast(p.ui.textDim, p.ui.bg), p.id).toBeGreaterThanOrEqual(4.5);
      expect(contrast(textFaint(p), p.ui.bg), p.id).toBeGreaterThanOrEqual(4.5);
    }
  });
});
