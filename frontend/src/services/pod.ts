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

/** -- pod history -- one player who went out of a game: players out in the same action share a place; turn null: not known. */
export interface EliminationEntry {
  seat: string;
  name: string;
  place: number;
  turn: number | null;
  /** life | poison | commander_damage | empty_library | effect | opponent_won | conceded | left | out */
  how: string;
  /** The rules engine's own words for it ("0 or less life"), "" when there are none. */
  reason: string;
}

/** -- pod history -- one player's public table when the result was recorded (never a hand or a library). */
export interface FinalBoardSeat {
  seat: string;
  name: string;
  life: number;
  poison: number;
  commanders: string[];
  /** Permanents by name (a face-down one: "face-down card"), at most a few dozen names; `more` counts the rest. */
  permanents: { name: string; count: number; land?: boolean }[];
  more: number;
  graveyard: number;
  exile: number;
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
  /** -- pod history -- absent or empty for results recorded before they were kept. */
  eliminations?: EliminationEntry[];
  final_board?: FinalBoardSeat[];
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
export const podResult = (id: string) => api.get<GameResult>(`/pod/results/${encodeURIComponent(id)}`);
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
