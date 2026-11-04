import { describe, expect, it } from "vitest";
import { fitName, NAME_ASC, NAME_CONDENSE, NAME_DESC, NAME_MIN_SCREEN, tileLook, tileMetrics, type TileLook } from "./tiles";

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
const width = (t: string, px: number) => t.length * px * 0.55 * NAME_CONDENSE;

describe("a tile's name", () => {
  it("stays on one line at full size when it fits", () => {
    const f = fitName(fakeContext(), "Sol Ring", 170, 200, font);
    expect(f.lines).toEqual(["Sol Ring"]);
    expect(f.px).toBe(23);
  });

  it("shrinks a little before it breaks", () => {
    const f = fitName(fakeContext(), "Doubling Season", 170, 200, font);
    expect(f.lines).toEqual(["Doubling Season"]);
    expect(f.px).toBeLessThan(23);
    expect(f.px).toBeGreaterThanOrEqual(18);
  });

  it("goes onto two lines, whole, rather than being cut short", () => {
    for (const name of ["Siege-Gang Commander", "Atraxa, Praetors' Voice", "Elesh Norn, Grand Cenobite"]) {
      const f = fitName(fakeContext(), name, 170, 200, font);
      expect(f.lines.join(" "), name).toBe(name);
      expect(f.lines, name).toHaveLength(2);
    }
  });

  it("draws two lines inside the bar: the band holds both, nothing past its edges or the frame's ring", () => {
    const W = 320;
    const maxW = W * 0.9;
    for (const look of [{ stretch: 1, min: 0.05 }, { stretch: 2.2, min: 0.05 }, { stretch: 1.6, min: 0.045 }] as TileLook[]) {
      const f = fitName(fakeContext(), "Elesh Norn, Grand Cenobite", maxW, W, font, look);
      const { bar } = tileMetrics(W, look);
      const ring = Math.max(3, W * 0.03);
      const em = f.px * look.stretch;
      expect(f.lines).toHaveLength(2);
      expect(bar - ring).toBeGreaterThanOrEqual(2 * (NAME_ASC + NAME_DESC) * em);
      f.lines.forEach((line, i) => {
        expect(f.base[i]! - NAME_ASC * em, `line ${i} top`).toBeGreaterThanOrEqual(ring);
        expect(f.base[i]! + NAME_DESC * em, `line ${i} foot`).toBeLessThanOrEqual(bar);
        expect(width(line, f.px)).toBeLessThanOrEqual(maxW);
      });
      // the second line starts below the first one's descenders
      expect(f.base[1]! - NAME_ASC * em).toBeGreaterThanOrEqual(f.base[0]! + NAME_DESC * em);
    }
  });

  it("keeps a one-line name inside the bar too", () => {
    const W = 320;
    for (const look of [{ stretch: 1, min: 0.05 }, { stretch: 2.2, min: 0.1 }] as TileLook[]) {
      const f = fitName(fakeContext(), "Forest", W * 0.9, W, font, look);
      const em = f.px * look.stretch;
      expect(f.base[0]! - NAME_ASC * em).toBeGreaterThanOrEqual(Math.max(3, W * 0.03));
      expect(f.base[0]! + NAME_DESC * em).toBeLessThanOrEqual(tileMetrics(W, look).bar);
    }
  });

  it("on a small tile, one shorter line at a readable size rather than tiny text", () => {
    const W = 320;
    const screenW = 93; // a tile at 1280 × 640
    const look = tileLook(screenW, 0.46);
    for (const name of ["Doubling Season", "Siege-Gang Commander", "Elesh Norn, Grand Cenobite"]) {
      const f = fitName(fakeContext(), name, W * 0.9, W, font, look);
      expect(f.lines, name).toHaveLength(1);
      // as seen: the em is at least the minimum
      expect((f.px / W) * screenW, name).toBeGreaterThanOrEqual(NAME_MIN_SCREEN);
      expect(width(f.lines[0]!, f.px), name).toBeLessThanOrEqual(W * 0.9);
    }
    expect(fitName(fakeContext(), "Elesh Norn, Grand Cenobite", W * 0.9, W, font, look).lines[0]!.endsWith("…")).toBe(true);
  });

  it("cuts short only a name that can't fit even on two lines", () => {
    const f = fitName(fakeContext(), "Supercalifragilisticexpialidociousnesses", 170, 200, font);
    expect(f.lines).toHaveLength(1);
    expect(f.lines[0]!.endsWith("…")).toBe(true);
  });

  it("is drawn tall for a table seen at a slant, and never smaller than the minimum on screen", () => {
    expect(tileLook(140, 0.46).stretch).toBe(2.2); // the duel's seat view
    expect(tileLook(140, 0.58).stretch).toBe(1.8); // a portrait screen's (steeper)
    expect(tileLook(140, 0.93).stretch).toBe(1); // four players' (nearly from above)
    expect(tileLook(93, 0.46).min).toBeGreaterThan(tileLook(140, 0.46).min);
    expect(tileLook(10, 0.46).min).toBeLessThanOrEqual(0.115); // capped at the full size
    // a large tile (zoomed in, few cards): two whole lines rather than one cut short
    const big = fitName(fakeContext(), "Elesh Norn, Grand Cenobite", 288, 320, font, tileLook(260, 0.46));
    expect(big.lines.join(" ")).toBe("Elesh Norn, Grand Cenobite");
  });
});
