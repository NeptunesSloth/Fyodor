/**
 * One roll, thrown (pure: no DOM, no WebGL; unit-tested). The roll's dice leave the roller's hand above the near
 * edge of their mat, arc across it and tumble to rest on its far half, knocking each other and glancing off the
 * roller's decks. Everything happens in the roller's own mat frame (x to their right, z toward them, the mat centred
 * on the origin, 10 × 6), against an environment every screen builds the same way, seeded by the roll: every screen
 * sees the same throw, wherever it sits at the table, and the 2D table can land the very same throw on its mat.
 *
 * A die that ends cocked (leaning on a deck or another die) or off the roller's side is thrown again with the next
 * seed; in the rare case none of a few throws is clean, the last frames ease it flat. Then each die is turned by the
 * symmetry that shows the server's number on top (table3d/diceGeometry.ts faceTurn).
 */
import * as THREE from "three";
import { DICE_SHOWN, type DiceShow } from "../game/dice";
import { COIN_RADIUS, COIN_THICK, coinTurn, dieSolid, faceText, faceTurn, kindsFor, percentile, tilt, topFace, topPoint, type DieKind } from "./diceGeometry";
import { poseAt, randomAxis, randomRotation, restSeconds, seeded, simulate, trackSeconds, FRAMES_PER_SECOND, type BodyInit, type Impact, type Obstacle, type Track } from "./physics";

/** Where a throw happens, in the roller's mat frame. */
export interface ThrowEnv {
  bounds: { minX: number; maxX: number; minZ: number; maxZ: number };
  obstacles: Obstacle[];
  /** The hand: the dice leave from around here (y is the height), aimed at the middle of `land`. */
  hand: THREE.Vector3;
  /** Where the dice should come to rest (they may roll a little past). */
  land: { minX: number; maxX: number; minZ: number; maxZ: number };
  /** A die resting outside this is thrown again. */
  keep: { minX: number; maxX: number; minZ: number; maxZ: number };
}

/** The live table: the roller's mat (10 × 6) and the table round it, the same on every screen. */
export function tableEnv(piles: Obstacle[] = []): ThrowEnv {
  return {
    // the table's own rail behind the roller and at the row's ends; across the aisle the other row (never reached)
    bounds: { minX: -7.7, maxX: 7.7, minZ: -14, maxZ: 4.4 },
    obstacles: piles,
    hand: new THREE.Vector3(0.9, 1.25, 3.7),
    land: { minX: -2.2, maxX: 2.6, minZ: -1.9, maxZ: 0.3 },
    // on the roller's own mat: not in the aisle (the plaques, the stack) nor, on the 2D table, the next mat
    keep: { minX: -4.8, maxX: 4.8, minZ: -2.8, maxZ: 2.9 },
  };
}

export interface ThrownDie {
  kind: DieKind;
  /** The face value shown on top (a d10's 0 for a 10; the tens die's 0–9). */
  face: number;
  /** What the chip says ("7", "00", "H"). */
  label: string;
  /** Index into the roll's results. */
  result: number;
  ignored: boolean;
  /** A d20's natural 20 or 1 (kept dice only). */
  crit: "high" | "low" | null;
  track: Track;
  /** The symmetry the visual mesh is turned by (body × turn). */
  turn: THREE.Quaternion;
  /** Seconds until it came to rest. */
  rest: number;
}

export interface Thrown { dice: ThrownDie[]; impacts: Impact[]; seconds: number; attempts: number; snapped: number }

export interface Spec { kind: DieKind; face: number; label: string; result: number; ignored: boolean; crit: ThrownDie["crit"]; heads?: boolean }

/** The dice a roll is thrown with: one per result (a d100 result is two), the first DICE_SHOWN. */
export function diceOf(show: Pick<DiceShow, "sides" | "results" | "coin" | "ignored">): Spec[] {
  const ignored = new Set(show.ignored ?? []);
  const out: Spec[] = [];
  show.results.forEach((v, i) => {
    const kinds = kindsFor(show.sides, show.coin);
    const skip = ignored.has(i);
    if (kinds[0] === "coin") {
      const heads = show.coin ? !!v : v === 2;
      out.push({ kind: "coin", face: heads ? 1 : 0, label: show.coin ? (heads ? "H" : "T") : String(v), result: i, ignored: skip, crit: null, heads });
    } else if (kinds.length === 2) {
      const [t, u] = percentile(v);
      out.push({ kind: "d10x10", face: t, label: faceText("d10x10", t), result: i, ignored: skip, crit: null });
      out.push({ kind: "d10", face: u, label: String(u), result: i, ignored: skip, crit: null });
    } else {
      const kind = kinds[0]!;
      const face = kind === "d10" ? v % 10 : v;
      const crit = kind === "d20" && !skip ? (v === 20 ? "high" : v === 1 ? "low" : null) : null;
      out.push({ kind, face, label: String(v), result: i, ignored: skip, crit });
    }
  });
  return out.slice(0, DICE_SHOWN);
}

