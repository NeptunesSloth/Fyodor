/** UPDATE CARD DATABASE on the host (backend app/cards/updater.py): check Scryfall, download, switch over. */
import { api, type CardDbStats } from "./api";

export interface CardJob {
  id: string;
  kind: string;
  state: "running" | "done" | "failed";
  done: number;
  total: number;
  phase: string;
  message: string;
}
export interface CardDataInfo { current: CardDbStats; job: CardJob | null; network: boolean }
export interface CardCheck { available: boolean; bulk_type: string; remote_updated_at: string; size: number | null; current: CardDbStats }

export const cardData = () => api.get<CardDataInfo>("/card-data");
export const checkCardData = () => api.post<CardCheck>("/card-data/check", {});
export const startCardUpdate = (force = false) => api.post<CardJob>("/card-data/update", { force });

const BULK_NAMES: Record<string, string> = {
  default_cards: "every printing",
  oracle_cards: "one printing per card",
  unique_artwork: "every artwork",
  all_cards: "every printing in every language",
};
export const bulkName = (kind: string | null) => (kind ? BULK_NAMES[kind] ?? kind : "");

const mb = (bytes: number) => `${Math.round(bytes / 1e6).toLocaleString()} MB`;

/** "Downloading 120 / 520 MB", "Importing 51,200 of about 112,000 printings", or just the phase. */
export function progressText(job: CardJob): string {
  if (job.phase === "Downloading") return job.total ? `Downloading ${mb(job.done)} / ${mb(job.total)}` : `Downloading ${mb(job.done)}`;
  if (job.phase === "Importing") return job.total > job.done ? `Importing ${job.done.toLocaleString()} of about ${job.total.toLocaleString()} printings` : `Importing ${job.done.toLocaleString()} printings`;
  return job.phase ? `${job.phase}…` : "Starting…";
}

/** 0–1 for a filled bar, or null while the step can't be measured. */
export function progressFraction(job: CardJob): number | null {
  if ((job.phase === "Downloading" || job.phase === "Importing") && job.total > 0) return Math.min(1, job.done / job.total);
  return null;
}

/** "31 Oct 2026" from Scryfall's "2026-10-31T09:04:12.123+00:00". */
export function scryfallDay(stamp: string | null): string {
  if (!stamp) return "an unknown date";
  const d = new Date(stamp);
  return Number.isNaN(d.getTime()) ? stamp.slice(0, 10) : d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

/** -- art folders -- more folders of card pictures the host reads in place (backend app/cards/art_folders.py). */
export interface ArtFolder {
  path: string;
  /** Where the pictures actually are (the chosen folder, or the images folder inside it). */
  folder: string;
  source: "bundled" | "auto" | "env" | "added";
  exists: boolean;
  layout: "fyodor" | "loose" | null;
  count: number;
}
export const artFolders = () => api.get<{ folders: ArtFolder[] }>("/art-folders");
export const addArtFolder = (path: string) => api.post<{ added: ArtFolder; folders: ArtFolder[] }>("/art-folders", { path });
export const removeArtFolder = (path: string) => api.del<{ folders: ArtFolder[] }>(`/art-folders?path=${encodeURIComponent(path)}`);
export const rescanArtFolders = () => api.post<{ folders: ArtFolder[] }>("/art-folders/rescan", {});

const SOURCE_LABELS: Record<ArtFolder["source"], string> = {
  bundled: "came with Fyodor",
  auto: "found on this computer",
  env: "FYODOR_ART_DIRS",
  added: "added here",
};
export const artSourceLabel = (source: ArtFolder["source"]) => SOURCE_LABELS[source] ?? source;

/** "1 picture", "12,400 pictures", or "missing" for a folder that isn't there now. */
export function artFolderCount(folder: ArtFolder): string {
  if (!folder.exists) return "missing";
  return folder.count === 1 ? "1 picture" : `${folder.count.toLocaleString()} pictures`;
}
