/**
 * Auto-centre (TABLETOP_QOL_MILESTONE #11): which public event, if any, the 3D camera should glance at after a view
 * update. Pure, so the filter is unit-tested; the camera move itself (a short look, then back; any input cancels it)
 * lives in Table3D.
 *
 * "important": a player eliminated, a commander cast by someone else, an attack declared on you (or your planeswalker
 * or battle), and a spell or ability of someone else's that targets you or a permanent you control.
 * "on" adds the start of your turn (the camera comes home to your seat, and stays) and other players' attacks.
 * Never routine draws, land plays or anything you did yourself.
 */
import type { GameView } from "../types/game";
import { combatCardIds } from "./focus";
import type { CameraPreset } from "./TableScene";

export type AutoCenterLevel = "off" | "important" | "on";

/** What the filter remembers of the previous view. */
export interface AutoSnap {
  stack: Set<string>;
  out: Set<string>;
  arrows: Set<string>;
  attackers: Set<string>;
  active: string;
  turn: number;
}

export function autoSnap(v: GameView): AutoSnap {
  return {
    stack: new Set(v.stack),
    out: new Set([...(v.rules?.conceded ?? []), ...Object.keys(v.rules?.lost ?? {})]),
    arrows: new Set((v.arrows ?? []).map((a) => a.id)),
    attackers: new Set(combatCardIds(v).filter((id) => v.cards[id]?.attacking || v.cards[id]?.attacking_without_target)),
    active: v.turn.active_player,
    turn: v.turn.number,
  };
}

/** The camera to glance with for what changed between two views, or null; the most important event wins. */
export function autoCenterTarget(before: AutoSnap, v: GameView, me: string, level: AutoCenterLevel): CameraPreset | null {
  if (level === "off") return null;
  const now = autoSnap(v);
  const seat = (pid: string | undefined): CameraPreset | null => (pid && pid !== me ? { focus: pid } : null);
  const mineCard = (id: string) => v.cards[id]?.controller === me && !!v.cards[id]?.zone.endsWith(":battlefield");

  // 1. an elimination
  for (const pid of now.out) if (!before.out.has(pid) && pid !== me) return { focus: pid };

  // 2. an attack declared on you, your planeswalker or your battle
  const fresh = [...now.attackers].filter((id) => !before.attackers.has(id));
  const onMe = fresh.some((id) => {
    const t = v.cards[id]?.attacking;
    return v.cards[id]?.controller !== me && !!t && (t.kind === "player" ? t.id === me : mineCard(t.id));
  });
  if (onMe) return { combat: true };

  // 3. someone else's spell or ability targeting you or a permanent you control
  for (const a of v.arrows ?? []) {
    if (a.kind !== "target" || before.arrows.has(a.id)) continue;
    const src = v.cards[a.source];
    const by = src?.controller ?? a.owner;
    if (by === me || !a.targets.some((t) => t === me || mineCard(t))) continue;
    return v.stack.includes(a.source) ? { stack: true } : seat(by);
  }

  // 4. a commander cast by someone else
  for (const id of v.stack) {
    const c = v.cards[id];
    if (!before.stack.has(id) && c && "commander_key" in c && c.commander_key && c.controller !== me) return { focus: c.controller };
  }

  if (level !== "on") return null;
  // 5. your turn begins: back to your seat
  if (now.active === me && (before.active !== me || before.turn !== now.turn)) return "seat";
  // 6. any other player's attack
  if (fresh.some((id) => v.cards[id]?.controller !== me)) return { combat: true };
  return null;
}
