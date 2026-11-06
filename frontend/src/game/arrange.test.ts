import { describe, expect, it } from "vitest";
import { applyOrder, arrangeBoard, arrangeCard, boardSlots, reorderOnDrop, rowOf, stackKey, TILE_RATIO, type ArrangeCard } from "./arrange";
import type { GameCard, VisibleCard } from "../types/game";
import type { CardData } from "../types/cards";

const card = (id: string, row: ArrangeCard["row"], extra: Partial<ArrangeCard> = {}): ArrangeCard =>
  ({ id, row, key: null, n: 1, turned: false, forward: false, host: null, ...extra });

const vis = (id: string, name: string, extra: Partial<VisibleCard> = {}): VisibleCard => ({
  id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, card_id: `c-${name}`, name, face: 0, revealed: false, note: "",
  is_token: false, ...extra,
});
const data = (type_line: string): CardData => ({ type_line, faces: [] } as unknown as CardData);

describe("arranged board: rows", () => {
  it("puts creatures in front, other permanents behind them, lands at the back", () => {
    const board = [
      ...["c1", "c2", "c3", "c4"].map((id) => card(id, "creature")), ...["a1", "a2", "a3"].map((id) => card(id, "other")),
      ...["l1", "l2", "l3", "l4", "l5"].map((id) => card(id, "land")),
    ];
    const l = arrangeBoard(board, { width: 900, height: 420, mirrored: false });
    const top = (id: string) => l.place.get(id)!.top;
    expect(top("c1")).toBeLessThan(top("a1")); // my mat: the front is the top, toward the middle of the table
    expect(top("a1")).toBeLessThan(top("l1"));
    const opp = arrangeBoard(board, { width: 900, height: 420, mirrored: true });
    const otop = (id: string) => opp.place.get(id)!.top;
    expect(otop("c1")).toBeGreaterThan(otop("a1")); // an opponent's front is the bottom of their mat
    expect(otop("a1")).toBeGreaterThan(otop("l1"));
  });

  it("keeps three rows even where a few artifacts would fit beside the lands (creatures; artifacts and enchantments; lands)", () => {
    for (const [w, h] of [[900, 420], [600, 200], [1400, 260]] as const) {
      const l = arrangeBoard([card("land", "land"), card("art", "other"), card("ench", "other"), card("cre", "creature")], { width: w, height: h, mirrored: false });
      const top = (id: string) => l.place.get(id)!.top;
      expect(top("cre")).toBeLessThan(top("art"));
      expect(top("art")).toBe(top("ench"));
      expect(top("art")).toBeLessThan(top("land"));
      expect(l.rows.map((r) => r.kind)).toEqual(["creature", "other", "land"]);
    }
  });

  it("sorts cards into rows by what they are", () => {
    expect(rowOf(vis("a", "Llanowar Elves"), data("Creature — Elf Druid"))).toBe("creature");
    expect(rowOf(vis("a", "Forest"), data("Basic Land — Forest"))).toBe("land");
    expect(rowOf(vis("a", "Dryad Arbor"), data("Land Creature — Forest Dryad"))).toBe("creature");
    expect(rowOf(vis("a", "Sol Ring"), data("Artifact"))).toBe("other");
    expect(rowOf(vis("a", "Mutavault"), data("Land"), { creature: true })).toBe("creature"); // animated: the rules say so
    expect(rowOf(vis("a", "Morph", { face_down: true }), data("Enchantment"))).toBe("creature"); // a face-down 2/2
    expect(rowOf({ id: "h", hidden: true, owner: "p2", controller: "p2", zone: "p2:battlefield", face_down: true } as GameCard, undefined)).toBe("creature");
    expect(rowOf(vis("a", "Unknown"), undefined)).toBe("other"); // type not loaded yet
    expect(rowOf(vis("t", "Goblin", { card_id: null, is_token: true, token: { name: "Goblin", type_line: "Token Creature — Goblin" } as VisibleCard["token"] }), undefined)).toBe("creature");
  });

  it("fills the mat: few cards are big; a long row wraps before its cards shrink, and a crowded one overlaps", () => {
    const few = arrangeBoard([card("a", "creature"), card("b", "land")], { width: 1200, height: 400, mirrored: false, maxW: 150 });
    expect(few.w).toBe(150);
    const long = arrangeBoard(Array.from({ length: 24 }, (_, i) => card(`c${i}`, "creature")), { width: 1200, height: 400, mirrored: false });
    expect(new Set([...long.place.values()].map((p) => p.top)).size).toBeGreaterThan(1); // more lines …
    expect(long.w).toBeGreaterThan(80); // … of readable cards
    const crowd = arrangeBoard(Array.from({ length: 80 }, (_, i) => card(`c${i}`, "creature")), { width: 1200, height: 300, mirrored: false, minW: 60 });
    expect(crowd.w).toBe(60); // never below the readable width for room …
    const places = Array.from({ length: 80 }, (_, i) => crowd.place.get(`c${i}`)!);
    for (const p of places) expect(p.left + crowd.w).toBeLessThanOrEqual(1200); // … they overlap instead, all on the mat
    expect(places[1]!.left - places[0]!.left).toBeLessThan(crowd.w);
    expect(places[1]!.z).toBeGreaterThan(places[0]!.z); // the later one on top
  });

  it("keeps every card on the mat, clear of the hand's overlap at the back", () => {
    const cards = [...Array.from({ length: 8 }, (_, i) => card(`c${i}`, "creature")), ...Array.from({ length: 6 }, (_, i) => card(`l${i}`, "land", { turned: i < 3 }))];
    const l = arrangeBoard(cards, { width: 1000, height: 330, mirrored: false, backInset: 30 });
    for (const [id, p] of l.place) {
      const turned = id.startsWith("l") && Number(id.slice(1)) < 3;
      const footH = turned ? l.w : l.h;
      const cy = p.top + l.h / 2;
      expect(cy - footH / 2).toBeGreaterThanOrEqual(0);
      expect(cy + footH / 2).toBeLessThanOrEqual(330 - 30 + 0.01);
      expect(p.left).toBeGreaterThanOrEqual(0);
      expect(p.left + l.w).toBeLessThanOrEqual(1000);
    }
  });

  it("gives a tapped card room to turn without covering its neighbour", () => {
    const l = arrangeBoard([card("a", "land", { turned: true }), card("b", "land")], { width: 1200, height: 300, mirrored: false });
    const a = l.place.get("a")!;
    const b = l.place.get("b")!;
    const aRight = a.left + l.w / 2 + l.h / 2; // turned: its footprint is as wide as the card is tall
    expect(b.left).toBeGreaterThanOrEqual(aRight);
  });

  it("never moves the rest of the board when a card taps or untaps", () => {
    const board = (tapped: boolean) => arrangeBoard([card("a", "creature", { turned: tapped }), card("b", "creature"), card("c", "creature"), card("l", "land")],
      { width: 1000, height: 400, mirrored: false });
    const [up, down] = [board(false), board(true)];
    for (const id of ["b", "c", "l"]) expect(down.place.get(id)).toEqual(up.place.get(id));
    expect(down.w).toBe(up.w);
  });

  it("keeps the turn dial's corner clear", () => {
    const cards = Array.from({ length: 6 }, (_, i) => card(`l${i}`, "land"));
    const l = arrangeBoard(cards, { width: 1200, height: 300, mirrored: false, keepOut: { top: 100, left: 900 } });
    for (const p of l.place.values()) expect(p.left + l.w).toBeLessThanOrEqual(900);
  });

  it("steps attackers and blockers forward", () => {
    const l = arrangeBoard([card("a", "creature", { forward: true }), card("b", "creature"), card("x", "land")], { width: 1200, height: 400, mirrored: false });
    expect(l.place.get("a")!.top).toBeLessThan(l.place.get("b")!.top);
  });
});

