/**
 * Thrown dice, simulated with cannon-es (a rigid-body physics library: MIT, pure JavaScript, bundled with the app
 * so the table stays offline). Each die is its real convex polyhedron (table3d/diceGeometry.ts; a coin is a
 * cylinder). The table top, its edges and the roller's piles are solid, so dice bounce, knock together, glance off
 * decks and roll to rest on a face. A throw is simulated ahead in fixed steps and played back. A seed makes the
 * throw identical on every screen at the table: the simulation runs in the roller's own mat frame, against an
 * environment every screen builds the same way, and uses no transcendental maths of its own.
 * Cards stay where the server puts them: physics is only for what is thrown.
 */
import * as CANNON from "cannon-es";
import * as THREE from "three";
import { seededRandom } from "../game/seededRandom";

export interface BodyInit {
  /** Hull vertices in the body's own frame (the centre of mass at the origin). */
  verts: THREE.Vector3[];
  /** The hull's faces as vertex indices, counter-clockwise seen from outside. */
  faces?: number[][];
  /** A coin: a cylinder along the body's Y axis, instead of the hull. */
  cylinder?: { radius: number; height: number };
  /** Bounding radius (the table's edges keep this much room). */
  radius: number;
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  spin: THREE.Vector3;
  rot: THREE.Quaternion;
  /** Rolling resistance stand-ins: a rounder die rolls further, the felt stops it (defaults: TUNING). */
  linearDamping?: number;
  angularDamping?: number;
}

/** Recorded poses per body: [x, y, z, qx, qy, qz, qw] per frame; `rest`: the frame it came to rest. */
export interface Track { frames: Float32Array; count: number; rest: number; settled: boolean }

/** A solid box on the table (a library pile), centred at (x, z), standing h tall. */
export interface Obstacle { x: number; z: number; w: number; d: number; h: number }

/** Something the dice hit hard enough to hear: when (simulated seconds), how hard (along the normal), what. */
export interface Impact { t: number; speed: number; body: number; with: "table" | "die" | "wall" | "deck" }

export interface SimOptions {
  /** Table-top bounds the dice stay inside (x/z min and max). */
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  obstacles?: Obstacle[];
  gravity?: number;
  maxSeconds?: number;
  /** Half the steps (1/120 s): a big throw, where the cost of many dice knocking together adds up. */
  coarse?: boolean;
}

export interface SimResult { tracks: Track[]; impacts: Impact[]; seconds: number }

const FINE = 1 / 240;
const FRAME = 1 / 120; // recorded 120 frames a second either way

/** Deterministic random numbers from a string (game/seededRandom.ts). */
export const seeded = seededRandom;

/** A uniformly random orientation from a seeded generator, with square roots only (same bits on every engine). */
export function randomRotation(rnd: () => number): THREE.Quaternion {
  for (;;) {
    const q = new THREE.Quaternion(rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1);
    const l = q.lengthSq();
    if (l > 0.01 && l <= 1) return q.normalize();
  }
}

/** A random unit vector (rejection sampled, square roots only). */
export function randomAxis(rnd: () => number): THREE.Vector3 {
  for (;;) {
    const v = new THREE.Vector3(rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1);
    const l = v.lengthSq();
    if (l > 0.01 && l <= 1) return v.normalize();
  }
}

const vec = (v: THREE.Vector3) => new CANNON.Vec3(v.x, v.y, v.z);

/** Felt over wood: dice skid and roll a little, bounce low. Resin on resin: a livelier knock. */
export const TUNING = {
  gravity: 60,
  feltFriction: 0.32,
  feltRestitution: 0.3,
  dieFriction: 0.18,
  dieRestitution: 0.42,
  wallRestitution: 0.36,
  linearDamping: 0.12,
  angularDamping: 0.22,
  sleepSpeed: 0.22,
  sleepTime: 0.14,
};

