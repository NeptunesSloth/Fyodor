/**
 * "Spread pile": the other way round from "Tidy my lands" (game/tidy.ts). A pile of identical tokens or lands (game/piles.ts: the
 * ×N on its top card) is laid out in rows from where it lies, each card its own spot, so one can be picked out, tapped or
 * targeted by eye. One `set_position` action, so a single Undo piles them back. Free placement only (arranged boards place
 * cards themselves).
 */
import { BF_H, BF_W, CARD_RATIO, CARD_VW } from "./geometry";

/** set_position takes at most this many moves (backend/app/game/actions.py SetPosition): past it, the top ones spread, the rest stay piled. */
export const MAX_SPREAD = 250;

const MARGIN = 16;
const CARD_H = CARD_VW * CARD_RATIO;
/** Column steps tried widest first: side by side, then overlapping but always wider apart than a pile's own spread (piles.ts STEP). */
const STEPS = [CARD_VW + 8, 60, 44, 30];
/** Rows overlap down to the card's name strip, never less (and always further apart than a pile's row: piles.ts ROW). */
const MIN_ROW = 28;

/** Moves (id, x, y) laying a pile (bottom card first, as game/piles.ts zonePiles gives it) out in rows from the pile's spot. */
export function spreadPileMoves(pile: { id: string; x: number; y: number }[]): [string, number, number][] {
  if (pile.length < 2) return [];
  // the top cards spread; past the action's limit the bottom ones stay where they lie
  const cards = pile.slice(-MAX_SPREAD);
  const n = cards.length;
  const room = BF_W - 2 * MARGIN - CARD_VW; // what the left edges may span
  const rowRoom = BF_H - CARD_H; // what the top edges may span
  let dx = STEPS[STEPS.length - 1]!;
  let cols = 1;
  let rows = 1;
  for (const step of STEPS) {
    dx = step;
    cols = Math.min(n, Math.floor(room / step) + 1);
    rows = Math.ceil(n / cols);
    if (rows === 1 || rowRoom / (rows - 1) >= MIN_ROW) break;
  }
  const dy = rows > 1 ? Math.min(CARD_H + 10, rowRoom / (rows - 1)) : 0;
  // from the pile's own spot, shifted only as far as the board needs to hold the whole grid
  const start = cards[0]!;
  const x0 = Math.max(MARGIN, Math.min(start.x, BF_W - MARGIN - CARD_VW - (cols - 1) * dx));
  const y0 = Math.max(0, Math.min(start.y, rowRoom - (rows - 1) * dy));
  return cards.map((c, i) => [c.id, Math.round(x0 + (i % cols) * dx), Math.round(y0 + Math.floor(i / cols) * dy)]);
}
