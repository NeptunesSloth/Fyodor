import { api } from "./api";
import type { Deck, DeckCategory, DeckEntry, DeckFormat, DeckSummary, ImportRequest, Job, ParsePreview, SourceDiff } from "../types/decks";

export const listDecks = () => api.get<DeckSummary[]>("/decks");
export const getDeck = (id: string) => api.get<Deck>(`/decks/${id}`);
export const createDeck = (body: ImportRequest) => api.post<Deck>("/decks", body);
export const previewImport = (body: ImportRequest) => api.post<ParsePreview>("/decks/preview", body);
/** Backwards-compatible text-only preview. */
export const parseDeck = (text: string) => previewImport({ text });
export const importOptions = () =>
  api.get<{ archidekt_url: boolean; archidekt_url_note: string; text: boolean; file: boolean; card_database: boolean }>("/decks/import-options");
export const updateDeck = (id: string, body: { name: string; format: DeckFormat; notes: string; entries: DeckEntry[]; categories?: DeckCategory[] }) =>
  api.put<Deck>(`/decks/${id}`, body);
export const importIntoDeck = (id: string, text: string, mode: "replace" | "append") =>
  api.post<Deck>(`/decks/${id}/import`, { text, mode });
export const duplicateDeck = (id: string) => api.post<Deck>(`/decks/${id}/duplicate`);
/** -- deck folders -- "" takes the deck out of every folder. */
export const moveDeckToFolder = (id: string, folder: string) => api.put<{ id: string; folder: string }>(`/decks/${id}/folder`, { folder });
/** Rename a folder; to "" removes it (its decks go back to the shelf). */
export const renameDeckFolder = (old: string, name: string) => api.post<{ moved: number }>("/deck-folders/rename", { old, new: name });
/** -- precons -- every Commander precon, bundled with the app. */
export interface Precon { id: string; name: string; set: string; released: string; commanders: string[]; added: boolean }
export const listPrecons = () => api.get<Precon[]>("/decks/precons");
export const addPrecons = (ids: string[]) => api.post<{ added: number; ids: string[] }>("/decks/precons", { ids });
/** -- saved rows -- forget the rows the deck learned at the table. */
export const resetDeckRows = (id: string) => api.del<{ id: string; row_overrides: Record<string, never> }>(`/decks/${id}/rows`);
export const deleteDeck = (id: string) => api.del<void>(`/decks/${id}`);
export const exportDeck = async (id: string, format: "archidekt" | "plain" = "archidekt"): Promise<string> => {
  const res = await fetch(`/api/decks/${id}/export?format=${format}`);
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  return res.text();
};
export const checkSource = (id: string) =>
  api.post<{ diff: SourceDiff; remote_updated_at: string | null; local_edits: boolean }>(`/decks/${id}/source/check`);
export const applySource = (id: string) => api.post<Deck>(`/decks/${id}/source/apply`);
export const ignoreSource = (id: string) => api.post<Deck>(`/decks/${id}/source/ignore`);
export const unlinkSource = (id: string) => api.del<void>(`/decks/${id}/source`);
/** missing: printings without their own picture here; borrowed: of those, the ones showing another printing's of the card. */
export interface ArtStatus { printings: number; missing: number; borrowed?: number }
export const artStatus = (id: string) => api.get<ArtStatus>(`/decks/${id}/art-status`);
export const cacheArt = (id: string) => api.post<Job>(`/decks/${id}/cache-art`);
export const getJob = (id: string) => api.get<Job>(`/jobs/${id}`);
/** Keep deck art for offline play: whether it's on, how many decks wait for the network, what is downloading now. */
export interface ArtKeeperStatus {
  enabled: boolean;
  pending: number;
  running: boolean;
  network: boolean;
  deck?: string;
  done?: number;
  total?: number;
}
export const artKeeper = () => api.get<ArtKeeperStatus>("/decks/art-keeper");
export const setArtKeeper = (enabled: boolean) => api.put<ArtKeeperStatus>("/decks/art-keeper", { enabled });

/** -- deck sharing -- friends on the network see this computer's decks only while `enabled` (all, or the ones marked shared). */
export interface Sharing { enabled: boolean; all: boolean }
export const deckSharing = () => api.get<Sharing>("/decks/sharing");
export const setDeckSharing = (body: Sharing) => api.put<Sharing>("/decks/sharing", body);
export const setDeckShared = (id: string, shared: boolean) => api.put<{ id: string; shared: boolean }>(`/decks/${id}/shared`, { shared });
/** A friend's shared decks (their Fyodor at `url`, asked by this computer's server). */
export interface FriendDeck { name: string; commanders: string[]; text: string }
export const friendDecks = (url: string) => api.get<{ from: string; url: string; decks: FriendDeck[] }>(`/lan/friend-decks?url=${encodeURIComponent(url)}`);

/** Poll a background job until it finishes. */
export async function waitForJob(id: string, onProgress: (job: Job) => void): Promise<Job> {
  for (;;) {
    const job = await getJob(id);
    onProgress(job);
    if (job.state !== "running") return job;
    await new Promise((r) => setTimeout(r, 600));
  }
}
