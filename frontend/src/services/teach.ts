/** -- Teach Fyodor -- the host's library of taught mechanics and card lines (backend app/api/teach.py). */

import type { CardLines, CheckResult, Entry, TaughtRow, Vocabulary } from "../teach/types";
import { api } from "./api";

export const getVocabulary = () => api.get<Vocabulary>("/teach/vocabulary");
export const listTaught = () => api.get<TaughtRow[]>("/teach");
export const checkEntry = (entry: Entry, typeLine?: string | null) =>
  api.post<CheckResult>("/teach/check", { entry, type_line: typeLine ?? null });
export const createTaught = (entry: Entry) => api.post<TaughtRow>("/teach", { entry });
export const updateTaught = (id: string, entry: Entry) => api.put<TaughtRow>(`/teach/${encodeURIComponent(id)}`, { entry });
export const enableTaught = (id: string, enabled: boolean) => api.patch<TaughtRow>(`/teach/${encodeURIComponent(id)}`, { enabled });
export const deleteTaught = (id: string) => api.del<void>(`/teach/${encodeURIComponent(id)}`);
export const cardLines = (cardId: string) => api.get<CardLines>(`/teach/card/${encodeURIComponent(cardId)}`);
export const tryIt = (entry: Entry, cardId?: string | null) =>
  api.post<{ game: { id: string }; seat?: { player_id: string; token: string } }>("/teach/try", { entry, card_id: cardId ?? null });

/** The export link (a small JSON file): the whole library, or the given entries. */
export const exportUrl = (ids?: string[]) =>
  `/api/teach/export${ids?.length ? `?${ids.map((i) => `ids=${encodeURIComponent(i)}`).join("&")}` : ""}`;

export async function importTaught(file: File): Promise<{ imported: number; replaced: number; entries: TaughtRow[] }> {
  const res = await fetch("/api/teach/import", { method: "POST", body: await file.text(), headers: { "content-type": "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* not json */ }
    throw new Error(detail);
  }
  return (await res.json()) as { imported: number; replaced: number; entries: TaughtRow[] };
}
