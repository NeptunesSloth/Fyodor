import { api } from "./api";
import type { CardData, SearchResponse } from "../types/cards";
import type { CardDbStats } from "./api";

export const searchCards = (q: string, opts: { tokens?: "true" | "false" | "any"; limit?: number; offset?: number } = {}) => {
  const params = new URLSearchParams({ q, tokens: opts.tokens ?? "false", limit: String(opts.limit ?? 60), offset: String(opts.offset ?? 0) });
  return api.get<SearchResponse>(`/cards/search?${params}`);
};
export const getCard = (id: string) => api.get<CardData>(`/cards/${encodeURIComponent(id)}`);
export const getPrintings = (id: string) => api.get<CardData[]>(`/cards/${encodeURIComponent(id)}/printings`);
export const getCardsBatch = (ids: string[]) => api.post<Record<string, CardData>>("/cards/batch", { ids });
export const autocomplete = (q: string) => api.get<string[]>(`/cards/autocomplete?q=${encodeURIComponent(q)}`);
export const getCardStats = () => api.get<CardDbStats>("/cards/stats");

export const imageUrl = (id: string, face = 0, size: "small" | "normal" | "large" = "normal") =>
  `/api/images/${id}?face=${face}&size=${size}`;
