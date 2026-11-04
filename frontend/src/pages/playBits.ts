/** Plain helpers behind the Play page and the launcher (no React, so they're tested directly). */
import type { DeckSummary } from "../types/decks";
import type { GameSummary, SaveSummary } from "../types/game";

/** The table's default seat colours, in seat order (the Play page's and the server's defaults). */
export const SEAT_COLORS = ["#d4a852", "#5fa8d3", "#c9677a", "#6fbf8f", "#a68bd6", "#d98c4a"];

/** Columns × rows of a table's commander mosaic for n seats: every cell stays landscape, so a commander's art window fills it. */
export function mosaicGrid(n: number): [number, number] {
  if (n <= 1) return [1, 1];
  if (n === 2) return [1, 2];
  if (n <= 4) return [2, 2];
  return [2, 3];
}

/** "Today, 22:51" / "Yesterday, 21:10" / "Sat 31 Oct, 20:15" for a save's local timestamp (YYYY-MM-DDTHH:MM:SS). */
export function whenSaved(stamp: string, now = new Date()): string {
  const d = new Date(stamp);
  if (Number.isNaN(d.getTime())) return stamp.replace("T", " ");
  const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((day(now) - day(d)) / 86_400_000);
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  const date = d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
  return `${date}, ${time}`;
}

/** A deck's playing cards: commander(s), companion and the library. */
export function deckSize(d: DeckSummary): number {
  return (d.counts.commander ?? 0) + (d.counts.companion ?? 0) + (d.counts.main ?? 0);
}

/** The words for a deck's commander(s), or its name when it has none. */
export function deckTitle(d: DeckSummary): string {
  return d.commanders.length ? d.commanders.join(" & ") : d.name;
}

/** The deck's own name under its commander, or null when it only repeats the title (a deck named after its commander). */
export function deckSubtitle(d: DeckSummary): string | null {
  return d.commanders.length && d.name.trim().toLowerCase() !== deckTitle(d).trim().toLowerCase() ? d.name : null;
}

/** What the launcher's "Continue" picks up. */
export type LastTable = { kind: "table"; game: GameSummary } | { kind: "save"; save: SaveSummary };

/**
 * The table played most recently that this device can open (`canOpen`: any table on the host, a held seat elsewhere),
 * else the newest save (the server lists saves newest first).
 */
export function lastTable(games: GameSummary[], saves: SaveSummary[] | null, canOpen: (g: GameSummary) => boolean): LastTable | null {
  const table = games.filter(canOpen).sort((a, b) => b.updated_at - a.updated_at)[0];
  if (table) return { kind: "table", game: table };
  const save = saves?.[0];
  return save ? { kind: "save", save } : null;
}

/** The saves the shelf shows: every manual save, and only the newest autosave of each game (the list is newest first). */
export function shelfSaves(saves: SaveSummary[]): SaveSummary[] {
  const seen = new Set<string>();
  return saves.filter((x) => !x.autosave || (!seen.has(x.game_id) && seen.add(x.game_id)));
}
