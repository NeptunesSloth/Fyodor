/**
 * Rules intents from the table (docs/AUTOMATION_UX.md, docs/3D_DIRECTION.md §1a).
 *
 * With automation on, a gesture becomes an intent: dragging a land from your hand onto your
 * battlefield plays it, dragging a spell onto the table or the stack casts it. The server checks
 * everything and answers with prompts; the client never decides legality. Holding Alt (the manual
 * override) keeps the old behaviour: the card just moves, logged as done by hand.
 */
import { perspective, useGame } from "../../state/gameStore";
import { useCardCache } from "../../state/cardCache";
import type { Action, GameView, PaymentMode, ResponseMode } from "../../types/game";
import { splitZone } from "../../types/game";
import type { DropResult } from "../dnd";

export const send = (action: Action) => useGame.getState().send(action);

export function automationOn(view: GameView | null): boolean {
  return !!view?.rules && !view.rules.paused;
}

export function isLand(cardId: string, view: GameView): boolean {
  const c = view.cards[cardId];
  if (!c || c.hidden || !c.card_id) return false;
  const data = useCardCache.getState().cards[c.card_id];
  const typeLine = data?.faces?.[c.face ?? 0]?.type_line ?? data?.type_line ?? "";
  return /\bLand\b/.test(typeLine);
}

/** Try to handle a drop as a rules intent. Returns true when it did (the caller does nothing). */
export function dropAsIntent(ids: string[], target: DropResult | null, seat?: string): boolean {
  const { view, actingAs } = useGame.getState();
  if (!view || !target || target.manual || !automationOn(view) || ids.length !== 1) return false;
  const me = seat ?? perspective(view, actingAs);
  const id = ids[0];
  const card = id ? view.cards[id] : undefined;
  if (!card) return false;
  const from = splitZone(card.zone);
  const to = splitZone(target.zone);
  const fromHandOrCommand = (from.zone === "hand" || from.zone === "command") && from.player === me;
  if (!fromHandOrCommand) return false;
  if (to.zone === "battlefield" && to.player === me && from.zone === "hand" && isLand(card.id, view)) {
    void send({ type: "play_land", card_id: card.id, ...(target.x != null ? { x: target.x, y: target.y } : {}) });
    return true;
  }
  if ((to.zone === "battlefield" && to.player === me) || to.zone === "stack") {
    void send({ type: "cast_spell", card_id: card.id });
    return true;
  }
  return false;
}

export const passPriority = (until?: string) => send({ type: "pass_priority", ...(until ? { until } : {}) });
export const choose = (decisionId: string, optionIds: string[], remember?: string) =>
  send({ type: "choose", decision_id: decisionId, option_ids: optionIds, ...(remember ? { remember } : {}) });
export const setPrefs = (patch: Record<string, unknown>) => send({ type: "set_prefs", ...patch });

export const RESPONSE_CYCLE: ResponseMode[] = ["off", "auto", "on"];
export const PAYMENT_CYCLE: PaymentMode[] = ["auto", "ask", "manual"];

export function next<T>(cycle: T[], current: T): T {
  return cycle[(cycle.indexOf(current) + 1) % cycle.length] ?? current;
}

/** The ability lines of a card's Oracle text, the way the server indexes them (reminder text removed). */
export function abilityLines(oracle: string): string[] {
  return oracle
    .split("\n")
    .map((line) => line.replace(/\s*\([^()]*\)/g, "").trim())
    .filter(Boolean);
}
