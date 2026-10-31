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
  | "setaside"
  | "phased"
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

export type FaceDownKind = "generic" | "morph" | "disguise" | "manifest" | "cloak" | "exile";
export const FACE_DOWN_LABEL: Record<FaceDownKind, string> = {
  generic: "Face down",
  morph: "Morph",
  disguise: "Disguise",
  manifest: "Manifest",
  cloak: "Cloak",
  exile: "Exiled face down",
};

interface CardBase {
  id: string;
  owner: string;
  controller: string;
  zone: string;
  face_down: boolean;
  /** How it got face down (public). */
  face_down_kind?: FaceDownKind;
  /** What the effect made it face down, e.g. "Forest land" (708.2a; public). */
  face_down_as?: string;
  x?: number;
  y?: number;
  tapped?: boolean;
  flipped?: boolean;
  counters?: Record<string, number>;
  attacking?: AttackTarget;
  attacking_without_target?: string;
  blocking?: string;
  blocking_without_attacker?: boolean;
  blocking_more?: string[]; // 509.1a: further attackers a creature that can block several blocks
  /** Manual table markers (public on the battlefield / stack, even when face down). */
  effects?: CardEffect[];
  damage?: number;
  stack_info?: { x: number | null; modes: string[]; tags: string[] };
  exile_group?: string;
  locked?: boolean;
  protected?: boolean;
  rotation?: number;
  attached_to?: string | null;
  attached_player?: string | null;  // an Aura enchanting a player
  group?: string | null;
  quantity?: number;
}

export interface CardEffect {
  id: string;
  name: string;
  value?: string;
  text?: string;
  color?: string;
}

export interface TableArrow {
  id: string;
  owner: string;
  source: string;
  targets: string[];
  kind: "target" | "attack" | "block" | "custom";
  label: string;
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
  /** Merged (mutate, 730) or melded (701.42) permanent: the cards or tokens representing it, topmost first (public). */
  merged?: { id: string; card_id: string | null; name: string; is_token: boolean; token?: TokenDef }[];
  melded?: boolean;
  choices?: Record<string, string>;
  token_source?: { source_id: string | null; name: string };
  test_object?: boolean;
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
  /** null: a face-down commander this viewer can't look at (708.5). */
  zone: string | null;
  tax: number;
  /** Times cast from the command zone. */
  casts?: number;
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
  /** Only in your own player entry. */
  deck_id?: string | null;
  /** Hidden from opponents when the table's deck privacy is "private". */
  deck_name?: string | null;
  token_shortcuts?: string[];
  commanders: CommanderInfo[];
  left?: boolean;
  sleeve?: string | null;
  playmat?: Playmat | null;
  /** Temporary mana pool, e.g. { U: 2, C: 3 }. */
  mana?: Record<string, number>;
  /** Restricted or remembered mana (CR 106.6): its type, its source's types, and the restriction in Oracle words. */
  mana_units?: ManaUnit[];
  hand_count: number;
  library_count: number;
}

export interface ManaUnit {
  id: number;
  sym: string;
  tags: string[];
  note: string;
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
  /** A public dice roll or coin flip's numbers (coin results: 1 heads, 0 tails). */
  roll?: { sides: number; results: number[]; coin: boolean };
  /** Cards turned over from the top of a library (reveal until, cascade): public, for their owner to place. */
  dig?: DigLog;
}

export interface DigLog { mode: "reveal_until" | "cascade"; player: string; cards: string[]; hit: string | null }

