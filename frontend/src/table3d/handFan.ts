/**
 * Another player's hand on the 3D table, as at Tabletop Simulator: their cards held up at their own edge of the table,
 * standing nearly upright and fanned in an arc, so every other seat sees a fan of real card backs there (count only:
 * the cards carry no identity, and both sides of each card are a back).
 *
 * Every fan leans away from my side of the table, so I see it whole from my seat: the far row's lean back toward their
 * owners (their backs face the table's middle and me); a neighbour in my row holds theirs tipped up to their eyes, its
 * top over their mat's edge, and I see it over their shoulder (a back again: the faces are never drawn). Each card is a
 * card's own size (CARD_W × CARD_H) and stays inside the table top's rail and above the felt.
 *
 * Pure three.js math (no WebGL), so it is unit-tested.
 */
import * as THREE from "three";
import { CARD_H, CARD_W, DUEL_FAN_X, MAT_D, RAIL, screenX, toWorld, type Seat, type TableSize } from "./layout";

/** One card of the fan: where its middle is and how it's turned (world). */
export interface FanCard {
  pos: THREE.Vector3;
  quat: THREE.Quaternion;
}

/** Cards drawn at most: a bigger hand shows its count on a tag over the fan (fanTag). */
export const FAN_MAX = 12;
/** The fan's layers: each card a hair in front of the one before (clear of z-fighting from across the table). */
export const FAN_LAYER = 0.012;
/** How far the held cards lean back from upright (radians): about 20°, as a hand is held. */
export const FAN_LEAN = THREE.MathUtils.degToRad(20);
/** The fan's arc: the angle between neighbouring cards (radians) and the radius of the arc their middles lie on. */
export const FAN_STEP = 0.075;
export const FAN_RADIUS = 4;
/** How high the fan's lowest corner is held over the felt. */
export const FAN_CLEAR = 0.03;

/**
 * How the fan stands for a seat: its foot's distance past the mat's own edge, its middle along that edge (mat-local x),
 * and whether its backs face the table's middle (the far row's) or its top leans over the mat (a seat in my row).
 */
export function fanStance(seat: Seat): { foot: number; along: number; acrossFromMe: boolean } {
  const acrossFromMe = Math.cos(seat.rot) < -1e-6;
  // 1v1: beside their heart and plate, right of them (as I see it), just past their far edge
  if (seat.duel) return { foot: 0.35, along: screenX(seat, DUEL_FAN_X), acrossFromMe };
  // more seats: in the band of wood between the mat's edge and the rail, centred on the mat; a fan leaning over its
  // mat stands further out, its top just over the mat's edge
  return { foot: acrossFromMe ? 0.3 : 0.62, along: 0, acrossFromMe };
}

/**
 * Whether a seat shows a fan on my screen: every seat but mine (my own hand is the overlay at the bottom of the
 * screen). The caller knows which seat is mine; this keeps the rule in one place.
 */
export function showsFan(seat: Pick<Seat, "player">, me: string): boolean {
  return seat.player !== me;
}

/**
 * The fan for `count` cards in a seat's hand, in world coordinates, in drawing order (left to right as I see it, each
 * in front of the one before). The cards' middles lie on an arc about a point below the hand, each turned out along it,
 * and the whole hand leans FAN_LEAN back from upright, away from my side of the table.
 */
