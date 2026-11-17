import { describe, expect, it } from "vitest";
import type { GameView } from "../../types/game";
import { paying } from "./RulesHud";

// -- playtest (nov 16) -- the prompts and the zone browser covered the land row while a cost was paid
const at = (decision: unknown, paused = false) => ({ rules: { paused, decision } }) as unknown as GameView;

describe("paying a cost keeps the lands in view", () => {
  it("is on for my payment plaques and for a question that says to tap mana first", () => {
    expect(paying(at({ player: "p1", display: { kind: "tap_mana" }, prompt: "Cast cost" }), "p1")).toBe(true);
    expect(paying(at({ player: "p1", display: { kind: "payment" }, prompt: "" }), "p1")).toBe(true);
    expect(paying(at({ player: "p1", kind: "confirm", prompt: "Rings of Brighthearth: pay {2}? (tap your mana first)" }), "p1")).toBe(true);
  });
  it("is off for anyone else's payment, other questions, no decision and paused automation", () => {
    expect(paying(at({ player: "p2", display: { kind: "tap_mana" }, prompt: "" }), "p1")).toBe(false);
    expect(paying(at({ player: "p1", kind: "choose_one", prompt: "Move Teysa Karlov to the command zone?" }), "p1")).toBe(false);
    expect(paying(at(null), "p1")).toBe(false);
    expect(paying(at({ player: "p1", display: { kind: "tap_mana" }, prompt: "" }, true), "p1")).toBe(false);
    expect(paying(null, "p1")).toBe(false);
  });
});
