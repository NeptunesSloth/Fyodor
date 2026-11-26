import type { DecisionOptionView, DecisionView } from "../../types/game";

/*
 * -- playtest (nov 17) -- the blockers prompt (RulesHud DeclareBlockers): each creature's power/toughness and combat keywords
 * (the server's `display.stats`, app/rules/combat.py combat_stats), and two creatures of one name told apart ("Hare Apparent #1",
 * "Hare Apparent #2") on both sides.
 */

export interface CombatStats { pt: string; keywords: string[] }

/** The stats the server sent for this prompt's creatures, by card id (an older table: none). */
export function combatStats(d: DecisionView): Record<string, CombatStats> {
  const raw = d.display?.stats; // (the blockers prompt, and the attackers prompt since nov 18)
  return raw && typeof raw === "object" ? (raw as Record<string, CombatStats>) : {};
}

/** Each option's name, numbered where two or more options of its side ("a:" or "b:") share it, in the server's order. */
export function numberedNames(options: DecisionOptionView[]): Record<string, string> {
  const count = new Map<string, number>();
  for (const o of options) count.set(`${o.id.slice(0, 2)}${o.label}`, (count.get(`${o.id.slice(0, 2)}${o.label}`) ?? 0) + 1);
  const seen = new Map<string, number>();
  const out: Record<string, string> = {};
  for (const o of options) {
    const key = `${o.id.slice(0, 2)}${o.label}`;
    const n = (seen.get(key) ?? 0) + 1;
    seen.set(key, n);
    out[o.id] = (count.get(key) ?? 0) > 1 ? `${o.label} #${n}` : o.label;
  }
  return out;
}

/** "2/2 · flying, first strike" (or just "2/2"); empty without stats. */
export function statLine(stats: CombatStats | undefined): string {
  if (!stats) return "";
  return [stats.pt, stats.keywords.join(", ")].filter(Boolean).join(" · ");
}
