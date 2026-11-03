/**
 * Pings, as in Tabletop Simulator: point at a card or a spot and everyone at the table sees "Alice: here".
 * This module answers two questions for both tables: what is under the pointer (a card everyone can see, or a
 * spot on a battlefield), and where a ping lands on this screen. The 3D table registers its own answers.
 */
import type { PingTarget } from "../services/night";
import type { GameView } from "../types/game";
import { findDropTarget } from "./dnd";
import { BF_H, BF_W, toPixels } from "./geometry";

export interface ScreenPoint { x: number; y: number }

interface Locator3D {
  /** the card, or the battlefield spot, under a client point on the canvas */
  targetAt(clientX: number, clientY: number): PingTarget | null;
  card(id: string): ScreenPoint | null;
  spot(player: string, x: number, y: number): ScreenPoint | null;
}

let locator3d: Locator3D | null = null;
export function setPingLocator3D(l: Locator3D | null): void {
  locator3d = l;
}

const PUBLIC_ZONES = new Set(["battlefield", "graveyard", "exile", "command", "stack"]);

/** Cards anyone can see: the server refuses the rest (pointing at a hidden card would give away its id). */
export function pingable(view: GameView, id: string): boolean {
  const c = view.cards[id];
  if (!c || ("hidden" in c && c.hidden)) return false;
  if ("face_down" in c && c.face_down) return false;
  return PUBLIC_ZONES.has(c.zone.split(":").pop() ?? "");
}

/** What a ping at this point would point at, or null when there is nothing to point at there. */
export function pingTargetAt(view: GameView, clientX: number, clientY: number): PingTarget | null {
  for (const el of document.elementsFromPoint(clientX, clientY)) {
    if (!(el instanceof HTMLElement)) continue;
    if (el.dataset.drop3d !== undefined) {
      const hit = locator3d?.targetAt(clientX, clientY) ?? null;
      if (hit && "card" in hit && !pingable(view, hit.card)) return null;
      return hit;
    }
    if (el.closest(".hand")) return null; // your own hand is private
    const card = el.closest<HTMLElement>("[data-card-id]")?.dataset.cardId;
    if (card) return pingable(view, card) ? { card } : null;
  }
  const drop = findDropTarget(clientX, clientY, 0, 0);
  if (drop?.zone.endsWith(":battlefield") && drop.x !== undefined && drop.y !== undefined) {
    return { player: drop.zone.split(":")[0]!, x: drop.x, y: drop.y };
  }
  return null;
}

/** Where a ping shows on this screen (client px), or null when its card or seat isn't on screen. */
export function pingPoint(target: PingTarget): ScreenPoint | null {
  if (document.querySelector("[data-drop3d]")) {
    return "card" in target ? locator3d?.card(target.card) ?? null : locator3d?.spot(target.player, target.x, target.y) ?? null;
  }
  if ("card" in target) {
    const el = document.querySelector(`.battlefield [data-card-id="${CSS.escape(target.card)}"]`)
      ?? document.querySelector(`.chain-list [data-card-id="${CSS.escape(target.card)}"]`)
      ?? document.querySelector(`main.table [data-card-id="${CSS.escape(target.card)}"]:not(.hand *)`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  const bf = document.querySelector<HTMLElement>(`[data-drop="${CSS.escape(`${target.player}:battlefield`)}"][data-battlefield]`);
  if (!bf) return null;
  const r = bf.getBoundingClientRect();
  const [px, py] = toPixels(Math.max(0, Math.min(BF_W, target.x)), Math.max(0, Math.min(BF_H, target.y)), r.width, r.height,
    Number(bf.dataset.cardh ?? 0), bf.dataset.mirrored !== undefined);
  return { x: r.left + px, y: r.top + py };
}
