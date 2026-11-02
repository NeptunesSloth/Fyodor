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

/** What the pod should know about the next game's order, from the server's preview: one line, names in turn order. */
export function previewLine(lobby: Pick<LobbyView, "turn_preview" | "seats" | "settings">): string {
  const p = lobby.turn_preview;
  const mode = lobby.settings.turn_order ?? "pod";
  const name = (id: string) => lobby.seats.find((s: LobbySeat) => s.id === id)?.name ?? `Seat ${id.slice(1)}`;
  const order = p?.order ?? lobby.seats.filter((s) => s.claimed).map((s) => s.id);
  if (order.length < 2) return "";
  const names = order.map(name).join(" → ");
  const source = p?.source ?? mode;
  if (source === "d20") return "Everyone rolls a d20 at the start: highest goes first, ties reroll. The rolls set the seating.";
  if (source === "winner_last") return `${names} · ${name(p!.previous_winner!)} won last game and goes last.`;
  if (source === "seats") return `${names} · ${name(order[0]!)} goes first.`;
  return `${names} · a random player goes first, then around the table.`;
}

/** A game's recorded d20 rounds, by name: "Ann 17, Ben 12 · tie-break Ann 4, Cat 9". */
export function rollsText(rounds: Record<string, number>[]): string {
  return rounds.map((r, i) => `${i ? "tie-break " : ""}${Object.entries(r).map(([n, v]) => `${n} ${v}`).join(", ")}`).join(" · ");
}
