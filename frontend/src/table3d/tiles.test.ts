import { describe, expect, it } from "vitest";
import { fitName, NAME_ASC, NAME_DESC, NAME_MIN_SCREEN, nameScreenEm, tileLook, tileMetrics, type TileLook } from "./tiles";

/** A canvas context's text measuring, roughly: each character 0.55 of the font size. */
function fakeContext(): CanvasRenderingContext2D {
  const g = {
    font: "10px x",
    measureText(t: string) {
      const px = Number(/(\d+)px/.exec(g.font)?.[1] ?? 10);
      return { width: t.length * px * 0.55 } as TextMetrics;
    },
  };
  return g as unknown as CanvasRenderingContext2D;
}
const font = (px: number) => `650 ${px}px Inter`;
const width = (t: string, px: number) => t.length * px * 0.55;
const NAMES = ["Sol Ring", "Goblin Chieftain", "Doubling Season", "Siege-Gang Commander", "Elesh Norn, Grand Cenobite"];

describe("a tile's name", () => {
  it("is one line at the look's size, whatever its length: a long one is cut short, never shrunk", () => {
    const W = 320;
    const look: TileLook = { stretch: 2.2, em: 0.11 };
    for (const name of NAMES) {
      const f = fitName(fakeContext(), name, W * 0.9, W, font, look);
      expect(f.px, name).toBe(Math.round(0.11 * W));
      expect(width(f.line, f.px), name).toBeLessThanOrEqual(W * 0.9);
      if (width(name, f.px) <= W * 0.9) expect(f.line).toBe(name);
      else expect(f.line.endsWith("…"), name).toBe(true);
    }
  });

  it("lies inside the bar: under the frame's ring, above the bar's foot", () => {
    const W = 320;
    for (const look of [{ stretch: 1, em: 0.1 }, { stretch: 2.2, em: 0.11 }, { stretch: 1.6, em: 0.08 }] as TileLook[]) {
      const f = fitName(fakeContext(), "Kalonian Hydra", W * 0.9, W, font, look);
      const em = f.px * look.stretch;
      expect(f.base - NAME_ASC * em).toBeGreaterThanOrEqual(Math.max(3, W * 0.03));
      expect(f.base + NAME_DESC * em).toBeLessThanOrEqual(tileMetrics(W, look).bar);
    }
  });

  it("is the same size on screen on every tile of a seat view, large tiles and small", () => {
    const squash = 0.46; // the duel's seat view
    for (const ppu of [45, 60, 100]) {
      const screenEm = nameScreenEm(ppu);
      for (const tileW of [0.9, 1.2, 1.55, 1.9]) {
        const screenW = tileW * ppu;
        const look = tileLook(screenW, squash, screenEm);
        const f = fitName(fakeContext(), "Goblin King", 288, 320, font, look);
        // as seen: within a pixel of the view's size (rounded to steps), unless the tile is too small for its band
        if (look.em * screenW >= screenEm - 1) expect(Math.abs((f.px / 320) * screenW - screenEm)).toBeLessThanOrEqual(1);
      }
    }
  });

  it("never smaller than the minimum on screen, larger on a larger screen", () => {
    expect(nameScreenEm(40)).toBe(NAME_MIN_SCREEN);
    expect(nameScreenEm(100)).toBeGreaterThan(NAME_MIN_SCREEN);
    expect(nameScreenEm(1000)).toBeLessThanOrEqual(14);
  });

  it("is drawn tall for a table seen at a slant; the band stays a modest share of the tile", () => {
    expect(tileLook(140, 0.46).stretch).toBe(2.2); // the duel's seat view
    expect(tileLook(140, 0.58).stretch).toBe(1.8); // a portrait screen's (steeper)
    expect(tileLook(140, 0.93).stretch).toBe(1); // four players' (nearly from above)
    // a tiny tile: its band capped (its name smaller than the others')
    const tiny = tileLook(40, 0.46, 10);
    expect(tileMetrics(320, tiny).bar).toBeLessThanOrEqual(320 * 0.34);
  });
});
