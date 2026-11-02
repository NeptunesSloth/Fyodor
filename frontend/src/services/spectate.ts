import { api } from "./api";
import { seatToken, type LobbyDeckBody } from "./games";

/*
 * Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md): for players who are out and spectators. Every
 * payload here is built by the server from the public (spectator) view; nothing here sends a game action.
 */

const seat = (gameId: string): Record<string, string> => {
  const t = seatToken(gameId);
  return t ? { "X-Seat-Token": t } : {};
};
const path = (gameId: string, rest: string, viewer?: string) =>
  `/games/${encodeURIComponent(gameId)}/${rest}${viewer ? `?viewer=${encodeURIComponent(viewer)}` : ""}`;

// --------------------------------------------------------------------------- live summary (practice table corner)

export interface LivePlayer {
  id: string;
  name: string;
  color: string | null;
  life: number;
  poison: number;
  out: "lost" | "conceded" | "left" | null;
  hand: number;
  library: number;
  commander_damage: { key: string; name: string; damage: number }[];
}

export interface LiveSummary {
  game: number;
  turn: number;
  phase: string | null;
  active: string;
  active_name: string;
  priority: string | null;
  waiting: string | null;
  players: LivePlayer[];
  stack: { count: number; top: string | null };
  log: string[];
  result: { winner_names: string[]; result_type: string } | null;
  revision: number;
}

/** A compact public summary of the live game. `viewer`: your seat, at a hot-seat table. */
export const watchLive = (gameId: string, viewer?: string) => api.get<LiveSummary>(path(gameId, "watch", viewer), seat(gameId));

// --------------------------------------------------------------------------- damage sandbox

export const SANDBOX_KEYWORDS = ["first strike", "double strike", "trample", "deathtouch", "lifelink", "indestructible", "infect", "wither"] as const;
export type SandboxKeyword = (typeof SANDBOX_KEYWORDS)[number];

export interface BoardCreature {
  id: string;
  controller: string;
  name: string;
  power: number;
  toughness: number;
  keywords: SandboxKeyword[];
  commander: string | null;
  damage: number;
  tapped: boolean;
  attacking: string | null;
  blocking: string | null;
}

export interface BoardPlayer {
  id: string;
  name: string;
  color: string | null;
  life: number;
  poison: number;
  commander_damage: Record<string, number>;
  out: boolean;
}

export interface SandboxBoard {
  players: BoardPlayer[];
  creatures: BoardCreature[];
  commanders: Record<string, string>;
}

export interface ScenarioCreature {
  id: string;
  name: string;
  controller: string;
  power: number;
  toughness: number;
  damage: number;
  keywords: SandboxKeyword[];
  commander: string | null;
  attacking: string | null;
  blocking: string | null;
}

export interface Scenario {
  players: { id: string; name: string; life: number; poison: number; commander_damage: Record<string, number> }[];
  creatures: ScenarioCreature[];
}

export interface SandboxResult {
  rounds: { round: "only" | "first" | "second"; dealt: { source: string; target: string; amount: number }[] }[];
  players: { id: string; life_before: number; life: number; poison_before: number; poison: number; commander_damage: Record<string, number>; loses: string[] }[];
  creatures: { id: string; died: string | null; damage: number; power: number; toughness: number }[];
}

export const sandboxBoard = (gameId: string, viewer?: string) => api.get<SandboxBoard>(path(gameId, "sandbox/board", viewer), seat(gameId));
export const runSandbox = (gameId: string, scenario: Scenario, viewer?: string) =>
  api.post<SandboxResult>(path(gameId, "sandbox/combat", viewer), scenario, seat(gameId));

// --------------------------------------------------------------------------- predictions

export type Market = "winner" | "next_out";

export interface PredictionPick { choice: string; choice_name: string; stake: number; outcome: "won" | "lost" | "void" | null }
export interface Standing { name: string; balance: number; correct: number; settled: number }
export interface PredictionRecap {
  game: number;
  picks: { name: string; market: Market; choice: string; choice_name: string; stake: number; outcome: "won" | "lost" | "void" }[];
  standings: Standing[];
}

export interface PredictionsView {
  game: number;
  can_predict: boolean;
  stakes: number[];
  markets: Market[];
  candidates: { id: string; name: string }[];
  balance: number;
  available: number;
  picks: Partial<Record<Market, PredictionPick>>;
  standings: Standing[];
  recap: PredictionRecap | null;
}

export const getPredictions = (gameId: string) => api.get<PredictionsView>(path(gameId, "predictions"), seat(gameId));
export const placePrediction = (gameId: string, body: { market: Market; choice: string; stake: number; name?: string }) =>
  api.post<PredictionsView>(path(gameId, "predictions"), body, seat(gameId));
export const withdrawPrediction = (gameId: string, market: Market) =>
  api.del<PredictionsView>(path(gameId, `predictions/${market}`), seat(gameId));

// --------------------------------------------------------------------------- next-game deck queue

export interface QueuedDeck { name: string; commanders: string[]; commander_ids: string[]; color_identity: string[]; card_count: number }

export const getNextDeck = (gameId: string) => api.get<{ queued: QueuedDeck | null }>(path(gameId, "next-deck"), seat(gameId));
export const queueNextDeck = (gameId: string, body: LobbyDeckBody) =>
  api.post<{ queued: QueuedDeck }>(path(gameId, "next-deck"), body, seat(gameId));
export const clearNextDeck = (gameId: string) => api.del<void>(path(gameId, "next-deck"), seat(gameId));

// --------------------------------------------------------------------------- the host's switch for reactions

export const setTableReactions = (gameId: string, on: boolean) =>
  api.post<{ reactions: boolean }>(path(gameId, "night/reactions"), { on }, seat(gameId));