describe("arranged board: stacks and attachments", () => {
  it("stacks identical lands and tokens into one slot with ×N on the top card", () => {
    const cards = [card("f1", "land", { key: "Forest" }), card("i1", "land", { key: "Island" }), card("f2", "land", { key: "Forest" }), card("f3", "land", { key: "Forest" })];
    const rows = boardSlots(cards);
    expect(rows.land.map((s) => s.ids)).toEqual([["f1", "f2", "f3"], ["i1"]]);
    const l = arrangeBoard(cards, { width: 1000, height: 300, mirrored: false });
    expect(l.place.get("f3")!.pile).toBe(3);
    expect(l.place.get("f1")!.pile).toBeUndefined();
    expect(l.place.get("f3")!.z).toBeGreaterThan(l.place.get("f1")!.z);
    expect(l.place.get("f3")!.left).toBeGreaterThan(l.place.get("f1")!.left); // each edge peeks out
  });

  it("counts a token stack's quantity", () => {
    const l = arrangeBoard([card("t1", "creature", { key: "Goblin", n: 10 }), card("t2", "creature", { key: "Goblin" })], { width: 1000, height: 300, mirrored: false });
    expect(l.place.get("t2")!.pile).toBe(11);
  });

  it("tucks an attachment under its host, peeking out, never in its own slot", () => {
    const cards = [card("bear", "creature"), card("sword", "other", { host: "bear" }), card("ring", "other")];
    const rows = boardSlots(cards);
    expect(rows.other.map((s) => s.ids)).toEqual([["ring"]]);
    expect(rows.creature[0]!.attach).toEqual(["sword"]);
    const l = arrangeBoard(cards, { width: 1000, height: 400, mirrored: false });
    const bear = l.place.get("bear")!;
    const sword = l.place.get("sword")!;
    expect(sword.z).toBeLessThan(bear.z);
    expect(sword.top).toBeLessThan(bear.top); // toward the middle of the table
    expect(sword.left).toBeGreaterThan(bear.left);
  });

  it("never stacks a card that carries its own state", () => {
    const forest = vis("f", "Forest");
    expect(stackKey(forest, "land")).not.toBeNull();
    expect(stackKey({ ...forest, tapped: true }, "land")).not.toBe(stackKey(forest, "land"));
    expect(stackKey({ ...forest, counters: { charge: 1 } }, "land")).toBeNull();
    expect(stackKey({ ...forest, note: "x" }, "land")).toBeNull();
    expect(stackKey({ ...forest, face_down: true }, "land")).toBeNull();
    expect(stackKey(vis("e", "Llanowar Elves"), "creature")).toBeNull(); // only lands and tokens stack
    const goblin = vis("g", "Goblin", { is_token: true, card_id: null, token: { name: "Goblin", power: "1", toughness: "1" } as VisibleCard["token"] });
    expect(stackKey(goblin, "creature")).toBe(stackKey({ ...goblin, id: "g2" }, "creature"));
    expect(stackKey({ ...goblin, damage: 1 }, "creature")).not.toBe(stackKey(goblin, "creature"));
    expect(stackKey({ ...goblin, attacking: { kind: "player", id: "p2" } }, "creature")).not.toBe(stackKey(goblin, "creature"));
  });

  it("reads a card's facts", () => {
    const c = arrangeCard(vis("x", "Grizzly Bears", { tapped: true, attacking: { kind: "player", id: "p2" } }), data("Creature — Bear"));
    expect(c).toMatchObject({ row: "creature", turned: true, forward: true, key: null, host: null });
  });
});

describe("arranged board: my order", () => {
  it("keeps the cards I placed in my order, new ones at the end", () => {
    expect(applyOrder(["a", "b", "c", "d"], [])).toEqual(["a", "b", "c", "d"]);
    expect(applyOrder(["a", "b", "c", "d"], ["c", "a", "x"])).toEqual(["c", "a", "b", "d"]);
  });

  it("moves a dragged card to where it was dropped in its row", () => {
    const cards = ["a", "b", "c"].map((id) => card(id, "creature"));
    const l = arrangeBoard([...cards, card("l", "land")], { width: 1000, height: 400, mirrored: false });
    const before = l.place.get("a")!.left;
    expect(reorderOnDrop(l, ["c"], before - 10)).toEqual(["c", "a", "b", "l"]);
    expect(reorderOnDrop(l, ["a"], 990)).toEqual(["b", "c", "a", "l"]);
    expect(reorderOnDrop(l, ["zz"], 0)).toBeNull();
  });

  it("keeps the tile shape", () => {
    const l = arrangeBoard([card("a", "creature")], { width: 500, height: 500, mirrored: false });
    expect(l.h / l.w).toBeCloseTo(TILE_RATIO);
  });
});
