import { describe, expect, it } from "vitest";
import { stepHeads, type HistoryItem } from "./HistoryDialog";

const item = (position: number, turn: number | null, phase: string | null): HistoryItem =>
  ({ position, seq: position, type: "pass_priority", actor: null, log: [], undone: false, turn, phase });

describe("stepHeads (undo back to here)", () => {
  it("heads each turn and step group at its newest row and remembers where the group began", () => {
    // newest first, as the dialog lists them
    const items = [item(5, 2, "combat_damage"), item(4, 2, "declare_attackers"), item(3, 2, "declare_attackers"), item(2, null, null), item(1, 1, "main1")];
    const heads = stepHeads(items);
    expect([...heads.keys()].sort()).toEqual([2, 4, 5]);
    expect(heads.get(4)).toEqual({ label: "Turn 2 · Attackers", first: 3 });
    expect(heads.get(5)!.first).toBe(5);
    expect(heads.get(2)!.first).toBe(1); // a row that logged nothing joins the group before it
  });

  it("is empty for an empty history", () => {
    expect(stepHeads([]).size).toBe(0);
  });
});
