/**
 * Combat damage totals for the combat lanes when token stacks attack (docs/TOKEN_STACKS.md §4: an unblocked stack deals quantity × its
 * power, 510.1a for each member, all at once, 510.2). Display only: the server deals the damage (and knows about first/double strike,
 * prevention, replacement…); this is the plain sum the players would do in their heads.
 */
import { useCardCache } from "../state/cardCache";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { stackSize } from "./tokenStacks";

/** A creature's power as the table shows it: the rules engine's current value, else the printed (or token) power; null when unknown. */
export function powerOf(view: GameView, card: GameCard): number | null {
  const pt = view.rules?.stats?.[card.id]?.pt;
  if (pt) return pt[0];
  if (!isVisible(card)) return null;
  const printed = card.token?.power ?? (card.card_id ? useCardCache.getState().cards[card.card_id]?.power : null);
  const n = printed != null ? Number.parseInt(String(printed), 10) : Number.NaN;
  return Number.isFinite(n) ? n : null;
}

/** What one attacker deals if unblocked: its members × its power (never below 0). null when its power is unknown. */
export function attackerDamage(view: GameView, card: GameCard): number | null {
  const p = powerOf(view, card);
  return p == null ? null : stackSize(card) * Math.max(0, p);
}

export interface FrontTotal {
  /** Damage the unblocked attackers deal (those whose power is known). */
  unblocked: number;
  /** Creatures attacking (stack members counted). */
  attackers: number;
  /** Some unblocked attacker's power is unknown (a face-down card without stats): the total is a lower bound. */
  partial: boolean;
  /** Any attacker here is a token stack: the lanes show totals only then. */
  stacked: boolean;
}

export function frontTotal(view: GameView, lanes: { attacker: GameCard; blockers: GameCard[] }[]): FrontTotal {
  let unblocked = 0;
  let attackers = 0;
  let partial = false;
  let stacked = false;
  for (const { attacker, blockers } of lanes) {
    const n = stackSize(attacker);
    attackers += n;
    stacked ||= n > 1;
    if (blockers.length) continue;
    const dmg = attackerDamage(view, attacker);
    if (dmg == null) partial = true;
    else unblocked += dmg;
  }
  return { unblocked, attackers, partial, stacked };
}

/** "1,024 damage unblocked" (with "at least" when a power is unknown). */
export function totalText(t: FrontTotal): string {
  return `${t.partial ? "at least " : ""}${t.unblocked.toLocaleString("en-US")} damage unblocked`;
}
