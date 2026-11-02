/**
 * Cards in exile this viewer may cast or play right now (Ian Malcolm's cards they don't own, impulse draw, adventure, plot, Hostage
 * Taker …), from the viewer's own rules hints: the server lists only what this viewer may do, so nothing here is anyone else's
 * business. ``exiled_with`` names the card whose "exiled with" link allows it ("Exiled with Ian Malcolm, Chaotician").
 */
import type { GameView } from "../types/game";
import { send } from "./rules/intents";

export interface ExileCastable { id: string; play: boolean; owner: string; source?: string }

const inExile = (view: GameView, id: string) => (view.cards[id]?.zone ?? "").endsWith(":exile");

export function exileCastables(view: GameView | null): ExileCastable[] {
  const rules = view?.rules;
  if (!view || !rules || rules.paused || !rules.hints.has_priority) return [];
  const h = rules.hints;
  const out: ExileCastable[] = [];
  const seen = new Set<string>();
  for (const [ids, play] of [[h.castable ?? [], false], [h.playable_lands ?? [], true]] as const) {
    for (const id of ids) {
      if (seen.has(id) || !inExile(view, id)) continue;
      seen.add(id);
      out.push({ id, play, owner: view.cards[id]!.zone.split(":")[0]!, ...(h.exiled_with?.[id] ? { source: h.exiled_with[id] } : {}) });
    }
  }
  return out;
}

/** How many cards of one exile pile this viewer may cast or play now. */
export function castableIn(view: GameView | null, zoneKey: string): number {
  return exileCastables(view).filter((c) => view?.cards[c.id]?.zone === zoneKey).length;
}

/** Cast it (asking for X first when the spell has X) or play the land. */
export function playFromExile(c: Pick<ExileCastable, "id" | "play">): Promise<boolean> {
  return send(c.play ? { type: "play_land", card_id: c.id } : { type: "cast_spell", card_id: c.id });
}
