import { api } from "./api";
import { seatToken } from "./games";

export type ResultType = "single" | "multiple" | "draw" | "no_result";
export type Outcome = "win" | "loss" | "draw" | "none";

export interface ResultPlayer {
  seat: string;
  player_id: string;
  name: string;
  deck_key: string | null;
  deck_name: string | null;
  commanders: string[];
  outcome: Outcome;
}

export interface GameResult {
  id: string;
  number: number;
  game_id: string;
  result_type: ResultType;
  table_name: string;
  format: string;
  started_at: string | null;
  recorded_at: string;
  duration_seconds: number | null;
  turns: number | null;
  notes: string;
  players: ResultPlayer[];
  winners: string[];
}

export interface PodPlayer {
  id: string;
  name: string;
  games: number;
  wins: number;
  losses: number;
  draws: number;
  win_pct: number | null;
}

export interface DeckStats extends Omit<PodPlayer, "id" | "name"> {
  deck_key: string;
  deck_name: string | null;
  commanders: string[];
}

export interface PodPlayerDetail extends PodPlayer {
  decks: DeckStats[];
  recent: { id: string; number: number; recorded_at: string; result_type: ResultType; table_name: string; turns: number | null;
    deck_name: string | null; commanders: string[]; outcome: Outcome }[];
}

const host = (gameId: string): Record<string, string> => {
  const t = seatToken(gameId);
  return t ? { "X-Seat-Token": t } : {};
};

export const recordResult = (gameId: string, body: { result_type: ResultType; winners: string[]; notes: string }) =>
  api.post<GameResult>(`/games/${gameId}/result`, body, host(gameId));
export const gameResult = (gameId: string) => api.get<GameResult | null>(`/games/${gameId}/result`);
export const podPlayers = () => api.get<PodPlayer[]>("/pod/players");
export const podPlayer = (id: string) => api.get<PodPlayerDetail>(`/pod/players/${encodeURIComponent(id)}`);
export const podResults = (limit = 100) => api.get<GameResult[]>(`/pod/results?limit=${limit}`);
export const editResult = (id: string, body: { result_type?: ResultType; winners?: string[]; notes?: string }) =>
  api.put<GameResult>(`/pod/results/${encodeURIComponent(id)}`, body);
export const deleteResult = (id: string) => api.del<void>(`/pod/results/${encodeURIComponent(id)}`);

export const RESULT_LABEL: Record<ResultType, string> = {
  single: "Single winner",
  multiple: "Multiple winners",
  draw: "Draw",
  no_result: "No result",
};

export const pct = (v: number | null) => (v == null ? "—" : `${v.toFixed(1).replace(/\.0$/, "")}%`);

export function duration(seconds: number | null): string {
  if (seconds == null) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

export const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
