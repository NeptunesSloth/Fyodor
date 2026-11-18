import { create } from "zustand";
import { perspective, useGame } from "../../state/gameStore";
import type { DecisionOptionView, DecisionView, GameView } from "../../types/game";
import { toast } from "../../components/Toasts";
import { attackTargetsFor, initialAttackPlan } from "./attackPlan";
import { combatStats, numberedNames } from "./blockerLabels";

/*
 * -- playtest (nov 18) -- the attack being put together, before it is declared: one pending plan ("a:<card>" → "t:<target>") shared by the
 * declare-attackers prompt (DeclareAttackers.tsx), a creature dragged forward on the 2D or 3D table, the "attack with all" buttons and the
 * A key. The table draws a planned attacker pushed forward toward its defender with a "→ Bob" badge. Nothing is sent until the prompt's
 * main button declares it; the server judges the whole declaration (costs, requirements, restrictions) and says what's wrong.
 */

export interface AttackDraft {
  /** The declare-attackers decision this plan answers (another decision: the plan is stale and ignored). */
  decision: string | null;
  plan: Record<string, string>;
  /** Token stacks: how many of the stack attack (all unless lowered). */
  counts: Record<string, number>;
  /** While a creature is dragged during the decision: what letting go does, and where the pointer is. */
  hint: { x: number; y: number; text: string; kind: "attack" | "home" | "refuse" } | null;
}

export const useAttackDraft = create<AttackDraft>(() => ({ decision: null, plan: {}, counts: {}, hint: null }));

/** The declare-attackers decision the local seat is making now, if any. */
export function myAttackDecision(view: GameView | null | undefined, actingAs: string | null = useGame.getState().actingAs): DecisionView | null {
  const d = view?.rules?.decision;
  if (!view || !d || d.kind !== "declare_attackers" || !d.options) return null;
  return d.player === perspective(view, actingAs) ? d : null;
}

/** Start (or keep) the draft for this decision: a new decision starts from what must attack (508.1d). */
export function openDraft(d: DecisionView): AttackDraft {
  const s = useAttackDraft.getState();
  if (s.decision === d.id) return s;
  const next = { decision: d.id, plan: initialAttackPlan(d), counts: {}, hint: null };
  useAttackDraft.setState(next);
  return next;
}

/** The plan the table draws: the draft of the decision I'm making now, else nothing. */
export function livePlan(view: GameView | null | undefined, draft: AttackDraft = useAttackDraft.getState()): Record<string, string> {
  const d = myAttackDecision(view);
  return d && draft.decision === d.id ? draft.plan : EMPTY;
}
const EMPTY: Record<string, string> = {};

export function setPlan(plan: Record<string, string>): void {
  useAttackDraft.setState({ plan });
}

/** One creature attacks this target ("t:…"), or not (""). */
export function assign(d: DecisionView, attacker: string, target: string): void {
  const plan = { ...openDraft(d).plan };
  if (target) plan[attacker] = target;
  else delete plan[attacker];
  setPlan(plan);
}

/** Every creature that may attack this target does; the others keep their choice (a must-attack creature elsewhere stays). */
export function planAll(d: DecisionView, plan: Record<string, string>, target: string): Record<string, string> {
  const next = { ...plan };
  for (const a of attackerOptions(d)) if (attackTargetsFor(d, a.id).some((t) => t.id === target)) next[a.id] = target;
  return next;
}

/** Back to the start: only what must attack (508.1d). */
export function clearPlan(d: DecisionView): Record<string, string> {
  return initialAttackPlan(d);
}

export const attackerOptions = (d: DecisionView): DecisionOptionView[] => (d.options ?? []).filter((o) => o.id.startsWith("a:"));

/** The targets at least one creature may attack, in the server's order (players first). */
export function reachableTargets(d: DecisionView): DecisionOptionView[] {
  const targets = (d.options ?? []).filter((o) => o.id.startsWith("t:"));
  return targets.filter((t) => attackerOptions(d).some((a) => attackTargetsFor(d, a.id).some((x) => x.id === t.id)));
}

/** Whether the plan sends everything that can attack this target at it. */
export function allAt(d: DecisionView, plan: Record<string, string>, target: string): boolean {
  const able = attackerOptions(d).filter((a) => attackTargetsFor(d, a.id).some((t) => t.id === target));
  return able.length > 0 && able.every((a) => plan[a.id] === target);
}

