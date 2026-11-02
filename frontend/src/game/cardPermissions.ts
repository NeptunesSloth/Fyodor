import { splitZone, type Action, type CardPermissions, type GameCard, type GameView } from "../types/game";

/**
 * -- table permissions -- the host's "Who may change a player's cards" setting. The server decides (app/game/table_rights.py);
 * this only keeps the table from offering what it would refuse: the card menu shows a card's edits only to whoever may make
 * them, and an edit sent anyway (a drag, a hotkey) is put back with the reason instead of failing.
 *
 * "owner": a player's cards are theirs to change, and the host can always help. Whose: on the battlefield and the stack, the
 * controller (a creature I stole is mine to tap and move until it goes back); in a hidden zone (hand, library…), that zone's
 * player; in any other zone, the owner and the player whose zone holds it (my card in your exile: both of us). Rules actions (casting, combat, everything the engine does), looking, arrows,
 * life and other player counters, and the table's procedures (resolve, phases, next turn) are never limited. A hot-seat table
 * ignores the setting: everyone sits at the host computer.
 */
export const CARD_PERMISSIONS: { id: CardPermissions; label: string; hint: string }[] = [
  { id: "everyone", label: "Everyone", hint: "Anyone at the table can move, tap and change any card, as at a real table" },
  {
    id: "owner",
    label: "Each player (and the host)",
    hint: "Only a card's player can move, tap or change it: the permanents and spells they control, the cards they own elsewhere. The host can always help. Casting, combat and everything the rules do stay open, as do life totals, arrows and looking",
  },
];

const HIDDEN_ZONES = new Set(["library", "hand", "sideboard", "foretell", "setaside", "attractions"]);

/** The seats who may change `card` under "owner" (the host aside), most responsible first. */
export function cardKeepers(card: Pick<GameCard, "zone" | "owner" | "controller">): string[] {
  const { player, zone } = splitZone(card.zone);
  if (zone === "stack" || zone === "battlefield" || zone === "phased") return [card.controller];
  if (HIDDEN_ZONES.has(zone) && player) return [player]; // whose hand / library it is (a hidden card's owner is not public)
  return [...new Set([card.owner, player].filter((p): p is string => !!p))];
}

/** The seat whose edits the setting limits in this browser, or null: everyone may, a hot-seat table, the host, a spectator. */
export function limitedSeat(view: GameView): string | null {
  const g = view.game;
  if ((g.settings?.card_permissions ?? "everyone") !== "owner" || g.mode === "local") return null;
  if (!(view.viewer in g.seats) || g.host_seat === view.viewer) return null;
  return view.viewer;
}

function refusalFor(view: GameView, who: string[]): string {
  const names = who.map((pid) => view.players.find((p) => p.id === pid)?.name ?? pid);
  return `${names[0]}'s cards: only ${names.join(", ")} or the host can change them at this table.`;
}

/** Why this browser may not change these cards (the server would refuse it), or null. */
export function cardEditRefusal(view: GameView, ids: string[]): string | null {
  const me = limitedSeat(view);
  if (!me) return null;
  for (const id of ids) {
    const card = view.cards[id];
    if (!card) continue;
    const who = cardKeepers(card);
    if (!who.includes(me)) return refusalFor(view, who);
  }
  return null;
}

// the manual table actions the server checks (app/game/table_rights.py), by the field naming what they change
const CARD_IDS = new Set([
  "move", "tap", "phase_shift", "counter", "delete_card", "face_down", "set_controller", "add_effect", "remove_effect", "set_damage",
  "set_exile_group", "return_to_owner", "rotate", "set_lock", "set_protect", "detach", "group", "ungroup", "merge_tokens", "attack", "attach",
]);
const CARD_ID = new Set([
  "set_counter", "set_face", "flip", "note", "set_choice", "set_stack_info", "set_copy_source", "set_commander", "stack_adjust",
  "split_stack", "expand_stack", "block",
]);
const PLAYER = new Set([
  "draw", "mill", "shuffle", "put_top_face_down", "cascade", "fetch_card", "discard_random", "untap_all", "reset_deck", "create_token",
  "copy_card", "spawn_card",
]);

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

/** The cards `action` changes as a manual table edit (none for actions the setting never limits). */
function touched(view: GameView, action: Action): string[] {
  const t = action.type;
  if (CARD_IDS.has(t)) return strings(action.card_ids);
  if (CARD_ID.has(t)) return strings([action.card_id]);
  if (t === "set_position") return strings(Array.isArray(action.moves) ? action.moves.map((m: unknown) => (Array.isArray(m) ? m[0] : null)) : []);
  if (t === "merge") return strings([action.card_id, action.spell_id]);
  if (t === "meld") return strings([action.card_id, action.other_id]);
  if (t === "cleanup") {
    const ids = strings(action.card_ids);
    if (ids.length) return ids;
    // "delete all tokens": the tokens the server would delete
    return strings(action.what).includes("tokens")
      ? Object.values(view.cards).filter((c) => !c.hidden && c.is_token && !c.protected && !c.commander_key).map((c) => c.id)
      : [];
  }
  return [];
}

/** Why the server would refuse `action` from this browser under the setting, or null (it may be sent). */
export function actionRefusal(view: GameView, action: Action): string | null {
  const me = limitedSeat(view);
  if (!me) return null;
  if (PLAYER.has(action.type)) {
    const pid = typeof action.player === "string" ? action.player : me;
    if (pid !== me && view.players.some((p) => p.id === pid)) return refusalFor(view, [pid]);
  }
  return cardEditRefusal(view, touched(view, action));
}
