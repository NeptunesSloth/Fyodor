import { describe, expect, it } from "vitest";
import { pileTops, type PileFacts } from "./piles";
import { MAX_SPREAD, spreadPileMoves } from "./spread";
import { BF_H, BF_W, CARD_RATIO, CARD_VW } from "./geometry";

const pile = (n: number, x = 400, y = 240) => Array.from({ length: n }, (_, i) => ({ id: `s${i}`, x, y }));
const asFacts = (moves: [string, number, number][]): PileFacts[] =>
  moves.map(([id, x, y]) => ({ id, name: "Saproling", x, y, tapped: false, land: true, key: "T|Saproling" }));

describe("spreadPileMoves", () => {
  it("lays a small pile out side by side from its own spot, in one action", () => {
    const moves = spreadPileMoves(pile(3));
    expect(moves).toEqual([["s0", 400, 240], ["s1", 492, 240], ["s2", 584, 240]]);
  });

  it("leaves no pile behind: every card on its own spot, none counted as a ×N again", () => {
    for (const n of [2, 12, 40, 200]) {
      const moves = spreadPileMoves(pile(n));
      expect(moves).toHaveLength(n);
      expect(new Set(moves.map(([, x, y]) => `${x}|${y}`)).size).toBe(n);
      expect(pileTops(asFacts(moves)).size).toBe(0);
    }
  });

  it("stays on the board, wherever the pile lies", () => {
    for (const [x, y] of [[940, 560], [0, 0], [-30, 700]]) {
      for (const [, mx, my] of spreadPileMoves(pile(120, x, y))) {
        expect(mx).toBeGreaterThanOrEqual(0);
        expect(mx + CARD_VW).toBeLessThanOrEqual(BF_W);
        expect(my).toBeGreaterThanOrEqual(0);
        expect(my + CARD_VW * CARD_RATIO).toBeLessThanOrEqual(BF_H + 1);
      }
    }
  });

  it("spreads at most what one set_position takes: the top cards, the bottom ones stay piled", () => {
    const moves = spreadPileMoves(pile(300));
    expect(moves).toHaveLength(MAX_SPREAD);
    expect(moves[0]![0]).toBe("s50");
    expect(moves[moves.length - 1]![0]).toBe("s299");
  });

  it("does nothing for a single card", () => {
    expect(spreadPileMoves(pile(1))).toEqual([]);
  });
});
