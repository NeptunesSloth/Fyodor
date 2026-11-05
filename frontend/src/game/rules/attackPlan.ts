import type { DecisionOptionView, DecisionView } from "../../types/game";

/** The server's guide on a declare-attackers decision (backend combat.attack_guide): each creature's own legal targets (508.1c, e.g.
 * Alexios "can't attack its owner") and the creatures a requirement says attack, with their best places (508.1d, e.g. Khârn "attacks or
 * blocks each combat if able"). Both are keyed by card id; an older table's decision has neither. */
function guide(d: DecisionView): { targets?: Record<string, string[]>; must?: Record<string, string[]> } {
  const targets = d.display?.targets;
  const must = d.display?.must_attack;
  return {
    targets: targets && typeof targets === "object" ? (targets as Record<string, string[]>) : undefined,
    must: must && typeof must === "object" ? (must as Record<string, string[]>) : undefined,
  };
}

/** The targets one attacker (its "a:<card>" option) is offered: its own legal ones when the server lists them, else every target. */
export function attackTargetsFor(d: DecisionView, attackerOptionId: string): DecisionOptionView[] {
  const all = (d.options ?? []).filter((o) => o.id.startsWith("t:"));
  const legal = guide(d).targets;
  if (!legal) return all;
  const mine = new Set(legal[attackerOptionId.slice(2)] ?? []);
  return all.filter((t) => mine.has(t.id.slice(2)));
}

/** Whether a requirement says this attacker ("a:<card>") attacks if able (508.1d). */
export function mustAttack(d: DecisionView, attackerOptionId: string): boolean {
  return (guide(d).must?.[attackerOptionId.slice(2)]?.length ?? 0) > 0;
}

/** The plan the declaration opens with ("a:<card>" → "t:<target>"): each creature that must attack, at the first of its best places.
 * The player may change it; the server judges the whole declaration (508.1d: requirements obeyed as far as possible). */
export function initialAttackPlan(d: DecisionView): Record<string, string> {
  const offered = new Set((d.options ?? []).map((o) => o.id));
  const plan: Record<string, string> = {};
  for (const [card, places] of Object.entries(guide(d).must ?? {})) {
    const place = places.find((t) => offered.has(`t:${t}`));
    if (offered.has(`a:${card}`) && place) plan[`a:${card}`] = `t:${place}`;
  }
  return plan;
}

/**
 * The declaration the server gets from the plan ("a:<card>" → "t:<target>"). A token stack ("Goblin ×512") attacks with all its members
 * unless `counts` names fewer (1..its size): then the declaration carries that count and the server splits the others off, in the same
 * action (docs/TOKEN_STACKS.md §4). `sizes`: each attacker's stack size (1 for a single creature).
 */
export function attackDeclarations(plan: Record<string, string>, counts: Record<string, number> = {}, sizes: Record<string, number> = {}): { card_id: string; target: string; count?: number }[] {
  return Object.entries(plan).map(([a, t]) => {
    const size = sizes[a] ?? 1;
    const k = counts[a];
    const part = k != null && Number.isFinite(k) && k >= 1 && k < size ? Math.floor(k) : null;
    return { card_id: a.slice(2), target: t.slice(2), ...(part != null ? { count: part } : {}) };
  });
}

/** How many creatures the plan attacks with (a stack counts its members, or the part of it that attacks). */
export function attackingCount(plan: Record<string, string>, counts: Record<string, number> = {}, sizes: Record<string, number> = {}): number {
  return attackDeclarations(plan, counts, sizes).reduce((n, d) => n + (d.count ?? sizes[`a:${d.card_id}`] ?? 1), 0);
}
