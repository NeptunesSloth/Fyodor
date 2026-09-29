/**
 * Minimal pointer-events drag and drop for cards.
 *
 * Drop targets are DOM elements carrying `data-drop="<zone key>"`. Battlefields also carry
 * `data-mirrored` when drawn upside down (opponents). A drag only starts after the pointer
 * moves a few pixels, so clicks and double-clicks keep working normally.
 */
import { create } from "zustand";
import { BF_H, BF_W } from "./geometry";

export interface DragGhost {
  ids: string[];
  from: string;
  x: number;
  y: number;
  offsetX: number;
  offsetY: number;
  width: number;
  overZone: string | null;
}

interface DragStore {
  drag: DragGhost | null;
  set: (d: DragGhost | null) => void;
}

export const useDrag = create<DragStore>((set) => ({ drag: null, set: (drag) => set({ drag }) }));

export interface DropResult {
  zone: string;
  /** Battlefield drop position (virtual units) of the grabbed card's top-left corner. */
  x?: number;
  y?: number;
  /** Hand / ordered-zone insert index. */
  index?: number;
  /** Library: drop on the lower half means "bottom". */
  position?: "top" | "bottom";
  /** The manual-override modifier (Alt) was held: do it by hand, not as a rules intent. */
  manual?: boolean;
}

const THRESHOLD = 5;

/** The 3D table resolves drops on its canvas (the canvas carries `data-drop3d`). */
let resolver3d: ((clientX: number, clientY: number) => DropResult | null) | null = null;
export function setDropResolver3D(fn: typeof resolver3d): void {
  resolver3d = fn;
}

export function findDropTarget(clientX: number, clientY: number, offsetX: number, offsetY: number): DropResult | null {
  const stack = document.elementsFromPoint(clientX, clientY);
  for (const el of stack) {
    if (!(el instanceof HTMLElement)) continue;
    if (el.dataset.drop3d !== undefined) {
      const hit = resolver3d?.(clientX, clientY);
      if (hit) return hit;
      continue;
    }
    const zone = el.dataset.drop;
    if (!zone) continue;
    const rect = el.getBoundingClientRect();
    if (el.dataset.battlefield !== undefined) {
      const mirrored = el.dataset.mirrored !== undefined;
      const cardH = Number(el.dataset.cardh ?? 0);
      let x = ((clientX - offsetX - rect.left) / rect.width) * BF_W;
      let y = ((clientY - offsetY - rect.top) / rect.height) * BF_H;
      if (mirrored) y = BF_H - y - (cardH / rect.height) * BF_H;
      x = Math.max(-20, Math.min(BF_W - 20, x));
      y = Math.max(-20, Math.min(BF_H - 20, y));
      return { zone, x, y };
    }
    if (el.dataset.ordered !== undefined) {
      const items = [...el.querySelectorAll<HTMLElement>("[data-index]")];
      let index = items.length;
      for (const item of items) {
        const r = item.getBoundingClientRect();
        if (clientX < r.left + r.width / 2) {
          index = Number(item.dataset.index);
          break;
        }
      }
      return { zone, index };
    }
    if (el.dataset.library !== undefined) {
      return { zone, position: clientY > rect.top + rect.height * 0.62 ? "bottom" : "top" };
    }
    return { zone };
  }
  return null;
}

/**
 * Start tracking a possible drag from a pointerdown event. `onDrop` receives the drop
 * target (or null when released outside any zone); `onClick` fires when the pointer never
 * moved past the drag threshold.
 */
export function beginPointerDrag(
  e: React.PointerEvent,
  opts: { ids: string[]; from: string; onDrop: (target: DropResult | null) => void; width?: number },
): void {
  if (e.button !== 0) return;
  const el = e.currentTarget as HTMLElement;
  const rect = el.getBoundingClientRect();
  const startX = e.clientX;
  const startY = e.clientY;
  const offsetX = startX - rect.left;
  const offsetY = startY - rect.top;
  let dragging = false;
  const setDrag = useDrag.getState().set;

  const move = (ev: PointerEvent) => {
    if (!dragging && Math.hypot(ev.clientX - startX, ev.clientY - startY) < THRESHOLD) return;
    if (!dragging) {
      dragging = true;
      document.body.classList.add("dragging");
    }
    const over = findDropTarget(ev.clientX, ev.clientY, offsetX, offsetY);
    setDrag({ ids: opts.ids, from: opts.from, x: ev.clientX, y: ev.clientY, offsetX, offsetY, width: opts.width ?? rect.width, overZone: over?.zone ?? null });
  };
  const up = (ev: PointerEvent) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", cancel);
    document.body.classList.remove("dragging");
    setDrag(null);
    if (dragging) {
      const target = findDropTarget(ev.clientX, ev.clientY, offsetX, offsetY);
      opts.onDrop(target ? { ...target, manual: ev.altKey } : null);
    }
  };
  const cancel = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    window.removeEventListener("pointercancel", cancel);
    document.body.classList.remove("dragging");
    setDrag(null);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
  window.addEventListener("pointercancel", cancel);
}