/** The A key: everything at the first defender, again at the next one, …, and after the last back to the start. */
export function cyclePlan(d: DecisionView, plan: Record<string, string>): Record<string, string> {
  const targets = reachableTargets(d);
  if (!targets.length) return plan;
  const at = targets.findIndex((t) => allAt(d, plan, t.id));
  if (at === targets.length - 1) return clearPlan(d);
  return planAll(d, plan, targets[at + 1]!.id);
}

/** A creature's power for the summary (`*` and unknown: null). */
function powerOf(pt: string | undefined): number | null {
  const p = pt?.split("/")[0];
  return p != null && /^-?\d+$/.test(p) ? Number(p) : null;
}

export interface Front { target: string; label: string; count: number; power: number; unknown: boolean }

/** The plan, per target: how many attack it and their total power (a stack: its attacking members). */
export function fronts(d: DecisionView, plan: Record<string, string>, sizes: Record<string, number> = {}, counts: Record<string, number> = {}): Front[] {
  const stats = combatStats(d);
  const labels = Object.fromEntries((d.options ?? []).map((o) => [o.id, o.label]));
  const out = new Map<string, Front>();
  for (const [a, t] of Object.entries(plan)) {
    const n = Math.min(sizes[a] ?? 1, counts[a] ?? sizes[a] ?? 1);
    const f = out.get(t) ?? { target: t, label: labels[t] ?? "?", count: 0, power: 0, unknown: false };
    const p = powerOf(stats[a.slice(2)]?.pt);
    f.count += n;
    if (p == null) f.unknown = true;
    else f.power += Math.max(0, p) * n;
    out.set(t, f);
  }
  const order = (d.options ?? []).map((o) => o.id);
  return [...out.values()].sort((x, y) => order.indexOf(x.target) - order.indexOf(y.target));
}

/** "4 attacking · 11 power → Bob", "6 attacking · 9 power → Bob · 3 power → Carol"; empty with no attackers. */
export function summaryLine(list: Front[]): string {
  const n = list.reduce((k, f) => k + f.count, 0);
  if (!n) return "";
  const pw = (f: Front) => `${f.power}${f.unknown ? "+" : ""} power`;
  if (list.length === 1) return `${n} attacking · ${pw(list[0]!)} → ${list[0]!.label}`;
  return `${n} attacking · ${list.map((f) => `${f.count} (${pw(f)}) → ${f.label}`).join(" · ")}`;
}

/** The names the prompt lists the attackers by: the face that is up (the server's label), two of one name numbered. */
export const attackerNames = (d: DecisionView): Record<string, string> => numberedNames(d.options ?? []);

// ------------------------------------------------------------------ the table: drag a creature forward to attack

/** What a drop of these cards means while I declare attackers: a defender ("p2", a planeswalker's id), "home" (my own row), or null. */
export type AttackSpot = string | "home" | null;

/**
 * Letting go of dragged cards during my declare-attackers decision. A defender: each dragged creature that may attack it does (the
 * others are named in a toast); "home": the dragged creatures stop attacking. True when the drop was about attacking (nothing moves);
 * false when no dragged card is a possible attacker or nothing changed, so the drag does what it always does.
 */
export function attackDrop(ids: string[], spot: AttackSpot): boolean {
  const view = useGame.getState().view;
  const d = myAttackDecision(view);
  useAttackDraft.setState({ hint: null });
  if (!d || !spot) return false;
  const mine = ids.map((id) => `a:${id}`).filter((a) => d.options!.some((o) => o.id === a));
  if (!mine.length) return false;
  const plan = { ...openDraft(d).plan };
  if (spot === "home") {
    const had = mine.filter((a) => plan[a]);
    if (!had.length) return false;
    for (const a of had) delete plan[a];
    setPlan(plan);
    return true;
  }
  const t = `t:${spot}`;
  if (!d.options!.some((o) => o.id === t)) return false;
  const names = attackerNames(d);
  const refused: string[] = [];
  for (const a of mine) {
    if (attackTargetsFor(d, a).some((x) => x.id === t)) plan[a] = t;
    else refused.push(names[a] ?? "It");
  }
  setPlan(plan);
  const label = d.options!.find((o) => o.id === t)?.label ?? "that";
  if (refused.length) toast(`${refused.join(", ")} can't attack ${label}`, "info");
  return true;
}

