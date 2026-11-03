/**
 * Client-side cache of card metadata keyed by printing id.
 *
 * Components ask for ids with `useCard(id)`; requests made in the same tick are coalesced
 * into one `/cards/batch` call. Card data never changes during a session, so entries are
 * cached forever.
 */
import { create } from "zustand";
import { getCardsBatch } from "../services/cards";
import type { CardData } from "../types/cards";

interface CardCacheState {
  cards: Record<string, CardData>;
  missing: Record<string, true>;
  put: (cards: CardData[]) => void;
}

export const useCardCache = create<CardCacheState>((set) => ({
  cards: {},
  missing: {},
  put: (cards) =>
    set((s) => {
      const next = { ...s.cards };
      for (const c of cards) next[c.id] = c;
      return { cards: next };
    }),
}));

let pending = new Set<string>();
const inflight = new Set<string>();
let scheduled = false;

export function requestCards(ids: Iterable<string>): void {
  const { cards, missing } = useCardCache.getState();
  for (const id of ids) {
    if (!id || cards[id] || missing[id] || inflight.has(id)) continue;
    pending.add(id);
  }
  if (pending.size && !scheduled) {
    scheduled = true;
    queueMicrotask(flush);
  }
}

async function flush(): Promise<void> {
  scheduled = false;
  const ids = [...pending];
  pending = new Set();
  for (const id of ids) inflight.add(id);
  try {
    for (let i = 0; i < ids.length; i += 1000) {
      const chunk = ids.slice(i, i + 1000);
      const found = await getCardsBatch(chunk);
      useCardCache.getState().put(Object.values(found));
      const notFound = chunk.filter((id) => !found[id]);
      if (notFound.length) {
        useCardCache.setState((s) => {
          const m = { ...s.missing };
          for (const id of notFound) m[id] = true;
          return { missing: m };
        });
      }
    }
  } catch (err) {
    console.error("Card batch request failed", err);
  } finally {
    for (const id of ids) inflight.delete(id);
  }
}

export function useCard(id: string | null | undefined): CardData | undefined {
  const card = useCardCache((s) => (id ? s.cards[id] : undefined));
  if (id && !card) requestCards([id]);
  return card;
}

/** Re-fetch cards whose data changed on the server (e.g. images were just cached). */
export function refreshCards(ids: string[]): void {
  useCardCache.setState((s) => {
    const cards = { ...s.cards };
    for (const id of ids) delete cards[id];
    return { cards };
  });
  requestCards(ids);
}

/** -- bring my decks -- the table just received art (from a player's own Fyodor): look again at the cards drawn as proxies. */
export function refreshImageless(): void {
  const ids = Object.values(useCardCache.getState().cards).filter((c) => !c.has_image).map((c) => c.id);
  if (ids.length) refreshCards(ids);
}
