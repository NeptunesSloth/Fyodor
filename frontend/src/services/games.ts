import { ApiError, api } from "./api";
import type { GameSummary, LobbySettings, LobbyView, SaveSummary } from "../types/game";

export interface CreatePlayer {
  name: string;
  deck_id: string | null;
  color?: string;
}

export interface CreateGameBody {
  name: string;
  format: "commander";
  mode: "local" | "lan";
  password?: string | null;
  players: CreatePlayer[];
  shuffle: boolean;
  first_player: number | "random" | null;
  starting_life?: number | null;
  auto_untap: boolean;
  /** LAN lobby: players take seats and choose their own decks before the host starts. */
  lobby?: boolean;
  /** Lobby turn order: "pod" = d20 for the first game, then the winner goes last. */
  turn_order?: LobbySettings["turn_order"];
  seats?: number;
  deck_privacy?: LobbySettings["deck_privacy"];
  mulligan_rule?: string;
  mulligan_policy?: import("../types/game").MulliganPolicy | null;
  priority_helper?: LobbySettings["priority_helper"];
  automation?: LobbySettings["automation"];
}

export interface CreatedGame {
  game: GameSummary;
  host_token: string;
  seat?: { player_id: string; token: string };
}

export const listGames = () => api.get<GameSummary[]>("/games");
export const createGame = (body: CreateGameBody) => api.post<CreatedGame>("/games", body);
export const closeGame = (id: string) => api.del<void>(`/games/${id}`);
export const listSaves = () => api.get<SaveSummary[]>("/saves");
export const loadSave = (id: string, mode: "local" | "lan" = "local", password?: string) =>
  api.post<CreatedGame>(`/saves/${id}/load`, { mode, password: password || null });
export const deleteSave = (id: string) => api.del<void>(`/saves/${id}`);
/** Portable package: the save plus its custom images and macros, as one zip (host only). */
export const packageUrl = (id: string) => `/api/saves/${id}/package`;
export async function importPackage(file: Blob): Promise<{ save: SaveSummary; assets_added: number; macros_added: number }> {
  const res = await fetch("/api/packages/import", { method: "POST", headers: { "Content-Type": "application/zip" }, body: file });
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText, body);
  return body;
}
export const joinGame = (body: { code: string; name?: string; password?: string; seat?: string | null; spectate?: boolean }) =>
  api.post<{ game_id: string; viewer: string; token: string; game: GameSummary }>("/join", body);
export const lanInfo = () => api.get<{ addresses: string[]; port: number; bound_host: string; reachable: boolean }>("/lan-info");

const seatKey = (gameId: string) => `fyodor.seat.${gameId}`;

/** Seat tokens are remembered per game so a refresh or reconnect reclaims the seat. */
export function rememberSeat(gameId: string, token: string): void {
  try {
    localStorage.setItem(seatKey(gameId), token);
  } catch {
    /* storage unavailable (private mode): the token only lives for this page */
  }
}

