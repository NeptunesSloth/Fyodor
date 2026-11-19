/**
 * Plain helpers behind joining tables from the Play page (no React, so they're tested directly): a join link's parameters
 * (`#/play?code=…&name=…&join=1`), what to do with them, the link to a table on another computer, and how the Play page and
 * the launcher list the tables found on the network (GET /api/lan/nearby).
 */
import type { BroughtLibrary, LobbyDeckBody, MyDeck } from "../services/games";
import type { GameSummary } from "../types/game";

/** A table another Fyodor on the network answered with (backend app/multiplayer/discovery.py). */
export interface NearbyTable {
  id: string;
  name: string;
  format: string;
  phase: "lobby" | "playing";
  code: string;
  has_password: boolean;
  seats: number;
  taken: number;
  open: number;
  players: string[];
  turn: number;
}

export interface NearbyServer {
  /** the host computer's name */
  name: string;
  /** http://<its address>:<port> */
  url: string;
  version: string;
  tables: NearbyTable[];
}

export interface NearbyRow {
  server: NearbyServer;
  table: NearbyTable;
}

export interface Invite {
  code: string;
  name: string;
  /** join=1, watch=1, or a plain invite link that only fills the code in */
  action: "join" | "watch" | "fill";
  /** the deck library the player's own Fyodor sent ahead (one use) */
  handoff: string | null;
}

export type InvitePlan = { kind: "open"; gameId: string } | { kind: "password" } | { kind: "join"; spectate: boolean } | { kind: "fill" };

const CODE = /^[A-Za-z0-9]{4,12}$/;
const TOKEN = /^[A-Za-z0-9_-]{8,64}$/;
const INVITE_KEYS = ["code", "name", "join", "watch", "handoff"];

/** A profile still called "Player" has no name of its own yet. */
export const ownName = (name: string | null | undefined): string => {
  const n = (name ?? "").trim();
  return n === "Player" ? "" : n;
};

export function readInvite(query: URLSearchParams): Invite | null {
  const code = (query.get("code") ?? "").trim();
  if (!CODE.test(code)) return null;
  const handoff = query.get("handoff");
  return {
    code: code.toUpperCase(),
    name: ownName(query.get("name")).slice(0, 40),
    action: query.get("join") === "1" ? "join" : query.get("watch") === "1" ? "watch" : "fill",
    handoff: handoff && TOKEN.test(handoff) ? handoff : null,
  };
}

/**
 * What a join link does once the tables are listed: open a seat this browser already holds at that table, ask for the
 * password the table needs, or join (or watch) at once. A table that isn't listed is tried anyway: the server says why not.
 */
export function planInvite(invite: Invite, games: GameSummary[], held: (gameId: string) => boolean): InvitePlan {
  if (invite.action === "fill") return { kind: "fill" };
  const listed = games.find((g) => g.code === invite.code);
  if (listed && held(listed.id)) return { kind: "open", gameId: listed.id };
  if (listed?.has_password) return { kind: "password" };
  return { kind: "join", spectate: invite.action === "watch" };
}

/** The address without the join link's parameters (anything else stays). */
export function withoutInvite(hash: string): string {
  const [path = "", query = ""] = hash.split("?");
  const params = new URLSearchParams(query);
  for (const k of INVITE_KEYS) params.delete(k);
  const rest = params.toString();
  return rest ? `${path}?${rest}` : path;
}

/** The Play page of the computer that hosts a table, ready to join it (or watch). */
export function joinLink(serverUrl: string, code: string, opts: { name?: string; watch?: boolean; handoff?: string | null } = {}): string {
  const params = new URLSearchParams({ code });
  const name = ownName(opts.name);
  if (name && !opts.watch) params.set("name", name);
  params.set(opts.watch ? "watch" : "join", "1");
  if (opts.handoff && !opts.watch) params.set("handoff", opts.handoff);
  return `${serverUrl.replace(/\/+$/, "")}/#/play?${params.toString()}`;
}

export function tableStatus(t: Pick<NearbyTable, "phase" | "seats" | "taken" | "turn">): string {
  return t.phase === "lobby" ? `In the lobby · ${t.taken} of ${t.seats} seats taken` : `Turn ${t.turn}`;
}

const rank = (phase: string | undefined, open: number) => (phase === "lobby" ? (open > 0 ? 0 : 1) : 2);