/** The caption a drag shows over this spot (null: the drag isn't about attacking). */
export function attackHint(ids: string[], spot: AttackSpot): Omit<NonNullable<AttackDraft["hint"]>, "x" | "y"> | null {
  const view = useGame.getState().view;
  const d = myAttackDecision(view);
  if (!d) return null;
  const mine = ids.map((id) => `a:${id}`).filter((a) => d.options!.some((o) => o.id === a));
  if (!mine.length) return null;
  if (!spot) return { text: "Drag toward an opponent to attack", kind: "home" };
  if (spot === "home") {
    const plan = useAttackDraft.getState().decision === d.id ? useAttackDraft.getState().plan : {};
    return mine.some((a) => plan[a]) ? { text: "Back in your row: doesn't attack", kind: "home" } : { text: "Drag toward an opponent to attack", kind: "home" };
  }
  const t = `t:${spot}`;
  const label = d.options!.find((o) => o.id === t)?.label;
  if (!label) return null;
  const able = mine.filter((a) => attackTargetsFor(d, a).some((x) => x.id === t)).length;
  if (!able) return { text: `Can't attack ${label}`, kind: "refuse" };
  return { text: `Attack ${label}${mine.length > 1 ? ` with ${able}` : ""}`, kind: "attack" };
}

/**
 * 2D: the defender under or ahead of the pointer. A planeswalker or battle that may be attacked, or a player's plaque, under it; any of
 * an opponent's zones; the front band of my own battlefield (the edge toward the opponents): the opponent whose board is nearest.
 * Elsewhere on my battlefield: "home".
 */
export function attackSpot2D(view: GameView, me: string, zone: string | null, clientX: number, clientY: number): AttackSpot {
  const d = myAttackDecision(view);
  if (!d) return null;
  const offered = new Set((d.options ?? []).filter((o) => o.id.startsWith("t:")).map((o) => o.id.slice(2)));
  const stack = typeof document !== "undefined" && document.elementsFromPoint ? document.elementsFromPoint(clientX, clientY) : [];
  for (const el of stack) {
    if (!(el instanceof HTMLElement)) continue;
    const card = el.closest<HTMLElement>("[data-card-id]")?.dataset.cardId;
    if (card && offered.has(card)) return card;
    const player = el.closest<HTMLElement>("[data-player-id]")?.dataset.playerId;
    if (player && offered.has(player)) return player;
  }
  const owner = zone?.split(":")[0];
  if (owner && owner !== me && offered.has(owner)) return owner;
  if (zone !== `${me}:battlefield`) return null;
  const board = document.querySelector<HTMLElement>(`[data-drop="${CSS.escape(`${me}:battlefield`)}"]`);
  const r = board?.getBoundingClientRect();
  if (!r || clientY > r.top + r.height * 0.28) return "home";
  let best: string | null = null;
  let dist = Infinity;
  for (const pid of offered) {
    const el = document.querySelector<HTMLElement>(`[data-drop="${CSS.escape(`${pid}:battlefield`)}"]`);
    if (!el) continue;
    const o = el.getBoundingClientRect();
    const dd = Math.hypot(o.left + o.width / 2 - clientX, o.top + o.height / 2 - clientY);
    if (dd < dist) [best, dist] = [pid, dd];
  }
  return best ?? "home";
}

/** The badge a planned or declared attacker wears on the table: its defender's initial, name and seat colour (never colour alone). */
export function defenderBadge(view: GameView, target: { kind?: string; id: string }): { initial: string; name: string; color: string } | null {
  const p = view.players.find((x) => x.id === target.id);
  if (p) return { initial: p.name.slice(0, 1).toUpperCase(), name: p.name, color: p.color };
  const c = view.cards[target.id];
  if (!c) return null;
  const ctl = view.players.find((x) => x.id === c.controller);
  const name = "name" in c && c.name ? String(c.name).split(" // ")[0]! : "a permanent";
  return { initial: (ctl?.name ?? name).slice(0, 1).toUpperCase(), name, color: ctl?.color ?? "#c9a45c" };
}
