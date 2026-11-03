/**
 * Cards you can flick, on the 3D table: let go of a dragged card while it's still moving and it slides on across
 * your mat, slowing on the felt, and knocks your other cards out of its way (cannon-es, the same library as the
 * dice). Cards stay flat and square to the mat, and stop at its edges. The slide is simulated ahead and played
 * back; where everything comes to rest goes to the server as one move, so the server still decides where cards
 * are, and every other screen sees them go there.
 *
 * Coordinates are the mat's own (world units, x to the owner's right, z toward the owner): table3d/layout.ts.
 */
import * as CANNON from "cannon-es";

export interface SlideCard {
  id: string;
  /** Centre on the mat. */
  x: number;
  z: number;
  /** Footprint (a tapped card is turned: wider than deep). */
  w: number;
  d: number;
  /** The flicked card(s), with their release velocity; every other card starts at rest. */
  vx?: number;
  vz?: number;
}

export interface Slide {
  /** Centre per frame, [x0, z0, x1, z1, …], for each card that moved. */
  tracks: Map<string, Float32Array>;
  frames: number;
  /** Where each moved card comes to rest. */
  rest: Map<string, [number, number]>;
}

const STEP = 1 / 120;
export const SLIDE_FPS = 120;
const MOVING = 1;
const RESTING = 2;
const WALL = 4;

const overlaps = (a: SlideCard, b: SlideCard) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.z - b.z) < (a.d + b.d) / 2;

/**
 * Simulate a flick on one mat (half extents `halfW` × `halfD`). Cards already overlapping a flicked card (it was
 * dropped on a pile) and cards overlapping each other are left alone: piles are on purpose, not collisions.
 */
export function slide(cards: SlideCard[], halfW: number, halfD: number, maxSeconds = 2.5): Slide {
  const world = new CANNON.World({ gravity: new CANNON.Vec3(0, 0, 0) });
  const felt = new CANNON.Material("card");
  world.addContactMaterial(new CANNON.ContactMaterial(felt, felt, { friction: 0, restitution: 0.25 }));
  const wall = (x: number, z: number, hx: number, hz: number) => {
    const b = new CANNON.Body({ mass: 0, material: felt, shape: new CANNON.Box(new CANNON.Vec3(hx, 0.5, hz)), collisionFilterGroup: WALL, collisionFilterMask: MOVING | RESTING });
    b.position.set(x, 0, z);
    world.addBody(b);
  };
  const t = 1;
  wall(-halfW - t, 0, t, halfD + 2 * t);
  wall(halfW + t, 0, t, halfD + 2 * t);
  wall(0, -halfD - t, halfW + 2 * t, t);
  wall(0, halfD + t, halfW + 2 * t, t);
  const flicked = cards.filter((c) => c.vx || c.vz);
  // a resting card under a flicked one, or in a pile with another, sits this one out
  const resting = cards.filter((c) => !flicked.includes(c) && !flicked.some((f) => overlaps(f, c)));
  const bodies = new Map<string, CANNON.Body>();
  const add = (c: SlideCard, moving: boolean) => {
    const b = new CANNON.Body({
      mass: 1, material: felt, shape: new CANNON.Box(new CANNON.Vec3(c.w / 2, 0.02, c.d / 2)),
      linearDamping: 0.93, // the felt: a flick at 10 units/s goes about 4 units
      collisionFilterGroup: moving ? MOVING : RESTING,
      // flicked cards don't knock each other (a dragged pile stays a pile); resting cards only move when hit
      collisionFilterMask: moving ? RESTING | WALL : MOVING | WALL,
    });
    b.linearFactor.set(1, 0, 1);
    b.angularFactor.set(0, 0, 0); // square to the mat, as a player leaves them
    b.position.set(c.x, 0, c.z);
    b.velocity.set(c.vx ?? 0, 0, c.vz ?? 0);
    world.addBody(b);
    bodies.set(c.id, b);
  };
  flicked.forEach((c) => add(c, true));
  resting.forEach((c) => add(c, false));
  const record: Map<string, number[]> = new Map([...bodies.keys()].map((id) => [id, []]));
  const steps = Math.round(maxSeconds / STEP);
  let frames = 0;
  for (let step = 0; step <= steps; step++) {
    for (const [id, b] of bodies) record.get(id)!.push(b.position.x, b.position.z);
    frames++;
    if ([...bodies.values()].every((b) => b.velocity.lengthSquared() < 0.0004)) break;
    world.step(STEP);
  }
  const tracks = new Map<string, Float32Array>();
  const rest = new Map<string, [number, number]>();
  for (const c of cards) {
    const r = record.get(c.id);
    if (!r) continue;
    const x = r[r.length - 2]!, z = r[r.length - 1]!;
    if (Math.hypot(x - c.x, z - c.z) < 0.02) continue; // didn't move
    tracks.set(c.id, Float32Array.from(r));
    rest.set(c.id, [x, z]);
  }
  return { tracks, frames, rest };
}
