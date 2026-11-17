import { describe, expect, it } from "vitest";
import { MAX_NON_HUMAN, botLevel, botName, botRequests, nonHuman, rememberedBots, seatName, seatsLeft } from "./botSeat";

describe("test opponent seats", () => {
  it("names seats like the server", () => {
    expect(botName(0)).toBe("Opponent");
    expect(botName(1)).toBe("Opponent 2");
  });

  it("shares the limit with the dummies", () => {
    expect(MAX_NON_HUMAN).toBe(3);
    expect(seatsLeft(0, 0)).toBe(3);
    expect(seatsLeft(2, 1)).toBe(0);
    expect(seatsLeft(3, 1)).toBe(0);
  });

  it("asks for the seats with a deck, in order, with their names", () => {
    expect(botRequests([{ name: " Gruul ", deck_id: "d1", level: "advanced" }, { name: "", deck_id: null }, { name: "", deck_id: "d2" }]))
      .toEqual([{ deck_id: "d1", name: "Gruul", level: "advanced" }, { deck_id: "d2", name: "Opponent 3", level: "intermediate" }]);
  });

  it("remembers seats, forgetting decks deleted since", () => {
    const known = (id: string) => id === "d1";
    expect(rememberedBots({ bots: [{ name: "A", deck_id: "d1", level: "simple" }, { name: "B", deck_id: "gone", level: "bogus" }, "junk"] }, known))
      .toEqual([{ name: "A", deck_id: "d1", level: "simple" }, { name: "B", deck_id: null, level: "intermediate" }]);
    expect(rememberedBots({}, known)).toEqual([]);
    expect(rememberedBots(null, known)).toEqual([]);
  });

  it("names a bot's seat with its level (none: Intermediate, as the server reads an older save)", () => {
    expect(seatName({ name: "Opponent", bot: "simple", bot_level: "advanced" })).toBe("Opponent (Advanced)");
    expect(seatName({ name: "Opponent", bot: "simple" })).toBe("Opponent (Intermediate)");
    expect(seatName({ name: "Alice", bot: null })).toBe("Alice");
    expect(botLevel({ bot: "simple" })).toBe("intermediate");
  });

  it("knows who nobody sits in", () => {
    expect(nonHuman({ dummy: true })).toBe(true);
    expect(nonHuman({ bot: "simple" })).toBe(true);
    expect(nonHuman({ dummy: false, bot: null })).toBe(false);
  });
});
