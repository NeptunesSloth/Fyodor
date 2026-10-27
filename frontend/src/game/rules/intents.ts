/**
 * Rules intents from the table (docs/AUTOMATION_UX.md, docs/3D_DIRECTION.md §1a).
 *
 * With automation on, a gesture becomes an intent: dragging a land from your hand onto your
 * battlefield plays it, dragging a spell onto the table or the stack casts it. The server checks
 * everything and answers with prompts; the client never decides legality. Holding Alt (the manual
 * override) keeps the old behaviour: the card just moves, logged as done by hand.
 */
import { create } from "zustand";
import { perspective, useGame } from "../../state/gameStore";
import { useCardCache } from "../../state/cardCache";
import type { Action, GameView, ResponseMode } from "../../types/game";
import { splitZone } from "../../types/game";
import type { DropResult } from "../dnd";

/** -- X announced (wave 24D) -- 107.3a, 601.2b: a cast or activation that needs X (the hints' `x_cast`, `activatable[].x`) waits here
 * for the player's number (the XPrompt in RulesHud); free and alternative-cost casts make X 0 on the server (107.3b). */
export const useXPrompt = create<{ action: Action | null; field: "x_value" | "kicker" | "chorus" }>(() => ({ action: null, field: "x_value" }));

export function needsX(view: GameView | null, a: Action): boolean {
  const h = view?.rules?.hints;
  if (!h || a.x_value !== undefined || a.free) return false;
  // -- wave 43D -- 107.3a: an alternative cost with {X} (harmonize, overload, surge, warp, bestow) and a kicker cost with {X} announce X too
  if (a.alt_cost !== undefined) return a.type === "cast_spell" && !!h.alt_castable?.[a.card_id as string]?.some((o) => o.id === a.alt_cost && o.x);
  if (a.type === "cast_spell") return !!h.x_cast?.includes(a.card_id as string) || (!!a.kicker && !!h.x_kicker?.includes(a.card_id as string));
  return a.type === "activate_ability" && !!h.activatable?.some((x) => x.card_id === a.card_id && x.ability === a.ability && x.x);
}

export const send = (action: Action): Promise<boolean> => {
  if (!needsX(useGame.getState().view, action)) return useGame.getState().send(action);
  useXPrompt.setState({ action, field: "x_value" });
  return Promise.resolve(true);
};

/** The platform numeric prompt closes before send, so a kicked cost with X may open its next prompt. */
export function submitNumericPrompt(text: string): boolean {
  const { action, field } = useXPrompt.getState();
  if (!action || !/^\d{1,4}$/.test(text) || Number(text) > 1000) return false;
  useXPrompt.setState({ action: null, field: "x_value" });
  void send({ ...action, [field]: Number(text) });
  return true;
}

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

const BASIC_TYPES = /\b(Plains|Island|Swamp|Mountain|Forest)\b/;

/** The index of a permanent's first mana ability, the way the server numbers abilities (a basic
 * land type's intrinsic "{T}: Add …" comes after the printed abilities). */
export function manaAbilityIndex(cardId: string, view: GameView): number | null {
  const c = view.cards[cardId];
  if (!c || c.hidden || !c.card_id) return null;
  const data = useCardCache.getState().cards[c.card_id];
  if (!data) return null;
  const face = data.faces?.[c.face ?? 0];
  const lines = abilityLines(face?.oracle_text ?? data.oracle_text ?? "");
  const i = lines.findIndex((l) => /^[^"]*\{T\}[^"]*: Add /.test(l));
  if (i >= 0) return i;
  const typeLine = face?.type_line ?? data.type_line ?? "";
  if (/\bLand\b/.test(typeLine) && BASIC_TYPES.test(typeLine.split("—")[1] ?? "")) return lines.length;
  const granted = view.rules?.stats?.[cardId]?.abilities?.find((a) => a.kind === "mana" && /\{T\}/.test(a.text));
  return granted ? granted.index : null;
}

