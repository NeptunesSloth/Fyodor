import { toast } from "../components/Toasts";
import { SPECTATOR, type GameView } from "../types/game";
import type { HotkeyId } from "./hotkeys";

/*
 * -- out of the game -- a seated player who conceded or lost has left the game (800.4a; 104.3a) and watches it go on. The
 * server refuses what would move the game for them (app/game/out_of_game.py); the table stops inviting them to: no "press D
 * to draw", no seat buttons, read-only counters, keys that would move the game do nothing (the server's reason, once), and
 * an action sent anyway is not sent (the reason instead of an error).
 */

/** Out of the game: the turn dial's own test ("You're out — watching"). A spectator is just watching. */
export function isOut(view: GameView | null | undefined, me: string | null | undefined): boolean {
  const r = view?.rules;
  return !!view && !!me && view.viewer !== SPECTATOR && !!r && (r.conceded.includes(me) || me in r.lost);
}

/** The server's own words (app/game/out_of_game.py), or null while `me` is still in the game. */
export function outReason(view: GameView | null | undefined, me: string | null | undefined): string | null {
  if (!isOut(view, me)) return null;
  const how = view!.rules!.conceded.includes(me!) ? "conceded" : "lost";
  return `You're out of this game (you ${how}): you can watch and chat, but not move the game.`;
}

// What the server still takes from a player who is out (app/game/out_of_game.py OUT_MAY): the rules intents (the engine
// answers those itself), and what anyone watching at the table does.
const RULES_INTENTS = [
  "play_land", "cast_spell", "activate_ability", "declare_attackers", "declare_blockers", "pass_priority", "choose", "concede", "set_stops",
  "set_prefs", "set_card_automation", "repeat_sequence", "turn_face_up", "unlock_door", "miracle_reveal", "end_effect", "pay_deferred",
];
const OUT_MAY = new Set([
  ...RULES_INTENTS, "chat", "roll", "coin", "rename_player", "set_appearance", "end_view", "response_pass", "response_auto", "configure",
  "remove_player", "set_table_playmat", "restart_game", "mulligan_finish",
]);

/** Why the server would refuse this action from `actor` (the seat it is sent as), or null: it may be sent. */
export function outRefusal(view: GameView | null | undefined, actor: string | null | undefined, actionType: string): string | null {
  return OUT_MAY.has(actionType) ? null : outReason(view, actor);
}

/**
 * The shortcuts that would move the game: they send what the server refuses from a player who is out. Looking around (the
 * camera and focus keys), the log, help, pings, dice, the hand's sort, closing a look, auto-pass and undo (the table's undo
 * setting decides that one) keep working.
 */
export const MOVING_KEYS: ReadonlySet<HotkeyId> = new Set<HotkeyId>([
  "tap", "draw", "next_step", "next_turn", "untap_all", "turn_over", "to_graveyard", "respond",
]);

const told = new Set<string>();

/**
 * A shortcut pressed by `me`: true when it would move the game and `me` is out, so it does nothing. The first such key in a
 * game says why (the server's reason); the ones after it stay quiet.
 */
export function outKeyBlocked(view: GameView | null | undefined, me: string | null | undefined, id: HotkeyId, say: (text: string) => void = (t) => toast(t, "info")): boolean {
  if (!MOVING_KEYS.has(id)) return false;
  const why = outReason(view, me);
  if (!why) return false;
  const key = `${view!.game.id}:${view!.game.night?.number ?? 0}:${me}`;
  if (!told.has(key)) {
    told.add(key);
    say(why);
  }
  return true;
}