/** Every table found, open lobbies first (then full lobbies, then games in progress), by computer name within each. */
export function nearbyRows(servers: NearbyServer[]): NearbyRow[] {
  const rows = servers.flatMap((server) => server.tables.map((table) => ({ server, table })));
  return rows
    .map((r, i) => ({ r, i, k: rank(r.table.phase, r.table.open) }))
    .sort((a, b) => a.k - b.k || a.r.server.name.localeCompare(b.r.server.name) || a.i - b.i)
    .map((x) => x.r);
}

/** The launcher's one line: the first table found that someone can sit down at. */
export function firstOpenLobby(servers: NearbyServer[] | null): NearbyRow | null {
  const row = nearbyRows(servers ?? [])[0];
  return row && row.table.phase === "lobby" && row.table.open > 0 ? row : null;
}

const openSeats = (g: GameSummary) => g.players.filter((p) => !p.claimed).length;

/** The Play page's tables in progress, open LAN lobbies first (the order is otherwise kept). */
export function orderGames(games: GameSummary[]): GameSummary[] {
  const k = (g: GameSummary) => (g.mode === "lan" ? rank(g.phase, openSeats(g)) : 2);
  return games.map((g, i) => ({ g, i })).sort((a, b) => k(a.g) - k(b.g) || a.i - b.i).map((x) => x.g);
}

/**
 * What a device that isn't the host can do with a table on its Play page: open the seat it already holds there, or join an
 * open seat (lobby or game in progress: the server has the last word) and watch any LAN table.
 */
export function tileActions(g: GameSummary, held: boolean): { open: boolean; join: boolean; watch: boolean } {
  if (g.mode !== "lan" || !g.code) return { open: false, join: false, watch: false };
  if (held) return { open: true, join: false, watch: false };
  return { open: false, join: openSeats(g) > 0, watch: true };
}

/** A deck a player can pick in one click at their seat. */
export interface OwnDeck {
  key: string;
  name: string;
  commanders: string[];
  /** the commander's printing, for its art */
  cover: string | null;
  body: LobbyDeckBody;
}

export interface OwnDecks {
  label: string;
  /** brought from the player's own Fyodor (else this browser's My decks) */
  brought: boolean;
  decks: OwnDeck[];
}

/**
 * The decks a seated player brings: the library their own Fyodor sent with their join, or, in a browser with no Fyodor of its
 * own, the decks saved in this browser (My decks, kept per host address).
 */
export function ownDecks(brought: BroughtLibrary | null, mine: MyDeck[]): OwnDecks | null {
  if (brought?.decks.length) {
    return {
      label: `Your decks, from ${brought.from ?? "your computer"}`,
      brought: true,
      decks: brought.decks.map((d, i) => ({ key: `b${i}`, name: d.name, commanders: d.commanders, cover: d.cover_id, body: { name: d.name, text: d.text } })),
    };
  }
  if (!mine.length) return null;
  return {
    label: "Your decks in this browser",
    brought: false,
    decks: mine.map((d) => ({
      key: d.id, name: d.name, commanders: d.commanders,
      cover: d.entries?.find((e) => e.section === "commander" && e.printing_id)?.printing_id ?? null, body: d.body,
    })),
  };
}

/**
 * -- friends' decks -- an address typed by hand ("192.168.1.20:8000", "http://192.168.1.20:8000/") as the friend's Fyodor URL,
 * else null. The server checks it again (this network only).
 */
export function friendAddress(input: string): string | null {
  const raw = input.trim().replace(/\/+$/, "");
  const m = /^(?:http:\/\/)?(\d{1,3}(?:\.\d{1,3}){3}|localhost)(?::(\d{1,5}))?$/i.exec(raw);
  if (!m) return null;
  return `http://${m[1]!.toLowerCase() === "localhost" ? "127.0.0.1" : m[1]}:${m[2] ?? "8000"}`;
}

/** How many cards a shared deck list holds ("12 Mountain" lines). */
export function listCount(text: string): number {
  let n = 0;
  for (const line of text.split("\n")) n += Number(/^\s*(\d+)x?\s/.exec(line)?.[1] ?? 0);
  return n;
}

/** The folder a copied deck goes into, so the shelf shows whose it was. */
export const friendFolder = (from: string) => `From ${from.trim() || "a friend"}`.slice(0, 60);