export function handFan(seat: Seat, count: number): FanCard[] {
  const shown = Math.min(Math.max(0, Math.floor(count)), FAN_MAX);
  if (!shown) return [];
  const { foot, along, acrossFromMe } = fanStance(seat);
  // the fan's frame: origin on the felt at the foot's middle, +z toward my side of the table (the side I see), y up;
  // the cards lean toward −z. Mat-local +z points at the seat's owner, so the far row's frame is turned round.
  const [fx, fz] = toWorld(seat, along, MAT_D / 2 + foot);
  const frame = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), seat.rot + (acrossFromMe ? Math.PI : 0));
  // stood up from flat (a flat card faces +y, its top toward −z): turned up about x until it leans FAN_LEAN back
  const stand = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2 - FAN_LEAN);
  const out: FanCard[] = [];
  for (let i = 0; i < shown; i++) {
    const theta = (i - (shown - 1) / 2) * FAN_STEP;
    // in the card's plane (x right, −z up the card): its middle on the arc, turned out along it
    const flat = new THREE.Vector3(FAN_RADIUS * Math.sin(theta), i * FAN_LAYER, -(CARD_H / 2 + FAN_RADIUS * (Math.cos(theta) - 1)));
    const twist = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -theta);
    const pos = flat.applyQuaternion(stand).applyQuaternion(frame).add(new THREE.Vector3(fx, 0, fz));
    const quat = frame.clone().multiply(stand).multiply(twist);
    out.push({ pos, quat });
  }
  // held up as one: the whole hand lifted until its lowest corner (an outer card's) is just clear of the felt
  let low = Infinity;
  for (const c of out) for (const p of fanCorners(c)) low = Math.min(low, p.y);
  for (const c of out) c.pos.y += FAN_CLEAR - low;
  return out;
}

/**
 * Where a re-fanned hand's cards start from (fresh copies, eased toward `goal` each frame): a card it keeps from where it
 * is now, a card drawn from behind the last card held (or, into an empty hand, already in its place). A card that left
 * is simply gone: its flight, if any, is the table's motion.
 */
export function refanFrom(now: FanCard[], goal: FanCard[]): FanCard[] {
  const last = now[now.length - 1];
  return goal.map((g, i) => {
    const from = now[i] ?? last ?? g;
    return { pos: from.pos.clone(), quat: from.quat.clone() };
  });
}

/**
 * One frame of a re-fan: every card `k` of the way to its goal (k = 1 under reduced motion: there at once). True once
 * all are there: -- flicker -- a card that has arrived is put exactly in place (a quaternion's angle can't be measured
 * below ~1e-4 rad, so its dot product is what's compared), never creeping by fractions of a pixel forever.
 */
export function easeFan(cur: FanCard[], goal: FanCard[], k: number): boolean {
  let done = true;
  for (let i = 0; i < goal.length; i++) {
    const c = cur[i]!;
    const g = goal[i]!;
    c.pos.lerp(g.pos, k);
    c.quat.slerp(g.quat, k);
    if (k >= 1 || (c.pos.distanceToSquared(g.pos) < 1e-8 && Math.abs(c.quat.dot(g.quat)) > 1 - 1e-9)) {
      c.pos.copy(g.pos);
      c.quat.copy(g.quat);
    } else done = false;
  }
  return done;
}

/** Where a fan's count tag floats (a hand bigger than FAN_MAX): just over the top of its middle card. */
export function fanTag(fan: FanCard[]): THREE.Vector3 | null {
  const mid = fan[Math.floor((fan.length - 1) / 2)];
  if (!mid) return null;
  return new THREE.Vector3(0, 0, -(CARD_H / 2 + 0.28)).applyQuaternion(mid.quat).add(mid.pos);
}

/** The four corners of a fan card (world): bottom left, bottom right, top right, top left (as the card is held). */
export function fanCorners(c: FanCard): THREE.Vector3[] {
  const w = CARD_W / 2;
  const h = CARD_H / 2;
  return [[-w, h], [w, h], [w, -h], [-w, -h]].map(([x, z]) => new THREE.Vector3(x, 0, z).applyQuaternion(c.quat).add(c.pos));
}

/** A fan card's own up (from its bottom edge to its top) and the normal of the side I see (world unit vectors). */
export function fanAxes(c: FanCard): { up: THREE.Vector3; normal: THREE.Vector3 } {
  return {
    up: new THREE.Vector3(0, 0, -1).applyQuaternion(c.quat),
    normal: new THREE.Vector3(0, 1, 0).applyQuaternion(c.quat),
  };
}

/** The table top's usable area inside the rail (half extents), where the fan must stay. */
export function insideRail(size: TableSize): { hx: number; hz: number } {
  return { hx: size.w / 2 - RAIL, hz: size.d / 2 - RAIL };
}
