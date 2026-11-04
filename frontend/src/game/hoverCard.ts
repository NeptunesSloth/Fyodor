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

/** Hide the preview until the next hover (its × and Esc). */
export function clearHover(): void {
  owner = null;
  if (useGame.getState().hover) useGame.getState().setHover(null);
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
