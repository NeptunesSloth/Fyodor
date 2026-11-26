/**
 * -- Teach Fyodor -- dragging a piece from the palette (or a row on the workspace, or a Target / Value chip) with the
 * pointer: a ghost follows the finger, the slots it may snap to light up, the one under it glows. Plain pointer events
 * (no library); the keyboard and click-to-add paths in the page do the same without a drag (WCAG 2.5.7).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Piece, Value } from "./types";

export type DragItem =
  | { kind: "piece"; piece: Piece }
  | { kind: "node"; uid: string; piece: Piece }
  | { kind: "chip"; value: Value; label: string; cat: string };

export interface DragState { item: DragItem; target: string | null }

const THRESHOLD = 6;

/** What is under the pointer: the data-attribute the page resolves a drop target from. */
export type Resolve = (item: DragItem, x: number, y: number) => string | null;

export function useDrag(resolve: Resolve, onDrop: (item: DragItem, target: string | null) => void) {
  const [drag, setDrag] = useState<DragState | null>(null);
  const ghost = useRef<HTMLDivElement | null>(null);
  const live = useRef<{ item: DragItem; x0: number; y0: number; active: boolean; target: string | null; pointerId: number } | null>(null);

  const place = (x: number, y: number) => {
    const g = ghost.current;
    if (g) g.style.transform = `translate(${x + 12}px, ${y + 10}px)`;
  };

  const finish = useCallback((drop: boolean) => {
    const l = live.current;
    live.current = null;
    document.body.classList.remove("t-dragging");
    if (l?.active) {
      setDrag(null);
      if (drop) onDrop(l.item, l.target);
    }
  }, [onDrop]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      const l = live.current;
      if (!l || e.pointerId !== l.pointerId) return;
      if (!l.active) {
        if (Math.hypot(e.clientX - l.x0, e.clientY - l.y0) < THRESHOLD) return;
        l.active = true;
        document.body.classList.add("t-dragging");
        setDrag({ item: l.item, target: null });
      }
      e.preventDefault();
      place(e.clientX, e.clientY);
      const target = resolve(l.item, e.clientX, e.clientY);
      if (target !== l.target) {
        l.target = target;
        setDrag({ item: l.item, target });
      }
    };
    const up = (e: PointerEvent) => {
      if (live.current && e.pointerId === live.current.pointerId) finish(true);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && live.current) finish(false);
    };
    window.addEventListener("pointermove", move, { passive: false });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      window.removeEventListener("keydown", key);
    };
  }, [resolve, finish]);

  /** Call from a draggable's onPointerDown (a primary button / touch). The click still fires when the pointer doesn't travel. */
  const start = useCallback((e: React.PointerEvent, item: DragItem) => {
    if (e.button !== 0 || live.current) return;
    live.current = { item, x0: e.clientX, y0: e.clientY, active: false, target: null, pointerId: e.pointerId };
    place(e.clientX, e.clientY);
  }, []);

  return { drag, start, ghost };
}

/** The draggable element under the point with the given attribute (or null). */
export function under(x: number, y: number, attr: string): HTMLElement | null {
  const el = document.elementFromPoint(x, y);
  return el instanceof Element ? (el.closest(`[${attr}]`) as HTMLElement | null) : null;
}
