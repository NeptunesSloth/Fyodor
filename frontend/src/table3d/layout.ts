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
}

export interface TableSize { w: number; d: number }

/**
 * Seats for 1–6 players, starting with the viewer at the south edge and going clockwise
 * (to the viewer's left first, as turn order goes around a real table).
 */
export function seats(order: string[], me: string): Seat[] {
  const start = Math.max(0, order.indexOf(me));
  const players = [...order.slice(start), ...order.slice(0, start)];
  const n = players.length;
  const south = MAT_D / 2 + 3.6; // distance of a south/north mat centre from the table centre
  const side = MAT_W / 2 + 2.6 + MAT_D / 2 + 0.6; // east/west mats sit outside the south/north strips
  const place = (i: number): Omit<Seat, "player"> => {
    if (n <= 2) return i === 0 ? { x: 0, z: south, rot: 0, side: "south" } : { x: 0, z: -south, rot: Math.PI, side: "north" };
    if (n === 3) {
      return [
        { x: 0, z: south, rot: 0, side: "south" as const },
        { x: -side, z: -1.5, rot: -Math.PI / 2, side: "west" as const },
        { x: side, z: -1.5, rot: Math.PI / 2, side: "east" as const },
      ][i]!;
    }
    if (n === 4) {
      return [
        { x: 0, z: south, rot: 0, side: "south" as const },
        { x: -side, z: 0, rot: -Math.PI / 2, side: "west" as const },
        { x: 0, z: -south, rot: Math.PI, side: "north" as const },
        { x: side, z: 0, rot: Math.PI / 2, side: "east" as const },
      ][i]!;
    }
    // 5–6: two mats at the north edge, and one at each end for the 6th.
    const half = MAT_W / 2 + 2.2;
    const layout: Omit<Seat, "player">[] = [
      { x: 0, z: south, rot: 0, side: "south" },
      { x: -side, z: 0, rot: -Math.PI / 2, side: "west" },
      { x: -half - 0.4, z: -south, rot: Math.PI, side: "north" },
      { x: half + 0.4, z: -south, rot: Math.PI, side: "north" },
      { x: side, z: 0, rot: Math.PI / 2, side: "east" },
    ];
    if (n === 6) layout.splice(1, 0, { x: -half - 0.4, z: south, rot: 0, side: "south" });
    if (n === 6) layout[0] = { x: half + 0.4, z: south, rot: 0, side: "south" };
    return layout[i]!;
  };
  return players.map((player, i) => ({ player, ...place(i) }));
}

/** The table top that fits every mat with a margin. */
export function tableSize(all: Seat[]): TableSize {
  let w = 0;
  let d = 0;
  for (const s of all) {
    const sideways = s.side === "west" || s.side === "east";
    const halfW = (sideways ? MAT_D : MAT_W + 2 * (STRIP_X - MAT_W / 2) + CARD_W) / 2;
    const halfD = (sideways ? MAT_W + 2 * (STRIP_X - MAT_W / 2) + CARD_W : MAT_D) / 2;
    w = Math.max(w, Math.abs(s.x) + halfW + 1.2);
    d = Math.max(d, Math.abs(s.z) + halfD + 1.4);
  }
  return { w: w * 2, d: d * 2 };
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

/** Which pile (if any) a mat-local point is on. */
export function pileAt(lx: number, lz: number): PileZone | null {
  for (const [zone, [px, pz]] of Object.entries(PILES) as [PileZone, [number, number]][]) {
    if (Math.abs(lx - px) <= CARD_W * 0.75 && Math.abs(lz - pz) <= CARD_H * 0.6) return zone;
  }
  return null;
}