export function seatToken(gameId: string): string | null {
  try {
    return localStorage.getItem(seatKey(gameId));
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------- lobby

/** A deck definition a player brings: content only (the host never reads files by path). */
export type PersonalEntry = Pick<import("../types/decks").DeckEntry, "section" | "quantity" | "name" | "printing_id"> &
  Partial<import("../types/decks").DeckEntry>;
export interface PersonalDeck {
  name: string;
  text: string;
  entries: PersonalEntry[];
  commanders: string[];
  companions: { name: string; printing_id: string }[];
}

export interface LobbyDeckBody {
  name?: string;
  collection?: PersonalEntry[];
  companion_id?: string;
  text?: string;
  archidekt?: string;
  json?: string;
  /** A deck in the host's library (only accepted from the host computer). */
  deck_id?: string;
}

const seatHeaders = (gameId: string): Record<string, string> => {
  const token = seatToken(gameId);
  return token ? { "X-Seat-Token": token } : {};
};
const lobbyPath = (gameId: string, rest = "") => `/games/${encodeURIComponent(gameId)}/lobby${rest}`;

export const getLobby = (gameId: string) => api.get<LobbyView | { phase: "playing" }>(lobbyPath(gameId), seatHeaders(gameId));
export const syncPersonalCollection = (gameId: string) => api.post<LobbyView>(lobbyPath(gameId, "/collection"), { collection: personalCollection() }, seatHeaders(gameId));
export const importPersonalDeck = (gameId: string, body: LobbyDeckBody) => api.post<PersonalDeck>(lobbyPath(gameId, "/import"), body, seatHeaders(gameId));
export const submitLobbyDeck = (gameId: string, body: LobbyDeckBody) => api.post<LobbyView>(lobbyPath(gameId, "/deck"), body, seatHeaders(gameId));
export const clearLobbyDeck = (gameId: string) => api.del<LobbyView>(lobbyPath(gameId, "/deck"), seatHeaders(gameId));
export const setLobbyReady = (gameId: string, ready: boolean) => api.post<LobbyView>(lobbyPath(gameId, "/ready"), { ready }, seatHeaders(gameId));
export const changeLobbySeat = (gameId: string, seat: string) => api.post<LobbyView>(lobbyPath(gameId, "/seat"), { seat }, seatHeaders(gameId));
export const setLobbyProfile = (gameId: string, body: { name?: string; color?: string }) =>
  api.post<LobbyView>(lobbyPath(gameId, "/profile"), body, seatHeaders(gameId));
export const leaveLobby = (gameId: string) => api.post<void>(lobbyPath(gameId, "/leave"), {}, seatHeaders(gameId));
export const updateLobbySettings = (gameId: string, body: Partial<LobbySettings>) =>
  api.post<LobbyView>(lobbyPath(gameId, "/settings"), body, seatHeaders(gameId));
/** -- seating -- host: every seat id once, in the order they should sit (seat 1 first). */
export const arrangeLobbySeats = (gameId: string, order: string[]) =>
  api.post<LobbyView>(lobbyPath(gameId, "/arrange"), { order }, seatHeaders(gameId));
export const kickFromLobby = (gameId: string, seat: string) => api.post<LobbyView>(lobbyPath(gameId, "/kick"), { seat }, seatHeaders(gameId));
export const startLobbyGame = (gameId: string, body: { force?: boolean; first_player?: "random" | number }) =>
  api.post<{ game: GameSummary }>(lobbyPath(gameId, "/start"), body, seatHeaders(gameId));

/**
 * Decks this browser has brought to tables before, so a guest on another computer can pick
 * "My decks" again without re-pasting. Stored only in this browser.
 */
export interface MyDeck {
  id: string;
  name: string;
  body: LobbyDeckBody;
  commanders: string[];
  savedAt: number;
  sourceKey?: string;
  entries?: PersonalEntry[];
  companions?: PersonalDeck["companions"];
}
const MY_DECKS = "fyodor.myDecks";

export function myDecks(): MyDeck[] {
  try {
    const raw = localStorage.getItem(MY_DECKS);
    const list = raw ? (JSON.parse(raw) as MyDeck[]) : [];
    return Array.isArray(list) ? list.filter((d) => d && typeof d.name === "string" && d.body) : [];
  } catch {
    return [];
  }
}

export function rememberMyDeck(name: string, body: LobbyDeckBody, commanders: string[], imported?: PersonalDeck): void {
  if (body.deck_id && !imported) return;
  // A URL is an import source, not an offline copy. Persist the resolved list when available.
  const savedBody: LobbyDeckBody = imported ? { name: imported.name, text: imported.text }
    : { name: body.name, text: body.text, json: body.json, archidekt: body.archidekt };
  const key = JSON.stringify(savedBody);
  const sourceKey = body.archidekt ? `archidekt:${body.archidekt.match(/(?:decks\/)?(\d+)/)?.[1] ?? body.archidekt}`
    : body.deck_id ? `host:${body.deck_id}` : undefined;
  const previous = myDecks().find(d => JSON.stringify(d.body) === key || (sourceKey && d.sourceKey === sourceKey));
  const list = myDecks().filter(d => d.id !== previous?.id && JSON.stringify(d.body) !== key);
  list.unshift({ id: previous?.id ?? Math.random().toString(36).slice(2, 10), name, body: savedBody, commanders,
    sourceKey: sourceKey ?? previous?.sourceKey,
    entries: imported?.entries.map(({ name, quantity, section, printing_id, oracle_id }) => ({ name, quantity, section, printing_id, oracle_id })),
    companions: imported?.companions, savedAt: Date.now() });
  // Never silently drop old decks or report a save when browser storage is full.
  try { localStorage.setItem(MY_DECKS, JSON.stringify(list)); }
  catch { throw new Error("Could not save My decks on this device. Export a backup or free browser storage, then retry."); }
}

export function personalCollection(): PersonalEntry[] {
  const owned = new Map<string, PersonalEntry>();
  for (const entry of myDecks().flatMap(d => d.entries ?? [])) {
    if (entry.section === "tokens" || entry.section === "maybeboard" || !entry.printing_id) continue;
    const key = entry.oracle_id ?? entry.printing_id;
    const prior = owned.get(key);
    if (prior) prior.quantity += entry.quantity;
    else owned.set(key, { ...entry, section: "main" });
  }
  // Preserve quantity while keeping each submitted entry inside the deck-entry API bounds.
  return Array.from(owned.values()).flatMap(entry => {
    const chunks: PersonalEntry[] = [];
    for (let remaining = entry.quantity; remaining > 0; remaining -= 999) chunks.push({ ...entry, quantity: Math.min(remaining, 999) });
    return chunks;
  });
}

export function forgetMyDeck(id: string): void {
  try {
    localStorage.setItem(MY_DECKS, JSON.stringify(myDecks().filter((d) => d.id !== id)));
  } catch {
    /* ignore */
  }
}

/** The table's importer: put a new deck in a seat without leaving the game (POST /games/{id}/load-deck). */
export const loadDeckAtTable = (gameId: string, body: LobbyDeckBody & { seat?: string; draw?: number }) =>
  api.post<{ deck: string; cards: number }>(`/games/${encodeURIComponent(gameId)}/load-deck`, body, seatHeaders(gameId));

