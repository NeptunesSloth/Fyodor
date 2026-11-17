/**
 * -- test opponent -- Sandbox's opponent that plays a deck (the server plays for it: app/game/bot.py). The Play page seats it with one of
 * your decks (or a precon); the table's top bar sets how fast it plays (app/multiplayer/bots.py). Dummies and opponents share one limit.
 */
import type { BotLevel, BotSpeed, GameView, PlayerView } from "../types/game";
import { MAX_DUMMIES } from "./targetDummy";

/** Dummies and opponents together, beside you (the server's autoseat.MAX_NON_HUMAN). */
export const MAX_NON_HUMAN = MAX_DUMMIES;
/** The opponent seat's colour (the server's: a muted violet no pod seat starts with). */
export const BOT_COLOR = "#7d6b9e";

/** An opponent seat set up on the Sandbox start: its name, the deck it plays (null: not chosen yet) and how well it plays. */
export interface BotSeat { name: string; deck_id: string | null; level?: BotLevel }

/** -- bot levels -- how well it plays, as the chips name them (the server's app/game/bot.py). */
export const BOT_LEVELS: { id: BotLevel; label: string; hint: string }[] = [
  { id: "simple", label: "Simple", hint: "Lands and its biggest spells; attacks where it is safe. No abilities or tricks" },
  { id: "intermediate", label: "Intermediate", hint: "Also its abilities and pump spells, careful attacks and blocks, removal at the biggest threat" },
  { id: "advanced", label: "Advanced", hint: "Also counterspells and mana held for them, lethal alpha strikes, wipes when behind, efficient sequencing" },
];
/** A seat without a level plays at Intermediate (as the server reads an older save). */
export const DEFAULT_BOT_LEVEL: BotLevel = "intermediate";

export function botLevel(p: Pick<PlayerView, "bot" | "bot_level">): BotLevel {
  return p.bot_level ?? DEFAULT_BOT_LEVEL;
}

export function botLevelName(level: BotLevel | null | undefined): string {
  return BOT_LEVELS.find((l) => l.id === level)?.label ?? "Intermediate";
}

/** The name a seat's plaque shows: an opponent the server plays for with its level ("Opponent (Advanced)"). */
export function seatName(p: Pick<PlayerView, "name" | "bot" | "bot_level">): string {
  return p.bot ? `${p.name} (${botLevelName(botLevel(p))})` : p.name;
}

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
    const { name, deck_id, level } = b as Partial<BotSeat>;
    return [{ name: typeof name === "string" ? name : botName(i), deck_id: typeof deck_id === "string" && known(deck_id) ? deck_id : null,
      level: BOT_LEVELS.some((l) => l.id === level) ? level : DEFAULT_BOT_LEVEL }];
  });
}

/** The seats to add at the start, in order, with a deck chosen (a seat without one is left out). */
export function botRequests(seats: BotSeat[]): { deck_id: string; name: string; level: BotLevel }[] {
  return seats.slice(0, MAX_NON_HUMAN).flatMap((b, i) => (b.deck_id
    ? [{ deck_id: b.deck_id, name: b.name.trim() || botName(i), level: b.level ?? DEFAULT_BOT_LEVEL }] : []));
}

/** The top bar's bot speeds, as it names them. */
export const BOT_SPEEDS: { id: BotSpeed; label: string; hint: string }[] = [
  { id: "normal", label: "Normal", hint: "A short pause between its actions, so you can follow them" },
  { id: "fast", label: "Fast", hint: "Plays its actions almost at once" },
  { id: "step", label: "Step", hint: "One action each time you press Next" },
];
