/**
 * -- live cursors -- (as in Tabletop Simulator) the math under every other seated player's pointer: pure, so it is
 * unit-tested (the meshes are table3d/cursors3d.ts).
 *
 * World coordinates differ per screen (layout.ts puts each viewer at the south edge), so a cursor travels in a
 * viewer-independent frame: the nearest seat and a point on that seat's battlefield in virtual units (1000 × 600, the
 * same on every screen). Unlike a card position (its top-left corner) this is the point itself, and it may lie off the
 * battlefield, on the wood or the rail.
 */
import { MAT_D, MAT_W, toLocal, toWorld, UNIT, type Seat, type TableSize } from "./layout";

/**
 * Over a card, the spot also names it and the point on it (cx/cy in its half-widths, -1..1, in the card's own frame):
 * each screen may lay a board out its own way (the arranged rows), so "over that card" is what has to match. The server
 * passes a card on only when everyone can see it.
 */
export interface CursorSpot { player: string; x: number; y: number; card?: string; cx?: number; cy?: number }

/** The range a cursor may take, in virtual units of its seat's battlefield (as the server clamps it). */
export const CURSOR_X: [number, number] = [-400, 1400];
export const CURSOR_Y: [number, number] = [-400, 1000];
/** How far past the table top's edge (world units) the pointer still counts as over the table: the rail. */
export const RAIL = 0.6;
/** At most this often to the server (ms): ~15 a second. */
export const SEND_EVERY = 66;
/** A cursor that hasn't moved for this long fades out (ms), over FADE ms. */
export const IDLE_MS = 3000;
export const FADE_MS = 600;

const clamp = (v: number, [lo, hi]: [number, number]) => Math.max(lo, Math.min(hi, v));

/** Is a world point on the table top (or its rail)? */
export function overTable(size: TableSize, wx: number, wz: number): boolean {
  return Math.abs(wx) <= size.w / 2 + RAIL && Math.abs(wz) <= size.d / 2 + RAIL;
}

/** World (x, z) → the cursor frame: the seat whose battlefield is nearest, and the point on it. */
export function worldToCursor(all: Seat[], wx: number, wz: number): CursorSpot | null {
  let best: { seat: Seat; d: number; lx: number; lz: number } | null = null;
  for (const seat of all) {
    const [lx, lz] = toLocal(seat, wx, wz);
    const dx = Math.max(0, Math.abs(lx) - MAT_W / 2);
    const dz = Math.max(0, Math.abs(lz) - MAT_D / 2);
    const d = dx * dx + dz * dz;
    if (!best || d < best.d) best = { seat, d, lx, lz };
  }
  if (!best) return null;
  const x = Math.round(clamp((best.lx + MAT_W / 2) * UNIT, CURSOR_X) * 10) / 10;
  const y = Math.round(clamp((best.lz + MAT_D / 2) * UNIT, CURSOR_Y) * 10) / 10;
  return { player: best.seat.player, x, y };
}

/** The cursor frame → this screen's world (x, z), or null for a seat not at this table. */
export function cursorToWorld(all: Seat[], spot: CursorSpot): [number, number] | null {
  const seat = all.find((s) => s.player === spot.player);
  if (!seat) return null;
  return toWorld(seat, spot.x / UNIT - MAT_W / 2, spot.y / UNIT - MAT_D / 2);
}

/**
 * One other player's cursor on this screen: where it is drawn, eased toward the latest position the server relayed,
 * and how visible it is (it fades out after IDLE_MS without a move, or at once when they leave the table).
 */
export class CursorTrack {
  x = 0;
  z = 0;
  tx = 0;
  tz = 0;
  /** When it last moved (ms); -Infinity before the first position. */
  moved = -Infinity;
  gone = false;
  private placed = false;

  /** A new position from the server. The first one appears where it is (it doesn't slide in from the table's middle). */
  target(wx: number, wz: number, now: number): void {
    this.tx = wx;
    this.tz = wz;
    if (!this.placed || this.gone) {
      this.x = wx;
      this.z = wz;
    }
    this.placed = true;
    this.gone = false;
    this.moved = now;
  }

  /** The same spot somewhere else on this screen (its seats were laid out again): no easing, and not a move. */
  jump(wx: number, wz: number): void {
    this.x = this.tx = wx;
    this.z = this.tz = wz;
  }

  /** They left the table (or their pointer left it): fade from now. */
  leave(now: number): void {
    if (!this.gone) this.moved = Math.min(this.moved, now - IDLE_MS);
    this.gone = true;
  }

  /** Ease toward the target for a frame of dt seconds (snap with reduced motion); returns the opacity, 0..1. */
  step(dt: number, now: number, reduced: boolean): number {
    // ~15 updates a second: a quick approach reads as smooth movement without lagging far behind the real pointer
    const k = reduced ? 1 : 1 - Math.exp(-dt * 18);
    this.x += (this.tx - this.x) * k;
    this.z += (this.tz - this.z) * k;
    return this.opacity(now);
  }

  opacity(now: number): number {
    if (!this.placed) return 0;
    const idle = now - this.moved;
    if (idle <= IDLE_MS) return 1;
    return Math.max(0, 1 - (idle - IDLE_MS) / FADE_MS);
  }
}

/**
 * When to send my own pointer: at most every SEND_EVERY ms, always the latest spot (a trailing send after a burst),
 * and one "gone" when it leaves the table. Nothing is sent twice.
 */
export class CursorOutbox {
  private latest: CursorSpot | null = null;
  private sent: CursorSpot | null = null;
  private last = -Infinity;
  private away = true;

  move(spot: CursorSpot | null): void {
    if (!spot) {
      this.leave();
      return;
    }
    this.latest = spot;
  }

  leave(): void {
    this.latest = null;
  }

  /** What to send now, if anything (call once a frame). */
  poll(now: number): CursorSpot | { gone: true } | null {
    if (!this.latest) {
      if (this.away) return null;
      this.away = true;
      this.sent = null;
      return { gone: true };
    }
    if (now - this.last < SEND_EVERY) return null;
    const s = this.latest;
    const t = this.sent;
    if (t && t.player === s.player && t.x === s.x && t.y === s.y && t.card === s.card && t.cx === s.cx && t.cy === s.cy) return null;
    this.sent = s;
    this.last = now;
    this.away = false;
    return s;
  }
}
