import { describe, expect, it } from "vitest";
import type { DecisionView } from "../../types/game";
import { combatStats, numberedNames, statLine } from "./blockerLabels";

const opt = (id: string, label: string) => ({ id, label, card_id: id.slice(2) });

describe("blockers prompt labels (playtest nov 17)", () => {
  it("numbers two creatures of one name on the same side, in the server's order, and leaves single names alone", () => {
    const names = numberedNames([opt("b:1", "Doombot"), opt("b:2", "Doctor Doom"), opt("b:3", "Doombot"),
      opt("a:4", "Hare Apparent"), opt("a:5", "Hare Apparent"), opt("a:6", "Rabbit"), opt("a:7", "Doombot")]);
    expect(names).toEqual({ "b:1": "Doombot #1", "b:2": "Doctor Doom", "b:3": "Doombot #2", "a:4": "Hare Apparent #1",
      "a:5": "Hare Apparent #2", "a:6": "Rabbit", "a:7": "Doombot" });
  });

  it("reads the server's stats and says them in a line", () => {
    const d = { display: { kind: "blockers", stats: { "4": { pt: "2/2", keywords: ["flying"] }, "1": { pt: "3/3", keywords: [] } } } } as unknown as DecisionView;
    const stats = combatStats(d);
    expect(statLine(stats["4"])).toBe("2/2 · flying");
    expect(statLine(stats["1"])).toBe("3/3");
    expect(statLine(undefined)).toBe("");
    expect(combatStats({ display: { kind: "payment" } } as unknown as DecisionView)).toEqual({});
  });
});