const radiusOf = (k: DieKind) => (k === "coin" ? COIN_RADIUS : dieSolid(k).radius);

/** Per kind: how quickly the felt takes a die's roll (rounder dice roll on further without it). */
export const DAMPING: Record<DieKind, [number, number]> = {
  d4: [0.12, 0.2], d6: [0.12, 0.24], d3: [0.12, 0.24], d8: [0.14, 0.3], d10: [0.16, 0.36], d10x10: [0.16, 0.36],
  d12: [0.22, 0.55], d20: [0.22, 0.5], dx: [0.22, 0.5], coin: [0.25, 0.3],
};
/** Per kind: how much of the way to its spot a die flies before it lands and rolls on (a d4 hardly rolls, a d20 does). */
export const CARRY: Record<DieKind, number> = {
  d4: 1.05, d6: 0.85, d3: 0.85, d8: 0.82, d10: 0.75, d10x10: 0.75, d12: 0.66, d20: 0.66, dx: 0.66, coin: 0.62,
};

function bodyOf(spec: Spec, pos: THREE.Vector3, vel: THREE.Vector3, spin: THREE.Vector3, rot: THREE.Quaternion): BodyInit {
  const [linearDamping, angularDamping] = DAMPING[spec.kind];
  if (spec.kind === "coin") {
    return { verts: [], cylinder: { radius: COIN_RADIUS, height: COIN_THICK }, radius: COIN_RADIUS, pos, vel, spin, rot, linearDamping, angularDamping };
  }
  const s = dieSolid(spec.kind);
  return { verts: s.verts, faces: s.polys, radius: s.radius, pos, vel, spin, rot, linearDamping, angularDamping };
}

/**
 * The dice leaving the hand: a loose clump round the hand (never touching), all thrown together toward a spot in the
 * landing area with a little scatter each, tumbling forward. They land in a clump and knock each other apart.
 */
export function launch(specs: Spec[], env: ThrowEnv, key: string): BodyInit[] {
  const rnd = seeded(key);
  const n = specs.length;
  const r = Math.max(...specs.map((s) => radiusOf(s.kind)));
  const gap = r * 2.08;
  // the clump: up to four across, then a layer above, then one further back
  const across = Math.min(n, n > 6 ? 4 : 3);
  const land = env.land;
  const aim = new THREE.Vector3(
    land.minX + (land.maxX - land.minX) * (0.3 + rnd() * 0.4),
    0,
    land.minZ + (land.maxZ - land.minZ) * (0.25 + rnd() * 0.5),
  );
  const flight = 0.3 + rnd() * 0.06;
  const carry = LAUNCH.carry * Math.min(...specs.map((s) => CARRY[s.kind]));
  const base = new THREE.Vector3((aim.x - env.hand.x) * carry / flight, 0, (aim.z - env.hand.z) * carry / flight);
  const fwd = new THREE.Vector3(base.z, 0, -base.x).normalize();
  return specs.map((spec, i) => {
    const layer = Math.floor(i / (across * 2));
    const inLayer = i % (across * 2);
    const row = Math.floor(inLayer / across);
    const col = (inLayer % across) - (Math.min(across, n - layer * across * 2 - row * across) - 1) / 2;
    const pos = new THREE.Vector3(
      env.hand.x + col * gap + (rnd() - 0.5) * 0.08,
      env.hand.y + layer * gap + (rnd() - 0.5) * 0.08,
      env.hand.z - row * gap + (rnd() - 0.5) * 0.08,
    );
    const vel = base.clone();
    vel.x += (rnd() - 0.5) * 1.6 + col * 0.35;
    vel.z += (rnd() - 0.5) * 1.2;
    vel.y = 1.0 + rnd() * 1.4;
    const coin = spec.kind === "coin";
    // dice spin about a random axis, mostly tumbling forward; a coin flips end over end
    const axis = coin ? new THREE.Vector3(fwd.x, (rnd() - 0.5) * 0.3, fwd.z).normalize() : fwd.clone().multiplyScalar(0.7).add(randomAxis(rnd).multiplyScalar(0.6)).normalize();
    const spin = axis.multiplyScalar(coin ? 16 + rnd() * 6 : 12 + rnd() * 9);
    return bodyOf(spec, pos, vel, spin, randomRotation(rnd));
  });
}

export interface Check { ok: boolean; flat: boolean; onTable: boolean; inside: boolean }

