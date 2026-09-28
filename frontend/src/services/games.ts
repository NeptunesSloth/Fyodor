import { api } from "./api";
import type { GameSummary, LobbySettings, LobbyView, SaveSummary } from "../types/game";

export interface CreatePlayer {
  name: string;
  deck_id: string | null;
  color?: string;
}

export interface CreateGameBody {
  name: string;
  format: "commander" | "constructed" | "sandbox";
  mode: "local" | "lan";
  password?: string | null;
  players: CreatePlayer[];
  shuffle: boolean;
  first_player: number | "random" | null;
  starting_life?: number | null;
  auto_untap: boolean;
  /** LAN lobby: players take seats and choose their own decks before the host starts. */
  lobby?: boolean;
  seats?: number;
  deck_privacy?: LobbySettings["deck_privacy"];
  mulligan_rule?: string;
  mulligan_policy?: import("../types/game").MulliganPolicy | null;
  priority_helper?: LobbySettings["priority_helper"];
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
export interface LobbyDeckBody {
  name?: string;
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
export const submitLobbyDeck = (gameId: string, body: LobbyDeckBody) => api.post<LobbyView>(lobbyPath(gameId, "/deck"), body, seatHeaders(gameId));
export const clearLobbyDeck = (gameId: string) => api.del<LobbyView>(lobbyPath(gameId, "/deck"), seatHeaders(gameId));
export const setLobbyReady = (gameId: string, ready: boolean) => api.post<LobbyView>(lobbyPath(gameId, "/ready"), { ready }, seatHeaders(gameId));
export const changeLobbySeat = (gameId: string, seat: string) => api.post<LobbyView>(lobbyPath(gameId, "/seat"), { seat }, seatHeaders(gameId));
export const setLobbyProfile = (gameId: string, body: { name?: string; color?: string }) =>
  api.post<LobbyView>(lobbyPath(gameId, "/profile"), body, seatHeaders(gameId));
export const leaveLobby = (gameId: string) => api.post<void>(lobbyPath(gameId, "/leave"), {}, seatHeaders(gameId));
export const updateLobbySettings = (gameId: string, body: Partial<LobbySettings>) =>
  api.post<LobbyView>(lobbyPath(gameId, "/settings"), body, seatHeaders(gameId));
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
}
const MY_DECKS = "fyodor.myDecks";
const MAX_MY_DECKS = 20;

export function myDecks(): MyDeck[] {
  try {
    const raw = localStorage.getItem(MY_DECKS);
    const list = raw ? (JSON.parse(raw) as MyDeck[]) : [];
    return Array.isArray(list) ? list.filter((d) => d && typeof d.name === "string" && d.body) : [];
  } catch {
    return [];
  }
}

export function rememberMyDeck(name: string, body: LobbyDeckBody, commanders: string[]): void {
  if (body.deck_id) return; // host-library decks are already stored on the host
  const key = JSON.stringify(body);
  const list = myDecks().filter((d) => JSON.stringify(d.body) !== key && d.name !== name);
  list.unshift({ id: Math.random().toString(36).slice(2, 10), name, body, commanders, savedAt: Date.now() });
  try {
    localStorage.setItem(MY_DECKS, JSON.stringify(list.slice(0, MAX_MY_DECKS)));
  } catch {
    /* storage full or unavailable: not remembered, nothing else breaks */
  }
}

export function forgetMyDeck(id: string): void {
  try {
    localStorage.setItem(MY_DECKS, JSON.stringify(myDecks().filter((d) => d.id !== id)));
  } catch {
    /* ignore */
  }
}
