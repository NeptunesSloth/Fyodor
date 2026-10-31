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
