import { describe, expect, it } from "vitest";
import { NO_FILTER, filterCards, filtering, toggle, type CardFilter, type FilterCard } from "./cardFilters";

const card = (id: string, name: string | null, type_line?: string, cmc?: number, colors: string[] = [], oracle_text = ""): FilterCard => ({
  id, name, data: type_line === undefined ? null : { type_line, cmc, colors, oracle_text },
});
// in library order
const LIB: FilterCard[] = [
  card("elves", "Llanowar Elves", "Creature — Elf Druid", 1, ["G"], "{T}: Add {G}."),
  card("ring", "Sol Ring", "Artifact", 1, [], "{T}: Add {C}{C}."),
  card("hidden", null), // a card this viewer can't see: no name, no data
  card("forest", "Forest", "Basic Land — Forest", 0),
  card("emrakul", "Emrakul, the Aeons Torn", "Legendary Creature — Eldrazi", 15),
  card("bolt", "Lightning Bolt", "Instant", 1, ["R"], "Lightning Bolt deals 3 damage to any target."),
  card("valki", "Valki, God of Lies", "Legendary Creature — God // Legendary Planeswalker — Tibalt", 2, ["B", "R"]),
  card("pending", "Arcane Signet"), // visible, but its data hasn't arrived
  card("dryad", "Dryad Arbor", "Land Creature — Forest Dryad", 0, ["G"]),
];
const ids = (f: Partial<CardFilter>) => filterCards(LIB, { ...NO_FILTER, ...f }).map((c) => c.id);

describe("filterCards", () => {
  it("shows everything in library order with no filter", () => {
    expect(filtering(NO_FILTER)).toBe(false);
    expect(filterCards(LIB, NO_FILTER)).toBe(LIB);
  });

  it("filters by text over name, type and rules text, never matching a hidden card", () => {
    expect(ids({ text: "  ADD " })).toEqual(["elves", "ring"]);
    expect(ids({ text: "elf" })).toEqual(["elves"]);
    expect(ids({ text: "signet" })).toEqual(["pending"]); // a name is enough for text
  });

  it("ORs chips within a group, ANDs the groups, and reads the front face's types", () => {
    expect(ids({ types: ["Land"] })).toEqual(["forest", "dryad"]);
    expect(ids({ types: ["Creature", "Instant"] })).toEqual(["elves", "emrakul", "bolt", "valki", "dryad"]);
    expect(ids({ types: ["Planeswalker"] })).toEqual([]); // Valki's back face doesn't count
    expect(ids({ types: ["Creature"], mvs: [1, 2] })).toEqual(["elves", "valki"]);
  });

  it("matches mana values, 7 meaning 7 or more", () => {
    expect(ids({ mvs: [0] })).toEqual(["forest", "dryad"]);
    expect(ids({ mvs: [7] })).toEqual(["emrakul"]);
  });

  it("matches colours, C meaning colourless; multicolour cards match each of their colours", () => {
    expect(ids({ colors: ["R"] })).toEqual(["bolt", "valki"]);
    expect(ids({ colors: ["C"] })).toEqual(["ring", "forest", "emrakul"]);
    expect(ids({ colors: ["G", "B"] })).toEqual(["elves", "valki", "dryad"]);
  });

  it("drops cards without data (hidden or not loaded) from any chip filter", () => {
    expect(ids({ mvs: [0, 1, 2, 3, 4, 5, 6, 7] })).not.toContain("pending");
    expect(ids({ colors: ["W", "U", "B", "R", "G", "C"] })).not.toContain("hidden");
  });

  it("sorts by name, mana value or type, stably, with unknown cards last", () => {
    expect(ids({ sort: "name" })).toEqual(["pending", "dryad", "emrakul", "forest", "bolt", "elves", "ring", "valki", "hidden"]);
    expect(ids({ sort: "mv" })).toEqual(["dryad", "forest", "bolt", "elves", "ring", "valki", "emrakul", "pending", "hidden"]);
    expect(ids({ sort: "type" })).toEqual(["dryad", "emrakul", "elves", "valki", "ring", "bolt", "forest", "pending", "hidden"]);
    expect(ids({ sort: "mv", types: ["Land"] })).toEqual(["dryad", "forest"]);
  });
});

describe("toggle", () => {
  it("adds and removes a chip", () => {
    expect(toggle(["G"], "R")).toEqual(["G", "R"]);
    expect(toggle(["G", "R"], "G")).toEqual(["R"]);
  });
});