export interface GameMeta {
  id: string;
  name: string;
  format: "commander" | "constructed" | "sandbox";
  seq: number;
  settings: {
    starting_life: number;
    auto_untap: boolean;
    auto_commander_tax: boolean;
    deck_privacy?: "private" | "commander_only" | "public";
    priority_helper?: "off" | "simple";
    mulligan?: MulliganPolicy | null;
    clear_mana_on_step?: boolean;
    auto_clear_combat?: boolean;
    allow_test_objects?: boolean;
  };
  can_undo: boolean;
  can_redo: boolean;
  mode: "local" | "lan";
  code: string | null;
  seats: Record<string, { claimed: boolean; connected: boolean; presence?: "open" | "connected" | "reconnecting" | "disconnected" }>;
  /** Custom images used at this table (sleeves, playmats), by asset id. */
  assets?: Record<string, AssetRef>;
  /** Set once the pod result for this game has been recorded. */
  result_id?: string | null;
  /** Authoritative revision: grows with every update the server sends. */
  revision?: number;
  /** LAN: the host's seat (table-level overrides are the host's). */
  host_seat?: string | null;
  /** Game night: turn order and its d20 rolls, an agreed-ending proposal, the result and rematch vote. */
  night?: NightInfo;
}

export type NightResultType = "single" | "multiple" | "draw" | "no_result";

/** Everything here is public (docs/GAME_NIGHT_FLOW.md). Seats are this game's player ids. */
export interface NightInfo {
  number: number;
  order_source: "d20" | "winner_last" | "host";
  /** d20 rounds: the first is everyone, later ones are tie-breaks among the tied players. */
  rolls: Record<string, number>[];
  previous_winner: string | null;
  proposal: { by: string; by_name: string; result_type: NightResultType; winners: string[]; winner_names: string[]; agreed: string[] } | null;
  result: { result_type: NightResultType; winners: string[]; winner_names: string[]; agreed: boolean } | null;
  votes: Record<string, "rematch" | "lobby">;
  history: { number: number; result_type: NightResultType; winner_names: string[]; agreed: boolean; order: string[]; turns: number }[];
}

/** How opening hands work at this table (see docs/MULLIGAN_RULES.md). */
export interface MulliganPolicy {
  id: string;
  display_name: string;
  starting_hand_size: number;
  free_mulligans: number;
  draw_count: number;
  shuffle_between_mulligans: boolean;
  cards_to_bottom: number;
  partial_hand_selection: boolean;
  set_aside_rejected_hands: boolean;
  final_shuffle: boolean;
  minimum_hand_size: number;
  max_mulligans: number | null;
  needs_definition: boolean;
}

export interface ResponseWindow {
  id: string;
  kind: "stack" | "resolve" | "phase" | "turn";
  opener: string;
  text: string;
  waiting: string[];
  passed: string[];
  responder: string | null;
  /** Something (resolve / next step / next turn) happens when everyone has passed. */
  has_intent: boolean;
}

export interface PregameSeat {
  status: "deciding" | "bottoming" | "kept";
  mulligans: number;
  to_bottom: number;
  kept: number | null;
}

export interface GameView {
  view_version: number;
  game: GameMeta;
  viewer: string;
  players: PlayerView[];
  seat_order: string[];
  turn: { number: number; active_player: string; phase: PhaseName };
  table: { monarch: string | null; initiative: string | null; day_night: "day" | "night" | null; playmat?: Playmat | null };
  /** Who is searching which zone (public); contents are only in the searcher's view. */
  searches: Record<string, string>;
  /** The viewer's own open private views (search / look at top N). */
  my_views?: { id: string; viewer: string; zone: string; kind: "search" | "look"; card_ids: string[] }[];
  /** Opening hands still being decided (null once everyone has kept). */
  pregame?: { seats: Record<string, PregameSeat>; finished: boolean; mine?: { powder: string[] } } | null;
  /** The open "anything in response?" check, if any (public). */
  response?: ResponseWindow | null;
  /** Players auto-passing response checks this turn. */
  auto_pass?: string[];
  cards: Record<string, GameCard>;
  arrows?: TableArrow[];
  zones: Record<string, string[] | LibraryView>;
  stack: string[];
  log: LogEntryView[];
  /** Rules automation (absent when automation is OFF). See docs/AUTOMATION_UX.md. */
  rules?: RulesView;
}

export type AutomationLevel = "off" | "assisted" | "full";
export type ResponseMode = "off" | "auto" | "on";
export type PaymentMode = "auto" | "ask" | "manual";

