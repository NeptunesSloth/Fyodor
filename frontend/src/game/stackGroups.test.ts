import { describe, expect, it } from "vitest";
import type { GameCard, GameView } from "../types/game";
import { chainEntries } from "./StackChain";
import { abilityShortName, arrowLines, batchTitle, groupStack, STACK_ARROW_CAP } from "./stackGroups";

const key = (map: Record<string, string | null>) => (id: string) => map[id] ?? null;

describe("groupStack", () => {
  it("groups consecutive identical objects, top first, keeping the order and the chain numbers", () => {
    // bottom → top: s1 (a spell), t1 t2 t3 (same trigger), u1 (another), t4 t5 (the first trigger again)
    const stack = ["s1", "t1", "t2", "t3", "u1", "t4", "t5"];
    const groups = groupStack(stack, key({ t1: "T", t2: "T", t3: "T", t4: "T", t5: "T", u1: "U" }));
    expect(groups).toEqual([
      { id: "t5", ids: ["t5", "t4"], no: 7 },
      { id: "u1", ids: ["u1"], no: 5 },
      { id: "t3", ids: ["t3", "t2", "t1"], no: 4 },
      { id: "s1", ids: ["s1"], no: 1 },
    ]);
  });
  it("never groups objects without a key (spells, targeted abilities, what a decision is about)", () => {
    expect(groupStack(["a", "b", "c"], () => null).map((g) => g.ids)).toEqual([["c"], ["b"], ["a"]]);
    // a keyless object between two identical ones keeps them apart
    expect(groupStack(["a", "x", "b"], key({ a: "T", b: "T" })).map((g) => g.ids)).toEqual([["b"], ["x"], ["a"]]);
  });
  it("an empty stack has no rows", () => {
    expect(groupStack([], () => "k")).toEqual([]);
  });
  it("400 landfall triggers are one row, and 20,000 objects group well within a frame", () => {
    const stack = Array.from({ length: 400 }, (_, i) => `t${i}`);
    expect(groupStack(stack, () => "landfall")).toEqual([{ id: "t399", ids: [...stack].reverse(), no: 400 }]);
    const big = Array.from({ length: 20000 }, (_, i) => `o${i}`);
    const began = performance.now();
    // twenty batches of 999 identical objects, each followed by one object of its own
    const groups = groupStack(big, (id) => {
      const n = Number(id.slice(1));
      return n % 1000 < 999 ? `k${Math.floor(n / 1000)}` : null;
    });
    expect(performance.now() - began).toBeLessThan(50);
    expect(groups.length).toBe(40);
    expect(groups.reduce((n, g) => n + g.ids.length, 0)).toBe(20000);
  });
});

describe("batch titles", () => {
  it("names a batch by its source and ability word", () => {
    expect(batchTitle("Scute Swarm", "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token.", "triggered", 400))
      .toBe("Scute Swarm — landfall ×400");
    expect(batchTitle("Scute Swarm", "Landfall — Whenever …", "triggered", 1)).toBe("Scute Swarm — landfall");
    expect(batchTitle("Soul Warden", "Whenever another creature enters, you gain 1 life.", "triggered", 1500)).toBe("Soul Warden — trigger ×1,500");
    expect(abilityShortName("{T}: Add {G}.", "activated")).toBe("ability");
  });
});

describe("chainEntries", () => {
  const ability = (id: string, text = "Landfall — Whenever a land you control enters, create a token.", controller = "p1"): GameCard => ({
    id, owner: controller, controller, zone: "stack", face_down: false, card_id: null, name: "Scute Swarm", face: 0, revealed: false, note: "",
    ability: { text, source_id: "src", source_card_id: null, source_name: "Scute Swarm", kind: "triggered" },
  } as unknown as GameCard);
  const view = (cards: GameCard[], extra: Record<string, unknown> = {}) => ({
    stack: cards.map((c) => c.id), cards: Object.fromEntries(cards.map((c) => [c.id, c])), arrows: [], ...extra,
  }) as unknown as GameView;

  it("groups by source, text and controller", () => {
    const cards = [ability("a"), ability("b"), ability("c", undefined, "p2"), ability("d"), ability("e", "Other text.")];
    expect(chainEntries(view(cards)).map((g) => g.ids)).toEqual([["e"], ["d"], ["c"], ["b", "a"]]);
  });
  it("keeps a targeted object and the object a decision is about on their own rows", () => {
    const cards = ["a", "b", "c", "d"].map((id) => ability(id));
    const v = view(cards, { arrows: [{ id: "x", source: "b", targets: ["p2"] }], rules: { decision: { source_id: "d" } } });
    expect(chainEntries(v).map((g) => g.ids)).toEqual([["d"], ["c"], ["b"], ["a"]]);
  });
  it("keeps objects with different notes (X, modes) apart", () => {
    const a = { ...ability("a"), stack_info: { x: 2, modes: [], tags: [] } } as GameCard;
    const b = { ...ability("b"), stack_info: { x: 3, modes: [], tags: [] } } as GameCard;
    expect(chainEntries(view([a, b])).map((g) => g.ids)).toEqual([["b"], ["a"]]);
  });
  it("1,000 identical triggers are one entry, its top object first", () => {
    const cards = Array.from({ length: 1000 }, (_, i) => ability(`t${i}`));
    const groups = chainEntries(view(cards));
    expect(groups).toHaveLength(1);
    expect(groups[0]!.ids).toHaveLength(1000);
    expect(groups[0]!.id).toBe("t999");
    expect(groups[0]!.no).toBe(1000);
  });
  it("groups targeted abilities that target the same, and keeps different targets apart (playtest B3)", () => {
    const cards = ["a", "b", "c", "d"].map((id) => ability(id, "Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life."));
    const arrows = [{ id: "1", source: "a", targets: ["p2"] }, { id: "2", source: "b", targets: ["p2"] }, { id: "3", source: "c", targets: ["p1"] },
      { id: "4", source: "d", targets: ["p1"] }];
    expect(chainEntries(view(cards, { arrows })).map((g) => g.ids)).toEqual([["d", "c"], ["b", "a"]]);
  });
});

describe("arrowLines (playtest B3)", () => {
  const arrow = (id: string, source: string, targets: string[], kind: "target" | "custom" = "target") => ({ id, owner: "p1", source, targets, kind, label: "" });

  it("a batch of identical stack objects points once at its target, marked ×N, from the batch's row", () => {
    const arrows = Array.from({ length: 68 }, (_, i) => arrow(`a${i}`, `t${i}`, ["p2"]));
    const groups = [{ id: "t67", ids: Array.from({ length: 68 }, (_, i) => `t${67 - i}`), no: 68 }];
    expect(arrowLines(arrows, groups)).toEqual([{ key: "t67|p2|target", source: "t67", target: "p2", kind: "target", label: "×68", count: 68 }]);
  });
  it("at most STACK_ARROW_CAP lines leave from the stack, top first; other arrows are all kept", () => {
    const n = STACK_ARROW_CAP + 30;
    const groups = Array.from({ length: n }, (_, i) => ({ id: `s${i}`, ids: [`s${i}`], no: n - i }));
    const arrows = [...groups.map((g, i) => arrow(`a${i}`, g.id, [`c${i}`])), arrow("x", "perm", ["c0"], "custom")];
    const lines = arrowLines(arrows, groups);
    expect(lines.filter((l) => l.source.startsWith("s"))).toHaveLength(STACK_ARROW_CAP);
    expect(lines.filter((l) => l.source.startsWith("s"))[0]!.source).toBe("s0");
    expect(lines.some((l) => l.source === "perm")).toBe(true);
  });
});
