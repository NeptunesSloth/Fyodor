import type { GameView, UndoPolicy } from "../types/game";
import { outReason } from "./outOfGame";

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
  const out = historyOut(view, actor);
  if (out) return out;
  const policy = g.settings.undo_policy ?? "everyone";
  if (policy === "host" && !g.undo_host) return `Only the host may ${op} at this table (the host's undo setting).`;
  if (policy !== "own") return null;
  const owner = by !== undefined ? by : op === "undo" ? g.undo_by : g.redo_by;
  if (!owner || owner === actor) return null;
  const name = view.players.find((p) => p.id === owner)?.name;
  const which = op === "undo" ? "the last action" : "the next action to redo";
  return `Players may only ${op} their own actions at this table: ${which} was ${name ? `${name}'s` : "another player's"}.`;
}

/**
 * -- out of the game (gaps5) -- a player who conceded or lost doesn't take the live game's actions back (server:
 * app/game/out_of_game.py history_refusal, in the same words); the host still does, so a mistaken concession can be taken back.
 */
function historyOut(view: GameView, actor: string | null): string | null {
  return view.game.undo_host ? null : outReason(view, actor);
}

/**
 * -- quick undo request -- what the Undo button does for `actor` now: undo directly, ask the table first (the server says
 * why: the undo setting refuses it, or the action showed hidden information or a random outcome), or nothing (refused, with
 * no one to ask; nothing to undo). Only the server decides; this reads its view.
 */
export type UndoMode =
  | { kind: "direct" }
  | { kind: "ask"; why: string }
  | { kind: "waiting"; why: string }
  | { kind: "refused"; why: string }
  | { kind: "none" };

export function undoMode(view: GameView, actor: string | null): UndoMode {
  const g = view.game;
  if (!g.can_undo) return { kind: "none" };
  const pending = g.undo_request;
  if (pending) {
    return { kind: "waiting", why: pending.by === actor ? "Your undo request is waiting for the table." : `${pending.by_name}'s undo request is waiting for the table.` };
  }
  const out = historyOut(view, actor);
  if (out) return { kind: "refused", why: out }; // (not "ask": a player who is out can't ask the table either)
  if (g.undo_ask) return { kind: "ask", why: g.undo_ask };
  const refused = undoRefusal(view, actor, "undo");
  return refused ? { kind: "refused", why: refused } : { kind: "direct" };
}

/** What the undo request bar shows this seat (`me`: the seat it acts as), or null when it shows nothing here. */
export interface UndoRequestSeat {
  /** "Bob asks to undo: cast Sol Ring" / "You asked to undo: draw". */
  title: string;
  /** Why it needed the table: what the action showed (null when the undo setting alone asked). */
  why: string | null;
  /** Who still has to answer (names). */
  waiting: string[];
  /** This seat answers now (Approve / Decline). */
  mustAnswer: boolean;
  /** This seat asked and may withdraw it. */
  mine: boolean;
}

export function undoRequestSeat(view: GameView, me: string | null): UndoRequestSeat | null {
  const r = view.game.undo_request;
  if (!r || !me || view.game.mode === "local") return null;
  const mine = r.by === me;
  const voter = r.voters.includes(me);
  if (!mine && !voter) return null; // spectators and players already out of the game don't answer it
  const name = (pid: string) => view.players.find((p) => p.id === pid)?.name ?? pid;
  return {
    title: mine ? `You asked to undo: ${r.label}` : `${r.by_name} asks to undo: ${r.label}`,
    why: r.why,
    waiting: r.waiting.map(name),
    mustAnswer: voter && r.waiting.includes(me),
    mine,
  };
}
