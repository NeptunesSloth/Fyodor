import { describe, expect, it } from "vitest";
import { arrangedCovers, freeCovers, pileBadgeSpot, type FreeFacts } from "./covers";
import { arrangeMat } from "./arrange3d";
import { type ArrangeCard } from "../game/arrange";
import { zonePileTops } from "../game/piles";
import type { GameView, VisibleCard } from "../types/game";

const card = (id: string, extra: Partial<ArrangeCard> = {}): ArrangeCard =>
  ({ id, row: "creature", key: "T|Saproling", n: 1, turned: false, forward: false, host: null, ...extra });
const spot = (id: string, x: number, y: number, extra: Partial<FreeFacts> = {}): FreeFacts => ({ id, x, y, turn: 0, ...extra });

/** What the table draws for a battlefield: one face mesh (one draw call, one pick candidate, one shadow) per card not covered. */
const drawn = (ids: string[], covers: Map<string, string>) => ids.filter((id) => !covers.has(id)).length;

describe("token piles cost what shows of them", () => {
  it("free placement: 200 tokens put on one spot draw one card", () => {
    // (the server puts tokens past a full battlefield on one spot: game/placement.py free_spot)
    const pile = Array.from({ length: 200 }, (_, i) => spot(`s${i}`, 12, 63));
    const covers = freeCovers(pile);
    expect(drawn(pile.map((c) => c.id), covers)).toBe(1); // before: 200
    expect(covers.get("s0")).toBe("s199"); // all under the top one
    expect(covers.has("s199")).toBe(false);
  });

  it("free placement: the top one picked up (selected) shows the next; cards side by side or turned differently stay drawn", () => {
    const pile = Array.from({ length: 5 }, (_, i) => spot(`s${i}`, 12, 63, i === 4 ? { lifted: true } : {}));
    const covers = freeCovers(pile);
    expect(covers.get("s0")).toBe("s3");
    expect(covers.has("s3") || covers.has("s4")).toBe(false);
    const row = [spot("a", 12, 63), spot("b", 102, 63), spot("c", 102, 63, { turn: 1 }), spot("d", 12.2, 63.1)];
    const rc = freeCovers(row);
    expect([...rc]).toEqual([["a", "d"]]); // only a, wholly under d; c is tapped over b, which still shows
  });

  it("arranged: a pile of 200 identical tokens draws its few visible edges", () => {
    const swarm = Array.from({ length: 200 }, (_, i) => card(`s${i}`));
    const m = arrangeMat(swarm, false);
    const covers = new Map([...m.spots].flatMap(([id, s]) => (s.cover ? [[id, s.cover] as const] : [])));
    expect(drawn(swarm.map((c) => c.id), covers)).toBe(4); // before: 200 (game/arrange.ts PILE_SHOWN edges)
    expect(m.spots.get("s199")!.pile).toBe(200); // the top one still says ×200
    expect(covers.get("s0")).toBe("s196"); // buried under the first edge that shows
    expect(new Set(covers.values()).size).toBe(1);
  });

  it("arranged: a small pile hides nothing, and a host's attachments are never buried", () => {
    const m = arrangeMat([card("a"), card("b"), card("c"), card("eq", { row: "other", key: null, host: "c" })], false);
    expect(arrangedCovers(m.layout).size).toBe(0);
  });
});

describe("free placement ×N on token piles (2D and 3D alike)", () => {
  const tok = (id: string, x: number, y: number, extra: Partial<VisibleCard> = {}): VisibleCard => ({
    id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, card_id: null, name: "Saproling", face: 0, revealed: false, note: "",
    is_token: true, token: { name: "Saproling", type_line: "Token Creature — Saproling", power: "1", toughness: "1" }, x, y, ...extra,
  } as VisibleCard);
  const viewOf = (cards: VisibleCard[]) =>
    ({ cards: Object.fromEntries(cards.map((c) => [c.id, c])), zones: { "p1:battlefield": cards.map((c) => c.id) } } as unknown as GameView);

  it("the top of a pile of identical tokens says how many there are; a row side by side, or one with a counter, doesn't join", () => {
    const pile = Array.from({ length: 200 }, (_, i) => tok(`s${i}`, 12, 63));
    const odd = tok("odd", 12, 63, { counters: { "+1/+1": 1 } });
    const row = [tok("r1", 300, 63), tok("r2", 390, 63)];
    const tops = zonePileTops(viewOf([...pile, odd, ...row]), "p1:battlefield");
    expect([...tops]).toEqual([["s199", 200]]);
  });
});

describe("pileBadgeSpot", () => {
  const W = 0.84;
  const H = 1.17;
  it("puts the badge on the card's top right corner, half off it, for a card read upright", () => {
    const at = pileBadgeSpot(0, 0.5, 0.2, W, H);
    expect(at.x).toBeCloseTo(0.42 - 0.15);
    expect(at.z).toBeCloseTo(-0.585 + 0.044);
  });
  it("keeps it top right from the viewer on an opponent's card (turned half round) and on a tapped one", () => {
    // an opponent's card: the viewer's top right is the card's own bottom left
    const op = pileBadgeSpot(Math.PI, 0.5, 0.2, W, H);
    expect(op.x).toBeCloseTo(-(0.42 - 0.15));
    expect(op.z).toBeCloseTo(0.585 - 0.044);
    // a tapped card lies sideways: the corner is out by half its height to the side
    const tap = pileBadgeSpot(Math.PI / 2, 0.5, 0.2, W, H);
    const viewerX = Math.cos(-Math.PI / 2) * tap.x + Math.sin(-Math.PI / 2) * tap.z;
    expect(viewerX).toBeCloseTo(0.585 - 0.15);
  });
});
