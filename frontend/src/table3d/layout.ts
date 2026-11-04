/**
 * Where everything sits on the 3D table. Pure math (no three.js) so it is unit-tested.
 *
 * World units: 1 = 100 battlefield virtual units. Each player owns a *mat* (their battlefield,
 * BF_W × BF_H virtual = 10 × 6 world) with a zone strip on each side. A mat's local frame:
 * x to the owner's right, z toward the owner (virtual y = 0 is the far edge of the battlefield,
 * as on the 2D table). The mat group is rotated about Y so that local +z points at its owner.
 */
import { BF_H, BF_W, CARD_RATIO, CARD_VW } from "../game/geometry";

export const UNIT = 100; // virtual units per world unit
export const MAT_W = BF_W / UNIT; // 10
export const MAT_D = BF_H / UNIT; // 6
export const CARD_W = CARD_VW / UNIT; // 0.84
export const CARD_H = CARD_W * CARD_RATIO; // ≈1.17
/** Zone strip offset from the mat centre (library/graveyard/exile right, command zone left). */
export const STRIP_X = MAT_W / 2 + 1.1;

export interface Seat {
  player: string;
  /** Mat centre in world coordinates. */
  x: number;
  z: number;
  /** Rotation about Y: local +z (toward the owner) → world. */
  rot: number;
  /** Where the camera sits to look at this seat's mat from the owner's side. */
  side: "south" | "north" | "west" | "east";
  /**
   * 1v1 (two facing seats), as on MTG Arena: the seat's plate and heart sit centred just past its own edge (mine below
   * my mat, above my hand; theirs beyond their far edge), not in the aisle.
   */
  duel?: boolean;
}

export interface TableSize { w: number; d: number }

/** Half the aisle between the two rows of mats: the stack, combat arrows and the life plaques live here. */
export const AISLE = 1.9;
/** 1v1's half aisle: only the stack and the combat arrows cross it (the plates and hearts sit by each player's own edge). */
export const DUEL_AISLE = 0.6;
/** How far a 1v1 seat's own edge zone reaches past its mat: the heart and plate row, and (across the table) the fan of backs. */
export const DUEL_EDGE = 2.75;
/** The 1v1 seat view's elevation (radians up from the felt; table3d/framing.ts): low, so the facing mats fill a wide screen. */
export const DUEL_VIEW = 0.5;
/** The rail's width inside the table top's edge (environment.ts: the leather rail and the brass inlay inside it). */
export const RAIL = 0.72;
/** Mat centre to mat centre along a row: the zone strips of neighbours don't touch. */
export const SEAT_DX = 2 * STRIP_X + CARD_W + 0.8;
/**
 * Which way along its mat a seat's heart and plaque sit: toward the middle of the table (where the scripted tables
 * keep the hearts, and where every seat can see them), or the owner's left for a seat in the middle of its row.
 * +1 is the owner's right in the mat's own frame.
 */
export function towardMiddle(seat: Seat): 1 | -1 {
  if (Math.abs(seat.x) < 0.01) return -1;
  return -Math.sign(seat.x) * Math.sign(Math.cos(seat.rot)) > 0 ? 1 : -1;
}

/**
 * In facing rows the far row's piles are mirrored: every library, graveyard and exile is on the same side of my screen
 * (my right), and every command zone on the other. Display only (piles are zones, not positions).
 */
export function mirrored(seat: Pick<Seat, "side">): boolean {
  return seat.side === "north";
}

/** Mat-local x that lands `sx` to the right of the mat's centre on my screen (rows face me or away from me). */
function screenX(seat: Pick<Seat, "rot">, sx: number): number {
  return Math.cos(seat.rot) >= 0 ? sx : -sx;
}

/** The life heart (table3d/seatProps.ts): its size, how high its bottom edge floats over the felt, and how far it is tipped up from flat. */
export const HEART = { w: 1.45, h: 1.45 * (232 / 256), y: 0.16 };
export function heartTilt(seat: Pick<Seat, "duel">): number {
  // 1v1, seen low: tipped up less, so it stands shorter between my mat and my hand
  return seat.duel ? 0.45 : 0.7;
}

/** 1v1: how far left of the mat's middle (as I see it) the heart sits; the plate starts at its right edge. */
export const DUEL_HEART_LEFT = 1.15;

/**
 * 1v1: how far past its own edge a seat's heart stands (its centre). It turns to face the camera, tipped up from its
 * edge nearest me. Theirs stands just past their far edge; mine further out, so that from my seat its top edge stays
 * below my mat's near edge (it never covers my mat).
 */
