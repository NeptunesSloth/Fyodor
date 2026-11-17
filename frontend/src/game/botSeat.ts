/**
 * -- test opponent -- Sandbox's opponent that plays a deck (the server plays for it: app/game/bot.py). The Play page seats it with one of
 * your decks (or a precon); the table's top bar sets how fast it plays (app/multiplayer/bots.py). Dummies and opponents share one limit.
 */
import type { BotSpeed, GameView, PlayerView } from "../types/game";
import { MAX_DUMMIES } from "./targetDummy";

/** Dummies and opponents together, beside you (the server's autoseat.MAX_NON_HUMAN). */
export const MAX_NON_HUMAN = MAX_DUMMIES;
/** The opponent seat's colour (the server's: a muted violet no pod seat starts with). */
export const BOT_COLOR = "#7d6b9e";
/** The policies it can play with, by the name the seat tile shows ("Plays: Simple"). */
export const BOT_POLICY_NAME: Record<string, string> = { simple: "Simple" };

/** An opponent seat set up on the Sandbox start: its name and the deck it plays (null: not chosen yet). */
export interface BotSeat { name: string; deck_id: string | null }

/** The name a new opponent seat gets: the server's own default ("Opponent", then numbered). */
export function botName(index: number): string {
  return index === 0 ? "Opponent" : `Opponent ${index + 1}`;
}

/** Whether ``p`` is a seat the server plays for, or a target dummy: nobody sits there. */
export function nonHuman(p: Pick<PlayerView, "dummy" | "bot">): boolean {
  return !!p.dummy || !!p.bot;
}

/** The table's opponents the server plays for, still at the table. */
export function botsOf(view: GameView | null | undefined): PlayerView[] {
  return view?.players.filter((p) => !!p.bot && !p.left) ?? [];
}

/** How many more dummies and opponents fit beside you. */
export function seatsLeft(dummies: number, bots: number): number {
  return Math.max(0, MAX_NON_HUMAN - dummies - bots);
}

/** The opponent seats remembered by "Same as last time": only decks still in the library (a deck deleted since: none chosen). */
export function rememberedBots(last: { bots?: unknown } | null, known: (id: string) => boolean): BotSeat[] {
  if (!last || !Array.isArray(last.bots)) return [];
  return last.bots.slice(0, MAX_NON_HUMAN).flatMap((b, i): BotSeat[] => {
    if (!b || typeof b !== "object") return [];
    const { name, deck_id } = b as Partial<BotSeat>;
    return [{ name: typeof name === "string" ? name : botName(i), deck_id: typeof deck_id === "string" && known(deck_id) ? deck_id : null }];
  });
}

/** The seats to add at the start, in order, with a deck chosen (a seat without one is left out). */
export function botRequests(seats: BotSeat[]): { deck_id: string; name: string }[] {
  return seats.slice(0, MAX_NON_HUMAN).flatMap((b, i) => (b.deck_id ? [{ deck_id: b.deck_id, name: b.name.trim() || botName(i) }] : []));
}

/** The top bar's bot speeds, as it names them. */
export const BOT_SPEEDS: { id: BotSpeed; label: string; hint: string }[] = [
  { id: "normal", label: "Normal", hint: "A short pause between its actions, so you can follow them" },
  { id: "fast", label: "Fast", hint: "Plays its actions almost at once" },
  { id: "step", label: "Step", hint: "One action each time you press Next" },
];
