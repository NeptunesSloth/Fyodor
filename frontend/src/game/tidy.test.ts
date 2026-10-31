import { describe, expect, it } from "vitest";
import { tidyLandMoves, tidyable, type LandFacts } from "./tidy";

const land = (id: string, name: string, typeLine = `Basic Land — ${name}`): LandFacts => ({ id, name, typeLine });

describe("tidyLandMoves", () => {
  it("piles identical lands, basics first in WUBRG order, then the rest by name", () => {
    const moves = tidyLandMoves([
      land("t", "Command Tower", "Land"), land("f1", "Forest"), land("i1", "Island"), land("f2", "Forest"),
      land("i2", "Island"), land("p", "Plains"), land("a", "Arcane Lighthouse", "Land"),
    ]);
    const order = moves.map((m) => m[0]);
    expect(order).toEqual(["p", "i1", "i2", "f1", "f2", "a", "t"]);
    const at: Record<string, [number, number]> = Object.fromEntries(moves.map(([id, x, y]) => [id, [x, y]]));
    expect(at.i2![0] - at.i1![0]).toBe(16); // a pile you can count
    expect(new Set(moves.map((m) => m[2])).size).toBe(1); // one row near my edge
    expect(at.p![1]).toBeGreaterThan(400);
  });
  it("leaves creature lands and non-lands alone", () => {
    expect(tidyable("Land Creature — Forest Dryad")).toBe(false);
    expect(tidyable("Artifact")).toBe(false);
    expect(tidyLandMoves([land("d", "Dryad Arbor", "Land Creature — Forest Dryad")])).toEqual([]);
  });
  it("wraps to another row instead of running off the mat, and tightens big piles", () => {
    const many = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes", "A", "B", "C"].flatMap((n, k) =>
      [0, 1, 2, 3].map((i) => land(`${k}-${i}`, n, n.length === 1 ? "Land" : `Basic Land — ${n}`)));
    const moves = tidyLandMoves(many);
    expect(Math.max(...moves.map((m) => m[1]))).toBeLessThan(1000);
    expect(new Set(moves.map((m) => m[2])).size).toBeGreaterThan(1);
    const twelve = tidyLandMoves(Array.from({ length: 12 }, (_, i) => land(`i${i}`, "Island")));
    expect(twelve[11]![1] - twelve[0]![1]).toBeLessThanOrEqual(96);
  });
});
