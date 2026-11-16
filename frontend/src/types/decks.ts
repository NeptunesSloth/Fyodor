export type Section = "commander" | "companion" | "main" | "sideboard" | "maybeboard" | "tokens" | "attractions" | "stickers";
export type DeckFormat = "commander"; // Fyodor is Commander-only
export const SECTIONS: Section[] = ["commander", "companion", "main", "sideboard", "maybeboard", "tokens", "attractions", "stickers"];
export const SECTION_LABEL: Record<Section, string> = {
  commander: "Commander",
  companion: "Companion",
  main: "Deck",
  sideboard: "Sideboard",
  maybeboard: "Maybeboard",
  tokens: "Tokens",
  attractions: "Attraction deck",
  stickers: "Sticker sheets",
};

export type Finish = "nonfoil" | "foil" | "etched";
export type Resolution = "exact" | "set" | "fallback" | "name" | "manual" | "unresolved";

export interface DeckEntry {
  section: Section;
  quantity: number;
  name: string;
  printing_id: string | null;
  oracle_id?: string | null;
  set_code: string | null;
  collector_number: string | null;
  finish?: Finish;
  categories?: string[];
  tags?: string[];
  resolution?: Resolution | null;
  requested?: { name: string | null; set_code: string | null; collector_number: string | null; printing_id: string | null } | null;
}

export interface DeckCategory {
  name: string;
  included_in_deck: boolean;
  premier: boolean;
}

export interface DeckSource {
  kind: "archidekt" | "text" | "file";
  id: string | null;
  url: string | null;
  name: string | null;
  updated_at: string | null;
  imported_at: string | null;
}

export interface ImportStats {
  source_kind: string;
  cards_total: number;
  entries: number;
  resolved: number;
  exact_printings: number;
  fallbacks: { name: string; requested: string; used: string; resolution: string }[];
  unresolved: UnresolvedLine[];
  commanders: string[];
  categories: string[];
  sections: Partial<Record<Section, number>>;
  errors: string[];
  notes: string[];
}

export interface SourceDiff {
  changed: boolean;
  added: { name: string; quantity: number; section: string }[];
  removed: { name: string; quantity: number; section: string }[];
  printing_changed: { name: string; from: string; to: string }[];
  category_changed: { name: string; from: string[]; to: string[] }[];
  section_changed: { name: string; from: string; to: string }[];
}

export interface Job {
  id: string;
  kind: string;
  label: string;
  state: "running" | "done" | "failed";
  done: number;
  total: number;
  failed: number;
  message: string;
}

export interface DeckWarning {
  level: "info" | "warning" | "error";
  message: string;
  card: string | null;
}

export interface DeckSummary {
  id: string;
  name: string;
  format: DeckFormat;
  updated_at: string;
  counts: Partial<Record<Section, number>>;
  commanders: string[];
  color_identity: string[];
  cover_id: string | null;
  unresolved: number;
  /** The shelf folder it sits in ("" = none). */
  folder?: string;
}

export interface UnresolvedLine {
  name: string;
  section: Section;
  quantity: number;
  suggestions: string[];
}

export interface ImportReport {
  unresolved: UnresolvedLine[];
  errors: string[];
  notes: string[];
}

export interface Deck {
  id: string;
  name: string;
  format: DeckFormat;
  notes: string;
  created_at: string;
  updated_at: string;
  entries: DeckEntry[];
  categories: DeckCategory[];
  source: DeckSource | null;
  summary: DeckSummary;
  warnings: DeckWarning[];
  import_report?: ImportStats;
  conflicts?: string[];
  /** -- saved rows -- card name -> the battlefield row it was moved to at the table (it enters there in later games) */
  row_overrides?: Record<string, SavedRow>;
}

export type SavedRow = "land" | "creature" | "other";

export interface ParsePreview extends ImportReport {
  name: string | null;
  format: DeckFormat | null;
  source: DeckSource | null;
  entries: DeckEntry[];
  categories: DeckCategory[];
  report: ImportStats;
}

export interface ImportRequest {
  text?: string;
  archidekt?: string;
  json?: string;
  name?: string;
  format?: DeckFormat;
}
