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

describe("the tap-mana plaque's title (playtest nov 16: \"Cast cost … for the planar die\")", () => {
  it("names a roll, an activation or a cast", async () => {
    const { payTitle } = await import("./RulesHud");
    expect(payTitle("the planar die")).toBe("Roll cost");
    expect(payTitle("Basalt Monolith's ability")).toBe("Activation cost");
    expect(payTitle("Lightning Bolt")).toBe("Cast cost");
  });
});

describe("the X prompt's guide (playtest nov 16: it started at 0 with no max)", () => {
  it("counts untapped lands and floating mana, and the X they leave after the rest of the cost", async () => {
    const { xEstimate } = await import("./RulesHud");
    const { useCardCache } = await import("../../state/cardCache");
    useCardCache.setState({ cards: { ...useCardCache.getState().cards,
      plains: { id: "plains", name: "Plains", type_line: "Basic Land — Plains", faces: [] },
      secure: { id: "secure", name: "Secure the Wastes", type_line: "Instant", mana_cost: "{X}{W}", faces: [] },
      fireball: { id: "fireball", name: "Fireball", type_line: "Sorcery", mana_cost: "{X}{X}{R}", faces: [] } } as never });
    const lands = Object.fromEntries(Array.from({ length: 6 }, (_, i) => [`l${i}`, { id: `l${i}`, zone: "p1:battlefield", card_id: "plains", tapped: i === 0 }]));
    const v = {
      zones: { "p1:battlefield": Object.keys(lands) }, players: [{ id: "p1", mana: { W: 2 } }], rules: { hints: {} },
      cards: { ...lands, s: { id: "s", zone: "p1:hand", card_id: "secure" }, f: { id: "f", zone: "p1:hand", card_id: "fireball" } },
    } as unknown as GameView;
    expect(xEstimate(v, "p1", { type: "cast_spell", card_id: "s" })).toEqual({ line: "You have 5 untapped lands and 2 mana floating.", max: 6 });
    expect(xEstimate(v, "p1", { type: "cast_spell", card_id: "f" })!.max).toBe(3); // (7 - 1) / 2
  });
});
