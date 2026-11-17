import { useEffect } from "react";
import { perspective, useGame } from "../state/gameStore";
import type { GameView } from "../types/game";
import { isLand } from "./rules/intents";

/**
 * -- playtest second pass (nov 17) -- keep my land row in view. Prompts (trigger order, discard, yes/no …), the target bar when my hand is
 * among the choices, and the draw notice all docked just above the hand, which on the 2D table is exactly where my lands lie: the player
 * may need to tap them, or just see them, while answering. This measures where my lands start on screen and gives the page
 * `--lands-clear` (px from the bottom of the window to just above the highest of them); the CSS docks those plaques above it
 * (game/rules/rules.css, drawNotice.css). Lands far up the screen (free placement in the middle of the mat) or none at all: no
 * variable, and everything stays where it was. The 3D table draws its cards on a canvas: nothing to measure there either.
 */

/** The clearance (px from the window's bottom) above my lands, or null when it doesn't apply. Pure: unit-tested. */
export function landsClearance(tops: number[], viewportH: number, handH: number): number | null {
  if (!tops.length || viewportH <= 0) return null;
  const top = Math.min(...tops);
  const clear = Math.round(viewportH - top + 8);
  // (only when the lands lie low, where the plaques dock; far up the mat they'd push every prompt off the top)
  if (clear <= handH + 14 || clear > viewportH * 0.55) return null;
  return clear;
}

function myLandTops(view: GameView, me: string): number[] {
  const zone = `${me}:battlefield`;
  const ids = (view.zones[zone] as string[] | undefined) ?? [];
  const box = document.querySelector(`.battlefield[data-drop="${CSS.escape(zone)}"]`);
  if (!box) return [];
  const tops: number[] = [];
  for (const id of ids) {
    if (!isLand(id, view)) continue;
    const el = box.querySelector(`[data-card-id="${CSS.escape(id)}"]`);
    const r = el?.getBoundingClientRect();
    if (r && r.height > 0) tops.push(r.top);
  }
  return tops;
}

/** Keep `--lands-clear` (and the `lands-clear` class) on the page up to date: after each view, and on resize. */
export function useLandsClearance(): void {
  useEffect(() => {
    let frame = 0;
    let last: number | null = -1;
    const measure = () => {
      frame = 0;
      const { view, actingAs } = useGame.getState();
      const handH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--hand-h")) || 150;
      const clear = view && !document.querySelector("main.table.is-3d") ? landsClearance(myLandTops(view, perspective(view, actingAs)), window.innerHeight, handH) : null;
      if (clear === last) return;
      last = clear;
      const body = document.body;
      body.classList.toggle("lands-clear", clear !== null);
      if (clear !== null) body.style.setProperty("--lands-clear", `${clear}px`);
      else body.style.removeProperty("--lands-clear");
    };
    const later = () => { if (!frame) frame = requestAnimationFrame(measure); };
    later();
    const unsub = useGame.subscribe((s, prev) => { if (s.view !== prev.view || s.actingAs !== prev.actingAs) later(); });
    window.addEventListener("resize", later);
    const tick = window.setInterval(later, 1500); // (the arranged board settles after its own layout pass)
    return () => {
      unsub();
      window.removeEventListener("resize", later);
      window.clearInterval(tick);
      if (frame) cancelAnimationFrame(frame);
      document.body.classList.remove("lands-clear");
      document.body.style.removeProperty("--lands-clear");
    };
  }, []);
}
