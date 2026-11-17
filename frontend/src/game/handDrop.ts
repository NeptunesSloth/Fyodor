/**
 * Dragging a card from your hand (or your commander from the command zone) onto the table, with rules automation on,
 * plays it: a land is played, anything else is cast, through the same intents as the card's menu (game/rules/intents.ts
 * `dropAsIntent`: the server then asks for mana, targets, X, modes). The server decides; a refusal shows its message
 * and the card stays where it was. Both tables (2D and 3D) and the hand go through here, so a drop means the same thing
 * on either.
 *
 * Holding Alt as you let go is the manual override: the card is placed by hand, as with automation off (manual tabletop
 * freedom is never removed). With automation off (or paused) a drag is always a plain move.
 */
import { toast } from "../components/Toasts";
import { perspective, useGame } from "../state/gameStore";
import { splitZone } from "../types/game";
import type { DropResult } from "./dnd";
import { automationOn, dropAsIntent, isLand, send } from "./rules/intents";

/**
 * What a drop means:
 * - `play`: play or cast it (a rules intent);
 * - `many`: several cards dragged at once onto the table: cast one at a time (nothing moves);
 * - `move`: a plain move (automation off or paused, Alt held, not from your hand, or not onto the table).
 */
export type HandDropKind = "play" | "many" | "move";

export interface HandDropFacts {
  automation: boolean;
  /** Alt was held: place it by hand. */
  manual: boolean;
  /** The dragged card's zone key ("p1:hand"). */
  from: string;
  /** The drop target's zone key, or null off the table. */
  to: string | null;
  me: string;
  count: number;
}

/** Onto the table: any battlefield (a cast permanent enters under its caster's control wherever it was dropped) or the stack. */
export function ontoTable(to: string | null): boolean {
  if (!to) return false;
  if (to === "stack") return true;
  return splitZone(to).zone === "battlefield";
}

export function handDropKind(f: HandDropFacts): HandDropKind {
  if (!f.automation || f.manual || !ontoTable(f.to)) return "move";
  const from = splitZone(f.from);
  if ((from.zone !== "hand" && from.zone !== "command") || from.player !== f.me) return "move";
  return f.count === 1 ? "play" : "many";
}

/** The caption the drag shows over the table: what letting go will do (null: nothing to say). */
export function dropCaption(kind: HandDropKind, land: boolean, manualOverTable: boolean): string | null {
  if (kind === "play") return `${land ? "Play land" : "Cast"} · Alt: place by hand`;
  if (kind === "many") return "Cast one card at a time · Alt: place by hand";
  return manualOverTable ? "Place by hand" : null;
}

/** The facts for a drag of `ids` onto `to`, from the store (null: no game). */
export function dropFacts(ids: string[], to: string | null, manual: boolean, seat?: string): HandDropFacts | null {
  const { view, actingAs } = useGame.getState();
  const card = ids[0] ? view?.cards[ids[0]] : undefined;
  if (!view || !card) return null;
  return { automation: automationOn(view), manual, from: card.zone, to, me: seat ?? perspective(view, actingAs), count: ids.length };
}

/**
 * Handle a drop from the hand or command zone as a play when automation is on. True when it was handled (the caller
 * does nothing more: on a refusal the card simply stays put); false for a plain move.
 */
export function dropFromHand(ids: string[], target: DropResult | null, seat?: string): boolean {
  if (!target) return false;
  const facts = dropFacts(ids, target.zone, !!target.manual, seat);
  if (!facts) return false;
  const kind = handDropKind(facts);
  if (kind === "move") return false;
  if (kind === "many") {
    toast("Cast one card at a time (hold Alt as you drop to place them by hand)", "info");
    return true;
  }
  const view = useGame.getState().view!;
  const id = ids[0]!;
  const mine = `${facts.me}:battlefield`;
  // dropped on someone else's side (or the stack): it's still mine to play, onto my side (where it lands is the server's
  // choice; only my own mat's spot is passed on)
  const at = target.zone === mine ? target : { zone: target.zone === "stack" ? "stack" : mine };
  // a land the engine says I can play (even before its card data has loaded here) is played, not cast
  if (splitZone(facts.from).zone === "hand" && !isLand(id, view) && view.rules?.hints?.playable_lands?.includes(id)) {
    void send({ type: "play_land", card_id: id, ...(at.x != null ? { x: at.x, y: at.y } : {}) });
    return true;
  }
  if (dropAsIntent(ids, { ...at, zone: at.zone === "stack" && isLand(id, view) ? mine : at.zone }, facts.me)) return true;
  toast("This card can't be played from here: hold Alt as you drop to place it by hand", "info");
  return true;
}
