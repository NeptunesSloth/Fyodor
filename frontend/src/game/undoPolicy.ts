import type { GameView, UndoPolicy } from "../types/game";

/**
 * The host's undo setting (server: app/game/undo_rights.py, which decides; this only dims the controls and explains).
 * "everyone": anyone seated undoes anything. "own": a player takes back only their own actions (an intent and the rules
 * follow-ups compiled into it are one action; another player's answer is theirs). "host": only the host (at a hot-seat
 * table everyone sits at the host computer, so it allows everyone there).
 */
export const UNDO_POLICIES: { id: UndoPolicy; label: string; hint: string }[] = [
  { id: "everyone", label: "Everyone", hint: "Anyone at the table can undo any action" },
  { id: "own", label: "Own actions only", hint: "Players can only undo their own actions" },
  { id: "host", label: "Host only", hint: "Only the host can undo" },
];

export type UndoOp = "undo" | "redo";

/** Who an undo from this browser is performed as: the seat (LAN), or the hot-seat player acting now. */
export function undoActor(view: GameView, actingAs: string | null): string | null {
  if (view.viewer in view.game.seats) return view.viewer;
  if (view.game.mode !== "local") return null; // a spectator
  return actingAs && view.seat_order.includes(actingAs) ? actingAs : view.turn.active_player;
}

/**
 * Why `actor` can't undo (redo) the next history entry under the table's undo setting, or null (also when there is
 * nothing to undo). `by`: whose entry it is, when the caller knows better than the view (the action it just sent).
 */
export function undoRefusal(view: GameView, actor: string | null, op: UndoOp = "undo", by?: string | null): string | null {
  const g = view.game;
  if (!actor) return `Spectators can't ${op}.`;
  const policy = g.settings.undo_policy ?? "everyone";
  if (policy === "host" && !g.undo_host) return `Only the host may ${op} at this table (the host's undo setting).`;
  if (policy !== "own") return null;
  const owner = by !== undefined ? by : op === "undo" ? g.undo_by : g.redo_by;
  if (!owner || owner === actor) return null;
  const name = view.players.find((p) => p.id === owner)?.name;
  const which = op === "undo" ? "the last action" : "the next action to redo";
  return `Players may only ${op} their own actions at this table: ${which} was ${name ? `${name}'s` : "another player's"}.`;
}
