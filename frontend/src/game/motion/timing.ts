/**
 * TABLE MOTION timing shared by both tables (docs/GAME_UI_MOTION_RESEARCH.md §2–3): every duration goes through ``motionMs`` (the
 * player's animation speed, 0.5–2×; reduced motion shortens travel, never removes feedback), and any click or key press jumps whatever is
 * playing to its end (the game never waits on an animation; Space is already a table key, so skipping isn't tied to one key).
 */
import { usePrefs } from "../../state/prefs";

/** Motion tokens (ms) from the research doc's choreography table. */
export const MOTION = {
  cardTravel: 260, // play / cast / move between zones
  drawTravel: 300,
  millStagger: 45, // per card; a group never staggers past groupMax
  groupMax: 300,
  shuffle: 420,
  lunge: 220, // an attacker or blocker steps forward
  floater: 900, // a damage or life number rises and fades
  maxFlights: 12, // more cards than this in one moment move at once, without flights
} as const;

export function motionPrefs(): { speed: number; reduced: boolean } {
  const p = usePrefs.getState();
  return { speed: p.animationSpeed > 0 ? p.animationSpeed : 1, reduced: !!p.reducedMotion };
}

/** A duration at the player's speed; with reduced motion, travel is shortened (``travel``) and the rest kept (numbers, fades). */
export function motionMs(ms: number, travel = true): number {
  const { speed, reduced } = motionPrefs();
  return Math.round((ms / speed) * (reduced && travel ? 0.4 : 1));
}

/** Whether the table should animate at all right now (a hidden tab catches up instantly). */
export function motionOn(): boolean {
  return typeof document === "undefined" || document.visibilityState !== "hidden";
}

type Skip = () => void;
const skips = new Set<Skip>();
let installed = false;

/** Run ``skip`` when the player clicks or presses a key: finish the motion now. Returns the unsubscribe. */
export function onMotionSkip(skip: Skip): () => void {
  skips.add(skip);
  if (!installed && typeof window !== "undefined") {
    installed = true;
    const all = () => {
      for (const s of [...skips]) {
        try {
          s();
        } catch {
          /* (display only) */
        }
      }
    };
    window.addEventListener("pointerdown", all, { capture: true, passive: true });
    window.addEventListener("keydown", all, { capture: true, passive: true });
  }
  return () => skips.delete(skip);
}
