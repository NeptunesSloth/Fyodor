/**
 * A small rigid-body simulation for thrown dice, written for Fyodor rather than pulled in as a physics
 * library. Convex bodies fall under gravity onto the table top, bounce (restitution), slide and roll
 * (friction), knock into each other (as spheres), and come to rest on a face. A throw is simulated ahead in
 * fixed steps and played back, so the server's number can be printed on whichever face ends up on top. A
 * seed makes the throw identical on every screen at the table.
 */
import * as THREE from "three";

export interface BodyInit {
  /** Hull vertices in the body's own frame (the centre of mass at the origin). */
  verts: THREE.Vector3[];
  /** Bounding radius, for knocks between dice and the inertia. */
  radius: number;
  pos: THREE.Vector3;
  vel: THREE.Vector3;
  spin: THREE.Vector3;
  rot: THREE.Quaternion;
}

/** Recorded poses per body: [x, y, z, qx, qy, qz, qw] per frame. */
export interface Track { frames: Float32Array; count: number }

export interface SimOptions {
  /** Table-top bounds the dice stay inside (x/z min and max). */
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  gravity?: number;
  maxSeconds?: number;
}

const STEP = 1 / 240;
const RECORD_EVERY = 2; // 120 frames a second
const RESTITUTION = 0.32;
const FRICTION = 0.5;
const WALL_BOUNCE = 0.45;

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

interface State { x: THREE.Vector3; q: THREE.Quaternion; v: THREE.Vector3; w: THREE.Vector3; invI: number; still: number; asleep: boolean; b: BodyInit }

const UP = new THREE.Vector3(0, 1, 0);
const tmp = { r: new THREE.Vector3(), p: new THREE.Vector3(), u: new THREE.Vector3(), t: new THREE.Vector3(), c: new THREE.Vector3(), dq: new THREE.Quaternion() };

/** Apply an impulse j at offset r from the centre. */
function impulse(s: State, r: THREE.Vector3, j: THREE.Vector3): void {
  s.v.add(j);
  s.w.add(tmp.c.copy(r).cross(j).multiplyScalar(s.invI));
}

/** Velocity of the body's point at offset r. */
function pointVel(s: State, r: THREE.Vector3, out: THREE.Vector3): THREE.Vector3 {
  return out.copy(s.w).cross(r).add(s.v);
}

/** Simulate the throw; every body ends at rest (or is eased flat if it hasn't settled in time). */
export function simulate(bodies: BodyInit[], opts: SimOptions): Track[] {
  const g = opts.gravity ?? 28;
  const steps = Math.round((opts.maxSeconds ?? 4) / STEP);
  const states: State[] = bodies.map((b) => ({
    x: b.pos.clone(), q: b.rot.clone(), v: b.vel.clone(), w: b.spin.clone(),
    invI: 1 / (0.4 * b.radius * b.radius), still: 0, asleep: false, b,
  }));
  const tracks: Track[] = bodies.map(() => ({ frames: new Float32Array(Math.ceil(steps / RECORD_EVERY + 2) * 7), count: 0 }));
  const record = (i: number) => {
    const s = states[i]!;
    const t = tracks[i]!;
    t.frames.set([s.x.x, s.x.y, s.x.z, s.q.x, s.q.y, s.q.z, s.q.w], t.count * 7);
    t.count++;
  };
  states.forEach((_, i) => record(i));
  for (let step = 1; step <= steps; step++) {
    let awake = 0;
    for (const s of states) {
      if (s.asleep) continue;
      awake++;
      s.v.y -= g * STEP;
      // the ground: every hull point below the table top pushes back (normal impulse, then friction)
      let deepest = 0;
      let touching = false;
      for (const local of s.b.verts) {
        const r = tmp.r.copy(local).applyQuaternion(s.q);
        const y = s.x.y + r.y;
        if (y >= 0) continue;
        touching = true;
        deepest = Math.min(deepest, y);
        const u = pointVel(s, r, tmp.u);
        const vn = u.y;
        if (vn >= 0) continue;
        const rxn = tmp.p.copy(r).cross(UP);
        const k = 1 + rxn.lengthSq() * s.invI;
        const jn = (-(1 + RESTITUTION) * vn) / k;
        impulse(s, r, tmp.t.set(0, jn, 0));
        // friction against the sliding direction, bounded by the normal impulse (Coulomb)
        const ut = pointVel(s, r, tmp.u).setY(0);
        const speed = ut.length();
        if (speed > 1e-5) {
          const dir = ut.divideScalar(speed);
          const rxt = tmp.p.copy(r).cross(dir);
          const kt = 1 + rxt.lengthSq() * s.invI;
          const jt = Math.min(FRICTION * jn, speed / kt);
          impulse(s, r, dir.multiplyScalar(-jt));
        }
      }
      if (deepest < 0) s.x.y -= deepest * 0.85;
      if (touching) {
        // rolling resistance: felt and wood soak up a little spin every step
        s.w.multiplyScalar(0.992);
        s.v.multiplyScalar(0.998);
      }
      // the table's edges
      const { minX, maxX, minZ, maxZ } = opts.bounds;
      const rad = s.b.radius;
      if (s.x.x < minX + rad && s.v.x < 0) s.v.x *= -WALL_BOUNCE;
      if (s.x.x > maxX - rad && s.v.x > 0) s.v.x *= -WALL_BOUNCE;
      if (s.x.z < minZ + rad && s.v.z < 0) s.v.z *= -WALL_BOUNCE;
      if (s.x.z > maxZ - rad && s.v.z > 0) s.v.z *= -WALL_BOUNCE;
      // integrate
      s.x.addScaledVector(s.v, STEP);
      const wl = s.w.length();
      if (wl > 1e-6) {
        tmp.dq.setFromAxisAngle(tmp.t.copy(s.w).divideScalar(wl), wl * STEP);
        s.q.premultiply(tmp.dq).normalize();
      }
      // asleep once it has sat still on the table for a moment
      s.still = touching && s.v.lengthSq() < 0.0025 && s.w.lengthSq() < 0.04 ? s.still + 1 : 0;
      if (s.still > 40) s.asleep = true;
    }
    // knocks between dice (as spheres): push apart and trade the closing speed
    for (let i = 0; i < states.length; i++) {
      for (let j = i + 1; j < states.length; j++) {
        const a = states[i]!, b = states[j]!;
        const d = tmp.p.copy(b.x).sub(a.x);
        const min = (a.b.radius + b.b.radius) * 0.82;
        const dist = d.length();
        if (dist >= min || dist < 1e-6) continue;
        const n = d.divideScalar(dist);
        const push = (min - dist) / 2;
        a.x.addScaledVector(n, -push);
        b.x.addScaledVector(n, push);
        const closing = tmp.u.copy(a.v).sub(b.v).dot(n);
        if (closing > 0) {
          const j = closing * (1 + RESTITUTION) / 2;
          a.v.addScaledVector(n, -j);
          b.v.addScaledVector(n, j);
          a.asleep = b.asleep = false;
          a.still = b.still = 0;
        }
      }
    }
    if (step % RECORD_EVERY === 0) states.forEach((_, i) => record(i));
    if (!awake) break;
  }
  states.forEach((_, i) => record(i));
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
