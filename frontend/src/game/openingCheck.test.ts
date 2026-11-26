import { describe, expect, it } from "vitest";
import { landColors, openingCheck } from "./openingCheck";

describe("opening hand check", () => {
  it("counts lands, the curve and the colours the lands make", () => {
    const hand = [
      { type_line: "Basic Land — Forest", oracle_text: "({T}: Add {G}.)" },
      { type_line: "Land", oracle_text: "{T}: Add {C}.\n{T}: Add {R} or {W}." },
      { type_line: "Creature — Elf Druid", cmc: 1, mana_cost: "{G}" },
      { type_line: "Instant", cmc: 1, mana_cost: "{R}" },
      { type_line: "Sorcery", cmc: 3, mana_cost: "{1}{U}{U}" },
      { type_line: "Creature — Dragon", cmc: 9, mana_cost: "{7}{R}{R}" },
    ];
    const c = openingCheck(hand);
    expect(c.lands).toBe(2);
    expect(c.curve).toEqual([0, 2, 0, 1, 0, 0, 0, 1]);
    expect(c.colors).toEqual([{ color: "U", ok: false }, { color: "R", ok: true }, { color: "G", ok: true }]);
  });

  it("reads any colour and basic land types", () => {
    expect(landColors({ type_line: "Land", oracle_text: "{T}: Add one mana of any color in your commander's color identity." })).toHaveLength(5);
    expect(landColors({ type_line: "Land — Forest Island" }).sort()).toEqual(["G", "U"]);
  });
});
