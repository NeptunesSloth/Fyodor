import type { DecisionView } from "../../types/game";

/**
 * The order prompt's rows (603.3b). A trigger order decision's display lists the chooser's triggers grouped — identical abilities (one key:
 * "Scute Swarm:0") are one row, "×N", picked as a block — with each ability's printed words and its source card while it is public. Any
 * other "order" decision (cards for the bottom of a library …) is one row per option. The answer is always every option id, in order.
 */
export interface OrderRow {
  key: string;
  ids: string[];
  name: string;
  /** the ability's words for the row ("Landfall: create a 1/1 green Insect creature token …"), "" when it has none */
  short: string;
  /** its full printed text (a tooltip), "" when it has none */
  text: string;
  count: number;
  /** the source card's id while it is public (its art), else null */
  source: string | null;
}

interface TriggerRowData { key?: unknown; ids?: unknown; name?: unknown; short?: unknown; text?: unknown; count?: unknown; source?: unknown }

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** The rows of an order decision: the server's trigger groups (each option exactly once), else one row per option. */
export function orderRows(d: DecisionView): OrderRow[] {
  const options = d.options ?? [];
  const known = new Set(options.map((o) => o.id));
  const groups = Array.isArray(d.display?.triggers) ? (d.display.triggers as TriggerRowData[]) : null;
  if (groups) {
    const seen = new Set<string>();
    const rows: OrderRow[] = [];
    for (const g of groups) {
      const ids = (Array.isArray(g.ids) ? g.ids : []).filter((id): id is string => typeof id === "string" && known.has(id) && !seen.has(id));
      if (!ids.length) continue;
      ids.forEach((id) => seen.add(id));
      rows.push({ key: str(g.key) || ids[0]!, ids, name: str(g.name), short: str(g.short), text: str(g.text), count: ids.length,
        source: typeof g.source === "string" ? g.source : null });
    }
    if (seen.size === known.size) return rows;
  }
  return options.map((o) => ({ key: o.id, ids: [o.id], name: o.label, short: "", text: "", count: 1, source: null }));
}

/** The answer for rows picked in this order (a block's triggers together, as they triggered). */
export function orderedIds(rows: OrderRow[], pickedKeys: string[]): string[] {
  const byKey = new Map(rows.map((r) => [r.key, r]));
  return pickedKeys.flatMap((k) => byKey.get(k)?.ids ?? []);
}

/** "Auto order": every row in the order listed (the order they triggered). */
export function autoOrderIds(rows: OrderRow[]): string[] {
  return rows.flatMap((r) => r.ids);
}

/** The prompt asks for this trigger order (rather than cards to arrange). */
export function isTriggerOrder(d: DecisionView): boolean {
  return d.kind === "order" && Array.isArray(d.display?.triggers);
}

/** A saved order ("always use this order for these cards") as words: the sources' names, first on the stack first. */
export function savedOrderLabel(keys: string[]): string {
  return keys.map((k) => k.replace(/:\d+$/, "")).join(" → ");
}
