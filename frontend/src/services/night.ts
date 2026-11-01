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

export interface OwnDeckCard { section: string; quantity: number; name: string; printing_id: string | null }

/** The deck this seat brought to the current game (only ever your own). */
export const ownDeck = (gameId: string, viewer?: string) =>
  api.get<{ name: string | null; cards: OwnDeckCard[] }>(`/games/${gameId}/night/deck${viewer ? `?viewer=${encodeURIComponent(viewer)}` : ""}`, seat(gameId));

export const REACTIONS = ["👍", "😂", "😮", "🔥", "💀", "👏"] as const;

export const sendSignal = (gameId: string, kind: "nudge" | "react", emoji?: string, as?: string) =>
  api.post(`/games/${gameId}/night/signal`, { kind, emoji: emoji ?? null, as_player: as ?? null }, seat(gameId));

export type PingTarget = { card: string } | { player: string; x: number; y: number };

/** "Look here" for everyone at the table (a card everyone can see, or a spot on a battlefield). */
export const sendPing = (gameId: string, target: PingTarget, as?: string) =>
  api.post(`/games/${gameId}/night/signal`, { kind: "ping", ...target, as_player: as ?? null }, seat(gameId));

// --------------------------------------------------------------------------- the elimination hub (docs/ELIMINATION_HUB.md)

/** Your private practice table for this game (resumed if you have one). `viewer`: your seat at a hot-seat table. */
export const openPractice = (gameId: string, opts: { viewer?: string; reset?: boolean } = {}) =>
  api.post<{ game_id: string; token: string; resumed: boolean }>(`/games/${gameId}/practice`,
    { viewer: opts.viewer ?? null, reset: !!opts.reset }, seat(gameId));

export const closePractice = (gameId: string, viewer?: string) =>
  api.del<void>(`/games/${gameId}/practice${viewer ? `?viewer=${encodeURIComponent(viewer)}` : ""}`, seat(gameId));

/** A copy of the deck you brought: a new library deck on the host computer (`deck_id`), else the list for My decks. */
export const deckLabCopy = (gameId: string, viewer?: string) =>
  api.post<{ deck_id: string | null; name: string; text: string; commanders: string[] }>(`/games/${gameId}/deck-lab`,
    { viewer: viewer ?? null }, seat(gameId));
