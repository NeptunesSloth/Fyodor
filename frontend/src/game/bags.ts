/**
 * -- table toys -- the bags (pure: unit-tested). Two kinds, as on Tabletop Simulator's tables (the reference study's "Table
 * of Doom" infinite bags), off the mats and opened on demand:
 *
 * - **The Bag of Extras** by your seat (a seat button, game/seatActions.ts): only the tokens your deck makes (its Tokens
 *   section and the tokens its cards list, as the server found them when the game started), as their printed cards, the
 *   search for any other token, counters and dice. It is infinite: pulling one out sends the table's ordinary action (create a token, add a counter or a resource, roll), so
 *   nothing new reaches the rules engine. A player who is out of the game makes no objects (game/outOfGame.ts).
 * - **The draw bag** (game/DrawBagPanel.tsx): the table fills it with chits (numbers, player names, teams, any words) and
 *   draws from it at random. Its contents live on the server only (app/game/handlers/toys.py); a view says how many.
 */
import type { CardData } from "../types/cards";
import { isVisible, type GameView } from "../types/game";

/** Counters the bag hands out onto the selected cards, and your own player counters. */
export const CARD_COUNTERS = ["+1/+1", "-1/-1", "loyalty", "charge", "shield", "stun"] as const;
export const PLAYER_COUNTERS = ["energy", "experience"] as const;
/** The dice in the bag (rolled with the table's own roll). */
export const BAG_DICE = [4, 6, 8, 10, 12, 20] as const;
/** Deck tokens shown at most. */
export const DECK_TOKENS_MAX = 30;

/** What makes two token printings the same token: its oracle id, or (without one) its name, P/T, types and colours. */
export function tokenKey(card: Pick<CardData, "oracle_id" | "name" | "power" | "toughness" | "type_line" | "colors">): string {
  if (card.oracle_id) return `o:${card.oracle_id}`;
  return `n:${card.name}|${card.power ?? ""}/${card.toughness ?? ""}|${card.type_line ?? ""}|${[...(card.colors ?? [])].sort().join("")}`;
}

/**
 * Each token once: other printings of the same token (tokenKey) are dropped, the first one's place kept, and the
 * printing with art preferred. A printing whose data hasn't loaded yet stands for itself until it has.
 */
export function uniqueTokens(ids: string[], info: (id: string) => CardData | undefined): string[] {
  const kept = new Map<string, string>(); // key → the printing shown
  for (const id of ids) {
    const card = info(id);
    const key = card ? tokenKey(card) : `id:${id}`;
    const had = kept.get(key);
    if (had === undefined) kept.set(key, id);
    else if (card?.has_image && !info(had)?.has_image) kept.set(key, id);
  }
  return [...kept.values()];
}

/** The tokens `me`'s deck makes: its own list (its Tokens section and the tokens its cards make, found by the server at the start),
 * then any more its visible cards list (a card taken from elsewhere), each token once. */
export function deckTokenIds(view: Pick<GameView, "players" | "cards">, me: string, related: (cardId: string) => string[] | undefined,
  info: (id: string) => CardData | undefined = () => undefined): string[] {
  const ids = new Set<string>();
  for (const id of view.players.find((p) => p.id === me)?.token_shortcuts ?? []) ids.add(id);
  for (const c of Object.values(view.cards)) {
    if (!isVisible(c) || c.owner !== me || !c.card_id) continue;
    for (const t of related(c.card_id) ?? []) ids.add(t);
  }
  return uniqueTokens([...ids], info).slice(0, DECK_TOKENS_MAX);
}

// -- the draw bag -------------------------------------------------------------------------------------------------------

/** Chits at most in one fill, and letters a chit (as the server takes them). */
export const FILL_MAX = 100;
export const CHIT_LEN = 40;

/** What was typed, as chits: one a line or between commas, trimmed, blanks dropped. */
export function parseChits(text: string): string[] {
  return text.split(/[\n,;]/).map((t) => t.trim().slice(0, CHIT_LEN)).filter(Boolean).slice(0, FILL_MAX);
}

/** "1" … "n". */
export const numberChits = (n: number): string[] => Array.from({ length: Math.max(1, Math.min(FILL_MAX, Math.floor(n))) }, (_, i) => String(i + 1));

/** The players still in the game (not left, not out), in seat order. */
export function inGame(view: Pick<GameView, "players" | "seat_order" | "rules">): GameView["players"] {
  const r = view.rules;
  return view.seat_order
    .map((id) => view.players.find((p) => p.id === id))
    .filter((p): p is GameView["players"][number] => !!p && !p.left && !(r && (r.conceded.includes(p.id) || p.id in r.lost)));
}

/** A chit per player still in the game, with their name. */
export const playerChits = (view: Pick<GameView, "players" | "seat_order" | "rules">): string[] => inGame(view).map((p) => p.name.slice(0, CHIT_LEN));

/** Teams for `n` players: as many "Team A", "Team B" … chits as players, the teams as even as they go. */
export function teamChits(n: number, teams = 2): string[] {
  const k = Math.max(2, Math.min(26, teams));
  return Array.from({ length: Math.max(k, n) }, (_, i) => `Team ${String.fromCharCode(65 + (i % k))}`);
}
