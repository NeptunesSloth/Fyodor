/**
 * Card filters for a long list of cards the viewer can already see: a library search, the top N of a library, a tutor's
 * legal finds. Chips within one group widen the list (Creature or Land), the groups narrow it (a Creature AND mana value 2).
 * Only the cards' own visible data is read: a hidden card has none, so it never matches an active filter.
 */

export const CARD_TYPES = ["Creature", "Land", "Artifact", "Enchantment", "Instant", "Sorcery", "Planeswalker", "Battle"] as const;
export type CardType = (typeof CARD_TYPES)[number];
/** Mana values 0–6 and "7 or more" (7). */
export const MANA_VALUES = [0, 1, 2, 3, 4, 5, 6, 7] as const;
export const COLORS = ["W", "U", "B", "R", "G", "C"] as const;
export type Color = (typeof COLORS)[number];
export type CardSort = "order" | "name" | "mv" | "type";
export const SORTS: { id: CardSort; label: string }[] = [
  { id: "order", label: "Library order" },
  { id: "name", label: "Name" },
  { id: "mv", label: "Mana value" },
  { id: "type", label: "Type" },
];

export interface CardFilter {
  text: string;
  types: CardType[];
  mvs: number[];
  colors: Color[];
  sort: CardSort;
}

export const NO_FILTER: CardFilter = { text: "", types: [], mvs: [], colors: [], sort: "order" };

/** What a filter reads of one card; ``null`` data: a hidden card, or one whose data hasn't arrived yet. */
export interface FilterCard {
  id: string;
  name: string | null;
  data: { type_line?: string | null; cmc?: number | null; colors?: string[]; oracle_text?: string | null } | null;
}

export const filtering = (f: CardFilter): boolean => !!f.text.trim() || f.types.length > 0 || f.mvs.length > 0 || f.colors.length > 0;

/** The front face's type line (a modal double-faced or split card is filtered by the face it's played as first). */
const front = (c: FilterCard): string => (c.data?.type_line ?? "").split("//")[0] ?? "";

function matches(c: FilterCard, f: CardFilter, q: string): boolean {
  if (c.name == null) return false; // hidden: nothing to match
  if (q && !(c.name.toLowerCase().includes(q) || (c.data?.type_line ?? "").toLowerCase().includes(q) || (c.data?.oracle_text ?? "").toLowerCase().includes(q))) return false;
  if (!f.types.length && !f.mvs.length && !f.colors.length) return true;
  if (!c.data) return false;
  if (f.types.length && !f.types.some((t) => front(c).includes(t))) return false;
  if (f.mvs.length) {
    const mv = Math.floor(c.data.cmc ?? 0);
    if (!f.mvs.some((m) => (m >= 7 ? mv >= 7 : mv === m))) return false;
  }
  if (f.colors.length) {
    const colors = c.data.colors ?? [];
    if (!f.colors.some((k) => (k === "C" ? colors.length === 0 : colors.includes(k)))) return false;
  }
  return true;
}

/** The order "Type" sorts by: lands last, as on a decklist. */
const TYPE_ORDER: CardType[] = ["Creature", "Planeswalker", "Battle", "Artifact", "Enchantment", "Instant", "Sorcery", "Land"];
const typeRank = (c: FilterCard) => {
  const t = front(c);
  const i = TYPE_ORDER.findIndex((k) => t.includes(k));
  return i < 0 ? TYPE_ORDER.length : i;
};

/**
 * The cards ``f`` shows, in its sort; ``cards`` come in their zone's order ("Library order"). The sorts are stable, ties keep
 * ties go by name, then the zone's order; a card without data (hidden) sorts after the rest.
 */
export function filterCards<T extends FilterCard>(cards: T[], f: CardFilter): T[] {
  const q = f.text.trim().toLowerCase();
  const shown = filtering(f) ? cards.filter((c) => matches(c, f, q)) : cards;
  if (f.sort === "order") return shown;
  const key = (c: FilterCard): [number, number | string] => {
    if (c.name == null) return [2, 0];
    if (f.sort === "name") return [0, c.name.toLowerCase()];
    if (f.sort === "mv") return [c.data ? 0 : 1, c.data?.cmc ?? 0];
    return [c.data ? 0 : 1, typeRank(c)];
  };
  return shown
    .map((c, i) => ({ c, i, k: key(c) }))
    .sort((a, b) => a.k[0] - b.k[0] || (a.k[1] < b.k[1] ? -1 : a.k[1] > b.k[1] ? 1 : 0) || (a.c.name ?? "").localeCompare(b.c.name ?? "") || a.i - b.i)
    .map((x) => x.c);
}

/** Flip one chip of a group on or off. */
export function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}
