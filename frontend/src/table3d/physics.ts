/**
 * Thrown dice, simulated with cannon-es (a rigid-body physics library: MIT, pure JavaScript, bundled with the app
 * so the table stays offline). Each die is its real convex polyhedron (a coin is a cylinder). The table top, its
 * edges and the seats' library piles are solid, so dice bounce, knock together, glance off decks and roll to
 * rest on a face. A throw is simulated ahead in fixed steps and played back, so the server's number can be
 * printed on whichever face ends up on top. A seed makes the throw identical on every screen at the table.
 * Cards stay where the server puts them: physics is only for what is thrown.
 */
import * as CANNON from "cannon-es";
import * as THREE from "three";

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
}

/** Recorded poses per body: [x, y, z, qx, qy, qz, qw] per frame. */
export interface Track { frames: Float32Array; count: number }

/** A solid box on the table (a library pile), centred at (x, z), standing h tall. */
export interface Obstacle { x: number; z: number; w: number; d: number; h: number }

export interface SimOptions {
  /** Table-top bounds the dice stay inside (x/z min and max). */
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  obstacles?: Obstacle[];
  gravity?: number;
  maxSeconds?: number;
}

const STEP = 1 / 240;
const RECORD_EVERY = 2; // 120 frames a second

/** Deterministic random numbers from a string (mulberry32 over a string hash). */
export function seeded(key: string): () => number {
  let h = 1779033703 ^ key.length;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 3432918353), (h = (h << 13) | (h >>> 19));
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const vec = (v: THREE.Vector3) => new CANNON.Vec3(v.x, v.y, v.z);

/** Simulate the throw until every body is at rest (or the time runs out). */
export function simulate(bodies: BodyInit[], opts: SimOptions): Track[] {
  const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -(opts.gravity ?? 28), 0), allowSleep: true });
  world.solver = Object.assign(new CANNON.GSSolver(), { iterations: 14 });
  const felt = new CANNON.Material("table");
  const bone = new CANNON.Material("die");
  world.addContactMaterial(new CANNON.ContactMaterial(felt, bone, { friction: 0.42, restitution: 0.32 }));
  world.addContactMaterial(new CANNON.ContactMaterial(bone, bone, { friction: 0.3, restitution: 0.4 }));
  // the table top, its four edges and the library piles
  const ground = new CANNON.Body({ mass: 0, material: felt, shape: new CANNON.Plane() });
  ground.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
  world.addBody(ground);
  const { minX, maxX, minZ, maxZ } = opts.bounds;
  const solid = (x: number, y: number, z: number, hx: number, hy: number, hz: number) => {
    const b = new CANNON.Body({ mass: 0, material: felt, shape: new CANNON.Box(new CANNON.Vec3(hx, hy, hz)) });
    b.position.set(x, y, z);
    world.addBody(b);
  };
  const wall = 0.5;
  solid(minX - wall, 1, (minZ + maxZ) / 2, wall, 1, (maxZ - minZ) / 2 + wall);
  solid(maxX + wall, 1, (minZ + maxZ) / 2, wall, 1, (maxZ - minZ) / 2 + wall);
  solid((minX + maxX) / 2, 1, minZ - wall, (maxX - minX) / 2 + wall, 1, wall);
  solid((minX + maxX) / 2, 1, maxZ + wall, (maxX - minX) / 2 + wall, 1, wall);
  for (const o of opts.obstacles ?? []) solid(o.x, o.h / 2, o.z, o.w / 2, o.h / 2, o.d / 2);
  // the dice
  const dice = bodies.map((b) => {
    const shape = b.cylinder
      ? new CANNON.Cylinder(b.cylinder.radius, b.cylinder.radius, b.cylinder.height, 20)
      : new CANNON.ConvexPolyhedron({ vertices: b.verts.map(vec), faces: b.faces });
    const body = new CANNON.Body({ mass: 1, material: bone, shape, linearDamping: 0.05, angularDamping: 0.12 });
    body.sleepSpeedLimit = 0.12;
    body.sleepTimeLimit = 0.25;
    body.position.copy(vec(b.pos));
    body.velocity.copy(vec(b.vel));
    body.angularVelocity.copy(vec(b.spin));
    body.quaternion.set(b.rot.x, b.rot.y, b.rot.z, b.rot.w);
    world.addBody(body);
    return body;
  });
  const steps = Math.round((opts.maxSeconds ?? 4) / STEP);
  const tracks: Track[] = dice.map(() => ({ frames: new Float32Array(Math.ceil(steps / RECORD_EVERY + 2) * 7), count: 0 }));
  const record = () => dice.forEach((d, i) => {
    const t = tracks[i]!;
    t.frames.set([d.position.x, d.position.y, d.position.z, d.quaternion.x, d.quaternion.y, d.quaternion.z, d.quaternion.w], t.count * 7);
    t.count++;
  });
  record();
  for (let step = 1; step <= steps; step++) {
    world.step(STEP);
    if (step % RECORD_EVERY === 0) record();
    if (dice.every((d) => d.sleepState === CANNON.Body.SLEEPING)) break;
  }
  record();
  return tracks;
}

/** A recorded pose at frame f (clamped). */
export function poseAt(track: Track, f: number, pos: THREE.Vector3, quat: THREE.Quaternion): void {
  const i = Math.max(0, Math.min(track.count - 1, f)) * 7;
  const a = track.frames;
  pos.set(a[i]!, a[i + 1]!, a[i + 2]!);
  quat.set(a[i + 3]!, a[i + 4]!, a[i + 5]!, a[i + 6]!);
}

/** Seconds of recorded motion. */
export const trackSeconds = (t: Track) => (t.count - 1) * STEP * RECORD_EVERY;
export const FRAMES_PER_SECOND = 1 / (STEP * RECORD_EVERY);
