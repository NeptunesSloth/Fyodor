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

/** How much of a card the rules engine plays by itself (GET /rules/coverage; app/rules/coverage.py). */
export interface CardCoverage {
  level: "FULL" | "PARTIAL" | "REVIEW" | "MANUAL";
  features: { id: string; label: string; supported: boolean }[];
  /** the parts played by hand */
  manual_parts: string[];
  /** a script exists, but the Oracle text changed since it was checked */
  review_needed: boolean;
}
const coverageCache = new Map<string, Promise<CardCoverage | null>>();
/** One printing's automation coverage, asked once per card per session (it only changes with a new Fyodor). */
export function getCoverage(id: string): Promise<CardCoverage | null> {
  let got = coverageCache.get(id);
  if (!got) {
    got = api.get<Record<string, CardCoverage>>(`/rules/coverage?card_ids=${encodeURIComponent(id)}`).then((r) => r[id] ?? null);
    got.catch(() => coverageCache.delete(id));
    coverageCache.set(id, got);
  }
  return got;
}

export const imageUrl = (id: string, face = 0, size: "small" | "normal" | "large" = "normal") =>
  `/api/images/${id}?face=${face}&size=${size}`;
