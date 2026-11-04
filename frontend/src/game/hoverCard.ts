/**
 * The large card preview's hover (game/Hud.tsx CardPreview), from the page's own card pictures: the hand, the stack, the
 * targeting tray, the payment and mulligan panels, the zone browser and exile's castables. The hover is set while the
 * pointer is on one and cleared when it leaves, and also when the element goes away under the pointer (a hand card
 * played, a stack entry resolved, a panel closed), which fires no pointerleave. The 3D table sets its own hover
 * (table3d/TableScene.ts setHover), and clears any left behind once the pointer is over empty table.
 */
import { useEffect } from "react";
import { useGame } from "../state/gameStore";

/** The element that last set the hover, and for which card. */
let owner: { id: string; el: HTMLElement } | null = null;

export interface HoverProps {
  onPointerEnter: (e: React.PointerEvent<HTMLElement>) => void;
  onPointerLeave: (e: React.PointerEvent<HTMLElement>) => void;
  /** React 19 runs the returned cleanup when the element unmounts. */
  ref: (el: HTMLElement | null) => (() => void) | undefined;
}

const clearIf = (id: string) => {
  const s = useGame.getState();
  if (s.hover === id) s.setHover(null);
};

const props = new Map<string, HoverProps>();

/**
 * The pointer handlers and ref for an element showing card `id` (spread them on it). One stable set per card, so a
 * re-render never looks like the element going away.
 */
export function hoverProps(id: string): HoverProps {
  let p = props.get(id);
  if (p) return p;
  p = {
    onPointerEnter: (e) => {
      owner = { id, el: e.currentTarget };
      useGame.getState().setHover(id);
    },
    onPointerLeave: (e) => {
      if (owner?.el === e.currentTarget) owner = null;
      clearIf(id);
    },
    ref: (el) => {
      if (!el) return undefined;
      return () => {
        if (owner?.el !== el || owner.id !== id) return;
        owner = null;
        clearIf(id);
      };
    },
  };
  props.set(id, p);
  return p;
}

/**
 * For a component that shows cards: `const hover = useHoverCard();` then `<li {...hover(id)}>`. Whatever it hovered is
 * cleared when its element goes away, and when the component unmounts.
 */
export function useHoverCard(): (id: string) => HoverProps {
  useEffect(() => () => {
    if (owner && !owner.el.isConnected) {
      const id = owner.id;
      owner = null;
      clearIf(id);
    }
  }, []);
  return hoverProps;
}

/** The element showing the hovered card on the page, while it is there (for the preview's dock). */
export function hoverElement(id: string): HTMLElement | null {
  return owner?.id === id && owner.el.isConnected ? owner.el : null;
}

/** Hide the preview until the next hover (its × and Esc), and let go of one held open (Hud.tsx CardPreview). */
export function clearHover(): void {
  owner = null;
  if (useGame.getState().hover) useGame.getState().setHover(null);
  if (typeof window !== "undefined" && typeof Event !== "undefined") window.dispatchEvent(new Event("fyodor:preview-close"));
}

/** Esc: closes the preview if one is showing (true: the key was used). */
export function previewKey(e: { key: string }): boolean {
  if (e.key !== "Escape" || !useGame.getState().hover) return false;
  clearHover();
  return true;
}

export interface Box { left: number; right: number; top: number; bottom: number }

/** The preview's width (CSS .card-preview) and its gap from the right edge of the screen. */
export const PREVIEW_W = 262;
export const PREVIEW_RIGHT_GAP = 12;

/**
 * Where the preview docks: on the right, always, whatever the pointer does; on the left only while the hovered card
 * itself lies under the right-docked panel (`panel`, its rectangle on the right).
 */
export function previewDock(card: Box | null, panel: Box): "left" | "right" {
  if (!card) return "right";
  const overlaps = card.left < panel.right && card.right > panel.left && card.top < panel.bottom && card.bottom > panel.top;
  return overlaps ? "left" : "right";
}

/** Space kept between the preview and the chrome around it. */
const GAP = 8;

/**
 * The first free stretch of the column x..x+w from `top` down to `bottom`, at least `minH` tall: past every obstacle
 * met in the column before that much room, and stopping above the next one (null: none).
 */
export function freeSlot(x: number, w: number, top: number, bottom: number, minH: number, obstacles: Box[]): { top: number; height: number } | null {
  const col = obstacles.filter((o) => o.left < x + w && o.right > x && o.bottom > top).sort((a, b) => a.top - b.top);
  let y = top;
  for (const o of col) {
    if (o.bottom <= y) continue;
    if (o.top - GAP - y >= minH) return { top: y, height: o.top - GAP - y };
    y = Math.max(y, o.bottom + GAP);
  }
  return bottom - y >= minH ? { top: y, height: bottom - y } : null;
}

/**
 * Where the preview goes: docked right under the top bar, as tall as the room before the next thing in that column (the
 * turn panel); on the left only while the hovered card itself lies under it, and then in the first column from the left
 * edge that is clear of the plates, strips and rails standing there (the battlefield gutter). `naturalH` is its height
 * at full size, for the hovered card's overlap; `maxH` the room it has (it shrinks its picture to fit).
 */
export function placePreview(o: { vw: number; vh: number; w: number; minH: number; top: number; naturalH: number; card: Box | null; obstacles: Box[] }):
  { side: "left" | "right"; left: number; top: number; maxH: number } {
  const bottom = o.vh - 12;
  const covers = (x: number, slot: { top: number; height: number }) => {
    const r = { left: x, right: x + o.w, top: slot.top, bottom: slot.top + Math.min(slot.height, o.naturalH) };
    return previewDock(o.card, r) === "left";
  };
  const rightX = o.vw - PREVIEW_RIGHT_GAP - o.w;
  const right = freeSlot(rightX, o.w, o.top, bottom, o.minH, o.obstacles);
  if (right && !covers(rightX, right)) return { side: "right", left: rightX, top: right.top, maxH: right.height };
  const xs = [PREVIEW_RIGHT_GAP, ...o.obstacles.filter((b) => b.left < o.vw / 2).map((b) => b.right + 10)]
    .filter((x) => x + o.w <= o.vw / 2 + o.w / 2).sort((a, b) => a - b);
  for (const x of xs) {
    const slot = freeSlot(x, o.w, o.top, bottom, o.minH, o.obstacles);
    if (slot && !covers(x, slot)) return { side: "left", left: x, top: slot.top, maxH: slot.height };
  }
  // nowhere clear (a crowded small window): the right dock, as tall as the window allows
  return right ? { side: "right", left: rightX, top: right.top, maxH: right.height } : { side: "right", left: rightX, top: o.top, maxH: bottom - o.top };
}
