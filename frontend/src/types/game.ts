/** Types mirroring the server's per-viewer game view (backend/app/game/views.py). */

export const PHASES = [
  "untap",
  "upkeep",
  "draw",
  "main1",
  "begin_combat",
  "declare_attackers",
  "declare_blockers",
  "combat_damage",
  "end_combat",
  "main2",
  "end",
  "cleanup",
] as const;
export type PhaseName = (typeof PHASES)[number];

export const PHASE_LABEL: Record<PhaseName, string> = {
  untap: "Untap",
  upkeep: "Upkeep",
  draw: "Draw",
  main1: "Main 1",
  begin_combat: "Begin combat",
  declare_attackers: "Attackers",
  declare_blockers: "Blockers",
  combat_damage: "Damage",
  end_combat: "End combat",
  main2: "Main 2",
  end: "End",
  cleanup: "Cleanup",
};

export type ZoneName =
  | "library"
  | "hand"
  | "battlefield"
  | "graveyard"
  | "exile"
  | "command"
  | "sideboard"
  | "companion"
  | "foretell"
  | "stack";

export const OMNISCIENT = "__omniscient__";
export const SPECTATOR = "__spectator__";

export interface TokenDef {
  name: string;
  card_id: string | null;
  power: string | null;
  toughness: string | null;
  colors: string[];
  type_line: string;
  text: string;
}

export interface AttackTarget {
  kind: "player" | "card";
  id: string;
}

interface CardBase {
  id: string;
  owner: string;
  controller: string;
  zone: string;
  face_down: boolean;
  x?: number;
  y?: number;
  tapped?: boolean;
  flipped?: boolean;
  counters?: Record<string, number>;
  attacking?: AttackTarget;
  blocking?: string;
}

export interface HiddenCard extends CardBase {
  hidden: true;
}

export interface VisibleCard extends CardBase {
  hidden?: undefined;
  card_id: string | null;
  name: string;
  face: number;
  revealed: boolean;
  note: string;
  is_token: boolean;
  token?: TokenDef;
  copy_of?: { source_id: string; source_name: string; modifications: string };
  ability?: { text: string; source_id: string | null; source_card_id: string | null; source_name: string | null; kind: string };
  commander_key?: string;
}

export type GameCard = HiddenCard | VisibleCard;

export interface LibraryView {
  count: number;
  known: [number, string][];
}

export interface CommanderInfo {
  key: string;
  name: string;
  card_id: string | null;
  instance_id: string | null;
  zone: string;
  tax: number;
}

export interface PlayerView {
  id: string;
  name: string;
  color: string;
  life: number;
  life_history: { turn: number; before: number; after: number }[];
  resources: Record<string, number>;
  commander_damage: Record<string, number>;
  commander_tax: Record<string, number>;
  city_blessing: boolean;
  mulligans: number;
  deck_id: string | null;
  deck_name: string | null;
  token_shortcuts?: string[];
  commanders: CommanderInfo[];
  hand_count: number;
  library_count: number;
}

export type LogPartView =
  | { t: string }
  | { card: { name: string; card_id: string | null } }
  | { group: { card: { name: string; card_id: string | null } }[]; hidden: number };

export interface LogEntryView {
  seq: number;
  ts: number;
  turn: number;
  phase: PhaseName;
  actor: string | null;
  kind: string;
  parts: LogPartView[];
}

export interface GameMeta {
  id: string;
  name: string;
  format: "commander" | "constructed" | "sandbox";
  seq: number;
  settings: { starting_life: number; auto_untap: boolean; auto_commander_tax: boolean };
  can_undo: boolean;
  can_redo: boolean;
  mode: "local" | "lan";
  code: string | null;
  seats: Record<string, { claimed: boolean; connected: boolean }>;
}

export interface GameView {
  view_version: number;
  game: GameMeta;
  viewer: string;
  players: PlayerView[];
  seat_order: string[];
  turn: { number: number; active_player: string; phase: PhaseName };
  table: { monarch: string | null; initiative: string | null; day_night: "day" | "night" | null };
  /** Who is searching which zone (public); contents are only in the searcher's view. */
  searches: Record<string, string>;
  /** The viewer's own open private views (search / look at top N). */
  my_views?: { id: string; viewer: string; zone: string; kind: "search" | "look"; card_ids: string[] }[];
  cards: Record<string, GameCard>;
  zones: Record<string, string[] | LibraryView>;
  stack: string[];
  log: LogEntryView[];
}

export interface GameSummary {
  id: string;
  name: string;
  format: string;
  mode: "local" | "lan";
  code: string | null;
  has_password: boolean;
  turn: number;
  players: { id: string; name: string; claimed: boolean; connected: boolean }[];
  spectators: number;
  updated_at: number;
}

export interface SaveSummary {
  id: string;
  game_id: string;
  name: string;
  autosave: boolean;
  version: number;
  created_at: string;
  size: number;
  game_name: string;
  format: string;
  turn: number;
  players: { name: string; life: number; deck: string | null }[];
}

export type Action = { type: string } & Record<string, unknown>;

export const zoneKey = (player: string | null, zone: ZoneName): string => (zone === "stack" ? "stack" : `${player}:${zone}`);

export function splitZone(key: string): { player: string | null; zone: ZoneName } {
  if (key === "stack") return { player: null, zone: "stack" };
  const idx = key.indexOf(":");
  return { player: key.slice(0, idx), zone: key.slice(idx + 1) as ZoneName };
}

export const isVisible = (c: GameCard | undefined): c is VisibleCard => !!c && !c.hidden;
