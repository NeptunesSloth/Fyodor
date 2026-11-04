/**
 * Another player's hand on the 3D table: a fan of card backs held up at their own edge of the table, leaning back toward
 * them as a real hand is held, so every other seat sees the backs (count only: the cards carry no identity). It stands
 * inside the table top, between their mat and the rail, and never dips below the felt: a flat fan past the mat used to
 * overhang the table's edge and cut through the rail.
 *
 * Pure three.js math (no WebGL), so it is unit-tested.
 */
import * as THREE from "three";
import { CARD_H, CARD_W, DUEL_EDGE, MAT_D, RAIL, toWorld, type Seat, type TableSize } from "./layout";

/** One card of the fan: where it is, how it's turned, and its size (world units). */
export interface FanCard {
  pos: THREE.Vector3;
  quat: THREE.Quaternion;
  scale: number;
}

/** Cards drawn at most (a bigger hand only widens the fan's count on the plate). */
export const FAN_MAX = 12;
/** The fan's layers: each card a hair in front of the one before (clear of z-fighting from far away). */
export const FAN_LAYER = 0.012;

/** How the fan stands for a seat: where its foot is past the mat's own edge, how far it leans back and its card size. */
export function fanStance(seat: Seat): { foot: number; lean: number; scale: number } {
  // 1v1: behind the heart and plate row, peeking over it (as the opponent's hand does on Arena)
  if (seat.duel) return { foot: DUEL_EDGE - 1.3, lean: 0.95, scale: 0.86 };
  // more seats: just past the mat's edge, in the band of wood before the rail, standing a little more upright
  return { foot: 0.16, lean: 1.12, scale: 0.72 };
}

/**
 * The fan for `count` cards in a seat's hand, in world coordinates. The fan stands with its foot along the seat's edge,
 * its cards spread in an arc and leaning `lean` radians up from the felt, top edges toward the owner.
 */
export function handFan(seat: Seat, count: number): FanCard[] {
  const shown = Math.min(Math.max(0, count), FAN_MAX);
  const { foot, lean, scale } = fanStance(seat);
  const h = CARD_H * scale;
  const out: FanCard[] = [];
  // the fan's frame: origin on the felt at the foot's middle, +z toward the table's middle (the backs face it), y up
  const [fx, fz] = toWorld(seat, 0, MAT_D / 2 + foot);
  const frame = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), seat.rot + Math.PI);
  const tilt = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), lean);
  const width = Math.min(3.0, 0.42 + shown * 0.3) * scale;
  const spread = Math.min(0.42, 0.09 * shown);
  for (let i = 0; i < shown; i++) {
    const t = shown === 1 ? 0 : i / (shown - 1) - 0.5;
    // laid flat first: spread along x, the outer cards a little lower (toward the foot), each a layer in front
    const twist = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -t * spread * 2);
    const flat = new THREE.Vector3(t * width, i * FAN_LAYER, -h / 2 + Math.abs(t) * 0.18 * scale);
    // then stood up about the foot: the card's bottom edge stays on the felt line, its top leans away from the table's middle
    const local = flat.clone().applyQuaternion(tilt);
    const pos = local.applyQuaternion(frame).add(new THREE.Vector3(fx, 0, fz));
    const quat = frame.clone().multiply(tilt).multiply(twist);
    const card = { pos, quat, scale };
    // a turned card's lower corner would dip into the felt: lift it clear
    const low = Math.min(...fanCorners(card).map((p) => p.y));
    pos.y += 0.02 - low;
    out.push(card);
  }
  return out;
}

/** The four corners of a fan card (world), for checks that it stays on the table top. */
export function fanCorners(c: FanCard): THREE.Vector3[] {
  const w = (CARD_W / 2) * c.scale;
  const h = (CARD_H / 2) * c.scale;
  return [[-w, -h], [w, -h], [w, h], [-w, h]].map(([x, z]) => new THREE.Vector3(x, 0, z).applyQuaternion(c.quat).add(c.pos));
}

/** The table top's usable area inside the rail (half extents), where the fan must stay. */
export function insideRail(size: TableSize): { hx: number; hz: number } {
  return { hx: size.w / 2 - RAIL, hz: size.d / 2 - RAIL };
}
