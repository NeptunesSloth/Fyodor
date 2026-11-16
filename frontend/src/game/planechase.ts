import type { GameView, PlanarCardView, PlanarFace, PlanechaseView } from "../types/game";

/*
 * -- planechase -- (CR 901, Commander's single shared planar deck) the plaque's logic, kept pure for the tests. The server deals the
 * deck, rolls the planar die and planeswalks (app/game/handlers/planechase.py); the table shows the face-up plane, its text and the
 * die, and the players apply what the plane does by hand. Nothing here decides an outcome: it reads the view.
 */

/** A plane's text split for the plaque: its static abilities, and its chaos ability ("Whenever chaos ensues" / "Whenever you roll {CHAOS}"). */
export function splitPlaneText(oracle: string | null | undefined): { statics: string[]; chaos: string | null } {
  const lines = (oracle ?? "").split("\n").map((l) => l.trim()).filter(Boolean);
  const isChaos = (l: string) => /chaos ensues|\{CHAOS\}/i.test(l);
  const chaos = lines.filter(isChaos);
  return { statics: lines.filter((l) => !isChaos(l)), chaos: chaos.length ? chaos.join("\n") : null };
}

export const FACE_LABEL: Record<PlanarFace, string> = { planeswalker: "Planeswalk", chaos: "Chaos", blank: "Blank" };

/**
 * How the plaque rolls the die: with rules automation running, through the rules engine (``roll_planar_die``: its cost is charged from
 * the roller's mana pool, or the "tap your mana" prompt opens; app/rules/planar_die.py); on a manual table, the table's own roll
 * (``planar_roll``: the cost is shown and paid by hand).
 */
export function planarRollAction(view: Pick<GameView, "rules">): { type: "roll_planar_die" | "planar_roll" } {
  return { type: view.rules && !view.rules.paused ? "roll_planar_die" : "planar_roll" };
}

/** -- 3D table -- the plane lying on the table was clicked: the plaque opens its full text (table3d/planar3d.ts → PlanechasePlaque). */
const textOpeners = new Set<() => void>();
export function showPlanarText(): void {
  for (const open of [...textOpeners]) open();
}
export function onShowPlanarText(open: () => void): () => void {
  textOpeners.add(open);
  return () => void textOpeners.delete(open);
}

/** The mana the next roll costs, as the cost text the table shows ("{0}", "{2}"). */
export const costText = (cost: number) => `{${Math.max(0, Math.floor(cost))}}`;

/**
 * How far to turn a plane's picture, in degrees, so it reads landscape: a plane is printed sideways, and a scan stored upright
 * (taller than wide) is turned a quarter clockwise. A landscape scan, or one not loaded yet, isn't turned. (Checked against Scryfall's
 * own scan of Academy at Tolaria West, 488 × 680 "normal": stored upright, its name and text run bottom to top along the long edges,
 * so a quarter turn clockwise reads them left to right. The 3D table turns its plane the same way: table3d/planar3d.ts.)
 */
export function planarRotation(width: number, height: number): 0 | 90 {
  return width > 0 && height > width ? 90 : 0;
}

/** What changed between two views of the planar deck, for the plaque's animations (null: nothing to play). */
export interface PlanarCue { walk: boolean; chaos: boolean; rolled: PlanarFace | null }

export function planechaseCue(prev: PlanechaseView | null | undefined, next: PlanechaseView | null | undefined): PlanarCue | null {
  if (!prev || !next) return null; // (the first sight of a deck, or one put away: no animation)
  const walk = next.walks > prev.walks;
  const roll = next.last_roll && next.last_roll.seq !== prev.last_roll?.seq ? next.last_roll : null;
  if (!walk && !roll) return null;
  return { walk, chaos: roll?.face === "chaos", rolled: roll?.face ?? null };
}

/** Whether `me` may roll the planar die now (the server decides; this only shows the button): the active player, not on a phenomenon. */
export function canRollPlanar(view: GameView, me: string): boolean {
  const pc = view.planechase;
  return !!pc && view.turn.active_player === me && !pc.current.phenomenon && view.players.some((p) => p.id === me);
}

/** -- planechase deck (wave D) -- every face-up card, `current` first (901.11c: two or more planes at once); an older view: just `current`. */
export function planarFaces(pc: Pick<PlanechaseView, "current" | "faces">): PlanarCardView[] {
  return pc.faces && pc.faces.length ? pc.faces : [pc.current];
}

/** The face-up planes' names as the plaque writes them ("Llanowar & Mount Keralia"). */
export function planarNames(pc: Pick<PlanechaseView, "current" | "faces">): string {
  return planarFaces(pc).map((c) => c.name).join(" & ");
}
