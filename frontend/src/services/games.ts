import { api } from "./api";
import type { GameSummary, SaveSummary } from "../types/game";

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
