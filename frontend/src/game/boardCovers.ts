/**
 * Token piles cost what shows of them on the 2D table too (the design rules: piles reduce cost; the 3D table does the same in
 * table3d/covers.ts). A card lying wholly under an identical one, on exactly its spot and turned the same way, is not rendered:
 * 200 Saprolings put on one spot were 200 TableCards, now one. Display only: each stays its own card (the marquee selects by
 * position, so it still takes the whole pile, and the ×N on the top card still counts them all).
 *
 * The same "lifted" rules as TableScene.syncCards: a selected card, one being dragged or on its way to a new spot, one the rules
 * light up (a target, something playable), one an arrow or a combat line leads to, and one something is attached to neither
 * hides nor is hidden.
 */
import { freeCovers, arrangedCovers } from "../table3d/covers";
import { isVisible, type GameView } from "../types/game";
import type { BoardLayout } from "./arrange";
import { legalClass } from "./rules/RulesHud";

export interface LiftFacts {
  selection: readonly string[];
  pending: Record<string, [number, number]>;
  /** The cards being dragged right now (game/dnd.ts). */
  dragging?: readonly string[];
}

/** The battlefield cards of `ids` that must stay drawn whatever lies on them. */
export function liftedIds(view: GameView, ids: readonly string[], me: string, facts: LiftFacts): Set<string> {
  const out = new Set<string>([...facts.selection, ...Object.keys(facts.pending), ...(facts.dragging ?? [])]);
  for (const a of view.arrows ?? []) {
    out.add(a.source);
    for (const t of a.targets) out.add(t);
  }
  for (const id of ids) {
    const c = view.cards[id];
    if (!c) continue;
    if (c.attacking || c.attacking_without_target || c.blocking || c.blocking_without_attacker) out.add(id);
    if (isVisible(c) && c.attached_to) out.add(c.attached_to);
    if (legalClass(view, id, me)) out.add(id);
  }
  return out;
}

/**
 * The cards of one battlefield not to render: covered by an identical card that is drawn. `layout`: the arranged board's (its
 * buried pile cards), else free placement (positions as the server keeps them, or pending).
 */
export function hiddenUnderPiles(view: GameView, ids: readonly string[], lifted: Set<string>, pending: Record<string, [number, number]>, layout?: BoardLayout | null): Set<string> {
  const covers = layout ? arrangedCovers(layout) : freeCovers(ids.flatMap((id) => {
    const c = view.cards[id];
    if (!c || c.x == null || c.y == null) return [];
    const [x, y] = pending[id] ?? [c.x, c.y];
    // (the same turn as TableScene's: tapped, flipped, rotated)
    return [{ id, x, y, turn: (c.tapped ? 1 : 0) + (c.flipped ? 2 : 0) + (c.rotation ?? 0) * 4, lifted: lifted.has(id) }];
  }));
  const out = new Set<string>();
  for (const [id, under] of covers) if (!lifted.has(id) && !lifted.has(under)) out.add(id);
  return out;
}
