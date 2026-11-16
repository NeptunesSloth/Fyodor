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
import { arrangedCovers } from "./covers";
import { CARD_H, CARD_W, MAT_D, MAT_W, toWorld, type Seat } from "./layout";

/** Arrange units (the 2D layout's px) per world unit. */
export const AU = 100;
/** The largest tile (world units): a normal, readable card on the big table (a card is 0.84 at its own size). */
export const TILE_MAX = 1.4;
/** Rows don't shrink their tiles below this (they overlap instead), so a crowded board still reads. */
export const TILE_MIN = 0.85;
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
  /** A stack member beneath its top card: it casts no contact shadow (80 soft shadows on one spot add up to a black slab). */
  under?: true;
  /** A pile's buried card (past the edges it shows): the card it lies wholly under, which hides it (table3d/covers.ts). */
  cover?: string;
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
export function arrangeMat(cards: Parameters<typeof arrangeBoard>[0], mirrored: boolean, keepOut: KeepOut | null = null): { layout: BoardLayout; spots: Map<string, MatSpot> } {
  const layout = arrangeBoard(cards, { width: MAT_W * AU, height: MAT_D * AU, mirrored, maxW: TILE_MAX * AU, minW: TILE_MIN * AU, keepOut });
  const spots = new Map<string, MatSpot>();
  const covers = arrangedCovers(layout);
  // a stack's buried cards share one height: a pile of 80 tokens lies as low as a pile of 5
  let rank = -1;
  let prevBuried = false;
  [...layout.place.entries()].sort((a, b) => a[1].z - b[1].z).forEach(([id, p]) => {
    if (!(p.buried && prevBuried)) rank++;
    prevBuried = !!p.buried;
    spots.set(id, {
      lx: (p.left + layout.w / 2) / AU - MAT_W / 2,
      lz: (p.top + layout.h / 2) / AU - MAT_D / 2,
      w: layout.w / AU,
      rank,
      ...(p.pile ? { pile: p.pile } : {}),
      ...(p.under ? { under: true as const } : {}),
      ...(covers.has(id) ? { cover: covers.get(id)! } : {}),
    });
  });
  return { layout, spots };
}

type MatSpot = { lx: number; lz: number; w: number; rank: number; pile?: number; under?: true; cover?: string };

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
  /** Changes whenever `data` may answer differently (the card cache's map): a mat whose inputs are all the same objects isn't looked at again. */
  version?: unknown;
  /** My order for a zone (game/arrange.ts boardOrder). */
  order: (zone: string) => string[];
}

interface SeatMemo {
  /** What it was laid out from (the view shares unchanged objects between updates: game/reconcile.ts). */
  ids: string[];
  refs: unknown[];
  order: string[];
  version: unknown;
  keep: string;
  frame: string;
  sig: string;
  layout: BoardLayout;
  mat: Mat;
  spots: Map<string, Spot>;
  piles: Map<string, number>;
}

/**
 * Every seat's arranged mat. Most updates change nothing on most boards: a mat whose cards are the same objects as
 * last time is reused as it was, and one whose cards changed is laid out again only when what it shows changed.
 * `layout` returns each battlefield card's spot.
 */
export class ArrangedBoards {
  private memo = new Map<string, SeatMemo>();
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
      const order = src.order(zone);
      // a mat across the table faces me: its front (the creatures) is toward me, the bottom of the mat as I see it
      const mirrored = seat.side !== mine.side;
      const keep = seat === mine && keepOut ? `${keepOut.top},${keepOut.left}` : "";
      const frame: Seat = { ...seat, rot: mine.rot };
      const frameKey = `${frame.x},${frame.z},${frame.rot},${mirrored}`;
      const refs: unknown[] = [];
      for (const id of ids) refs.push(view.cards[id], stats?.[id]);
      let m = this.memo.get(seat.player);
      const same = m && m.ids === ids && m.order === order && m.version === src.version && m.keep === keep && m.frame === frameKey
        && m.refs.length === refs.length && m.refs.every((r, i) => r === refs[i]);
      if (!same) {
        const facts = applyOrder(ids, order).flatMap((id) => {
          const c = view.cards[id];
          if (!c) return [];
          return [arrangeCard(c, isVisible(c) && c.card_id ? src.data(c.card_id) : undefined, stats?.[id])];
        });
        // (tapping a card never moves its row: every slot keeps room for its card turned, game/arrange.ts)
        const sig = `${keep}#` + facts.map((f) => `${f.id}|${f.row}|${f.key ?? ""}|${f.n}|${f.forward ? 1 : 0}|${f.host ?? ""}`).join("\n");
        const index = new Map(ids.map((id, i) => [id, i]));
        let layout: BoardLayout;
        let local: ReturnType<typeof arrangeMat>["spots"];
        if (m && m.sig === sig && m.frame === frameKey) {
          layout = m.layout;
          local = new Map([...m.spots].map(([id, s]) => [id, s]));
        } else {
          ({ layout, spots: local } = arrangeMat(facts, mirrored, seat === mine ? keepOut : null));
        }
        const spots = new Map<string, Spot>();
        const piles = new Map<string, number>();
        for (const [id, s] of local) {
          const [x, z] = toWorld(frame, s.lx, s.lz);
          spots.set(id, { lx: s.lx, lz: s.lz, w: s.w, rank: s.rank, ...(s.pile ? { pile: s.pile } : {}), ...(s.under ? { under: s.under } : {}), ...(s.cover ? { cover: s.cover } : {}), x, z, rot: mine.rot, index: index.get(id) ?? 0, player: seat.player });
          if (s.pile) piles.set(id, s.pile);
        }
        m = { ids, refs, order, version: src.version, keep, frame: frameKey, sig, layout, mat: { layout, frame, mirrored, zone }, spots, piles };
        this.memo.set(seat.player, m);
      }
      this.mats.set(seat.player, m!.mat);
      for (const [id, s] of m!.spots) out.set(id, s);
    }
    for (const p of [...this.memo.keys()]) if (!seats.some((s) => s.player === p)) this.memo.delete(p);
    return out;
  }

  /** The ×N counts on one mat (top card id → n), as game/piles.ts zonePileTops gives them for free placement. */
  piles(player: string): Map<string, number> {
    return this.memo.get(player)?.piles ?? new Map();
  }
}
