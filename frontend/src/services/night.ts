import { api } from "./api";
import { seatToken } from "./games";
import type { NightResultType } from "../types/game";

/** Game night calls (docs/GAME_NIGHT_FLOW.md). At a hot-seat table `as` says which player answers. */
const seat = (gameId: string): Record<string, string> => {
  const t = seatToken(gameId);
  return t ? { "X-Seat-Token": t } : {};
};

export const proposeEnd = (gameId: string, result_type: NightResultType, winners: string[], as?: string) =>
  api.post(`/games/${gameId}/night/propose`, { result_type, winners, as_player: as ?? null }, seat(gameId));

export const answerProposal = (gameId: string, agree: boolean, as?: string) =>
  api.post(`/games/${gameId}/night/answer`, { agree, as_player: as ?? null }, seat(gameId));

export const voteNext = (gameId: string, choice: "rematch" | "lobby", opts: { as?: string; force?: boolean } = {}) =>
  api.post<{ decision: "rematch" | "lobby" | null }>(`/games/${gameId}/night/vote`,
    { choice, as_player: opts.as ?? null, force: !!opts.force }, seat(gameId));
