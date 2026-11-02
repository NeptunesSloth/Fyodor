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
