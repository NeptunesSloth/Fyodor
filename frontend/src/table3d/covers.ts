/**
 * Token piles cost what shows of them (the design rules: big boards stay smooth, piles reduce cost). Every battlefield card is its
 * own face mesh, and three.js draws each one separately however alike they are, so 200 Saprolings were 200 draws, 200 pick
 * candidates and 200 contact shadows on one spot. A card lying wholly under another one shows nothing: it is not drawn, not
 * picked and casts no shadow (TableScene hides it while it is covered). Display only: it stays its own card on the server and on
 * the table (select it, drag the top one off and the next one shows, the ×N counts it).
 *
 * Pure (no three.js), so it is unit-tested.
 */
import type { BoardLayout } from "../game/arrange";

/** A battlefield card in free placement, in zone (stacking) order: later ones lie on top. */
export interface FreeFacts {
  id: string;
  /** Its spot (the battlefield's virtual units). */
  x: number;
  y: number;
  /** How it is turned (tapped, rotated, flipped): equal for cards turned the same way. */
  turn: number;
  /** Raised off the felt (selected, a targeting choice, a move on its way): it neither hides nor hides anything. */
  lifted?: boolean;
  /**
   * -- playtest (nov 16) -- what it looks like (its printing and face, or "hidden"): only a card that looks the same hides another (a
   * token pile). A different card lying exactly under one (Marina's Grimoire under Shabraz) stays drawn, its edge-on face the hint.
   */
  look?: string;
}

/** How near two spots must be to count as one (virtual units: a card is 84 wide; tokens put on one spot sit exactly on it). */
const SAME = 0.5;

/** Free placement: card id → the card covering it, the top one of the cards that look the same lying on exactly its spot, turned the same way. */
export function freeCovers(cards: FreeFacts[]): Map<string, string> {
  const spots = new Map<string, string[]>();
  for (const c of cards) {
    if (c.lifted) continue;
    const key = `${Math.round(c.x / SAME)}|${Math.round(c.y / SAME)}|${Math.round(c.turn * 1000)}|${c.look ?? ""}`;
    const at = spots.get(key);
    if (at) at.push(c.id);
    else spots.set(key, [c.id]);
  }
  const out = new Map<string, string>();
  for (const ids of spots.values()) {
    const top = ids[ids.length - 1]!;
    for (let i = 0; i < ids.length - 1; i++) out.set(ids[i]!, top);
  }
  return out;
}

/**
 * -- arranged boards -- a pile's buried cards (game/arrange.ts: past the few edges a pile shows, they lie under its first edge):
 * card id → that first edge.
 */
export function arrangedCovers(layout: BoardLayout): Map<string, string> {
  const out = new Map<string, string>();
  for (const row of layout.rows) {
    for (const slot of row.slots) {
      const cover = slot.find((id) => !layout.place.get(id)?.buried);
      if (!cover) continue;
      for (const id of slot) if (layout.place.get(id)?.buried) out.set(id, cover);
    }
  }
  return out;
}

/**
 * Where a pile's ×N badge sits on its top card (TableScene.sizeBadges), in the card's own frame: on the corner that is top right
 * from the viewer, the badge's centre a little in from it (it half hangs off the card, covering as little art as it can).
 * `r` turns the viewer's frame into the card's (viewer rotation − card rotation); `w`/`h` are the badge's and `cardW`/`cardH`
 * the card's sizes. The viewer's frame has x to the right and −z up the screen.
 */
export function pileBadgeSpot(r: number, w: number, h: number, cardW: number, cardH: number): { x: number; z: number } {
  const c = Math.cos(r);
  const s = Math.sin(r);
  // the card's footprint as the viewer sees it (a tapped card lies sideways)
  const hx = (Math.abs(c) * cardW + Math.abs(s) * cardH) / 2;
  const hz = (Math.abs(s) * cardW + Math.abs(c) * cardH) / 2;
  const vx = hx - w * 0.3;
  const vz = -hz + h * 0.22;
  return { x: c * vx + s * vz, z: -s * vx + c * vz };
}
