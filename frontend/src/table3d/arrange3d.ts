/**
 * The arranged 3D boards: each mat lays itself out with the 2D table's rows (game/arrange.ts, the same code and the
 * same per-device setting): creatures toward the middle of the table, other permanents behind them, lands by the
 * owner's edge with identical ones stacked ×N, tokens stacked, Auras and Equipment tucked under their host. Cards are
 * art tiles sized to fill the mat, and every board reads upright from my seat, as on MTG Arena: a mat across the table
 * is laid out in my frame (its front toward me), not its owner's.
 *
 * Display only: the server's positions are untouched (free placement and saves use them). Pure (no three.js), so it
 * is unit-tested.
 */
import { applyOrder, arrangeBoard, arrangeCard, reorderOnDrop, TILE_RATIO, type BoardLayout } from "../game/arrange";
import { isVisible, type GameView } from "../types/game";
import type { CardData } from "../types/cards";
import { CARD_H, CARD_W, MAT_D, MAT_W, toWorld, type Seat } from "./layout";

/** Arrange units (the 2D layout's px) per world unit. */
export const AU = 100;
/** The largest tile (world units): about twice a card, so a mat with a few permanents isn't bare felt. */
export const TILE_MAX = 1.9;
/** Rows don't shrink their tiles below this (they overlap instead), so a crowded board still reads. */
export const TILE_MIN = 0.8;
/** A tile's depth over a card's, at the same width (the group's z scale). */
export const TILE_SQUASH = (TILE_RATIO * CARD_W) / CARD_H;

export interface Spot {
  /** The tile's centre in world coordinates. */
  x: number;
  z: number;
  /** Its centre on the mat, in my frame (x to my right, z toward me). */
  lx: number;
  lz: number;
  /** Which way it faces: my seat's rotation (it reads upright for me). */
  rot: number;
  /** Tile width (world). */
  w: number;
  /** Stacking on its mat: higher lies on top. */
  rank: number;
  /** Its index in its zone (the free layout's stacking height, which the table may add a lift to). */
  index: number;
  /** ×N on a stack's top card. */
  pile?: number;
  player: string;
}

/** A corner of my mat the turn dial covers (layout units, game/arrange.ts): rows reaching below `top` stop short of `left`. */
export type KeepOut = { top: number; left: number };

export interface Mat {
  layout: BoardLayout;
  /** The frame the layout is in: the mat's centre, turned like my seat. */
  frame: Seat;
  mirrored: boolean;
  zone: string;
}

/** A tile's group scale for its width: uniform on x (and y), squashed on z by TILE_SQUASH. */
export function tileScale(w: number): number {
  return w / CARD_W;
}

/** Lay out one mat: placements in its frame (world units, tile centres) and the 2D layout they came from. */
export function arrangeMat(cards: Parameters<typeof arrangeBoard>[0], mirrored: boolean, keepOut: KeepOut | null = null): { layout: BoardLayout; spots: Map<string, { lx: number; lz: number; w: number; rank: number; pile?: number }> } {
  const layout = arrangeBoard(cards, { width: MAT_W * AU, height: MAT_D * AU, mirrored, maxW: TILE_MAX * AU, minW: TILE_MIN * AU, keepOut });
  const spots = new Map<string, { lx: number; lz: number; w: number; rank: number; pile?: number }>();
  [...layout.place.entries()].sort((a, b) => a[1].z - b[1].z).forEach(([id, p], rank) => {
    spots.set(id, {
      lx: (p.left + layout.w / 2) / AU - MAT_W / 2,
      lz: (p.top + layout.h / 2) / AU - MAT_D / 2,
      w: layout.w / AU,
      rank,
      ...(p.pile ? { pile: p.pile } : {}),
    });
  });
  return { layout, spots };
}

/** A point on a mat (its frame, world units) → the arranged layout's units, as the top-left of a tile there. */
export function toArrange(layout: BoardLayout, lx: number, lz: number): [number, number] {
  return [(lx + MAT_W / 2) * AU - layout.w / 2, (lz + MAT_D / 2) * AU - layout.h / 2];
}

/**
 * After a flick across my arranged mat: the new order. Each row's slots go where they came to rest: to the line of
 * their row nearest where they stopped, then left to right. `rest`: where a card stopped (layout units, its centre),
 * or null if it didn't move.
 */
