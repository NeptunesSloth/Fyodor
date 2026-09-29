/** Small helpers that build and send common actions. */
import type { FaceDownKind } from "../types/game";
import { useGame } from "../state/gameStore";
import type { Action, ZoneName } from "../types/game";

export const send = (action: Action) => useGame.getState().send(action);

export function moveCards(
  ids: string[],
  zone: ZoneName,
  opts: { player?: string | null; position?: "top" | "bottom"; index?: number; x?: number; y?: number; face_down?: boolean; face_down_kind?: FaceDownKind } = {},
) {
  if (!ids.length) return Promise.resolve(false);
  const action: Action = { type: "move", card_ids: ids, to: { zone, player: opts.player ?? null } };
  if (opts.position) action.position = opts.position;
  if (opts.index != null) action.index = opts.index;
  if (opts.x != null && opts.y != null) {
    action.x = opts.x;
    action.y = opts.y;
  }
  if (opts.face_down != null) action.face_down = opts.face_down;
  if (opts.face_down_kind) action.face_down_kind = opts.face_down_kind;
  return send(action);
}

export const tapCards = (ids: string[], tapped?: boolean) => send({ type: "tap", card_ids: ids, ...(tapped == null ? {} : { tapped }) });
export const addCounter = (ids: string[], kind: string, delta: number) => send({ type: "counter", card_ids: ids, kind, delta });
export const draw = (player: string, count = 1) => send({ type: "draw", player, count });
export const changeLife = (player: string, delta: number) => send({ type: "life", player, delta });
export const changeResource = (player: string, key: string, delta: number) => send({ type: "resource", player, key, delta });

/** Selection-aware target list: act on the whole selection when the clicked card is part of it. */
export function targetsFor(cardId: string): string[] {
  const { selection } = useGame.getState();
  return selection.includes(cardId) ? selection : [cardId];
}

export const COMMON_COUNTERS = ["+1/+1", "-1/-1", "loyalty", "charge", "shield", "stun", "time", "oil", "lore", "quest", "defense"];
