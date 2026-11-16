/**
 * Arena-style "×N" on piles of identical lands and identical tokens. Display only: wherever identical lands sit overlapping in a row
 * (as "Tidy my lands" leaves them, or as a player piled them by hand), or identical tokens lie on top of one another (the server puts
 * tokens past a full battlefield on one spot), the top card of the pile says how many there are. Nothing is grouped on the server, so
 * every card stays its own object: tap one, drag one out, and the count follows.
 */
import { isVisible, type GameCard, type GameView } from "../types/game";
import { stackKey } from "./arrange";
import { typeLine } from "./selection";

/** n: how many it stands for (a token stack's quantity; 1 for a card). land: it may pile (a land, or a token with `key`);
 * key: what identical means when it isn't just the name (a token's P/T, counters, damage, controller: game/arrange.ts stackKey). */
export interface PileFacts { id: string; name: string; x: number; y: number; tapped: boolean; land: boolean; n?: number; key?: string }

const STEP = 24; // the most a pile spreads per card (tidy uses 16 or less)
const ROW = 10; // how far off the row a card may sit and still count

/** Top card id → pile size, for piles of 2 or more. The top card is the right-most, the one fully in view. */
export function pileTops(cards: PileFacts[]): Map<string, number> {
  const groups = new Map<string, PileFacts[]>();
  for (const c of cards) {
    if (!c.land) continue;
    const key = `${c.key ?? c.name}|${c.tapped ? 1 : 0}`;
    const g = groups.get(key);
    if (g) g.push(c);
    else groups.set(key, [c]);
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
  // a token something is attached to keeps its own count (its attachments sit by it)
  const hosts = new Set<string>();
  for (const id of ids) {
    const c = view.cards[id];
    if (isVisible(c) && c.attached_to) hosts.add(c.attached_to);
  }
  return pileTops(ids.flatMap((id) => {
    const c = view.cards[id];
    if (!isVisible(c) || c.face_down || c.attached_to || c.x == null || c.y == null) return [];
    const line = typeLine(c);
    const land = /\bLand\b/.test(line) && !/\bCreature\b/.test(line);
    // identical tokens pile where they overlap (a row of them side by side is no pile)
    const key = c.is_token && !land && !hosts.has(id) ? stackKey(c, "creature") : null;
    if (key) return [{ id, name: c.name, x: c.x, y: c.y, tapped: !!c.tapped, land: true, n: c.quantity ?? 1, key }];
    return [{ id, name: c.name, x: c.x, y: c.y, tapped: !!c.tapped, land, n: c.quantity ?? 1 }];
  }));
}

/** "×65,536": a count mark with thousands separators (an engine token stack can stand for a huge number of tokens). */
export const countText = (n: number): string => `×${n.toLocaleString("en-US")}`;

/**
 * The ×N a battlefield card carries, in the 2D and 3D tables alike: the pile of identical lands it tops, or else the token stack it is
 * ("Goblin ×10": one card the server counts as `quantity` tokens, see game/tokenStacks.ts). Null: nothing to count.
 */
export function countMark(card: GameCard | undefined, pile?: number): { n: number; title: string; testId: string } | null {
  if (pile) {
    const what = card && isVisible(card) && card.is_token ? `${card.name} tokens in this stack` : "identical lands in this pile";
    return { n: pile, title: `${pile} ${what}`, testId: "pile-count" };
  }
  const n = card?.quantity ?? 1;
  if (n <= 1) return null;
  const what = card && isVisible(card) ? `${card.name} tokens` : "tokens";
  return { n, title: `A stack of ${n.toLocaleString("en-US")} ${what} (one card for all of them)`, testId: "stack-count" };
}