/** Simulate the throw until every body is at rest (or the time runs out). */
export function simulate(bodies: BodyInit[], opts: SimOptions): SimResult {
  const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -(opts.gravity ?? TUNING.gravity), 0), allowSleep: true });
  world.solver = Object.assign(new CANNON.GSSolver(), { iterations: 14 });
  world.broadphase = new CANNON.SAPBroadphase(world); // many still cards and piles, a few moving dice
  const felt = new CANNON.Material("table");
  const rail = new CANNON.Material("rail");
  const resin = new CANNON.Material("die");
  world.addContactMaterial(new CANNON.ContactMaterial(felt, resin, { friction: TUNING.feltFriction, restitution: TUNING.feltRestitution }));
  world.addContactMaterial(new CANNON.ContactMaterial(rail, resin, { friction: 0.3, restitution: TUNING.wallRestitution }));
  world.addContactMaterial(new CANNON.ContactMaterial(resin, resin, { friction: TUNING.dieFriction, restitution: TUNING.dieRestitution }));
  const what = new Map<number, Impact["with"]>();
  // the table top, its four edges and the piles
  const ground = new CANNON.Body({ mass: 0, material: felt, shape: new CANNON.Plane() });
  ground.quaternion.set(-Math.SQRT1_2, 0, 0, Math.SQRT1_2); // −90° about x: the plane faces up
  world.addBody(ground);
  what.set(ground.id, "table");
  const { minX, maxX, minZ, maxZ } = opts.bounds;
  const solid = (x: number, y: number, z: number, hx: number, hy: number, hz: number, kind: Impact["with"]) => {
    const b = new CANNON.Body({ mass: 0, material: kind === "deck" ? felt : rail, shape: new CANNON.Box(new CANNON.Vec3(hx, hy, hz)) });
    b.position.set(x, y, z);
    world.addBody(b);
    what.set(b.id, kind);
  };
  const wall = 0.5;
  solid(minX - wall, 1, (minZ + maxZ) / 2, wall, 1, (maxZ - minZ) / 2 + wall, "wall");
  solid(maxX + wall, 1, (minZ + maxZ) / 2, wall, 1, (maxZ - minZ) / 2 + wall, "wall");
  solid((minX + maxX) / 2, 1, minZ - wall, (maxX - minX) / 2 + wall, 1, wall, "wall");
  solid((minX + maxX) / 2, 1, maxZ + wall, (maxX - minX) / 2 + wall, 1, wall, "wall");
  for (const o of opts.obstacles ?? []) solid(o.x, o.h / 2, o.z, o.w / 2, o.h / 2, o.d / 2, "deck");
  // the dice
  const dice = bodies.map((b, i) => {
    const shape = b.cylinder
      ? new CANNON.Cylinder(b.cylinder.radius, b.cylinder.radius, b.cylinder.height, 24)
      : new CANNON.ConvexPolyhedron({ vertices: b.verts.map(vec), faces: b.faces });
    const body = new CANNON.Body({ mass: 1, material: resin, shape, linearDamping: b.linearDamping ?? TUNING.linearDamping, angularDamping: b.angularDamping ?? TUNING.angularDamping });
    body.sleepSpeedLimit = TUNING.sleepSpeed;
    body.sleepTimeLimit = TUNING.sleepTime;
    body.position.copy(vec(b.pos));
    body.velocity.copy(vec(b.vel));
    body.angularVelocity.copy(vec(b.spin));
    body.quaternion.set(b.rot.x, b.rot.y, b.rot.z, b.rot.w);
    world.addBody(body);
    what.set(body.id, "die");
    return { body, index: i };
  });
  const indexOf = new Map(dice.map((d) => [d.body.id, d.index]));
  const STEP = opts.coarse ? FRAME : FINE;
  const RECORD_EVERY = Math.round(FRAME / STEP);
  const steps = Math.round((opts.maxSeconds ?? 4) / STEP);
  const tracks: Track[] = dice.map(() => ({ frames: new Float32Array(Math.ceil(steps / RECORD_EVERY + 2) * 7), count: 0, rest: 0, settled: false }));
  const record = () => dice.forEach(({ body: d }, i) => {
    const t = tracks[i]!;
    t.frames.set([d.position.x, d.position.y, d.position.z, d.quaternion.x, d.quaternion.y, d.quaternion.z, d.quaternion.w], t.count * 7);
    if (d.sleepState !== CANNON.Body.SLEEPING) t.rest = t.count + 1;
    t.count++;
  });
  // impacts: every contact this step that closes fast enough, once per pair per 60 ms (faces slapping down as a die
  // tumbles count too, not only first touches)
  const impacts: Impact[] = [];
  const lastHit = new Map<string, number>();
  const hear = (step: number) => {
    const t = step * STEP;
    for (const c of world.contacts) {
      const a = indexOf.get(c.bi.id);
      const b = indexOf.get(c.bj.id);
      if (a === undefined && b === undefined) continue;
      const speed = Math.abs(c.getImpactVelocityAlongNormal());
      if (speed < 0.45) continue;
      const pair = `${c.bi.id}:${c.bj.id}`;
      if (t - (lastHit.get(pair) ?? -1) < 0.06) continue;
      lastHit.set(pair, t);
      const body = a ?? b!;
      const other = a === undefined ? c.bi.id : c.bj.id;
      impacts.push({ t, speed, body, with: a !== undefined && b !== undefined ? "die" : what.get(other) ?? "table" });
    }
  };
  record();
  let step = 1;
  for (; step <= steps; step++) {
    world.step(STEP);
    hear(step);
    if (step % RECORD_EVERY === 0) record();
    if (dice.every(({ body }) => body.sleepState === CANNON.Body.SLEEPING)) break;
  }
  record();
  dice.forEach(({ body }, i) => { tracks[i]!.settled = body.sleepState === CANNON.Body.SLEEPING; });
  return { tracks, impacts, seconds: Math.min(step, steps) * STEP };
}

/** A recorded pose at frame f (clamped). */
export function poseAt(track: Track, f: number, pos: THREE.Vector3, quat: THREE.Quaternion): void {
  const i = Math.max(0, Math.min(track.count - 1, f)) * 7;
  const a = track.frames;
  pos.set(a[i]!, a[i + 1]!, a[i + 2]!);
  quat.set(a[i + 3]!, a[i + 4]!, a[i + 5]!, a[i + 6]!);
}

const qa = new THREE.Quaternion();
const pa = new THREE.Vector3();
/** The pose at a fractional frame (smooth playback at any frame rate or animation speed). */
export function poseLerp(track: Track, f: number, pos: THREE.Vector3, quat: THREE.Quaternion): void {
  const last = track.count - 1;
  if (f >= last) return poseAt(track, last, pos, quat);
  const i = Math.max(0, Math.floor(f));
  const k = Math.max(0, f - i);
  poseAt(track, i, pos, quat);
  if (k <= 0) return;
  poseAt(track, i + 1, pa, qa);
  pos.lerp(pa, k);
  quat.slerp(qa, k);
}

/** Seconds of recorded motion. */
export const trackSeconds = (t: Track) => (t.count - 1) * FRAME;
/** Seconds until this body came to rest. */
export const restSeconds = (t: Track) => Math.min(t.count - 1, t.rest) * FRAME;
export const FRAMES_PER_SECOND = 1 / FRAME;
