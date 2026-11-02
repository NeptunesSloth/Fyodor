import { SPECTATOR, type GameView } from "../types/game";

/*
 * -- final board -- after a recorded result the table is the final board (docs/3D_DIRECTION.md §7a "View final board"):
 * anyone may close the result panel and look around (either renderer, the camera, card details, the log); nothing changes it.
 * The server refuses every change (`Night.final_board`); the client doesn't send what it would refuse, so a drag on the
 * finished table snaps back quietly instead of failing. The rematch vote is the server's and survives closing the panel.
 */

/** Table talk, and closing a private look at cards (it only hides them again), stay open after the result (as on the server). */
const POSTGAME_ACTIONS = new Set(["chat", "end_view"]);

export const FINAL_BOARD_NOTE = "The game is over: the final board can be looked at but not changed.";

/** Why the client won't send this action (the game has a result), or null. */
export function finalBoardRefusal(view: Pick<GameView, "game"> | null, actionType: string): string | null {
  if (!view?.game.night?.result || POSTGAME_ACTIONS.has(actionType)) return null;
  return FINAL_BOARD_NOTE;
}

export interface BoardBar {
  /** "Game 2 · Ann wins", "Game 3 · Draw". */
  line: string;
  /** "Votes 2/4" at a LAN table (null at a hot-seat one, where one click decides). */
  votes: string | null;
  /** This seat's own choice so far, if it made one. */
  mine: "rematch" | "lobby" | null;
}

/** What the small bar over the final board says (the result, and how far the vote is), or null before a result. */
export function boardBar(view: GameView, me: string): BoardBar | null {
  const night = view.game.night;
  const result = night?.result;
  if (!night || !result) return null;
  const local = view.game.mode === "local";
  const what = result.result_type === "draw" ? "Draw" : result.result_type === "no_result" ? "No result"
    : `${result.winner_names.join(" & ")} ${result.winners.length > 1 ? "win" : "wins"}`;
  const voters = view.seat_order.filter((pid) => local || view.game.seats[pid]?.claimed);
  const voted = voters.filter((pid) => night.votes[pid]).length;
  const seated = view.viewer !== SPECTATOR && view.seat_order.includes(me);
  return {
    line: `Game ${night.number} · ${what}`,
    votes: local ? null : `Votes ${voted}/${voters.length}`,
    mine: seated ? night.votes[me] ?? null : null,
  };
}
