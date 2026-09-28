export type Section = "commander" | "companion" | "main" | "sideboard" | "maybeboard" | "tokens";
export type DeckFormat = "commander" | "constructed" | "sandbox";
export const SECTIONS: Section[] = ["commander", "companion", "main", "sideboard", "maybeboard", "tokens"];
export const SECTION_LABEL: Record<Section, string> = {
  commander: "Commander",
  companion: "Companion",
  main: "Deck",
  sideboard: "Sideboard",
  maybeboard: "Maybeboard",
  tokens: "Tokens",
};

export interface DeckEntry {
  section: Section;
  quantity: number;
  name: string;
  printing_id: string | null;
  set_code: string | null;
  collector_number: string | null;
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
  summary: DeckSummary;
  warnings: DeckWarning[];
  import_report?: ImportReport;
}

export interface ParsePreview extends ImportReport {
  name: string | null;
  entries: DeckEntry[];
}
