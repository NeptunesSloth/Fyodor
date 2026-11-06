import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MenuItem } from "../components/ContextMenu";
import type { GameCard, GameView, RulesView, VisibleCard } from "../types/game";
import { countMark, countText, pileTops } from "./piles";
import { attackSomeItem, identicalTokens, splitForPart, stackSize, tokenStackItems } from "./tokenStacks";

const sent: Record<string, unknown>[] = [];
vi.mock("./actions", () => ({ send: (a: Record<string, unknown>) => { sent.push(a); return Promise.resolve(true); } }));
const asked = vi.hoisted(() => ({ answer: null as number | null, title: "" }));
vi.mock("../components/Prompt", () => ({ askNumber: (title: string) => { asked.title = title; return Promise.resolve(asked.answer); }, askText: () => Promise.resolve(null) }));

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
    expect(labels(sub)).toEqual(["Split one off", "Split off…", "Split into 10 tokens", "—", "Tap some…", "Sacrifice some…", "—", "Add one", "Remove one"]);
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
    expect(labels(entry(items, "Token stack")!.submenu!)).toEqual(["Split one off", "Split off…", "Split into 3 tokens", "—", "Tap some…"]);
  });
  it("an engine stack too big to spread offers only splits, and reads its count with separators", () => {
    const stack = token("s", { quantity: 65536 });
    const items = tokenStackItems(stack, view([stack], { paused: false }), "p1", ["s"]);
    expect(labels(items)).toEqual(["Token stack ×65,536"]);
    expect(labels(entry(items, "Token stack")!.submenu!)).toEqual(["Split one off", "Split off…", "—", "Tap some…"]);
    expect(countText(65536)).toBe("×65,536");
    expect(countMark(stack)?.title).toContain("65,536 Goblin tokens");
  });
});

describe("acting on part of a stack", () => {
  const flush = () => new Promise((r) => setTimeout(r, 0));
  it("splits the rest off, so the card itself stands for exactly k (its id is known before the split)", () => {
    expect(splitForPart(10, 3)).toBe(7);
    expect(splitForPart(10, 10)).toBe(0);
    expect(splitForPart(10, 12)).toBe(0);
    expect(splitForPart(10, 0)).toBe(9); // (at least one)
  });
  it("Tap some… splits n − k off, then taps the k-sized card", async () => {
    const stack = token("s", { quantity: 10 });
    const sub = entry(tokenStackItems(stack, view([stack]), "p1", ["s"]), "Token stack")!.submenu!;
    asked.answer = 3;
    entry(sub, "Tap some…")!.onClick!();
    await flush();
    expect(asked.title).toContain("Tap how many of the 10 Goblin tokens");
    expect(sent).toEqual([{ type: "split_stack", card_id: "s", count: 7 }, { type: "tap", card_ids: ["s"], tapped: true }]);
  });
  it("all of them: no split; a tapped stack offers Untap some…", async () => {
    const stack = token("s", { quantity: 5, tapped: true });
    const sub = entry(tokenStackItems(stack, view([stack]), "p1", ["s"]), "Token stack")!.submenu!;
    asked.answer = 5;
    entry(sub, "Untap some…")!.onClick!();
    await flush();
    expect(sent).toEqual([{ type: "tap", card_ids: ["s"], tapped: false }]);
  });
  it("Sacrifice some… (by hand: automation off or paused) moves the k-sized card to its owner's graveyard; cancelling does nothing", async () => {
    const stack = token("s", { quantity: 20 });
    const sub = entry(tokenStackItems(stack, view([stack], { paused: true }), "p1", ["s"]), "Token stack")!.submenu!;
    asked.answer = null;
    entry(sub, "Sacrifice some…")!.onClick!();
    await flush();
    expect(sent).toEqual([]);
    asked.answer = 4;
    entry(sub, "Sacrifice some…")!.onClick!();
    await flush();
    expect(sent).toEqual([{ type: "split_stack", card_id: "s", count: 16 }, { type: "move", card_ids: ["s"], to: { zone: "graveyard", player: "p1" } }]);
  });
  it("Attack with some of the ×N: per target, then the table's attack with exactly k", async () => {
    const stack = token("s", { quantity: 40 });
    const item = attackSomeItem(stack, "p1", [{ label: "Bob", target: { kind: "player", id: "p2" } }])!;
    expect(item.label).toBe("Attack with some of the ×40");
    asked.answer = 25;
    entry(item.submenu!, "Bob…")!.onClick!();
    await flush();
    expect(sent).toEqual([{ type: "split_stack", card_id: "s", count: 15 }, { type: "attack", card_ids: ["s"], target: { kind: "player", id: "p2" } }]);
    expect(attackSomeItem(token("t"), "p1", [{ label: "Bob", target: { kind: "player", id: "p2" } }])).toBeNull();
    expect(attackSomeItem(stack, "p2", [{ label: "Alice", target: { kind: "player", id: "p1" } }])).toBeNull();
  });
});
