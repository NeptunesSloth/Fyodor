/**
 * Arena-style "×N" on piles of identical lands. Display only: wherever identical lands sit overlapping in a row (as
 * "Tidy my lands" leaves them, or as a player piled them by hand), the top card of the pile says how many there are.
 * Nothing is grouped on the server, so every card stays its own object: tap one, drag one out, and the count follows.
 */
import { isVisible, type GameCard, type GameView } from "../types/game";
import { typeLine } from "./selection";

/** n: how many it stands for (a token stack's quantity; 1 for a card). */
export interface PileFacts { id: string; name: string; x: number; y: number; tapped: boolean; land: boolean; n?: number }

const STEP = 24; // the most a pile spreads per card (tidy uses 16 or less)
const ROW = 10; // how far off the row a card may sit and still count

/** Top card id → pile size, for piles of 2 or more. The top card is the right-most, the one fully in view. */
export function pileTops(cards: PileFacts[]): Map<string, number> {
  const groups = new Map<string, PileFacts[]>();
  for (const c of cards) {
    if (!c.land) continue;
    const key = `${c.name}|${c.tapped ? 1 : 0}`;
    groups.set(key, [...(groups.get(key) ?? []), c]);
  }
  const tops = new Map<string, number>();
  for (const group of groups.values()) {
    const sorted = [...group].sort((a, b) => a.x - b.x || a.y - b.y);
    let run: PileFacts[] = [];
    const close = () => {
      if (run.length >= 2) tops.set(run[run.length - 1]!.id, run.reduce((sum, p) => sum + (p.n ?? 1), 0));
      run = [];
    };
    for (const c of sorted) {
      const prev = run[run.length - 1];
      if (prev && (c.x - prev.x > STEP || Math.abs(c.y - prev.y) > ROW)) close();
      run.push(c);
    }
    close();
  }
  return tops;
}

/** The piles on one battlefield (zone key like "p1:battlefield"), from what this viewer can see. */
export function zonePileTops(view: GameView, zone: string): Map<string, number> {
  const ids = (view.zones[zone] as string[] | undefined) ?? [];
  return pileTops(ids.flatMap((id) => {
    const c = view.cards[id];
    if (!isVisible(c) || c.face_down || c.attached_to || c.x == null || c.y == null) return [];
    const line = typeLine(c);
    return [{ id, name: c.name, x: c.x, y: c.y, tapped: !!c.tapped, land: /\bLand\b/.test(line) && !/\bCreature\b/.test(line), n: c.quantity ?? 1 }];
  }));
}

/**
 * The ×N a battlefield card carries, in the 2D and 3D tables alike: the pile of identical lands it tops, or else the token stack it is
 * ("Goblin ×10": one card the server counts as `quantity` tokens, see game/tokenStacks.ts). Null: nothing to count.
 */
export function countMark(card: GameCard | undefined, pile?: number): { n: number; title: string; testId: string } | null {
  if (pile) return { n: pile, title: `${pile} identical lands in this pile`, testId: "pile-count" };
  const n = card?.quantity ?? 1;
  if (n <= 1) return null;
  const what = card && isVisible(card) ? `${card.name} tokens` : "tokens";
  return { n, title: `A stack of ${n} ${what} (one card for all of them)`, testId: "stack-count" };
}
