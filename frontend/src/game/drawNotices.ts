import { create } from "zustand";
import type { GameView } from "../types/game";

/**
 * -- draw notice -- what I just drew, for me only (DrawNotice.tsx), as MTG Arena shows it. Built only from my own view: cards that are
 * new in MY hand zone and came from my library (unknown to me a moment ago, or known there: the top of my library I looked at). A card
 * that was somewhere I could see it (bounced, undone, returned from exile, a tutor's search) isn't a draw. Opponents never get one:
 * their hands aren't in my view, and the public log line ("Alice drew 3 cards") is all the table sees.
 */

export type DrawNoticePref = "all" | "effects" | "off";

export interface DrawEvent {
  ids: string[];
  /** Drawn by an effect (a trigger, a spell, a loop, a manual draw), not the draw step's one card. */
  effect: boolean;
}

/** The cards drawn into `me`'s hand between two views, or null (nothing drawn, or nothing worth a notice: the opening hand, a tutor). */
export function newDraws(prev: GameView | null | undefined, next: GameView, me: string): DrawEvent | null {
  if (!prev || prev.game.id !== next.game.id) return null;
  if (next.pregame && !next.pregame.finished) return null; // opening hands and mulligans
  const key = `${me}:hand`;
  const before = prev.zones[key];
  const after = next.zones[key];
  if (!Array.isArray(after) || !Array.isArray(before)) return null;
  // a search of my library (a tutor) puts cards in my hand from the library: that isn't a draw
  if (prev.searches[me] || next.searches[me] || prev.my_views?.some((v) => v.kind === "search")) return null;
  const had = new Set(before);
  const library = `${me}:library`;
  const ids = after.filter((id) => {
    if (had.has(id)) return false;
    const was = prev.cards[id];
    return !was || was.zone === library;
  });
  if (!ids.length) return null;
  const drawStep = next.turn.phase === "draw" && next.turn.active_player === me && ids.length === 1 && !next.stack.length && !prev.stack.length;
  return { ids, effect: !drawStep };
}

/** Whether a draw gets a notice under the player's setting. */
export function wantsNotice(pref: DrawNoticePref, ev: DrawEvent): boolean {
  return pref === "all" || (pref === "effects" && ev.effect);
}

/** One notice, however many draws feed it (a draw loop is one notice with a count, never a flood). */
export interface DrawBatch {
  key: number;
  ids: string[];
}

/** Faces a notice shows at most; the rest are a "+N". */
export const NOTICE_FACES = 8;

/** Add a draw to the notice on screen (if it's still up) or start a new one. */
export function mergeBatch(cur: DrawBatch | null, ids: string[], key: number): DrawBatch {
  if (!cur) return { key, ids: [...ids] };
  const seen = new Set(cur.ids);
  return { key: cur.key, ids: [...cur.ids, ...ids.filter((id) => !seen.has(id))] };
}

/** What a notice shows: the first NOTICE_FACES faces, and how many more were drawn. */
export function noticeFaces(batch: DrawBatch): { faces: string[]; more: number } {
  const faces = batch.ids.slice(0, NOTICE_FACES);
  return { faces, more: batch.ids.length - faces.length };
}

/** "You drew Lightning Bolt, Island and 2 more" (names as my view has them). */
export function drewLine(names: string[], total: number, limit = 4): string {
  if (!total) return "";
  const listed = names.slice(0, Math.min(limit, names.length));
  const rest = total - listed.length;
  if (!rest) return listed.length === 1 ? listed[0]! : `${listed.slice(0, -1).join(", ")} and ${listed[listed.length - 1]}`;
  return `${listed.join(", ")} and ${rest} more`;
}

/** The cards I drew and haven't looked at yet (highlighted in my hand until hovered, or until the turn moves on). */
export const useFreshDraws = create<{ ids: string[]; turn: number; add: (ids: string[], turn: number) => void; seen: (id: string) => void; clear: () => void }>((set, get) => ({
  ids: [],
  turn: 0,
  add: (ids, turn) => set((s) => ({ ids: s.turn === turn ? [...s.ids, ...ids.filter((id) => !s.ids.includes(id))] : [...ids], turn })),
  seen: (id) => { if (get().ids.includes(id)) set((s) => ({ ids: s.ids.filter((x) => x !== id) })); },
  clear: () => set({ ids: [] }),
}));
