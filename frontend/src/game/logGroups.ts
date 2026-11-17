import type { LogPartView } from "../types/game";

type Group = Extract<LogPartView, { group: unknown }>["group"];

/**
 * -- playtest (nov 16) -- a log line's list of cards with the same card counted once: a mill or a "put on top" of 50 cards read
 * "Mountain, Mountain, Mountain, …"; it reads "Mountain ×42, Lightning Bolt". First appearance keeps the order.
 */
export function countedGroup(group: Group): { card: Group[number]["card"]; n: number }[] {
  const out: { card: Group[number]["card"]; n: number }[] = [];
  const at = new Map<string, number>();
  for (const g of group) {
    const key = `${g.card.name}|${g.card.card_id ?? ""}`;
    const i = at.get(key);
    if (i === undefined) {
      at.set(key, out.length);
      out.push({ card: g.card, n: 1 });
    } else out[i]!.n++;
  }
  return out;
}

/** A counted name: "Mountain ×42" (just the name for one). */
export const countedName = (c: { card: { name: string }; n: number }): string => (c.n > 1 ? `${c.card.name} ×${c.n}` : c.card.name);

/** The group's words for a one-line reading (the ticker, the history). */
export function groupText(group: Group): string {
  return countedGroup(group).map(countedName).join(", ");
}