export function duelOut(seat: Pick<Seat, "duel" | "side">): number {
  const t = heartTilt(seat);
  const half = (HEART.h / 2) * Math.cos(t);
  if (seat.side !== "south") return 0.15 + half;
  const top = HEART.y + HEART.h * Math.sin(t);
  return top / Math.tan(DUEL_VIEW) + 0.1 + half;
}

/**
 * Where a seat's life heart floats, mat-local: over the aisle by the mat's inner corner nearest the middle; in 1v1,
 * centred past the mat's own edge (with the plate on its right, as I see it).
 */
export function heartSpot(seat: Seat): [number, number] {
  if (seat.duel) return [screenX(seat, -DUEL_HEART_LEFT), MAT_D / 2 + duelOut(seat)];
  return [towardMiddle(seat) * (MAT_W / 2 - 0.6), -MAT_D / 2 - AISLE * 0.4];
}

/**
 * Where a seat's plaque (portrait, name, trackers) sits, mat-local: beside its heart, a little further along; in 1v1,
 * just right of its heart past the mat's own edge (the DOM plate's left edge is placed against the heart on screen).
 */
export function plaqueSpot(seat: Seat): [number, number] {
  if (seat.duel) return [screenX(seat, -DUEL_HEART_LEFT + 0.85), MAT_D / 2 + duelOut(seat)];
  return [towardMiddle(seat) * (MAT_W / 2 - 3.5), -MAT_D / 2 - AISLE / 2];
}

/**
 * Seats for 1–6 players in two facing rows, as on the scripted Commander tables of Tabletop Simulator
 * (Oops I Baked a Pie's four- and six-seat tables): the viewer's row at the south edge, the rest across
 * the aisle, and every mat upright for its owner (nobody's cards read sideways). Turn order goes
 * clockwise around the table: along the viewer's row to their left, then back along the far row.
 */
export function seats(order: string[], me: string): Seat[] {
  const start = Math.max(0, order.indexOf(me));
  const players = [...order.slice(start), ...order.slice(0, start)];
  const n = players.length;
  const nSouth = Math.max(1, Math.floor(n / 2));
  const nNorth = n - nSouth;
  const rowX = (i: number, k: number) => (i - (k - 1) / 2) * SEAT_DX;
  const duel = n === 2;
  const rowZ = MAT_D / 2 + (duel ? DUEL_AISLE : AISLE);
  // clockwise seen from above: the south row east → west, then the north row west → east
  const southRow = Array.from({ length: nSouth }, (_, i) => ({ x: rowX(nSouth - 1 - i, nSouth), z: rowZ, rot: 0, side: "south" as const }));
  const northRow = Array.from({ length: nNorth }, (_, i) => ({ x: rowX(i, nNorth), z: -rowZ, rot: Math.PI, side: "north" as const }));
  const ring: Omit<Seat, "player">[] = [...southRow, ...northRow];
  // the viewer sits in the middle of their row (east of the middle when the row is even)
  const mine = Math.floor((nSouth - 1) / 2);
  return players.map((player, i) => ({ player, ...ring[(mine + i) % n]!, ...(duel ? { duel: true } : {}) }));
}

/** Half the aisle between the rows (the stack's drop area is its middle). */
export function aisleOf(all: Seat[]): number {
  return all.some((s) => s.duel) ? DUEL_AISLE : AISLE;
}

/** The table top that fits every mat with a margin. */
export function tableSize(all: Seat[]): TableSize {
  let w = 0;
  let d = 0;
  for (const s of all) {
    const sideways = s.side === "west" || s.side === "east";
    const halfW = (sideways ? MAT_D : MAT_W + 2 * (STRIP_X - MAT_W / 2) + CARD_W) / 2;
    const halfD = (sideways ? MAT_W + 2 * (STRIP_X - MAT_W / 2) + CARD_W : MAT_D) / 2;
    // past the mat's own edge (where its owner sits): room for their hand's fan before the rail, and in 1v1 for their
    // heart and plate too; along the row, room for the zone strips
    const own = s.duel ? DUEL_EDGE + RAIL : 1.4;
    w = Math.max(w, Math.abs(s.x) + halfW + (sideways ? own : 1.2));
    d = Math.max(d, Math.abs(s.z) + halfD + (sideways ? 1.2 : own));
  }
  return { w: w * 2, d: d * 2 };
}

/**
 * The old fixed seat camera, replaced by the fitted framing (table3d/framing.ts) and kept as the baseline its tests
 * measure against. It sat behind my seat, looking across the aisle, my mat
 * large and the far row whole. It leans toward the table's middle when my seat is off-centre, as you would at a long
 * table, and is framed from the far mats' back edge down to my seat's buttons, just past my mat's near edge and above my
 * hand (solved for 16:9; a narrower screen pulls back to keep the far row whole).
 */
