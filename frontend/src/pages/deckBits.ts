/** Plain helpers behind the Decks page and the deck editor (no React, so they're tested directly). */
import type { GlyphKind } from "../cards/proxy";
import type { GameResult } from "../services/pod";
import type { CardData } from "../types/cards";
import type { DeckEntry, DeckWarning } from "../types/decks";

/** What the pod's recorded games say about one library deck. */
export interface DeckRecord {
  games: number;
  wins: number;
  /** recorded_at of the newest game it played */
  last: string;
}

/** Each library deck's games, wins and last game, from the pod's recorded results (players carry `deck:<id>` keys). */
export function deckRecords(results: Pick<GameResult, "recorded_at" | "players">[]): Map<string, DeckRecord> {
  const out = new Map<string, DeckRecord>();
  for (const r of results) {
    const seen = new Set<string>();
    for (const p of r.players) {
      const id = p.deck_key?.startsWith("deck:") ? p.deck_key.slice(5) : null;
      if (!id) continue;
      const rec = out.get(id) ?? { games: 0, wins: 0, last: "" };
      if (!seen.has(id)) rec.games += 1; // the same deck at two seats is still one game for it
      seen.add(id);
      if (p.outcome === "win") rec.wins += 1;
      if (r.recorded_at > rec.last) rec.last = r.recorded_at;
      out.set(id, rec);
    }
  }
  return out;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "2 wins in 5 games", "No wins in 3 games", "1 win in 1 game". */
export function recordText(r: Pick<DeckRecord, "games" | "wins">): string {
  return `${r.wins ? plural(r.wins, "win") : "No wins"} in ${plural(r.games, "game")}`;
}

/** "today", "yesterday", "on Sat 31 Oct" (with the year when it isn't this one): when a deck last played. */
export function playedWhen(stamp: string, now = new Date()): string {
  const d = new Date(stamp);
  if (Number.isNaN(d.getTime())) return "";
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((day(now) - day(d)) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `on ${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) })}`;
}

/** A deck in the library search: its name or a commander's contains the words typed. */
export function deckMatches(d: { name: string; commanders: string[] }, query: string): boolean {
  const needle = query.trim().toLowerCase();
  return !needle || d.name.toLowerCase().includes(needle) || d.commanders.some((c) => c.toLowerCase().includes(needle));
}

/** The main deck's mana curve (nonland cards by mana value, 7+ together), its average mana value and its land count. */
export function curveStats(entries: DeckEntry[], cards: Record<string, CardData | undefined>): { buckets: number[]; average: number | null; lands: number; spells: number } {
  const buckets = Array.from({ length: 8 }, () => 0);
  let lands = 0;
  let spells = 0;
  let total = 0;
  for (const e of entries) {
    if (e.section !== "main") continue;
    const c = e.printing_id ? cards[e.printing_id] : undefined;
    if (!c) continue;
    if ((c.type_line ?? "").includes("Land")) {
      lands += e.quantity;
      continue;
    }
    buckets[Math.min(7, Math.floor(c.cmc ?? 0))]! += e.quantity;
    spells += e.quantity;
    total += (c.cmc ?? 0) * e.quantity;
  }
  return { buckets, average: spells ? total / spells : null, lands, spells };
}

/** The deck checks in one line for the editor's header: the worst level and how many there are. */
export function checkSummary(warnings: Pick<DeckWarning, "level">[]): { level: "ok" | DeckWarning["level"]; text: string } {
  const n = (level: DeckWarning["level"]) => warnings.filter((w) => w.level === level).length;
  const errors = n("error");
  const warns = n("warning");
  const infos = n("info");
  if (errors) return { level: "error", text: plural(errors + warns, "problem") };
  if (warns) return { level: "warning", text: plural(warns, "warning") };
  if (infos) return { level: "info", text: plural(infos, "note") };
  return { level: "ok", text: "No problems found" };
}

const GROUP_PLURAL: Record<string, string> = {
  Creature: "Creatures", Planeswalker: "Planeswalkers", Battle: "Battles", Instant: "Instants", Sorcery: "Sorceries",
  Artifact: "Artifacts", Enchantment: "Enchantments", Land: "Lands",
};

/** A type group's heading ("Sorceries"); category names stay as they are. */
export function groupTitle(label: string): string {
  return GROUP_PLURAL[label] ?? label;
}

/** The proxy card's icon for a type group, so the list and the cards share one set of type marks. */
export function groupGlyph(label: string): GlyphKind | null {
  const kind = label.toLowerCase();
  return kind in GLYPH_KINDS ? (kind as GlyphKind) : null;
}
const GLYPH_KINDS = { creature: 1, planeswalker: 1, battle: 1, land: 1, instant: 1, sorcery: 1, artifact: 1, enchantment: 1, other: 1 };