export interface DecisionOptionView {
  id: string;
  label: string;
  card_id: string | null;
  group?: string | null;
}

export interface DecisionView {
  id: string;
  player: string;
  /** "waiting": someone else's decision whose nature isn't public (only ``public`` is sent). */
  kind: "manual_resolution" | "declare_attackers" | "declare_blockers" | "choose_one" | "choose_cards" | "confirm" | "reconcile" | "order" | "divide" | "waiting";
  prompt: string;
  source_id: string | null;
  /** Only in the chooser's own view. */
  options?: DecisionOptionView[];
  min_choices?: number;
  max_choices?: number;
  rememberable?: boolean;
  /** A spell's or ability's mode / target choice (601.2): answering ["cancel"] takes the cast back, nothing paid. */
  cancelable?: boolean;
  /** Presentation hints for the chooser (e.g. a payment's suggested sources). */
  display?: { kind: string; [key: string]: unknown };
  /** Other players' view of someone's decision: only who is choosing. */
  public?: { type: "PLAYER_MAKING_CHOICE"; chooser: string };
}

export interface RulesPrefs {
  response: ResponseMode;
  stops_my_turn: string[];
  stops_their_turn: string[];
  bluff_stops: boolean;
  payment: PaymentMode;
  mana_sources: Record<string, "prefer" | "save">;
  auto_resolve_own_triggers: "off" | "safe" | "on";
  auto_order_identical_triggers: boolean;
  auto_target?: boolean;
  ask_graveyard_order: boolean;
  hold_priority: boolean;
  full_control: boolean;
  force_stop: boolean;
  pass_until: string | null;
  stop_after: string | null;
  yields: { kind: string; key: string; context: string; turn: number }[];
}

export interface RulesHints {
  deferred_payments?: { id: string; cost: string; name: string }[];
  has_priority?: boolean;
  playable_lands?: string[];
  castable?: string[];
  free_castable?: string[]; // a permission lets you cast these without paying their mana costs
  alt_castable?: Record<string, { id: string; label: string; x?: boolean }[]>; // alternative costs (118.9): card id → costs it can be cast for now (x: the cost has {X}, 107.3a)
  optional_costs?: Record<string, { id: string; label: string }[]>; // optional additional costs (Defiler of Vigor): card id → sources
  x_cast?: string[]; // castable cards of yours that ask for X when cast (107.3a); the server validates the range (min 0)
  chorus?: string[]; // castable creature cards whose cast may set `chorus` (Chorus of the Conclave, 601.2b, wave 110C)
  x_kicker?: string[]; // castable cards of yours whose kicker cost has {X}: only a kicked cast asks for it (107.3a, wave 43D)
  activatable?: { card_id: string; ability: number; x?: boolean }[]; // x: the activation asks for X (107.3k)
  miracle?: string[]; // cards of yours you may reveal for miracle now (702.94a)
  channel?: string; // -- wave 110I -- Channel: the player-level mana ability's ActivateAbility.card_id ("player:channel110i"), while you have it (605.3a)
}

export interface RulesView {
  automation: AutomationLevel;
  preset: "sandbox" | "assisted" | "full" | "custom";
  options: Record<string, boolean | string>;
  status: { auto: string; resp: string | null };
  paused: boolean;
  priority: string | null;
  passed: string[];
  attacking_bands?: string[][]; // Public card IDs; bands last until their members leave combat.
  conceded: string[];
  lost: Record<string, string>;
  winner: string | null;
  draw_reason?: string | null;
  overrides: number;
  decision: DecisionView | null;
  prefs: RulesPrefs | null;
  reconcile: { id: string; card: string | null; player: string | null; question: string }[];
  card_modes: Record<string, "manual" | "assisted">;
  hints: RulesHints;
  /** Controlling another player (CR 723): the seat this viewer acts as right now (hints and priority are theirs), and who controls whom. */
  acting_as?: string | null;
  /** Set for the controlled player: who makes their choices now (they may only concede, 723.6). */
  controlled_by?: string;
  control?: { controlled: string; controller: string; status: "pending" | "active" }[];
  /** Current P/T and keyword changes of visible battlefield creatures (anthems, pumps, crew …). */
  stats?: Record<string, CardStats>;
  failure?: { intent: string; at: number };
}

