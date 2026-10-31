/**
 * Sorting your own hand, as MTG Arena does: as drawn, by mana value, colour, type or name. Display only: the hand
 * keeps its order on the server, and nobody else sees your hand anyway.
 */
import type { HandSort } from "../state/prefs";

export const HAND_SORTS: HandSort[] = ["drawn", "mana", "color", "type", "name"];
export const HAND_SORT_LABEL: Record<HandSort, string> = {
  drawn: "as drawn",
  mana: "by mana value",
  color: "by colour",
  type: "by type",
  name: "by name",
};

export const nextHandSort = (s: HandSort): HandSort => HAND_SORTS[(HAND_SORTS.indexOf(s) + 1) % HAND_SORTS.length]!;

export interface HandFacts { name: string; mv: number; colors: string[]; typeLine: string }

const WUBRG = "WUBRG";
const TYPE_ORDER = ["Land", "Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Artifact", "Enchantment"];

const isLand = (f: HandFacts) => /\bLand\b/.test(f.typeLine);
/** Mono colours in WUBRG order, then multicolour, then colourless; lands after the spells. */
function colorRank(f: HandFacts): number {
  if (isLand(f)) return 8;
  if (f.colors.length > 1) return 6;
  if (f.colors.length === 1) return Math.max(0, WUBRG.indexOf(f.colors[0]!));
  return 7;
}
function typeRank(f: HandFacts): number {
  const i = TYPE_ORDER.findIndex((t) => new RegExp(`\\b${t}\\b`).test(f.typeLine));
  return i < 0 ? TYPE_ORDER.length : i;
}

const KEYS: Record<Exclude<HandSort, "drawn">, (f: HandFacts) => (number | string)[]> = {
  mana: (f) => [isLand(f) ? 0 : 1, f.mv, f.name],
  color: (f) => [colorRank(f), f.mv, f.name],
  type: (f) => [typeRank(f), f.mv, f.name],
  name: (f) => [f.name],
};

function compare(a: (number | string)[], b: (number | string)[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i];
    const y = b[i];
    if (x === y) continue;
    if (typeof x === "number" && typeof y === "number") return x - y;
    return String(x).localeCompare(String(y));
  }
  return 0;
}

/** The hand in display order. Cards we know nothing about (not loaded yet) keep their place at the end. */
export function sortHand(ids: string[], facts: (id: string) => HandFacts | null, mode: HandSort): string[] {
  if (mode === "drawn") return ids;
  const key = KEYS[mode];
  const known = ids.map((id, i) => ({ id, i, f: facts(id) }));
  return known
    .sort((a, b) => {
      if (!a.f || !b.f) return (a.f ? 0 : 1) - (b.f ? 0 : 1) || a.i - b.i;
      return compare(key(a.f), key(b.f)) || a.i - b.i;
    })
    .map((x) => x.id);
}
