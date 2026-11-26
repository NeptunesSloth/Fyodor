import { describe, expect, it } from "vitest";
import { hiddenUnderPiles, liftedIds } from "./boardCovers";
import { zonePiles, zonePileTops } from "./piles";
import { spreadPileMoves } from "./spread";
import type { GameView, VisibleCard } from "../types/game";

const tok = (id: string, x: number, y: number, extra: Partial<VisibleCard> = {}): VisibleCard => ({
  id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, card_id: null, name: "Saproling", face: 0, revealed: false, note: "",
  is_token: true, token: { name: "Saproling", type_line: "Token Creature — Saproling", power: "1", toughness: "1" }, x, y, ...extra,
} as VisibleCard);
const viewOf = (cards: VisibleCard[], extra: Partial<GameView> = {}) =>
  ({ cards: Object.fromEntries(cards.map((c) => [c.id, c])), zones: { "p1:battlefield": cards.map((c) => c.id) }, ...extra } as unknown as GameView);

/** What Battlefield.tsx renders (free placement): one TableCard per id not hidden. */
function rendered(view: GameView, opts: { selection?: string[]; pending?: Record<string, [number, number]>; dragging?: string[] } = {}): string[] {
  const ids = view.zones["p1:battlefield"] as string[];
  const pending = opts.pending ?? {};
  const lifted = liftedIds(view, ids, "p1", { selection: opts.selection ?? [], pending, dragging: opts.dragging });
  const hidden = hiddenUnderPiles(view, ids, lifted, pending);
  return ids.filter((id) => !hidden.has(id));
}

describe("2D token piles render what shows of them", () => {
  const pile = Array.from({ length: 200 }, (_, i) => tok(`s${i}`, 12, 63));

  it("200 identical tokens on one spot render one TableCard, and its ×N still counts 200", () => {
    const view = viewOf(pile);
    expect(rendered(view)).toEqual(["s199"]); // before: 200
    expect(zonePileTops(view, "p1:battlefield").get("s199")).toBe(200);
  });

  it("selected, dragged and moving cards stay rendered (as the 3D table lifts them)", () => {
    const view = viewOf(pile);
    expect(rendered(view, { selection: ["s3", "s4"] }).sort()).toEqual(["s199", "s3", "s4"]);
    expect(rendered(view, { dragging: ["s7"] }).sort()).toEqual(["s199", "s7"]);
    expect(rendered(view, { pending: { s9: [500, 200] } }).sort()).toEqual(["s199", "s9"]);
  });

  it("a selected top card no longer hides the rest: the next one down shows", () => {
    expect(rendered(viewOf(pile), { selection: ["s199"] }).sort()).toEqual(["s198", "s199"]);
  });

  it("cards in combat, at an arrow's end or something is attached to stay rendered", () => {
    const cards = [...pile.slice(0, 10), tok("aura", 300, 300, { name: "Aura", is_token: false, attached_to: "s2" })];
    cards[4] = { ...cards[4]!, attacking: { kind: "player", id: "p2" } };
    const view = viewOf(cards, { arrows: [{ id: "a1", owner: "p1", source: "s6", targets: ["s1"], kind: "target", label: "" }] });
    expect(rendered(view).sort()).toEqual(["aura", "s1", "s2", "s4", "s6", "s9"]);
  });

  it("cards side by side, or turned differently, are not covered", () => {
    const view = viewOf([tok("a", 12, 63), tok("b", 40, 63), tok("c", 40, 63, { tapped: true })]);
    expect(rendered(view)).toEqual(["a", "b", "c"]);
  });
});

describe("bulk-created tokens are one pile", () => {
  // create_token with count 30 (backend handlers/cards.py): 30 separate tokens on the one spot it chose
  const made = Array.from({ length: 30 }, (_, i) => tok(`g${i}`, 300, 200, { name: "Goblin" }));

  it("30 tokens made at once count ×30, draw one card, and Spread pile lays out all 30", () => {
    const view = viewOf(made);
    expect(zonePileTops(view, "p1:battlefield").get("g29")).toBe(30);
    expect(rendered(view)).toEqual(["g29"]);
    const piles = zonePiles(view, "p1:battlefield");
    expect(piles).toHaveLength(1);
    const moves = spreadPileMoves(piles[0]!);
    expect(moves).toHaveLength(30);
    expect(new Set(moves.map(([, x, y]) => `${x},${y}`)).size).toBe(30);
  });

  it("the old fan (10 per row, 16 apart) was no pile at all: no ×N, every card drawn", () => {
    const fanned = made.map((c, i) => ({ ...c, x: 300 + (i % 10) * 16, y: 200 + Math.floor(i / 10) * 16 + (i % 10) * 4 }));
    const view = viewOf(fanned);
    expect(zonePiles(view, "p1:battlefield")).toEqual([]);
    expect(rendered(view)).toHaveLength(30);
  });
});
