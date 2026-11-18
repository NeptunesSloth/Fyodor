/**
 * -- day and night (CR 726) -- what the table says when it becomes day or night. The server decides (502.2, 726.2); the
 * client only marks the change: a short sun or moon rising under the top bar's day/night indicator, and the 2D table's felt
 * a shade cooler and darker while it is night (the 3D room's light: table3d/dayNight.ts).
 */
export type DayNightMode = "day" | "night" | null;

export interface DayNightMoment {
  /** What it became. */
  to: "day" | "night";
  /** What it was (null: day and night just began). */
  from: "day" | "night" | null;
  /** The words under the glyph (the rules' own: "it becomes night", 726.2). */
  line: string;
}

/** The moment a change from ``prev`` to ``next`` shows, or null (no change, or day and night ended: the indicator just goes). */
export function dayNightMoment(prev: DayNightMode, next: DayNightMode): DayNightMoment | null {
  if (!next || prev === next) return null;
  return { to: next, from: prev, line: next === "night" ? "It becomes night" : "It becomes day" };
}

/** How long the moment stays (ms at 1× speed): the glyph rises, holds and fades; click-through and skippable. */
export const DAY_NIGHT_MOMENT_MS = 1400;
