import { describe, expect, it } from "vitest";
import type { DecisionView } from "../../types/game";
import { divideRows, evenFill, firstFill, lethalFill } from "./DivideRows";

const trample = {
  id: "d", player: "p1", kind: "divide", prompt: "Divide Mossborn Hydra's 256 combat damage", source_id: null,
  options: [{ id: "b1", label: "Elturel Survivors", card_id: "b1" }, { id: "b2", label: "Wall", card_id: "b2" }, { id: "p2", label: "Bob", card_id: null }],
  display: { kind: "divide", total: 256, what: "damage", least: 0, lethal: [4, 3], need: [4, 3], free: 2, deathtouch: false,
    stats: { b1: { pt: "4/5", keywords: [], damage: 1 }, b2: { pt: "0/3", keywords: [], damage: 0 } } },
} as unknown as DecisionView;

describe("divide prompt rows (playtest nov 18)", () => {
  it("knows each blocker's lethal damage and the trampler's row, which takes the rest", () => {
    const { rows, total, combat } = divideRows(trample);
    expect(combat).toBe(true);
    expect(rows.map((r) => [r.id, r.need, r.free])).toEqual([["b1", 4, false], ["b2", 3, false], ["p2", null, true]]);
    expect(lethalFill(rows, total, 0)).toEqual([4, 3, 249]);
    expect(firstFill(rows, total, 0)).toEqual([256, 0, 0]);
  });

  it("without trample the rest stays on the first blocker; short damage covers blockers in order", () => {
    const d = { ...trample, options: trample.options!.slice(0, 2), display: { ...trample.display, lethal: [], need: [4, 3], free: null, total: 5 } } as unknown as DecisionView;
    const { rows } = divideRows(d);
    expect(lethalFill(rows, 9, 0)).toEqual([6, 3]);
    expect(lethalFill(rows, 5, 0)).toEqual([4, 1]);
  });

  it("a spell's division: at least 1 each, evenly or all to the first", () => {
    const d = { ...trample, display: { kind: "divide", total: 7, what: "damage" } } as unknown as DecisionView;
    const { rows, total, least, combat } = divideRows(d);
    expect([combat, least]).toEqual([false, 1]);
    expect(evenFill(rows, total, least)).toEqual([3, 2, 2]);
    expect(firstFill(rows, total, least)).toEqual([5, 1, 1]);
  });
});
