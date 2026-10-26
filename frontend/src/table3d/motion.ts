/**
 * Small, pure pieces of the 3D table's card motion (unit-tested): the shortest turn between two
 * angles, and how high a card rides while it is hovered, selected or turning (a tap lifts the card a
 * little as it turns, like a hand turning a real card). Motion is cosmetic: the server's view is
 * always the target.
 */

/** Signed shortest difference b − a, in (−π, π]. */
export function angleDelta(a: number, b: number): number {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d <= -Math.PI) d += Math.PI * 2;
  return d;
}

export interface LiftState {
  hovered: boolean;
  selected: boolean;
  /** Radians the card still has to turn (a tap in progress). */
  turning: number;
}

export const HOVER_LIFT = 0.12;
export const SELECT_LIFT = 0.07;

/** Extra height above the card's resting place. */
export function liftFor(s: LiftState): number {
  const turn = Math.min(0.28, Math.abs(s.turning) * 0.18);
  return Math.max(s.hovered ? HOVER_LIFT : 0, s.selected ? SELECT_LIFT : 0) + turn;
}

/** Easing factor for a frame: exponential approach, or an instant snap with reduced motion. */
export function ease(dt: number, rate: number, reduced: boolean): number {
  return reduced ? 1 : 1 - Math.exp(-dt * rate);
}
