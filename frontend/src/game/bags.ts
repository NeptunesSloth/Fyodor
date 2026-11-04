/**
 * -- table toys -- the bags (pure: unit-tested). Two kinds, as on Tabletop Simulator's tables (the reference study's "Table
 * of Doom" infinite bags), off the mats and opened on demand:
 *
 * - **The Bag of Extras** by your seat (a seat button, game/seatActions.ts): the tokens your deck makes (its Tokens section
 *   and the tokens its cards list), the common extras (Treasure, Clue, Food, Blood, 1/1s), counters and dice. It is
 *   infinite: pulling one out sends the table's ordinary action (create a token, add a counter or a resource, roll), so
 *   nothing new reaches the rules engine. A player who is out of the game makes no objects (game/outOfGame.ts).
 * - **The draw bag** (game/DrawBagPanel.tsx): the table fills it with chits (numbers, player names, teams, any words) and
 *   draws from it at random. Its contents live on the server only (app/game/handlers/toys.py); a view says how many.
 */
import type { CardData } from "../types/cards";
import { isVisible, type GameView } from "../types/game";

/** A token the Bag of Extras makes: a card from the database (`card_id`), or one defined here. */
export interface ExtraToken {
  id: string;
  label: string;
  /** P/T shown on the chip ("1/1"). */
  pt?: string;
  tint: string;
  token: Record<string, unknown>;
}

/** The predefined tokens with their full rules text, as the server's rules create them (app/rules/scripts.py PREDEFINED_TOKENS). */
export const COMMON_TOKENS: ExtraToken[] = [
  { id: "treasure", label: "Treasure", tint: "#d9b267", token: { name: "Treasure", type_line: "Token Artifact — Treasure", text: "{T}, Sacrifice this token: Add one mana of any color." } },
  { id: "clue", label: "Clue", tint: "#9fb3c8", token: { name: "Clue", type_line: "Token Artifact — Clue", text: "{2}, Sacrifice this token: Draw a card." } },
  { id: "food", label: "Food", tint: "#c9a57a", token: { name: "Food", type_line: "Token Artifact — Food", text: "{2}, {T}, Sacrifice this token: You gain 3 life." } },
  { id: "blood", label: "Blood", tint: "#c0544a", token: { name: "Blood", type_line: "Token Artifact — Blood", text: "{1}, {T}, Discard a card, Sacrifice this token: Draw a card." } },
  { id: "soldier", label: "Soldier", pt: "1/1", tint: "#efe6cf", token: { name: "Soldier", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Soldier" } },
  { id: "spirit", label: "Spirit", pt: "1/1", tint: "#efe6cf", token: { name: "Spirit", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Spirit", text: "Flying" } },
  { id: "goblin", label: "Goblin", pt: "1/1", tint: "#d8735a", token: { name: "Goblin", power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin" } },
  { id: "saproling", label: "Saproling", pt: "1/1", tint: "#7fae6a", token: { name: "Saproling", power: "1", toughness: "1", colors: ["G"], type_line: "Token Creature — Saproling" } },
  { id: "thopter", label: "Thopter", pt: "1/1", tint: "#b7b2a8", token: { name: "Thopter", power: "1", toughness: "1", colors: [], type_line: "Token Artifact Creature — Thopter", text: "Flying" } },
];

/** Counters the bag hands out onto the selected cards, and your own player counters. */
export const CARD_COUNTERS = ["+1/+1", "-1/-1", "loyalty", "charge", "shield", "stun"] as const;
export const PLAYER_COUNTERS = ["energy", "experience"] as const;
/** The dice in the bag (rolled with the table's own roll). */
export const BAG_DICE = [4, 6, 8, 10, 12, 20] as const;
/** Deck tokens shown at most. */
export const DECK_TOKENS_MAX = 12;

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

/** The tokens `me`'s deck makes: its Tokens section, then those its visible cards list (as the Create tokens dialog suggests), each once. */
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

/** Rules text without reminder text, spaces evened out. */
const rulesText = (t: string | null | undefined) => (t ?? "").replace(/\([^()]*\)/g, "").replace(/\s+/g, " ").trim().toLowerCase();

/**
 * Whether a printing from the card database is one of the bag's common tokens: the same name, types, P/T, colours and
 * rules text (reminder text aside). The bag shows its art and makes the token from it.
 */
export function matchesToken(card: CardData, t: ExtraToken): boolean {
  const want = t.token as { name: string; type_line: string; text?: string; power?: string; toughness?: string; colors?: string[] };
  const same = (a: string[] | undefined, b: string[] | undefined) => [...(a ?? [])].sort().join("") === [...(b ?? [])].sort().join("");
  return card.is_token && card.name.toLowerCase() === want.name.toLowerCase() && card.type_line === want.type_line
    && (card.power ?? null) === (want.power ?? null) && (card.toughness ?? null) === (want.toughness ?? null)
    && same(card.colors, want.colors) && rulesText(card.oracle_text) === rulesText(want.text);
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