export interface Playmat {
  asset_id: string;
  fit: "cover" | "contain" | "stretch";
  scale: number;
  offset_x: number;
  offset_y: number;
  rotation: 0 | 90 | 180 | 270;
  opacity: number;
  show_zones: boolean;
}

export interface AssetRef {
  url: string;
  width: number;
  height: number;
  kind: string;
}

export interface GameSummary {
  id: string;
  phase?: "lobby" | "playing";
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

// ---------------------------------------------------------------------------- lobby

export interface LobbySettings {
  name: string;
  format: "commander" | "constructed" | "sandbox";
  seats: number;
  starting_life: number | null;
  deck_privacy: "private" | "commander_only" | "public";
  mulligan_rule: string;
  mulligan_policy: MulliganPolicy | null;
  priority_helper: "off" | "simple";
  auto_untap: boolean;
  automation: AutomationLevel;
  /** "pod": d20 for game 1 and after a draw, then the previous winner goes last. */
  turn_order?: "pod" | "random";
}

export interface LobbyDeckSummary {
  offline?: import("../services/games").PersonalDeck;
  card_count: number;
  name?: string;
  commanders?: string[];
  commander_ids?: string[];
  color_identity?: string[];
  /** Automation coverage of the deck: card counts per level. */
  coverage?: { FULL: number; PARTIAL: number; REVIEW: number; MANUAL: number };
  list?: { section: string; quantity: number; name: string }[];
  /** Advisory deck checks for the table's format (never block the game). */
  warning_count?: number;
  warnings?: { level: "info" | "warning" | "error"; message: string; card?: string | null }[];
  report?: {
    cards_total?: number;
    exact_printings?: number;
    unresolved: { line?: string; name?: string; reason?: string }[];
    notes?: string[];
    errors?: string[];
  };
}

export interface LobbySeat {
  id: string;
  name: string;
  color: string;
  claimed: boolean;
  connected: boolean;
  ready: boolean;
  host: boolean;
  deck: LobbyDeckSummary | null;
}

export interface LobbyView {
  phase: "lobby";
  /** Room revision when this lobby was built (older ones arriving late are ignored). */
  revision?: number;
  game: { id: string; mode: "lan"; code: string | null; has_password: boolean };
  viewer: string;
  is_host: boolean;
  settings: LobbySettings;
  /** The effective mulligan policy (null: mulligans by hand). */
  mulligan: MulliganPolicy | null;
  seats: LobbySeat[];
  spectators: number;
  start_blockers: string[];
  /** Tonight's finished games, oldest first (the session recap). */
  night?: (NightInfo["history"][number] & { minutes?: number; commanders?: Record<string, string[]> })[];
}

export interface CardStats {
  /** Private special-action costs for a face-down permanent this viewer controls. */
  turn_up?: { method: "morph" | "disguise" | "mana_cost"; cost: string }[];
  pt?: [number, number];
  base?: [string | null, string | null];  // printed power/toughness
  gained?: string[];
  lost?: string[];
  creature?: boolean;
  /** A Room's unlocked doors (709.5c): 1 = left half, 2 = right half. */
  doors?: number[];
  /** A Room's two halves (its own, or the copied card's): each door's name and unlock cost. */
  halves?: { name: string; mana_cost: string }[];
  /** Abilities granted by other permanents (numbered from 100). */
  abilities?: { index: number; text: string; kind: string }[];
  /** -- licids (wave 50A) -- 116.2c: the cost you may pay (a special action) to end the effect you have on this permanent ("You may pay {W} to end this effect"). */
  end_cost?: string;
  /** The special action's own wording when it doesn't end an effect (Leonin Arbiter: "Ignore … until end of turn"). */
  end_label?: string;
}