export function orderFromRest(layout: BoardLayout, rest: (id: string) => [number, number] | null): string[] {
  const kinds: string[] = [];
  for (const r of layout.rows) if (!kinds.includes(r.kind)) kinds.push(r.kind);
  const out: string[] = [];
  for (const kind of kinds) {
    const lines = layout.rows.filter((r) => r.kind === kind);
    const placed = lines.flatMap((r) => r.slots).map((slot) => {
      const id = slot[0]!;
      const p = layout.place.get(id);
      const at = rest(id) ?? (p ? [p.left + layout.w / 2, p.top + layout.h / 2] as [number, number] : [0, 0] as [number, number]);
      const line = lines.reduce((best, r, i) => (Math.abs(r.top + r.height / 2 - at[1]) < Math.abs(lines[best]!.top + lines[best]!.height / 2 - at[1]) ? i : best), 0);
      return { slot, line, x: at[0] };
    });
    placed.sort((a, b) => a.line - b.line || a.x - b.x);
    for (const p of placed) out.push(...p.slot);
  }
  return out;
}

/** Where a card dropped on its own arranged mat goes in my order (null: it isn't on that board). */
export function reorderMat(mat: Mat, moving: string[], lx: number, lz: number): string[] | null {
  const [x, y] = toArrange(mat.layout, lx, lz);
  return reorderOnDrop(mat.layout, moving, x, y);
}

export interface ArrangeSources {
  /** The card's data (its type line), once it has loaded. */
  data: (cardId: string) => CardData | undefined;
  /** My order for a zone (game/arrange.ts boardOrder). */
  order: (zone: string) => string[];
}

/**
 * Every seat's arranged mat, laid out again only when what it shows changed (most updates change nothing on most
 * boards). `layout` returns each battlefield card's spot (empty when the boards are in free placement).
 */
export class ArrangedBoards {
  private cache = new Map<string, { sig: string; layout: BoardLayout; spots: ReturnType<typeof arrangeMat>["spots"] }>();
  readonly mats = new Map<string, Mat>();

  layout(view: GameView, seats: Seat[], me: string, src: ArrangeSources, keepOut: KeepOut | null = null): Map<string, Spot> {
    const out = new Map<string, Spot>();
    this.mats.clear();
    const mine = seats.find((s) => s.player === me) ?? seats[0];
    if (!mine) return out;
    const stats = view.rules?.stats;
    for (const seat of seats) {
      const zone = `${seat.player}:battlefield`;
      const ids = (view.zones[zone] as string[] | undefined) ?? [];
      const index = new Map(ids.map((id, i) => [id, i]));
      const facts = applyOrder(ids, src.order(zone)).flatMap((id) => {
        const c = view.cards[id];
        if (!c) return [];
        return [arrangeCard(c, isVisible(c) && c.card_id ? src.data(c.card_id) : undefined, stats?.[id])];
      });
      // a mat across the table faces me: its front (the creatures) is toward me, the bottom of the mat as I see it
      const mirrored = seat.side !== mine.side;
      const keep = seat === mine ? keepOut : null;
      const sig = `${mirrored ? 1 : 0}|${keep ? `${keep.top},${keep.left}` : ""}#` + facts.map((f) => `${f.id}|${f.row}|${f.key ?? ""}|${f.n}|${f.turned ? 1 : 0}|${f.forward ? 1 : 0}|${f.host ?? ""}`).join("\n");
      let hit = this.cache.get(seat.player);
      if (!hit || hit.sig !== sig) {
        const m = arrangeMat(facts, mirrored, keep);
        hit = { sig, ...m };
        this.cache.set(seat.player, hit);
      }
      const frame: Seat = { ...seat, rot: mine.rot };
      this.mats.set(seat.player, { layout: hit.layout, frame, mirrored, zone });
      for (const [id, s] of hit.spots) {
        const [x, z] = toWorld(frame, s.lx, s.lz);
        out.set(id, { ...s, x, z, rot: mine.rot, index: index.get(id) ?? 0, player: seat.player });
      }
    }
    for (const p of [...this.cache.keys()]) if (!seats.some((s) => s.player === p)) this.cache.delete(p);
    return out;
  }

  /** The ×N counts on one mat (top card id → n), as game/piles.ts zonePileTops gives them for free placement. */
  piles(spots: Map<string, Spot>, player: string): Map<string, number> {
    const out = new Map<string, number>();
    for (const [id, s] of spots) if (s.player === player && s.pile) out.set(id, s.pile);
    return out;
  }
}
