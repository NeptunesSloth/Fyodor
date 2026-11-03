/**
 * -- table toys -- the dice cannon (docs/3D_DIRECTION.md §7 "Tabletop toys"), the part every table shares (pure: no DOM,
 * no WebGL; unit-tested). The server fires it (app/game/handlers/toys.py): every number, who each die is fired at, and for
 * "Who goes first" every re-fire of a tie are in the log entry's roll (`cannon`). A table plays it back as volleys: one
 * throw per player per volley, each landing in front of its player (their seat colour for "Who goes first", the firer's
 * for a volley), the re-fires of a tie after the dice before them have landed. The flight is cosmetic: the dice land on the
 * server's numbers the same way the other dice do (table3d/diceThrow.ts), seeded by the log entry, the same on every screen.
 *
 * Off the mats: the cannon rolls in from the table's edge only to fire and parks off the table again (the reference study's
 * "no novelty objects on the active table"); reduced motion shows only the results, low graphics no physics at all.
 */
import type { CannonLog } from "../types/game";
import type { DiceShow } from "./dice";

/** One throw of a cannon show: the dice fired at one player in one volley. */
export interface Volley {
  /** The throw's own key (the log entry's, the volley and the player): every screen seeds the same throw from it. */
  key: string;
  round: number;
  player: string;
  /** Indexes into the show's results. */
  indices: number[];
  /** "first": this die decided who goes first; "tie": it tied for the highest and was fired again. */
  tag: "first" | "tie" | null;
  /** The throw as the dice code takes it (actor: the player it lands in front of). */
  show: DiceShow;
}

/** The cannon's part of a roll (absent on a plain roll, or an older server). */
export const cannonOf = (show: Pick<DiceShow, "cannon">): CannonLog | null => show.cannon ?? null;

/** A cannon show's throws, in firing order: by volley, then seat (as the server lists them). */
export function volleys(show: DiceShow): Volley[] {
  const c = cannonOf(show);
  if (!c) return [];
  const out: Volley[] = [];
  const at = new Map<string, Volley>();
  const last = Math.max(0, ...c.rounds);
  show.results.forEach((v, i) => {
    const player = c.players[i] ?? show.actor ?? "";
    const round = c.rounds[i] ?? 0;
    const id = `${round}:${player}`;
    let vol = at.get(id);
    if (!vol) {
      vol = { key: `${show.key}#cannon${round}:${player}`, round, player, indices: [], tag: null, show: { key: "", actor: player, sides: show.sides, results: [], coin: false } };
      at.set(id, vol);
      out.push(vol);
    }
    vol.indices.push(i);
    vol.show.results.push(v);
  });
  for (const vol of out) {
    vol.show.key = vol.key;
    if (c.mode !== "first") continue;
    if (vol.round === last && vol.player === c.winner) vol.tag = "first";
    else if (vol.round < last && c.players.some((p, i) => p === vol.player && c.rounds[i] === vol.round + 1)) vol.tag = "tie";
  }
  return out;
}

/** How many volleys a show fires (1 + the re-fires of a tie). */
export const volleyCount = (show: DiceShow): number => (cannonOf(show) ? Math.max(0, ...cannonOf(show)!.rounds) + 1 : 0);

/** The line under a cannon throw: "Bob · d20: 19", "Alice · 3d6: 2 + 5 + 6 = 13" (the same as a roll's). */
export function tagLabel(tag: Volley["tag"]): string | null {
  return tag === "first" ? "Goes first" : tag === "tie" ? "Tied: fired again" : null;
}

/** The log's headline for a "Who goes first" volley: "Bob goes first (19)". Null for a plain volley. */
export function firstHeadline(show: DiceShow, nameOf: (pid: string) => string): string | null {
  const c = cannonOf(show);
  if (!c || c.mode !== "first" || !c.winner) return null;
  const last = Math.max(0, ...c.rounds);
  const i = c.players.findIndex((p, k) => p === c.winner && c.rounds[k] === last);
  return i < 0 ? null : `${nameOf(c.winner)} goes first (${show.results[i]})`;
}

// -- timing (ms at 1×, the table's animation speed scales it) ------------------------------------------------------------

export const CANNON_MS = {
  /** Rolling in from the table's edge to its spot. */
  rollIn: 650,
  /** Swinging round to aim before each volley. */
  aim: 220,
  /** The first volley fires this long after it starts rolling in. */
  first: 900,
  /** A re-fire comes this long after the dice before it have all landed. */
  refire: 450,
  /** It leaves this long after the last volley fired. */
  linger: 700,
  /** Rolling back out. */
  rollOut: 600,
} as const;

/** When each volley fires, from when each one's dice have all landed (`settled(round, firedAt)` returns ms of show time). */
export function fireTimes(rounds: number, settled: (round: number, firedAt: number) => number): number[] {
  const out: number[] = [];
  let at: number = CANNON_MS.first;
  for (let r = 0; r < rounds; r++) {
    out.push(at);
    at = settled(r, at) + CANNON_MS.refire;
  }
  return out;
}

/** How long a die flies from the muzzle to where its throw takes over (seconds), by the distance (mat units). */
export function flightSeconds(distance: number): number {
  return Math.max(0.5, Math.min(1.25, 0.38 + distance * 0.03));
}
