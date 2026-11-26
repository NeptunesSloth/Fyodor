import type { LogEntryView } from "../types/game";

/**
 * -- public reveals -- 701.20a: a log line that turned cards face up for the table ("Alice revealed cards from the top of her library
 * (Nissa, Resurgent Animist): Lightning Bolt, Island and Llanowar Elves — found Llanowar Elves"). The notice shows exactly the cards that
 * line names to this viewer (printing ids: art and names, never which library card is which); a card it doesn't name to them is counted.
 */
export interface Reveal {
  key: string;
  player: string;
  source: string | null;
  cards: { name: string; card_id: string | null }[];
  hidden: number;
  /** the card a "reveal … until" found (the last one revealed), or null */
  found: { name: string; card_id: string | null } | null;
  until: boolean;
}

export const revealKey = (e: LogEntryView) => `${e.seq}:${e.ts}`;

export function revealOf(e: LogEntryView): Reveal | null {
  if (!e.reveal) return null;
  const group = e.parts.find((p): p is Extract<typeof p, { group: unknown }> => "group" in p);
  if (!group) return null;
  const cards = group.group.map((g) => g.card);
  if (!cards.length) return null;
  const found = e.reveal.found && group.hidden === 0 ? cards[cards.length - 1]! : null;
  return { key: revealKey(e), player: e.reveal.player, source: e.reveal.source, cards, hidden: group.hidden, found, until: e.reveal.until };
}

/** The reveals among log entries not seen before (oldest first); each key is added to ``seen``. */
export function freshReveals(log: LogEntryView[], seen: Set<string>): Reveal[] {
  const out: Reveal[] = [];
  for (const e of log) {
    if (!e.reveal || seen.has(revealKey(e))) continue;
    seen.add(revealKey(e));
    const r = revealOf(e);
    if (r) out.push(r);
  }
  return out;
}
