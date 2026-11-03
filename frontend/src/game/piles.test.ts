import { describe, expect, it } from "vitest";
import { pileTops, type PileFacts } from "./piles";
import { tidyLandMoves } from "./tidy";

const c = (id: string, name: string, x: number, y = 470, extra: Partial<PileFacts> = {}): PileFacts =>
  ({ id, name, x, y, tapped: false, land: true, ...extra });

describe("pileTops", () => {
  it("counts identical lands sitting in an overlapping row; the right-most card carries the count", () => {
    const tops = pileTops([c("i1", "Island", 16), c("i2", "Island", 32), c("i3", "Island", 48), c("p1", "Plains", 200)]);
    expect([...tops]).toEqual([["i3", 3]]);
  });
  it("splits by tapped state, by gaps and by rows, and ignores non-lands", () => {
    const tops = pileTops([
      c("a", "Forest", 0), c("b", "Forest", 16), c("t", "Forest", 32, 470, { tapped: true }),
      c("far", "Forest", 300), c("up", "Forest", 316, 300),
      c("x", "Sol Ring", 0, 100, { land: false }), c("y", "Sol Ring", 10, 100, { land: false }),
    ]);
    expect([...tops]).toEqual([["b", 2]]);
  });
  it("labels exactly what Tidy my lands builds", () => {
    const lands = ["Island", "Island", "Island", "Island", "Command Tower"].map((n, i) => ({ id: `l${i}`, name: n, typeLine: n === "Island" ? "Basic Land — Island" : "Land" }));
    const placed = tidyLandMoves(lands).map(([id, x, y]) => c(id, lands.find((l) => l.id === id)!.name, x, y));
    expect([...pileTops(placed)]).toEqual([["l3", 4]]);
  });
});
