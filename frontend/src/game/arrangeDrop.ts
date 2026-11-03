/**
 * Dragging a card along its own arranged board reorders it on this screen only (game/arrange.ts): nothing is sent.
 * Each arranged battlefield publishes its current layout here, so a drop can find the slot it landed in.
 */
import { create } from "zustand";
import { useGame } from "../state/gameStore";
import type { DropResult } from "./dnd";
import { BF_H, BF_W } from "./geometry";
import { reorderOnDrop, saveBoardOrder, type BoardLayout } from "./arrange";

interface Board { layout: BoardLayout; width: number; height: number; mirrored: boolean }
const boards = new Map<string, Board>();

/** Bumped when my order changes (it lives in session storage, outside React). */
export const useBoardOrderTick = create<{ n: number; bump: () => void }>((set) => ({ n: 0, bump: () => set((s) => ({ n: s.n + 1 })) }));

export function publishBoard(zone: string, layout: BoardLayout | null, width: number, height: number, mirrored: boolean): void {
  if (layout) boards.set(zone, { layout, width, height, mirrored });
  else boards.delete(zone);
}

/** A drop of `ids` on the arranged board they're already on: reorder them there. False: not an arranged reorder (drop as usual). */
export function reorderArranged(ids: string[], from: string, target: DropResult | null): boolean {
  if (!target || target.zone !== from || target.x == null) return false;
  const board = boards.get(from);
  const gameId = useGame.getState().view?.game.id;
  if (!board || !gameId) return false;
  // back from the drop's virtual units to this mat's px (an opponent's mat is mirrored: see dnd.findDropTarget)
  const y = target.y == null ? undefined : board.mirrored
    ? board.height - (target.y / BF_H) * board.height - board.layout.h
    : (target.y / BF_H) * board.height;
  const order = reorderOnDrop(board.layout, ids, (target.x / BF_W) * board.width, y);
  if (!order) return true; // dropped where it was: nothing to do (and never a server move)
  saveBoardOrder(gameId, from, order);
  useBoardOrderTick.getState().bump();
  return true;
}
