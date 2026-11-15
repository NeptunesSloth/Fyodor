import { describe, expect, it } from "vitest";
import { ArrangedBoards, arrangeMat, orderFromRest, reorderMat, TILE_MAX, TILE_MIN, TILE_SQUASH, toArrange } from "./arrange3d";
import { MAT_D, MAT_W, seats, toLocal } from "./layout";
import { TILE_RATIO, type ArrangeCard } from "../game/arrange";
import { CARD_H, CARD_W } from "./layout";
import type { GameView, VisibleCard } from "../types/game";
import type { CardData } from "../types/cards";

const card = (id: string, row: ArrangeCard["row"], extra: Partial<ArrangeCard> = {}): ArrangeCard =>
  ({ id, row, key: null, n: 1, turned: false, forward: false, host: null, ...extra });

const vis = (id: string, owner: string, name: string, extra: Partial<VisibleCard> = {}): VisibleCard => ({
  id, owner, controller: owner, zone: `${owner}:battlefield`, face_down: false, card_id: `c-${name}`, name, face: 0, revealed: false, note: "",
  is_token: false, x: 0, y: 0, ...extra,
});

const TYPES: Record<string, string> = { Bear: "Creature — Bear", Forest: "Basic Land — Forest", Ring: "Artifact", Wolf: "Creature — Wolf" };
const data = (cardId: string) => ({ type_line: TYPES[cardId.slice(2)] ?? "", faces: [] } as unknown as CardData);

/** A 4-player view: each seat has two creatures, a mana rock and three Forests. */
function view(): GameView {
  const cards: Record<string, VisibleCard> = {};
  const zones: Record<string, string[]> = {};
  for (const p of ["p1", "p2", "p3", "p4"]) {
    const ids = [`${p}-bear`, `${p}-wolf`, `${p}-ring`, `${p}-f1`, `${p}-f2`, `${p}-f3`];
    const names = ["Bear", "Wolf", "Ring", "Forest", "Forest", "Forest"];
    ids.forEach((id, i) => { cards[id] = vis(id, p, names[i]!); });
    zones[`${p}:battlefield`] = ids;
  }
  return { cards, zones, seat_order: ["p1", "p2", "p3", "p4"] } as unknown as GameView;
}

describe("arranged 3D mats", () => {
  it("fills a mat: creatures toward the middle, lands at the owner's edge, tiles at most about twice a card", () => {
    const board = [card("c1", "creature"), card("c2", "creature"), card("a1", "other"), card("l1", "land"), card("l2", "land")];
    const mine = arrangeMat(board, false);
    const z = (id: string) => mine.spots.get(id)!.lz;
    expect(z("c1")).toBeLessThan(z("a1")); // my mat: the front is away from me, toward the aisle
    expect(z("a1")).toBeLessThanOrEqual(z("l1"));
    expect(mine.spots.get("c1")!.w).toBeCloseTo(TILE_MAX); // few cards: big tiles
    for (const s of mine.spots.values()) {
      expect(Math.abs(s.lx) + s.w / 2).toBeLessThanOrEqual(MAT_W / 2 + 1e-6); // on the felt
      expect(Math.abs(s.lz) + (s.w * TILE_RATIO) / 2).toBeLessThanOrEqual(MAT_D / 2 + 1e-6);
    }
    const across = arrangeMat(board, true);
    expect(across.spots.get("c1")!.lz).toBeGreaterThan(across.spots.get("l1")!.lz); // a mat across the table: its front toward me
  });

  it("keeps tiles readable on a crowded mat (they overlap rather than shrink past the floor)", () => {
    const crowd = arrangeMat(Array.from({ length: 60 }, (_, i) => card(`c${i}`, "creature")), false);
    expect(crowd.spots.get("c0")!.w).toBeGreaterThanOrEqual(TILE_MIN - 1e-6);
  });

  it("stacks ranks so a pile's top card and a host lie over what is under them", () => {
    const m = arrangeMat([card("f1", "land", { key: "F" }), card("f2", "land", { key: "F" }), card("eq", "other", { host: "bear" }), card("bear", "creature")], false);
    expect(m.spots.get("f2")!.rank).toBeGreaterThan(m.spots.get("f1")!.rank);
    expect(m.spots.get("f2")!.pile).toBe(2);
    expect(m.spots.get("bear")!.rank).toBeGreaterThan(m.spots.get("eq")!.rank); // tucked under its host
  });

  it("lays a big token pile low, with only its top card labelled and shadowed", () => {
    const swarm = Array.from({ length: 80 }, (_, i) => card(`s${i}`, "creature", { key: "Swarm" }));
    const m = arrangeMat(swarm, false);
    const top = m.spots.get("s79")!;
    expect(top.pile).toBe(80);
    expect(top.under).toBeUndefined();
    expect(swarm.slice(0, 79).every((c) => m.spots.get(c.id)!.under)).toBe(true);
    // the buried cards share one height: the top lies a few layers up, not 80
    expect(top.rank - m.spots.get("s0")!.rank).toBeLessThanOrEqual(4);
  });

  it("squashes a card to a tile's proportions", () => {
    expect((CARD_H * TILE_SQUASH) / CARD_W).toBeCloseTo(TILE_RATIO);
  });
});

