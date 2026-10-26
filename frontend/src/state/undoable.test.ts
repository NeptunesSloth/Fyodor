import { describe, expect, it } from "vitest";
import { undoableSummary } from "./gameStore";

describe("undoable action summaries", () => {
  it("names cards sent to a hidden or lost zone", () => {
    expect(undoableSummary({ type: "move", card_ids: ["a"], to: { zone: "graveyard" } })).toBe("1 card put into the graveyard");
    expect(undoableSummary({ type: "move", card_ids: ["a", "b"], to: { zone: "exile" } })).toBe("2 cards exiled");
    expect(undoableSummary({ type: "move", card_ids: ["a"], to: { zone: "library" } })).toBe("1 card put into a library");
    expect(undoableSummary({ type: "delete_card", card_ids: ["a"] })).toBe("1 card removed from the game");
    expect(undoableSummary({ type: "mill", count: 3 })).toBe("Milled 3 cards");
  });

  it("stays quiet for ordinary play", () => {
    expect(undoableSummary({ type: "move", card_ids: ["a"], to: { zone: "battlefield" } })).toBeNull();
    expect(undoableSummary({ type: "tap", card_ids: ["a"] })).toBeNull();
    expect(undoableSummary({ type: "pass_priority" })).toBeNull();
  });
});

import { recoveryHint } from "./gameStore";

describe("recovery hints for refused actions", () => {
  it("points at the way forward when the message doesn't", () => {
    expect(recoveryHint("Ornithopter can only be activated when you have priority (not while paying a cost)")).toMatch(/turn dial/);
    expect(recoveryHint("Not enough mana to pay {2}{U}")).toMatch(/mana/);
    expect(recoveryHint("That isn't a legal target")).toMatch(/highlighted targets/);
    expect(recoveryHint("Llanowar Elves has summoning sickness", "move")).toMatch(/hold Alt/);
  });

  it("stays quiet when the message already guides, or Alt can't help", () => {
    expect(recoveryHint("Tap your mana first: {2} isn't in your mana pool")).toBe("");
    expect(recoveryHint("Choose one of the offered options")).toBe("");
    expect(recoveryHint("Only the host can do that", "move")).toBe("");
    expect(recoveryHint("Llanowar Elves has summoning sickness", "tap")).toBe("");
    expect(recoveryHint("Something odd happened")).toBe("");
  });
});