/** With automation on, tapping one of your untapped mana sources taps it *for mana* (players
 * always tap their own mana; the engine never does it for them). Returns true when handled. */
export function tapForMana(cardId: string, seat?: string): boolean {
  const { view, actingAs } = useGame.getState();
  if (!view || !automationOn(view)) return false;
  const me = seat ?? perspective(view, actingAs);
  const c = view.cards[cardId];
  if (!c || c.hidden || c.tapped || c.face_down || c.controller !== me || !c.zone.endsWith(":battlefield")) return false;
  const d = view.rules?.decision;
  const pay = d && d.player === me && d.display?.kind === "tap_mana"
    ? (d.display as { sources?: string[]; convoke?: string[]; improvise?: string[] }) : null;
  if (pay && !pay.sources?.includes(cardId)) {
    // Not a mana source: commit it to pay part of the cost (or take it back). No mana is added.
    if (pay.convoke?.includes(cardId)) return payWith(cardId, "convoke");
    if (pay.improvise?.includes(cardId)) return payWith(cardId, "improvise");
  }
  const index = manaAbilityIndex(cardId, view);
  if (index == null) return false;
  void send({ type: "activate_ability", card_id: cardId, ability: index });
  return true;
}

/** Convoke / improvise: this creature / artifact pays one symbol of the spell's cost (click again
 * to take it back). The server taps it only when the whole cost is paid; it never adds mana. */
export function payWith(cardId: string, kind: "convoke" | "improvise"): boolean {
  void send({ type: "activate_ability", card_id: cardId, ability: 0, [kind]: true });
  return true;
}

/** Delve: this card from your graveyard pays {1} (during the payment prompt; exiled only when the
 * whole cost is paid; click again to take it back). */
export function delveCard(cardId: string): boolean {
  const { view, actingAs } = useGame.getState();
  const d = view?.rules?.decision;
  if (!view || !d || d.player !== perspective(view, actingAs) || d.display?.kind !== "tap_mana") return false;
  if (!((d.display as { delve?: string[] }).delve ?? []).includes(cardId)) return false;
  void send({ type: "activate_ability", card_id: cardId, ability: 0, delve: true });
  return true;
}

/** Tap / untap from a gesture (double-click, T, menu): one mana source taps for mana. */
export function tapGesture(ids: string[], tapPlain: (ids: string[]) => void): void {
  if (ids.length === 1 && tapForMana(ids[0]!)) return;
  tapPlain(ids);
}

export const passPriority = (until?: string) => send({ type: "pass_priority", ...(until ? { until } : {}) });
export const choose = (decisionId: string, optionIds: string[], remember?: string) =>
  send({ type: "choose", decision_id: decisionId, option_ids: optionIds, ...(remember ? { remember } : {}) });
/** Answer a "choose a card name" decision (CR 201.4): the typed Oracle name (the server checks it). */
export const chooseName = (decisionId: string, name: string) =>
  send({ type: "choose", decision_id: decisionId, option_ids: [], name });
/** Answer a "divide" decision (601.2d): an amount per option, in the options' order. */
export const divide = (decisionId: string, amounts: number[]) =>
  send({ type: "choose", decision_id: decisionId, option_ids: [], amounts });
export const setPrefs =(patch: Record<string, unknown>) => send({ type: "set_prefs", ...patch });
/** Concede (CR 104.3a): any time — with or without priority, during anyone's decision, while paused. */
export const concede = () => send({ type: "concede" });

/** Whether `me` may concede now: a seated player still in a game the rules engine runs, not over yet. */
export function canConcede(view: GameView | null, me: string | null): boolean {
  const rules = view?.rules;
  if (!view || !rules || !me || view.viewer === "__spectator__" || !view.seat_order.includes(me)) return false;
  return !rules.winner && !rules.draw_reason && !rules.conceded.includes(me) && !(me in (rules.lost ?? {}));
}

export const RESPONSE_CYCLE: ResponseMode[] = ["off", "auto", "on"];

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
