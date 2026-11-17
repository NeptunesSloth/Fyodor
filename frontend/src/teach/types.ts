/**
 * -- Teach Fyodor -- the vocabulary the backend serves (app/rules/taught_vocab.py) and the shape of a taught entry
 * (app/rules/taught.py). Everything here is data: pieces, their settings and the values a player picked.
 */

export type Role = "trigger" | "activated" | "static_hat" | "condition" | "cost" | "limit" | "optional_cost" | "effect" | "static"
  | "may" | "ifdo" | "then";

export interface Category { id: string; label: string; hint: string }

export interface NumberSlot { kind: "number" | "signed"; min: number; max: number; param: boolean; default: number }
export interface ChoiceSlot { kind: "choice"; options: string[]; default: string }
export interface ManaSlot { kind: "mana"; default: string; colored?: boolean }
export type Slot = NumberSlot | ChoiceSlot | ManaSlot;

export interface Piece {
  id: string;
  cat: string;
  role: Role;
  label: string;
  text: string;
  slots?: Record<string, Slot>;
  /** a static's wording without an If piece ("Flying" rather than "This creature has flying.") */
  bare?: string;
  /** a Do piece that may go inside "You may …" */
  may?: boolean;
  /** a Do piece that only follows this other piece ("Keep one of the milled cards" after "Mill cards") */
  after?: string;
  needs_condition?: boolean;
  no_condition?: boolean;
  trigger_only?: boolean;
}

export interface Option { text: string; plural?: boolean; cat?: string }

export interface Vocabulary {
  version: number;
  categories: Category[];
  pieces: Piece[];
  options: Record<string, Option>;
  values: (number | string)[];
}

/** A slot's value: a number, "N" / "-N" (the keyword's number), an option id or a mana cost. */
export type Value = number | string;

export interface Block {
  id: string;
  values?: Record<string, Value>;
  body?: Block[];
}

export interface Ability { hat: Block; body: Block[] }

export interface KeywordEntry {
  kind: "keyword";
  name: string;
  param: boolean;
  reminder: string;
  abilities: Ability[];
}

export interface CardEntry {
  kind: "card";
  oracle_id: string;
  line: string;
  card_name: string;
  type_line?: string;
  name?: string;
  abilities: Ability[];
}

export type Entry = KeywordEntry | CardEntry;

/** One row of the host's library (GET /api/teach). */
export interface TaughtRow {
  id: string;
  kind: "keyword" | "card";
  name: string;
  oracle_id: string | null;
  line: string | null;
  enabled: boolean;
  entry: Entry;
  lines: string[];
  updated_at: string;
}

export interface Problem { where: string; message: string }

export interface CheckResult {
  ok: boolean;
  problems: Problem[];
  lines: string[];
  abilities: { text: string; understood: boolean; definition: unknown }[];
}

export interface CardLine {
  text: string;
  face: string;
  type_line: string | null;
  manual: boolean;
  taught_id: string | null;
  keyword: { name: string; param: boolean } | null;
}

export interface CardLines {
  card: { id: string; name: string; oracle_id: string; type_line: string | null; has_script: boolean };
  level: string;
  level_taught: string;
  lines: CardLine[];
}

export const pieceIndex = (voc: Vocabulary): Record<string, Piece> => Object.fromEntries(voc.pieces.map((p) => [p.id, p]));
