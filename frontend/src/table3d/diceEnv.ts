/**
 * The world a roll is thrown into, built from the public view alone, the same way on every screen (3D table, the 2D
 * table's overlay): the roller's mat frame (table3d/diceThrow.ts tableEnv) with their piles standing on it and the cards
 * on their battlefield as thin slabs, so dice glance off decks and ride over cards, and every screen's throw is the same.
 */
import type { GameView, LibraryView } from "../types/game";
import { tableEnv, type ThrowEnv } from "./diceThrow";
import { CARD_H, CARD_W, PILES, virtualToLocal } from "./layout";
import type { Obstacle } from "./physics";

const THICK = 0.016;
const CARD_TOP = 0.024;
/** How tall a pile of n cards stands (as the 3D table draws it). */
export const pileHeight = (n: number) => (n <= 0 ? 0 : Math.min(n, 40) * THICK * 0.9 + Math.max(0, n - 40) * THICK * 0.35);
/** Cards a throw takes into account at most (the oldest first: lands and such, under everything else). */
const MAX_CARDS = 40;

/** `mirror`: the roller's piles stand on the other side of their mat on this screen (the far row's: table3d/layout.ts mirrored). */
export function rollerEnv(view: GameView | null | undefined, player: string | null, mirror = false): ThrowEnv {
  if (!view || !player) return tableEnv();
  const obstacles: Obstacle[] = [];
  for (const zone of ["library", "graveyard", "exile", "command"] as const) {
    const z = view.zones[`${player}:${zone}`];
    const n = Array.isArray(z) ? z.length : (z as LibraryView | undefined)?.count ?? 0;
    if (n <= 0) continue;
    const [x, z2] = PILES[zone];
    obstacles.push({ x: mirror ? -x : x, z: z2, w: CARD_W, d: CARD_H, h: pileHeight(n) + THICK });
  }
  const bf = (view.zones[`${player}:battlefield`] as string[] | undefined) ?? [];
  bf.slice(0, MAX_CARDS).forEach((id, i) => {
    const c = view.cards[id];
    if (!c) return;
    const [x, z] = virtualToLocal(c.x ?? 20 + (i % 10) * 90, c.y ?? 20 + Math.floor(i / 10) * 130);
    const sideways = !!c.tapped !== (Math.abs(((c.rotation ?? 0) % 180)) === 90);
    // a card lies on the felt: one even height for all (the drawn cards step up a hair each, which would tip dice)
    obstacles.push({ x, z, w: sideways ? CARD_H : CARD_W, d: sideways ? CARD_W : CARD_H, h: CARD_TOP });
  });
  return tableEnv(obstacles);
}