/** Did each die come to rest flat on the table, on the roller's side? */
export function judge(specs: Spec[], tracks: Track[], env: ThrowEnv): Check[] {
  const p = new THREE.Vector3();
  const q = new THREE.Quaternion();
  return specs.map((spec, i) => {
    const t = tracks[i]!;
    poseAt(t, t.count - 1, p, q);
    let flat: boolean, height: number;
    if (spec.kind === "coin") {
      flat = Math.abs(new THREE.Vector3(0, 1, 0).applyQuaternion(q).y) > 0.9985;
      height = COIN_THICK / 2;
    } else {
      const s = dieSolid(spec.kind);
      flat = tilt(s, q) < 0.0015;
      height = s.inradius;
    }
    // on the felt, or lying on a card (never on a deck, another die or tipped up against one)
    const onTable = p.y - height > -0.02 && p.y - height < 0.12;
    const k = env.keep;
    const inside = p.x > k.minX && p.x < k.maxX && p.z > k.minZ && p.z < k.maxZ;
    return { ok: flat && onTable && inside && t.settled, flat, onTable, inside };
  });
}

/** Ease a die that didn't come to rest cleanly flat onto the table over its last few frames. */
function settle(spec: Spec, track: Track, env: ThrowEnv): Track {
  const p = new THREE.Vector3();
  const q = new THREE.Quaternion();
  poseAt(track, track.count - 1, p, q);
  let height: number, flatQ: THREE.Quaternion;
  if (spec.kind === "coin") {
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
    flatQ = new THREE.Quaternion().setFromUnitVectors(up, new THREE.Vector3(0, Math.sign(up.y) || 1, 0)).multiply(q);
    height = COIN_THICK / 2;
  } else {
    const s = dieSolid(spec.kind);
    const down = s.faces.map((f) => f.normal.clone().applyQuaternion(q)).reduce((a, b) => (b.y < a.y ? b : a));
    flatQ = new THREE.Quaternion().setFromUnitVectors(down, new THREE.Vector3(0, -1, 0)).multiply(q);
    height = s.inradius;
  }
  const k = env.keep;
  const end = new THREE.Vector3(Math.max(k.minX + 0.5, Math.min(k.maxX - 0.5, p.x)), height, Math.max(k.minZ + 0.5, Math.min(k.maxZ - 0.5, p.z)));
  const extra = Math.round(0.28 * FRAMES_PER_SECOND);
  const frames = new Float32Array((track.count + extra) * 7);
  frames.set(track.frames.subarray(0, track.count * 7));
  const pp = new THREE.Vector3();
  const qq = new THREE.Quaternion();
  for (let i = 1; i <= extra; i++) {
    const k2 = i / extra;
    const e = k2 * k2 * (3 - 2 * k2);
    pp.copy(p).lerp(end, e);
    pp.y += Math.sin(Math.PI * k2) * 0.12; // a small hop as it drops flat
    qq.copy(q).slerp(flatQ, e);
    frames.set([pp.x, pp.y, pp.z, qq.x, qq.y, qq.z, qq.w], (track.count - 1 + i) * 7);
  }
  return { frames, count: track.count + extra, rest: track.count + extra - 1, settled: true };
}

const ATTEMPTS = 6;
/** How much of the way to its spot a die flies before it lands and rolls (tuned with the physics). */
export const LAUNCH = { carry: 1 };

/** Throw a roll's dice in `env`: the same tracks for the same roll on every screen. */
export function throwRoll(show: Pick<DiceShow, "key" | "sides" | "results" | "coin" | "ignored">, env: ThrowEnv): Thrown {
  const specs = diceOf(show);
  let best: { tracks: Track[]; impacts: Impact[]; checks: Check[]; seconds: number } | null = null;
  let attempts = 0;
  // a big throw is costly to simulate again: fewer tries, and a die that still ends cocked is eased flat
  const tries = specs.length <= 3 ? ATTEMPTS : specs.length <= 6 ? 3 : 1;
  for (let a = 0; a < tries; a++) {
    attempts++;
    const bodies = launch(specs, env, a ? `${show.key}#${a}` : show.key);
    const sim = simulate(bodies, { bounds: env.bounds, obstacles: env.obstacles, maxSeconds: 3.6 });
    const checks = judge(specs, sim.tracks, env);
    const bad = checks.filter((c) => !c.ok).length;
    if (!best || bad < best.checks.filter((c) => !c.ok).length) best = { ...sim, checks };
    if (!bad) break;
  }
  const { impacts, checks } = best!;
  let snapped = 0;
  const tracks = best!.tracks.map((t, i) => {
    if (checks[i]!.ok) return t;
    snapped++;
    return settle(specs[i]!, t, env);
  });
  const p = new THREE.Vector3();
  const q = new THREE.Quaternion();
  const dice: ThrownDie[] = specs.map((spec, i) => {
    const track = tracks[i]!;
    poseAt(track, track.count - 1, p, q);
    let turn: THREE.Quaternion;
    if (spec.kind === "coin") turn = coinTurn(q, !!spec.heads);
    else {
      const s = dieSolid(spec.kind);
      turn = faceTurn(s, spec.kind === "d4" ? topPoint(s, q) : topFace(s, q), spec.face);
    }
    const { heads: _h, ...rest } = spec;
    return { ...rest, track, turn, rest: restSeconds(track) };
  });
  return { dice, impacts, seconds: Math.max(...tracks.map(trackSeconds)), attempts, snapped };
}
