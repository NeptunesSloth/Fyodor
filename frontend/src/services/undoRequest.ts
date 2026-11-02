import { api } from "./api";
import { seatToken } from "./games";
import type { GameView } from "../types/game";

/** -- quick undo request -- ask the table to undo the last action, or answer the request (server: app/game/undo_requests.py). */
export type UndoRequestOp = "request" | "approve" | "decline" | "withdraw";

export const undoRequest = (gameId: string, op: UndoRequestOp, as?: string | null) => {
  const t = seatToken(gameId);
  return api.post<GameView>(`/games/${gameId}/undo-request`, { op, as: as ?? null }, t ? { "X-Seat-Token": t } : {});
};
