/**
 * "Tidy my lands": an optional helper, like Arena's stacked lands and the TTS Portable Playmat's land rows. It never
 * runs by itself, and the table stays free-form. It piles identical lands along the edge of my battlefield nearest me
 * (basics first in WUBRG order, then the rest by name), one `set_position` action, so a single Undo puts them back.
 */
import { BF_H, BF_W, CARD_RATIO, CARD_VW } from "./geometry";

export interface LandFacts { id: string; name: string; typeLine: string }

const BASICS = ["Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"];
const MARGIN = 16;
const GAP = 18;
const ROW_H = CARD_VW * CARD_RATIO + 14;

/** A land the helper may move: a noncreature land (creature lands fight; leave them where they stand). */
export const tidyable = (typeLine: string) => /\bLand\b/.test(typeLine) && !/\bCreature\b/.test(typeLine);

function rank(f: LandFacts): [number, string] {
  const basic = /\bBasic\b/.test(f.typeLine) ? BASICS.findIndex((b) => new RegExp(`\\b${b}\\b`).test(f.typeLine)) : -1;
  return basic >= 0 ? [basic, f.name] : [BASICS.length, f.name];
}

/** Spread inside a pile: wide enough to count small piles, tighter for big ones. */
const spread = (n: number) => (n <= 6 ? 16 : Math.max(5, 96 / (n - 1)));

/** Moves (id, x, y) that pile identical lands in rows from the near edge outward. */
export function tidyLandMoves(lands: LandFacts[]): [string, number, number][] {
  const piles = new Map<string, LandFacts[]>();
  for (const l of lands.filter((x) => tidyable(x.typeLine))) piles.set(l.name, [...(piles.get(l.name) ?? []), l]);
  const ordered = [...piles.values()].sort((a, b) => {
    const [ra, na] = rank(a[0]!);
    const [rb, nb] = rank(b[0]!);
    return ra - rb || na.localeCompare(nb);
  });
  const moves: [string, number, number][] = [];
  let x = MARGIN;
  let y = BF_H - ROW_H;
  for (const pile of ordered) {
    const dx = spread(pile.length);
    const width = CARD_VW + dx * (pile.length - 1);
    if (x > MARGIN && x + width > BF_W - MARGIN) {
      x = MARGIN;
      y = Math.max(0, y - ROW_H);
    }
    pile.forEach((l, i) => moves.push([l.id, Math.round(x + i * dx), Math.round(y)]));
    x += width + GAP;
  }
  return moves;
}
