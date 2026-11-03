import type { DecisionOptionView, GameView } from "../../types/game";

export interface OptionGroup {
  /** The player whose objects these are (the controller of the cards; the player themself for a player option), or null. */
  player: string | null;
  options: DecisionOptionView[];
}

/**
 * A target list read at a glance: the options under the player who controls them (in seat order, the chooser first),
 * cards before players. Nothing is added or dropped, only ordered; options that are neither a card nor a player
 * (Cancel, "Done") stay in one group with no player at the end.
 */
export function groupByController(options: DecisionOptionView[], view: GameView, me: string): OptionGroup[] {
  const order = [me, ...view.seat_order.filter((p) => p !== me)];
  const seats = new Set(view.players.map((p) => p.id));
  const owner = (o: DecisionOptionView): string | null => {
    if (o.card_id) return view.cards[o.card_id]?.controller ?? null;
    return seats.has(o.id) ? o.id : null;
  };
  const groups = new Map<string | null, DecisionOptionView[]>();
  for (const o of options) {
    const p = owner(o);
    groups.set(p, [...(groups.get(p) ?? []), o]);
  }
  const rank = (p: string | null) => (p === null ? order.length : order.indexOf(p) < 0 ? order.length - 0.5 : order.indexOf(p));
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b))
    .map(([player, opts]) => ({ player, options: [...opts.filter((o) => o.card_id), ...opts.filter((o) => !o.card_id)] }));
}
