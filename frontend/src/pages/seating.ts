import { seats } from "../table3d/layout";
import type { LobbySeat, LobbySettings, LobbyView } from "../types/game";

/*
 * -- seating -- the host arranges the lobby's seats (docs/GAME_NIGHT_FLOW.md §2). The server keeps the seats in seating order
 * (seat 1 first) and decides the turn order at the start; these helpers only build the order the host asks for and the line
 * that tells the pod what the next game's order will be.
 */

export type TurnOrderMode = NonNullable<LobbySettings["turn_order"]>;

export const TURN_ORDER_LABEL: Record<TurnOrderMode, string> = {
  pod: "Pod rule — d20 for the first game, then the winner goes last",
  random: "Random first player, then around the table",
  seats: "Seat order — seat 1 goes first, then around the table",
};

/** The short form for the lobby header. */
export const TURN_ORDER_SHORT: Record<TurnOrderMode, string> = {
  pod: "d20, then the winner goes last",
  random: "random first player",
  seats: "seat 1 first, as seated",
};

/** Every seat id in seating order, with `from` moved to `to`'s place (a drag: the others shift up or down by one). */
export function moveSeat(order: string[], from: string, to: string): string[] {
  const i = order.indexOf(from);
  const j = order.indexOf(to);
  if (i < 0 || j < 0 || i === j) return order;
  const out = order.filter((id) => id !== from);
  out.splice(j, 0, from);
  return out;
}

/** Every seat id in seating order, with `id` swapped with its neighbour (`delta` -1: one seat earlier, +1: one later). */
export function nudgeSeat(order: string[], id: string, delta: -1 | 1): string[] {
  const i = order.indexOf(id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= order.length) return order;
  const out = [...order];
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}

/** Whether the host's arrow can move this seat that way (not past either end of the table). */
export function canNudge(order: string[], id: string, delta: -1 | 1): boolean {
  const j = order.indexOf(id) + delta;
  return order.includes(id) && j >= 0 && j < order.length;
}

/**
 * The next game's order in parts, from the server's preview: the claimed seats in turn order (none while a d20 decides the
 * seating), the player known to go first, and the sentence that explains it.
 */
export function previewParts(lobby: Pick<LobbyView, "turn_preview" | "seats" | "settings">): {
  order: string[];
  first: string | null;
  note: string;
  source: "d20" | "winner_last" | "random" | "seats";
} {
  const p = lobby.turn_preview;
  const name = (id: string) => lobby.seats.find((s: LobbySeat) => s.id === id)?.name ?? `Seat ${id.slice(1)}`;
  const order = p?.order ?? lobby.seats.filter((s) => s.claimed).map((s) => s.id);
  const mode = lobby.settings.turn_order ?? "pod";
  const source = p?.source ?? (mode === "seats" ? "seats" : "random");
  if (order.length < 2) return { order: [], first: null, note: "", source };
  if (source === "d20") return { order: [], first: null, note: "Everyone rolls a d20 at the start: highest goes first, ties reroll. The rolls set the seating.", source };
  if (source === "winner_last") return { order, first: order[0]!, note: `${name(p!.previous_winner!)} won last game and goes last.`, source };
  if (source === "seats") return { order, first: order[0]!, note: `${name(order[0]!)} goes first.`, source };
  return { order, first: null, note: "A random player goes first, then around the table.", source };
}

/** What the pod should know about the next game's order, from the server's preview: one line, names in turn order. */
export function previewLine(lobby: Pick<LobbyView, "turn_preview" | "seats" | "settings">): string {
  const { order, note, source } = previewParts(lobby);
  if (!note || !order.length) return note;
  const name = (id: string) => lobby.seats.find((s: LobbySeat) => s.id === id)?.name ?? `Seat ${id.slice(1)}`;
  return `${order.map(name).join(" → ")} · ${source === "random" ? note.charAt(0).toLowerCase() + note.slice(1) : note}`;
}

/**
 * Where each player sits on a miniature of the table (the lobby's seat preview), as fractions of its width (x) and depth (y,
 * 0 = the far edge): the 3D table's own seating (table3d/layout.ts), the viewer's row nearest, turn order clockwise.
 */
export function miniSeats(order: string[], me: string): { id: string; x: number; y: number }[] {
  if (!order.length) return [];
  const placed = seats(order, me);
  const span = Math.max(...placed.map((s) => Math.abs(s.x))) || 1;
  return placed.map((s) => ({ id: s.player, x: 0.5 + (s.x / span) * 0.34, y: s.z > 0 ? 1 : 0 }));
}

/** A game's recorded d20 rounds, by name: "Ann 17, Ben 12 · tie-break Ann 4, Cat 9". */
export function rollsText(rounds: Record<string, number>[]): string {
  return rounds.map((r, i) => `${i ? "tie-break " : ""}${Object.entries(r).map(([n, v]) => `${n} ${v}`).join(", ")}`).join(" · ");
}
