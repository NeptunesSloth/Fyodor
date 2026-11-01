import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MenuItem } from "../components/ContextMenu";
import type { GameCard, GameView, RulesView, VisibleCard } from "../types/game";
import { countMark, pileTops } from "./piles";
import { identicalTokens, stackSize, tokenStackItems } from "./tokenStacks";

const sent: Record<string, unknown>[] = [];
vi.mock("./actions", () => ({ send: (a: Record<string, unknown>) => { sent.push(a); return Promise.resolve(true); } }));

const GOBLIN = { name: "Goblin", card_id: null, power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin", text: "" };

function token(id: string, extra: Partial<VisibleCard> = {}): VisibleCard {
  return { id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, card_id: null, name: "Goblin", face: 0,
    revealed: false, note: "", is_token: true, token: GOBLIN, x: 100, y: 100, ...extra };
}

function view(cards: GameCard[], rules?: Partial<RulesView>): GameView {
  const zones: Record<string, string[]> = {};
  for (const c of cards) (zones[c.zone] ??= []).push(c.id);
  return { cards: Object.fromEntries(cards.map((c) => [c.id, c])), zones, ...(rules ? { rules: rules as RulesView } : {}) } as unknown as GameView;
}

const labels = (items: MenuItem[]) => items.map((i) => (i === "separator" ? "—" : i.label));
const entry = (items: MenuItem[], label: string) => items.find((i): i is Exclude<MenuItem, "separator"> => i !== "separator" && i.label.startsWith(label));

beforeEach(() => { sent.length = 0; });

describe("the ×N count", () => {
  it("shows a token stack's quantity, and nothing for a single card", () => {
    expect(countMark(token("a", { quantity: 10 }))).toMatchObject({ n: 10, testId: "stack-count", title: expect.stringContaining("10 Goblin tokens") });
    expect(countMark(token("a"))).toBeNull();
    expect(countMark(token("a", { quantity: 1 }))).toBeNull();
    expect(stackSize(token("a", { quantity: 7 }))).toBe(7);
    expect(stackSize(undefined)).toBe(1);
  });
  it("a land pile's count wins, and counts the stacks in it", () => {
    expect(countMark(token("a", { quantity: 3 }), 5)).toMatchObject({ n: 5, testId: "pile-count" });
    const c = (id: string, x: number, n?: number) => ({ id, name: "Wastes", x, y: 470, tapped: false, land: true, n });
    expect([...pileTops([c("a", 0, 3), c("b", 16)])]).toEqual([["b", 4]]);
  });
});

describe("token stack menu", () => {
  it("lets the stack's controller split one off, split some off, or spread it out", () => {
    const stack = token("s", { quantity: 10 });
    const items = tokenStackItems(stack, view([stack]), "p1", ["s"]);
    const sub = entry(items, "Token stack ×10")!.submenu!;
    expect(labels(sub)).toEqual(["Split one off", "Split off…", "Split into 10 tokens", "—", "Add one", "Remove one"]);
    entry(sub, "Split one off")!.onClick!();
    entry(sub, "Split into")!.onClick!();
    expect(sent).toEqual([{ type: "split_stack", card_id: "s", count: 1 }, { type: "expand_stack", card_id: "s" }]);
  });
  it("shows nothing to other players, for single tokens with nothing to stack, or for real cards", () => {
    const stack = token("s", { quantity: 4 });
    expect(tokenStackItems(stack, view([stack]), "p2")).toEqual([]);
    expect(tokenStackItems(token("t"), view([token("t")]), "p1")).toEqual([]);
    const card = token("c", { is_token: false, quantity: 1 });
    expect(tokenStackItems(card, view([card, token("t")]), "p1")).toEqual([]);
  });
  it("stacks identical tokens on the battlefield into this one (the same token, tapped state and counters)", () => {
    const a = token("a", { quantity: 3 });
    const others = [token("b"), token("c", { tapped: true }), token("d", { counters: { "+1/+1": 1 } }), token("e", { controller: "p2", zone: "p2:battlefield" }),
      token("f", { token: { ...GOBLIN, power: "2" } }), token("g", { protected: true }), token("h", { quantity: 2 })];
    const v = view([a, ...others]);
    expect(identicalTokens(a, v)).toEqual(["a", "b", "h"]);
    const merge = entry(tokenStackItems(a, v, "p1", ["a"]), "Stack identical tokens")!;
    expect(merge.label).toBe("Stack identical tokens (×6)");
    merge.onClick!();
    expect(sent).toEqual([{ type: "merge_tokens", card_ids: ["a", "b", "h"] }]);
  });
  it("stacks only within a selection of two or more", () => {
    const cards = [token("a"), token("b"), token("c")];
    expect(identicalTokens(cards[0]!, view(cards), ["a", "c"])).toEqual(["a", "c"]);
  });
  it("with rules automation on, splits but never stacks (the server keeps every token its own object)", () => {
    const stack = token("s", { quantity: 3 });
    const items = tokenStackItems(stack, view([stack, token("t")], { paused: false }), "p1", ["s"]);
    expect(labels(items)).toEqual(["Token stack ×3"]);
    expect(labels(entry(items, "Token stack")!.submenu!)).toEqual(["Split one off", "Split off…", "Split into 3 tokens"]);
  });
});
