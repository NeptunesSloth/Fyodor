/**
 * Commander damage at a glance (TABLETOP_QOL_MILESTONE #6): what each commander has dealt to each player. Everything
 * here is public: every player's commander damage is in every view, and a card is only treated as a commander when
 * the server told this viewer so (`commander_key` is only sent on cards the viewer may see).
 */
import { isVisible, type GameCard, type PlayerView } from "../types/game";

/** 903.10a: 21 or more combat damage from one commander. */
export const LETHAL_COMMANDER = 21;

type Players = Pick<PlayerView, "id" | "name" | "color" | "commanders" | "commander_damage" | "left">[];

export interface Dealt {
  player: string;
  name: string;
  color: string;
  damage: number;
}

/**
 * What one commander has dealt to each player: every opponent of its owner, plus its owner too if the commander
 * hit them while someone else controlled it (903.10a counts damage from the same commander, whoever controls it).
 * A player who left the game is listed only if it took some.
 */
export function commanderDealt(players: Players, key: string): Dealt[] {
  const owner = players.find((p) => p.commanders.some((c) => c.key === key));
  if (!owner) return [];
  return players
    .filter((p) => (p.commander_damage[key] ?? 0) > 0 || (p.id !== owner.id && !p.left))
    .map((p) => ({ player: p.id, name: p.name, color: p.color, damage: p.commander_damage[key] ?? 0 }));
}

/** "Bob 8 · Cara 0": the one-line form, for tooltips. */
export function dealtText(rows: Dealt[]): string {
  return rows.map((r) => `${r.name} ${r.damage}`).join(" · ");
}

/** The commander a card is, as far as this viewer knows (null for hidden cards and non-commanders). */
export function commanderKeyOf(card: GameCard | undefined): string | null {
  return card && isVisible(card) && card.commander_key ? card.commander_key : null;
}

export interface MatrixCol { id: string; name: string; color: string }
export interface MatrixRow {
  key: string;
  name: string;
  owner: MatrixCol;
  /** One per column: the damage this commander dealt that player; `own` marks its owner's column. */
  cells: { player: string; damage: number; own: boolean }[];
}

/**
 * The whole table's commander damage: a row per commander (in seat order, partners together), a column per player.
 * Players who left stay as columns only while some commander damage is recorded against them.
 */
export function commanderMatrix(players: Players): { cols: MatrixCol[]; rows: MatrixRow[] } {
  const cols = players
    .filter((p) => !p.left || Object.values(p.commander_damage).some((n) => n > 0))
    .map((p) => ({ id: p.id, name: p.name, color: p.color }));
  const rows = players.flatMap((o) => o.commanders.map((c) => ({
    key: c.key,
    name: c.name,
    owner: { id: o.id, name: o.name, color: o.color },
    cells: cols.map((col) => ({
      player: col.id,
      damage: players.find((p) => p.id === col.id)?.commander_damage[c.key] ?? 0,
      own: col.id === o.id,
    })),
  })));
  return { cols, rows };
}
