import { describe, expect, it } from "vitest";
import type { DecisionOptionView, GameView } from "../../types/game";
import { groupByController } from "./decisionGroups";

const view = {
  seat_order: ["p1", "p2", "p3"],
  players: [{ id: "p1" }, { id: "p2" }, { id: "p3" }],
  cards: { a: { controller: "p2" }, b: { controller: "p1" }, c: { controller: "p2" }, d: { controller: "p3" } },
} as unknown as GameView;
const opt = (id: string, card = false): DecisionOptionView => ({ id, label: id, card_id: card ? id : null, group: null });

describe("a target list grouped by who controls each option", () => {
  it("puts the chooser first, then the other seats in turn order; a player's own option follows their cards", () => {
    const groups = groupByController([opt("a", true), opt("p2"), opt("d", true), opt("b", true), opt("c", true)], view, "p1");
    expect(groups.map((g) => [g.player, g.options.map((o) => o.id)])).toEqual([["p1", ["b"]], ["p2", ["a", "c", "p2"]], ["p3", ["d"]]]);
  });

  it("drops nothing: options that are neither a card nor a player end in a group of their own", () => {
    const groups = groupByController([opt("cancel"), opt("a", true)], view, "p3");
    expect(groups.map((g) => g.player)).toEqual(["p2", null]);
    expect(groups.flatMap((g) => g.options).map((o) => o.id).sort()).toEqual(["a", "cancel"]);
  });
});
