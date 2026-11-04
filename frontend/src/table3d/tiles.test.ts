import { describe, expect, it } from "vitest";
import { fitName } from "./tiles";

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

describe("a tile's name", () => {
  it("stays on one line at full size when it fits", () => {
    const f = fitName(fakeContext(), "Sol Ring", 170, 200, font);
    expect(f).toEqual({ lines: ["Sol Ring"], px: 29 });
  });

  it("shrinks a little before it breaks", () => {
    const f = fitName(fakeContext(), "Goblin Guide", 170, 200, font);
    expect(f.lines).toEqual(["Goblin Guide"]);
    expect(f.px).toBeLessThan(29);
    expect(f.px).toBeGreaterThanOrEqual(20);
  });

  it("goes onto two lines, whole, rather than being cut short", () => {
    for (const name of ["Doubling Season", "Winding Constrictor", "Kalonian Hydra", "Siege-Gang Commander", "Atraxa, Praetors' Voice"]) {
      const f = fitName(fakeContext(), name, 170, 200, font);
      expect(f.lines.join(" "), name).toBe(name);
      expect(f.lines.length).toBeLessThanOrEqual(2);
    }
  });

  it("cuts short only a name that can't fit even on two lines", () => {
    const f = fitName(fakeContext(), "Supercalifragilisticexpialidocious", 170, 200, font);
    expect(f.lines).toHaveLength(1);
    expect(f.lines[0]!.endsWith("…")).toBe(true);
  });
});
