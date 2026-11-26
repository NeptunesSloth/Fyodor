import { describe, expect, it } from "vitest";
import type { DecisionView } from "../../types/game";
import { autoOrderIds, isTriggerOrder, orderedIds, orderRows, savedOrderLabel } from "./triggerOrder";

const opt = (id: string, label = id) => ({ id, label, card_id: null, group: null });
const decision = (triggers?: unknown[]): DecisionView => ({
  id: "d", player: "p1", kind: "order", prompt: "Order your triggered abilities", source_id: null, min_choices: 4, max_choices: 4,
  options: [opt("n1", "Nissa — Landfall: add one mana"), opt("s1"), opt("s2"), opt("a1")],
  ...(triggers ? { display: { kind: "", triggers, rememberable: true } } : {}),
});
const TRIGGERS = [
  { key: "Nissa, Resurgent Animist:0", ids: ["n1"], name: "Nissa, Resurgent Animist", short: "Landfall: add one mana of any color.", text: "Landfall — …", count: 1, source: "c1" },
  { key: "Scute Swarm:0", ids: ["s1", "s2"], name: "Scute Swarm", short: "Landfall: create a 1/1 green Insect creature token.", text: "", count: 2, source: null },
  { key: "Avenger of Zendikar:1", ids: ["a1"], name: "Avenger of Zendikar", short: "Landfall: you may put a +1/+1 counter …", text: "", count: 1, source: "c3" },
];

describe("the trigger order prompt's rows", () => {
  it("groups identical triggers into one row with a count, in the order they triggered", () => {
    const rows = orderRows(decision(TRIGGERS));
    expect(rows.map((r) => [r.name, r.count, r.source])).toEqual([["Nissa, Resurgent Animist", 1, "c1"], ["Scute Swarm", 2, null], ["Avenger of Zendikar", 1, "c3"]]);
    expect(isTriggerOrder(decision(TRIGGERS))).toBe(true);
  });

  it("answers with every trigger: a block's triggers together", () => {
    const rows = orderRows(decision(TRIGGERS));
    expect(orderedIds(rows, ["Avenger of Zendikar:1", "Scute Swarm:0", "Nissa, Resurgent Animist:0"])).toEqual(["a1", "s1", "s2", "n1"]);
    expect(autoOrderIds(rows)).toEqual(["n1", "s1", "s2", "a1"]);
  });

  it("falls back to one row per option without groups, or when the groups don't cover every option", () => {
    expect(orderRows(decision()).map((r) => r.ids)).toEqual([["n1"], ["s1"], ["s2"], ["a1"]]);
    expect(isTriggerOrder(decision())).toBe(false);
    const partial = orderRows(decision(TRIGGERS.slice(0, 2)));
    expect(partial).toHaveLength(4);
    expect(partial[0]!.name).toBe("Nissa — Landfall: add one mana");
  });

  it("never lists an option twice or one the decision doesn't have", () => {
    const rows = orderRows(decision([...TRIGGERS, { key: "x", ids: ["s1", "zz"], name: "X", count: 2 }]));
    expect(autoOrderIds(rows)).toEqual(["n1", "s1", "s2", "a1"]);
  });

  it("words a saved order by the sources' names", () => {
    expect(savedOrderLabel(["Avenger of Zendikar:1", "Scute Swarm:0", "Nissa, Resurgent Animist:0"])).toBe("Avenger of Zendikar → Scute Swarm → Nissa, Resurgent Animist");
  });
});
