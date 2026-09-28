import { api } from "./api";
import type { Deck, DeckEntry, DeckFormat, DeckSummary, ParsePreview } from "../types/decks";

export const listDecks = () => api.get<DeckSummary[]>("/decks");
export const getDeck = (id: string) => api.get<Deck>(`/decks/${id}`);
export const createDeck = (body: { name?: string; format?: DeckFormat; text: string }) => api.post<Deck>("/decks", body);
export const parseDeck = (text: string) => api.post<ParsePreview>("/decks/parse", { text });
export const updateDeck = (id: string, body: { name: string; format: DeckFormat; notes: string; entries: DeckEntry[] }) =>
  api.put<Deck>(`/decks/${id}`, body);
export const importIntoDeck = (id: string, text: string, mode: "replace" | "append") =>
  api.post<Deck>(`/decks/${id}/import`, { text, mode });
export const duplicateDeck = (id: string) => api.post<Deck>(`/decks/${id}/duplicate`);
export const deleteDeck = (id: string) => api.del<void>(`/decks/${id}`);
export const exportDeck = async (id: string): Promise<string> => {
  const res = await fetch(`/api/decks/${id}/export`);
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  return res.text();
};
