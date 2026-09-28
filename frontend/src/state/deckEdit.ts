/** Pure deck-list editing operations used by the deck editor (unit tested). */
import type { CardData } from "../types/cards";
import type { DeckEntry, Section } from "../types/decks";

export function addCard(entries: DeckEntry[], card: Pick<CardData, "id" | "name" | "set_code" | "collector_number">, section: Section = "main", quantity = 1): DeckEntry[] {
  const idx = entries.findIndex((e) => e.section === section && e.printing_id === card.id);
  if (idx >= 0) return changeQuantity(entries, idx, quantity);
  return [
    ...entries,
    { section, quantity, name: card.name, printing_id: card.id, set_code: card.set_code, collector_number: card.collector_number },
  ];
}

export function changeQuantity(entries: DeckEntry[], index: number, delta: number): DeckEntry[] {
  const entry = entries[index];
  if (!entry) return entries;
  const quantity = Math.min(999, entry.quantity + delta);
  if (quantity <= 0) return removeEntry(entries, index);
  return entries.map((e, i) => (i === index ? { ...e, quantity } : e));
}

export function removeEntry(entries: DeckEntry[], index: number): DeckEntry[] {
  return entries.filter((_, i) => i !== index);
}

/** Move `count` copies (default: all) of an entry to another section, merging with an existing row. */
export function moveToSection(entries: DeckEntry[], index: number, section: Section, count?: number): DeckEntry[] {
  const entry = entries[index];
  if (!entry || entry.section === section) return entries;
  const moving = Math.min(entry.quantity, count ?? entry.quantity);
  let next = moving === entry.quantity ? removeEntry(entries, index) : changeQuantity(entries, index, -moving);
  const target = next.findIndex((e) => e.section === section && e.printing_id === entry.printing_id && e.name === entry.name);
  if (target >= 0) next = changeQuantity(next, target, moving);
  else {
    const insertAt = moving === entry.quantity ? index : index + 1;
    next = [...next.slice(0, insertAt), { ...entry, section, quantity: moving }, ...next.slice(insertAt)];
  }
  return next;
}

/** Make a card the (only) commander: current commanders go back to the main deck. */
export function setCommander(entries: DeckEntry[], index: number, keepExisting = false): DeckEntry[] {
  const entry = entries[index];
  if (!entry) return entries;
  let next = entries;
  if (!keepExisting) {
    next = next.map((e) => (e.section === "commander" && e !== entry ? { ...e, section: "main" as Section } : e));
  }
  const idx = next.indexOf(next.find((e) => e.name === entry.name && e.printing_id === entry.printing_id && e.section === entry.section) ?? entry);
  return moveToSection(next, idx, "commander", 1);
}

export function setPrinting(entries: DeckEntry[], index: number, card: Pick<CardData, "id" | "name" | "set_code" | "collector_number">): DeckEntry[] {
  return entries.map((e, i) =>
    i === index ? { ...e, printing_id: card.id, name: card.name, set_code: card.set_code, collector_number: card.collector_number } : e,
  );
}

export function sectionCount(entries: DeckEntry[], section: Section): number {
  return entries.reduce((n, e) => (e.section === section ? n + e.quantity : n), 0);
}

const TYPE_ORDER = ["Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Artifact", "Enchantment", "Land"] as const;

/** Group label for the main deck view ("Creature", "Land", ...), using the front face's type line. */
export function typeGroup(typeLine: string | null | undefined): string {
  const front = (typeLine ?? "").split("//")[0] ?? "";
  for (const t of TYPE_ORDER) if (front.includes(t)) return t;
  return "Other";
}

export const TYPE_GROUP_ORDER: string[] = [...TYPE_ORDER, "Other"];
