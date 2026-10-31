import { describe, expect, it } from "vitest";
import { nextHandSort, sortHand, type HandFacts } from "./handSort";

const CARDS: Record<string, HandFacts> = {
  island: { name: "Island", mv: 0, colors: [], typeLine: "Basic Land — Island" },
  bolt: { name: "Lightning Bolt", mv: 1, colors: ["R"], typeLine: "Instant" },
  sol: { name: "Sol Ring", mv: 1, colors: [], typeLine: "Artifact" },
  atraxa: { name: "Atraxa, Praetors' Voice", mv: 4, colors: ["W", "U", "B", "G"], typeLine: "Legendary Creature — Phyrexian Angel Horror" },
  swords: { name: "Swords to Plowshares", mv: 1, colors: ["W"], typeLine: "Instant" },
  counter: { name: "Counterspell", mv: 2, colors: ["U"], typeLine: "Instant" },
  elves: { name: "Llanowar Elves", mv: 1, colors: ["G"], typeLine: "Creature — Elf Druid" },
};
const HAND = ["counter", "island", "atraxa", "bolt", "sol", "swords", "elves"];
const facts = (id: string) => CARDS[id] ?? null;

describe("sortHand", () => {
  it("keeps the drawn order", () => expect(sortHand(HAND, facts, "drawn")).toEqual(HAND));
  it("by mana value: lands first, then cheapest, ties by name", () =>
    expect(sortHand(HAND, facts, "mana")).toEqual(["island", "bolt", "elves", "sol", "swords", "counter", "atraxa"]));
  it("by colour: WUBRG, then multicolour, colourless, lands", () =>
    expect(sortHand(HAND, facts, "color")).toEqual(["swords", "counter", "bolt", "elves", "atraxa", "sol", "island"]));
  it("by type: lands, creatures, instants, artifacts", () =>
    expect(sortHand(HAND, facts, "type")).toEqual(["island", "elves", "atraxa", "bolt", "swords", "counter", "sol"]));
  it("by name", () => expect(sortHand(HAND, facts, "name")[0]).toBe("atraxa"));
  it("cards not loaded yet stay at the end in drawn order", () =>
    expect(sortHand(["x2", "atraxa", "x1", "island"], facts, "mana")).toEqual(["island", "atraxa", "x2", "x1"]));
  it("cycles through every mode", () => expect(nextHandSort("name")).toBe("drawn"));
});