export function seatCamera(mine: Seat, size: TableSize, aspect: number): { pos: [number, number, number]; look: [number, number, number] } {
  const reach = Math.max((size.w / aspect) * 1.1, size.d);
  return { look: [mine.x * 0.25, 0, mine.z - 3.75], pos: [mine.x * 0.35, reach * 1.07, mine.z + MAT_D / 2 + reach * 0.48] };
}

/** Mat-local → world (x, z). */
export function toWorld(seat: Seat, lx: number, lz: number): [number, number] {
  const c = Math.cos(seat.rot);
  const s = Math.sin(seat.rot);
  return [seat.x + lx * c + lz * s, seat.z - lx * s + lz * c];
}

/** World (x, z) → mat-local. */
export function toLocal(seat: Seat, wx: number, wz: number): [number, number] {
  const dx = wx - seat.x;
  const dz = wz - seat.z;
  const c = Math.cos(seat.rot);
  const s = Math.sin(seat.rot);
  return [dx * c - dz * s, dx * s + dz * c];
}

/** Battlefield virtual position (card top-left) → mat-local centre of the card. */
export function virtualToLocal(x: number, y: number): [number, number] {
  return [x / UNIT - MAT_W / 2 + CARD_W / 2, y / UNIT - MAT_D / 2 + CARD_H / 2];
}

/** Mat-local card centre → battlefield virtual top-left, clamped like the 2D table. */
export function localToVirtual(lx: number, lz: number): [number, number] {
  const x = (lx + MAT_W / 2 - CARD_W / 2) * UNIT;
  const y = (lz + MAT_D / 2 - CARD_H / 2) * UNIT;
  return [Math.max(-20, Math.min(BF_W - 20, x)), Math.max(-20, Math.min(BF_H - 20, y))];
}

/** Is a mat-local point on the battlefield area (with a little slack)? */
export function onBattlefield(lx: number, lz: number): boolean {
  return Math.abs(lx) <= MAT_W / 2 + 0.3 && Math.abs(lz) <= MAT_D / 2 + 0.3;
}

export type PileZone = "library" | "graveyard" | "exile" | "command";

/** Zone piles in mat-local coordinates: library nearest the owner's right hand. */
export const PILES: Record<PileZone, [number, number]> = {
  library: [STRIP_X, MAT_D / 2 - CARD_H / 2],
  graveyard: [STRIP_X, MAT_D / 2 - CARD_H * 1.65],
  exile: [STRIP_X, MAT_D / 2 - CARD_H * 2.8],
  command: [-STRIP_X, MAT_D / 2 - CARD_H / 2],
};

/**
 * The command zone's slots, one per commander, as on the Oops mat: the commander's by the owner's left hand, a
 * partner's (or background's) above it, in line with the graveyard on the other side.
 */
export const COMMAND_SLOTS: [number, number][] = [PILES.command, [-STRIP_X, MAT_D / 2 - CARD_H * 1.65], [-STRIP_X, MAT_D / 2 - CARD_H * 2.8]];

/** A pile's spot on this seat's mat, mat-local (mirrored for the far row: see `mirrored`). */
export function pileSpot(seat: Pick<Seat, "side"> | undefined, zone: PileZone): [number, number] {
  const [x, z] = PILES[zone];
  return seat && mirrored(seat) ? [-x, z] : [x, z];
}

/** A command zone slot (0: the commander's, 1: a partner's or background's) on this seat's mat, mat-local. */
export function commandSlot(seat: Pick<Seat, "side"> | undefined, slot: number): [number, number] {
  const [x, z] = COMMAND_SLOTS[Math.min(slot, COMMAND_SLOTS.length - 1)]!;
  return seat && mirrored(seat) ? [-x, z] : [x, z];
}

/** Where a commander's tax counter sits, mat-local: just outside its slot (on this seat's mat, when given). */
export function taxSpot(slot: number, seat?: Pick<Seat, "side">): [number, number] {
  const [x, z] = commandSlot(seat, slot);
  return [x + Math.sign(x) * (CARD_W / 2 + 0.36), z];
}

/** Which pile (if any) a mat-local point is on (a partner's slot is the command zone too), on this seat's mat when given. */
export function pileAt(lx: number, lz: number, seat?: Pick<Seat, "side">): PileZone | null {
  for (const zone of Object.keys(PILES) as PileZone[]) {
    const [px, pz] = pileSpot(seat, zone);
    if (Math.abs(lx - px) <= CARD_W * 0.75 && Math.abs(lz - pz) <= CARD_H * 0.6) return zone;
  }
  const [px, pz] = commandSlot(seat, 1);
  if (Math.abs(lx - px) <= CARD_W * 0.75 && Math.abs(lz - pz) <= CARD_H * 0.6) return "command";
  return null;
}
