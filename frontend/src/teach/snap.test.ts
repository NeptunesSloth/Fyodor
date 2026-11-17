import { describe, expect, it } from "vitest";
import { emptyScript, fromEntry, insert, newNode } from "./script";
import { chipFits, chipSlots, firstSpot, spots } from "./snap";
import { vocabulary } from "./testVocabulary";
import type { Entry } from "./types";

const voc = vocabulary();
const piece = (id: string) => voc.pieces.find((p) => p.id === id)!;
const DIVE: Entry = { kind: "keyword", name: "Dive", param: true, reminder: "", abilities: [{ hat: { id: "etb" },
  body: [{ id: "mill", values: { n: "N" } }, { id: "may", body: [{ id: "from_milled", values: { n: "N", card: "card_creature" } }] }] }] };

describe("snap spots", () => {
  it("a When piece goes on the hat; nothing else fits an ability without a hat", () => {
    const s = emptyScript();
    expect(spots(piece("etb"), s, voc)).toEqual([{ path: { ability: 0, index: [] }, kind: "hat" }]);
    expect(spots(piece("draw"), s, voc)).toEqual([]);
    expect(firstSpot(piece("etb"), s, voc, 0)?.kind).toBe("hat");
  });
  it("a Do piece snaps between rows and inside an empty If-you-do, not inside a full You may", () => {
    const s = fromEntry(DIVE);
    const got = spots(piece("draw"), s, voc);
    expect(got.map((g) => g.path.index)).toEqual([[0], [1], [2]]);
    expect(firstSpot(piece("draw"), s, voc, 0)?.path.index).toEqual([2]);
  });
  it("Keep one of the milled cards only follows Mill cards, also inside a You may right under it", () => {
    const s = fromEntry(DIVE);
    expect(spots(piece("from_milled"), s, voc).map((g) => g.path.index)).toEqual([[1]]);
    expect(spots(piece("from_milled"), emptyScript(), voc)).toEqual([]);
    const open = fromEntry({ ...DIVE, abilities: [{ hat: { id: "etb" }, body: [{ id: "mill", values: { n: "N" } }, { id: "may", body: [] }] }] });
    expect(spots(piece("from_milled"), open, voc).map((g) => [g.kind, g.path.index])).toEqual([["body", [1]], ["inside", [1, 0]]]);
    expect(firstSpot(piece("from_milled"), open, voc, 0)?.kind).toBe("inside"); // (a click fills the open You may)
    const far = fromEntry({ ...DIVE, abilities: [{ hat: { id: "etb" }, body: [{ id: "mill", values: { n: 2 } }, { id: "draw", values: { n: 1 } }, { id: "may", body: [] }] }] });
    expect(spots(piece("from_milled"), far, voc).map((g) => g.path.index)).toEqual([[1]]);
  });
  it("an If piece goes first and only once; If you do needs a You may before it", () => {
    const s = fromEntry(DIVE);
    expect(spots(piece("if_your_turn"), s, voc).map((g) => g.path.index)).toEqual([[0]]);
    const withIf = insert(s, { ability: 0, index: [0] }, newNode(piece("if_your_turn")));
    expect(spots(piece("if_life"), withIf, voc)).toEqual([]);
    expect(spots(piece("ifdo"), s, voc).map((g) => g.path.index)).toEqual([[2]]);
    expect(spots(piece("then"), s, voc).map((g) => g.path.index)).toEqual([[1]]);
  });
  it("costs sit right under Pay to use it, limits last, and statics only under Always", () => {
    let s = emptyScript();
    s = insert(s, { ability: 0, index: [] }, newNode(piece("activated")));
    s = insert(s, { ability: 0, index: [0] }, newNode(piece("cost_mana")));
    s = insert(s, { ability: 0, index: [1] }, newNode(piece("draw")));
    expect(spots(piece("cost_tap"), s, voc).map((g) => g.path.index)).toEqual([[0], [1]]);
    expect(spots(piece("limit_sorcery"), s, voc).map((g) => g.path.index)).toEqual([[2]]);
    expect(spots(piece("has_kw"), s, voc)).toEqual([]);
    expect(spots(piece("pay_mana"), s, voc)).toEqual([]); // (a Pay-to-use ability already has its cost)
    s = insert(s, { ability: 0, index: [0] }, newNode(piece("cost_tap")));
    expect(spots(piece("cost_tap"), s, voc)).toEqual([]); // once
    let a = emptyScript();
    a = insert(a, { ability: 0, index: [] }, newNode(piece("static")));
    expect(spots(piece("has_kw"), a, voc).map((g) => g.path.index)).toEqual([[0]]);
    expect(spots(piece("draw"), a, voc)).toEqual([]);
    expect(spots(piece("if_opp_lands"), a, voc)).toEqual([]); // trigger only
    a = insert(a, { ability: 0, index: [0] }, newNode(piece("has_kw")));
    expect(spots(piece("anthem"), a, voc)).toEqual([]); // one Always piece
    expect(spots(piece("if_your_turn"), a, voc).map((g) => g.path.index)).toEqual([[0]]);
  });
  it("swapping the hat keeps a body that still fits", () => {
    const s = fromEntry(DIVE);
    expect(spots(piece("dies"), s, voc)).toEqual([{ path: { ability: 0, index: [] }, kind: "hat" }]);
    expect(spots(piece("static"), s, voc)).toEqual([]); // the mill doesn't fit under Always
  });
});

describe("chips", () => {
  it("land on settings that take them", () => {
    const draw = piece("draw").slots!.n!;
    expect(chipFits(2, draw, false)).toBe(true);
    expect(chipFits(99, draw, false)).toBe(false);
    expect(chipFits("N", draw, false)).toBe(false);
    expect(chipFits("N", draw, true)).toBe(true);
    expect(chipSlots("t_creature", piece("destroy"), false)).toEqual(["what"]);
    expect(chipSlots("t_creature", piece("draw"), false)).toEqual([]);
    expect(chipSlots(3, piece("damage"), false)).toEqual(["n"]);
    expect(chipSlots("t_self", piece("damage"), false)).toEqual([]);
  });
});
