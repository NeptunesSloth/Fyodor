/**
 * The combat filter: big-board readability. On a table of 150 permanents the few that matter to a combat get lost, so this
 * screen can dim the rest (display only, this screen only; dimmed cards stay fully usable). Three modes, cycled from the top
 * bar or its key:
 *  - off;
 *  - "creatures": every non-creature permanent dims;
 *  - "combat" (can attack / block): in declare attackers, all but the creatures that may attack; in declare blockers, all but
 *    the defending players' creatures that may block; outside those steps, as "creatures".
 * Cards already in the combat (attacking, blocking) stay lit in "combat": they are what the other side looks at.
 *
 * What "may attack / block" reads, best first (the server decides; this only shows):
 *  1. my own declare-attackers / declare-blockers decision (rules automation): its options are exactly the creatures the
 *     server lets attack or block (haste, defender, "can't block" … all applied);
 *  2. otherwise the attacking (active) player's untapped creatures, less the ones the server's `summoning_sick` hint names. That
 *     hint is mine only (and already counts haste: a hasty creature isn't in it), so for another player's attack, or with
 *     automation off, every untapped creature they control counts (the view says nothing more about their sickness);
 *  3. blockers: the defending players' untapped creatures, the defenders being the players attacked (or who control an attacked
 *     planeswalker or battle); with no attacker declared yet, everyone but the active player.
 */
import { useMemo } from "react";
import { useCardCache } from "../state/cardCache";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, type GameCard, type GameView } from "../types/game";
import { toast } from "../components/Toasts";
import { typeLine } from "./selection";

export type CombatFilter = "off" | "creatures" | "combat";

/** The modes in cycle order, as the top bar names them (never by color alone: words and a mark). */
export const COMBAT_FILTERS: { id: CombatFilter; label: string; short: string }[] = [
  { id: "off", label: "Show all permanents", short: "No filter" },
  { id: "creatures", label: "Creatures only (dim the rest)", short: "Creatures" },
  { id: "combat", label: "Can attack / block (dim the rest)", short: "Attack / block" },
];

export const nextCombatFilter = (m: CombatFilter): CombatFilter =>
  COMBAT_FILTERS[(COMBAT_FILTERS.findIndex((f) => f.id === m) + 1) % COMBAT_FILTERS.length]!.id;

/** Next mode (the top bar's button, the More menu, its key), said in words as it changes. */
export function cycleCombatFilter(): void {
  const prefs = usePrefs.getState();
  const next = nextCombatFilter(prefs.combatFilter);
  prefs.set({ combatFilter: next });
  toast(`Combat filter: ${COMBAT_FILTERS.find((f) => f.id === next)!.label.toLowerCase()}`);
}

/** A creature on the battlefield as this viewer can tell: its type line, a crewed or animated one, any face-down permanent (708.2a: a 2/2). */
export function isCreature(c: GameCard, view: GameView, typeOf: (c: GameCard) => string = typeLine): boolean {
  if (c.face_down || !isVisible(c)) return c.face_down_as ? /\bCreature\b/.test(c.face_down_as) : true;
  return !!view.rules?.stats?.[c.id]?.creature || /\bCreature\b/.test(typeOf(c));
}

const inCombat = (c: GameCard) => !!(c.attacking || c.attacking_without_target || c.blocking || c.blocking_without_attacker);

/** Battlefield card ids the filter leaves lit; null: the filter is off (everything lit). */
export function litCards(view: GameView, me: string, mode: CombatFilter, typeOf: (c: GameCard) => string = typeLine): Set<string> | null {
  if (mode === "off") return null;
  const lit = new Set<string>();
  const onBoard: GameCard[] = [];
  for (const [zone, ids] of Object.entries(view.zones)) {
    if (!zone.endsWith(":battlefield") || !Array.isArray(ids)) continue;
    for (const id of ids) {
      const c = view.cards[id];
      if (c) onBoard.push(c);
    }
  }
  const step = view.turn.phase;
  const combat = mode === "combat" && (step === "declare_attackers" || step === "declare_blockers") ? step : null;
  if (!combat) {
    for (const c of onBoard) if (isCreature(c, view, typeOf)) lit.add(c.id);
    return lit;
  }
  for (const c of onBoard) if (inCombat(c)) lit.add(c.id);
  // 1. my own declaration: the server's list of who may attack ("a:<id>") or block ("b:<id>")
  const d = view.rules?.decision;
  const prefix = combat === "declare_attackers" ? "a:" : "b:";
  if (d && d.player === me && d.kind === combat && d.options) {
    for (const o of d.options) if (o.id.startsWith(prefix)) lit.add(o.id.slice(2));
    return lit;
  }
  const active = view.turn.active_player;
  const ready = (c: GameCard) => !c.tapped && isCreature(c, view, typeOf);
  if (combat === "declare_attackers") {
    // 2. the attacker's untapped creatures, less my summoning-sick ones (the hint is mine only; it already counts haste)
    const sick = new Set(active === me ? view.rules?.hints.summoning_sick ?? [] : []);
    for (const c of onBoard) if (c.controller === active && ready(c) && !sick.has(c.id)) lit.add(c.id);
    return lit;
  }
  // 3. the defenders' untapped creatures
  const defenders = new Set<string>();
  for (const c of onBoard) {
    const t = c.attacking;
    if (!t) continue;
    if (t.kind === "player") defenders.add(t.id);
    else if (view.cards[t.id]) defenders.add(view.cards[t.id]!.controller);
  }
  if (!defenders.size) for (const p of view.seat_order) if (p !== active) defenders.add(p);
  for (const c of onBoard) if (defenders.has(c.controller) && ready(c)) lit.add(c.id);
  return lit;
}

/** The lit set for the 2D table, worked out again only when the view, the mode or the type lines change. */
export function useLitCards(me: string): Set<string> | null {
  const mode = usePrefs((s) => s.combatFilter);
  const view = useGame((s) => s.view);
  const types = useCardCache((s) => s.cards); // type lines arrive after the first render
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `types` is read through typeLine
  return useMemo(() => (view && mode !== "off" ? litCards(view, me, mode) : null), [view, me, mode, types]);
}