describe("arranged 3D boards: every board reads upright from my seat", () => {
  const none: string[] = []; // boardOrder keeps the same array until my order changes
  const src = { data, order: () => none };

  it("lays out every seat, mats across the table facing me", () => {
    const b = new ArrangedBoards();
    const s = seats(["p1", "p2", "p3", "p4"], "p1");
    const spots = b.layout(view(), s, "p1", src);
    expect(spots.size).toBe(24);
    const mine = s.find((x) => x.player === "p1")!;
    for (const spot of spots.values()) expect(spot.rot).toBe(mine.rot); // all turned to read from my seat
    // my creatures are on the far side of my mat (toward the aisle); an opponent across has theirs on the near side
    const across = s.find((x) => x.side !== mine.side)!;
    const lzOf = (id: string, seat: typeof mine) => toLocal({ ...seat, rot: mine.rot }, spots.get(id)!.x, spots.get(id)!.z)[1];
    expect(lzOf("p1-bear", mine)).toBeLessThan(lzOf("p1-f1", mine));
    expect(lzOf(`${across.player}-bear`, across)).toBeGreaterThan(lzOf(`${across.player}-f1`, across));
    // the three Forests are one stack
    const tops = b.piles("p1");
    expect([...tops.values()]).toEqual([3]);
  });

  it("reuses a mat whose cards are the same objects (the view shares unchanged ones)", () => {
    const b = new ArrangedBoards();
    const s = seats(["p1", "p2", "p3", "p4"], "p1");
    const v = view();
    const first = b.layout(v, s, "p1", src);
    const again = b.layout({ ...v }, s, "p1", src);
    expect(again.get("p2-bear")).toBe(first.get("p2-bear"));
    const tapped = { ...v, cards: { ...v.cards, "p2-bear": { ...v.cards["p2-bear"]!, tapped: true } as VisibleCard } };
    const after = b.layout(tapped, s, "p1", src);
    expect(after.get("p3-bear")).toBe(first.get("p3-bear")); // other mats untouched
    expect(after.get("p2-bear")).not.toBe(first.get("p2-bear"));
  });

  it("lays a mat out again only when what it shows changes", () => {
    const b = new ArrangedBoards();
    const s = seats(["p1", "p2", "p3", "p4"], "p1");
    const v = view();
    b.layout(v, s, "p1", src);
    const before = b.mats.get("p2")!.layout;
    b.layout({ ...v, cards: { ...v.cards } }, s, "p1", src);
    expect(b.mats.get("p2")!.layout).toBe(before);
    // tapping a creature turns it in its slot: the rows stay as they were
    const tapped = { ...v, cards: { ...v.cards, "p2-bear": { ...v.cards["p2-bear"]!, tapped: true } as VisibleCard } };
    b.layout(tapped, s, "p1", src);
    expect(b.mats.get("p2")!.layout).toBe(before);
    // tapping a Forest takes it out of the untapped Forests' stack: laid out again
    const land = { ...tapped, cards: { ...tapped.cards, "p2-f1": { ...v.cards["p2-f1"]!, tapped: true } as VisibleCard } };
    b.layout(land, s, "p1", src);
    expect(b.mats.get("p2")!.layout).not.toBe(before);
  });

  it("follows my order for a board", () => {
    const b = new ArrangedBoards();
    const s = seats(["p1", "p2"], "p1");
    const spots = b.layout(view(), s, "p1", { data, order: (zone) => (zone === "p1:battlefield" ? ["p1-wolf", "p1-bear"] : []) });
    expect(spots.get("p1-wolf")!.lx).toBeLessThan(spots.get("p1-bear")!.lx);
  });
});

describe("arranged 3D boards: rearranging", () => {
  it("a drop along my row reorders it", () => {
    const b = new ArrangedBoards();
    const s = seats(["p1", "p2"], "p1");
    const spots = b.layout(view(), s, "p1", { data, order: () => [] });
    const mat = b.mats.get("p1")!;
    const wolf = spots.get("p1-wolf")!;
    const order = reorderMat(mat, ["p1-bear"], wolf.lx + 0.4, wolf.lz)!;
    expect(order.indexOf("p1-bear")).toBeGreaterThan(order.indexOf("p1-wolf"));
  });

  it("after a flick, each row's cards take the order they came to rest in", () => {
    const m = arrangeMat([card("a", "creature"), card("b", "creature"), card("c", "creature"), card("l", "land")], false);
    const mat = { layout: m.layout, frame: seats(["p1"], "p1")[0]!, mirrored: false, zone: "p1:battlefield" };
    const pa = m.layout.place.get("a")!;
    // "a" slid past "c"
    const order = orderFromRest(mat.layout, (id) => (id === "a" ? [m.layout.place.get("c")!.left + m.layout.w * 2, pa.top + m.layout.h / 2] : null));
    expect(order).toEqual(["b", "c", "a", "l"]);
    expect(toArrange(m.layout, 0, 0)[0]).toBeCloseTo((MAT_W / 2) * 100 - m.layout.w / 2);
  });
});
