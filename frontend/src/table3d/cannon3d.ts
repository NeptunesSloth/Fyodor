/**
 * -- table toys -- the dice cannon on the 3D table (game/cannon.ts plans it; table3d/dice.ts throws its dice). A small
 * brass naval cannon on an oak carriage, built here from lathe and box shapes (no model files: offline, ~2.2k triangles,
 * five draw calls). It isn't on the table: when someone fires it, it rolls in from the table's edge to the end of the
 * aisle (off every mat), swings round to aim, fires each volley with a kick and a puff of smoke, and rolls back off once the
 * dice are on their way. Reduced motion and low graphics never show it (just the dice, at rest). Stepped from the table's
 * own frame loop (one rAF owner); the table's animation speed scales it, exactly as it scales the dice it fires.
 */
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { CANNON_MS, fireTimes, tagLabel, volleyCount, volleys } from "../game/cannon";
import { diceClock, type DiceShow } from "../game/dice";
import { cannonBoom } from "../game/diceSound";
import type { GameView } from "../types/game";
import type { DiceTray } from "./dice";
import { rollerEnv } from "./diceEnv";
import { cannonEnv, cannonLaunch } from "./diceThrow";
import type { Seat } from "./layout";

/** The barrel's elevation and size, the pivot it turns on (carriage frame: +z is where it points, y up). */
const ELEVATION = 0.42;
const BARREL = 1.75;
const PIVOT = new THREE.Vector3(0, 0.62, -0.1);
const WHEEL_R = 0.36;
const WHEEL_X = 0.36;

export interface CannonShot {
  /** Ms of show time after the run starts (the dice of this volley leave the muzzle then). */
  at: number;
  /** Where it aims (world): the middle of the mats this volley is fired at. */
  aim: THREE.Vector3;
}

export interface CannonRun {
  /** Where it stands to fire (world, on the table), and the table's edge it rolls in from and back off to. */
  spot: THREE.Vector3;
  edge: THREE.Vector3;
  shots: CannonShot[];
  /** When it starts rolling back off (ms of show time). */
  leave: number;
  started: number;
}

interface Puff { sprite: THREE.Sprite; at: number; dir: THREE.Vector3; base: THREE.Vector3; flash: boolean }

let smokeTex: THREE.Texture | null = null;
function smokeTexture(): THREE.Texture {
  if (smokeTex) return smokeTex;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
  grad.addColorStop(0, "rgba(255,255,255,0.95)");
  grad.addColorStop(0.45, "rgba(235,232,226,0.55)");
  grad.addColorStop(1, "rgba(220,216,210,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  smokeTex = new THREE.CanvasTexture(c);
  smokeTex.colorSpace = THREE.SRGBColorSpace;
  return smokeTex;
}

const ease = (k: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, k)), 3);
const easeIn = (k: number) => Math.pow(Math.min(1, Math.max(0, k)), 2);
/** Turning toward a point: the yaw that points the carriage's +z at it. */
const yawToward = (from: THREE.Vector3, to: THREE.Vector3) => Math.atan2(to.x - from.x, to.z - from.z);
const lerpAngle = (a: number, b: number, k: number) => a + (Math.atan2(Math.sin(b - a), Math.cos(b - a))) * k;

/** The brass barrel: breech knob, reinforce rings and a swelled muzzle with its bore, turned on a lathe along +y. */
function barrelGeometry(): THREE.BufferGeometry {
  const pts: [number, number][] = [
    [0, -0.3], [0.05, -0.29], [0.075, -0.24], [0.05, -0.2], [0.06, -0.15], [0.16, -0.12], [0.205, -0.06], [0.215, 0],
    [0.235, 0.02], [0.235, 0.07], [0.205, 0.09], [0.195, 0.55], [0.215, 0.57], [0.215, 0.62], [0.18, 0.64], [0.165, 1.2],
    [0.18, 1.22], [0.18, 1.26], [0.15, 1.28], [0.14, BARREL - 0.12], [0.175, BARREL - 0.07], [0.19, BARREL - 0.02],
    [0.17, BARREL], [0.09, BARREL], [0.085, BARREL - 0.25], [0, BARREL - 0.26],
  ];
  const lathe = new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(r, y)), 22);
  // trunnions: the pins it pivots on
  const pin = new THREE.CylinderGeometry(0.07, 0.07, 0.62, 12).rotateZ(Math.PI / 2).translate(0, 0.42, 0);
  const g = mergeGeometries([lathe.toNonIndexed(), pin.toNonIndexed()])!;
  lathe.dispose();
  pin.dispose();
  g.rotateX(Math.PI / 2); // along +z
  return g;
}

/** The oak carriage: two cheeks stepped up to the trunnions, a bed and the axle. */
function carriageGeometry(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  for (const side of [-1, 1]) {
    parts.push(new THREE.BoxGeometry(0.1, 0.34, 1.0).translate(side * 0.26, 0.42, -0.2));
    parts.push(new THREE.BoxGeometry(0.1, 0.16, 0.42).translate(side * 0.26, 0.62, 0.02));
  }
  parts.push(new THREE.BoxGeometry(0.5, 0.08, 1.0).translate(0, 0.28, -0.2));
  parts.push(new THREE.CylinderGeometry(0.05, 0.05, WHEEL_X * 2 + 0.12, 10).rotateZ(Math.PI / 2).translate(0, WHEEL_R, 0.05));
  parts.push(new THREE.CylinderGeometry(0.045, 0.045, WHEEL_X * 2 + 0.12, 10).rotateZ(Math.PI / 2).translate(0, WHEEL_R * 0.75, -0.62));
  const g = mergeGeometries(parts.map((p) => p.toNonIndexed()))!;
  parts.forEach((p) => p.dispose());
  return g;
}

/** A spoked wheel with an iron tyre, about the x axis. */
function wheelGeometry(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [new THREE.TorusGeometry(WHEEL_R - 0.03, 0.035, 6, 26).rotateY(Math.PI / 2)];
  parts.push(new THREE.CylinderGeometry(0.075, 0.075, 0.12, 12).rotateZ(Math.PI / 2));
  for (let i = 0; i < 6; i++) parts.push(new THREE.BoxGeometry(0.035, WHEEL_R * 2 - 0.08, 0.04).rotateX((i * Math.PI) / 6));
  const g = mergeGeometries(parts.map((p) => p.toNonIndexed()))!;
  parts.forEach((p) => p.dispose());
  return g;
}

export class CannonRig {
  readonly group = new THREE.Group();
  private carriage = new THREE.Group();
  private pivot = new THREE.Group();
  private barrel: THREE.Mesh;
  private wheels: THREE.Mesh[] = [];
  private shadow: THREE.Mesh;
  private puffs: Puff[] = [];
  private disposables: { dispose(): void }[] = [];
  private run: CannonRun | null = null;
  private fired = 0;
  private yaw = 0;
  private rolled = 0;
  private last = new THREE.Vector3();
  private tmp = new THREE.Vector3();

  constructor(envMap: THREE.Texture | null, shadows: boolean) {
    const brass = this.keep(new THREE.MeshStandardMaterial({ color: "#b98a3e", metalness: 1, roughness: 0.3, envMap, envMapIntensity: 1.4 }));
    const oak = this.keep(new THREE.MeshStandardMaterial({ color: "#5a3a22", roughness: 0.72, metalness: 0 }));
    const iron = this.keep(new THREE.MeshStandardMaterial({ color: "#3b2a1c", roughness: 0.6, metalness: 0.25 }));
    this.barrel = new THREE.Mesh(this.keep(barrelGeometry()), brass);
    this.pivot.position.copy(PIVOT);
    this.pivot.rotation.x = -ELEVATION;
    this.pivot.add(this.barrel);
    const body = new THREE.Mesh(this.keep(carriageGeometry()), oak);
    const wheel = this.keep(wheelGeometry());
    for (const side of [-1, 1]) {
      const w = new THREE.Mesh(wheel, iron);
      w.position.set(side * WHEEL_X, WHEEL_R, 0.05);
      this.wheels.push(w);
    }
    for (const m of [this.barrel, body, ...this.wheels]) m.castShadow = shadows;
    this.carriage.add(body, this.pivot, ...this.wheels);
    // a soft contact shadow on the felt
    const blob = document.createElement("canvas");
    blob.width = blob.height = 64;
    const g = blob.getContext("2d")!;
    const grad = g.createRadialGradient(32, 32, 2, 32, 32, 31);
    grad.addColorStop(0, "rgba(0,0,0,0.55)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    this.shadow = new THREE.Mesh(this.keep(new THREE.PlaneGeometry(1.3, 1.9).rotateX(-Math.PI / 2)),
      this.keep(new THREE.MeshBasicMaterial({ map: this.keep(new THREE.CanvasTexture(blob)), transparent: true, depthWrite: false })));
    this.shadow.position.set(0, 0.005, -0.15);
    this.shadow.renderOrder = 1;
    this.carriage.add(this.shadow);
    this.group.add(this.carriage);
    this.group.visible = false;
  }

  private keep<T extends { dispose(): void }>(x: T): T {
    this.disposables.push(x);
    return x;
  }

  /** The muzzle (world) with the carriage at `spot`, aimed at `aim`: where the volley's dice leave from. */
  muzzle(spot: THREE.Vector3, aim: THREE.Vector3): THREE.Vector3 {
    const yaw = yawToward(spot, aim);
    const along = new THREE.Vector3(0, Math.sin(ELEVATION), Math.cos(ELEVATION)).multiplyScalar(BARREL);
    const local = PIVOT.clone().add(along).applyAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    this.group.updateWorldMatrix(true, false);
    return this.group.localToWorld(local.add(spot));
  }

  /** Roll in, fire each volley, roll off (replaces a run still going). */
  fire(run: CannonRun): void {
    this.clearPuffs();
    this.run = run;
    this.fired = 0;
    this.yaw = yawToward(run.edge, run.spot);
    this.carriage.position.copy(run.edge);
    this.last.copy(run.edge);
    this.group.visible = true;
  }

  /** Is it on the table (tests and diagnostics)? */
  get busy(): boolean {
    return this.run !== null;
  }

  /** Step it (ms clock, the table's animation speed; the dice's test clock freezes it too): true while it moves. */
  update(now: number, speed: number): boolean {
    const r = this.run;
    if (!r) return false;
    const t = diceClock.frozen ?? (now - r.started) * Math.max(0.25, speed);
    this.stepPuffs(t);
    const pos = this.carriage.position;
    let yaw = this.yaw;
    const out = t - r.leave;
    if (t < CANNON_MS.rollIn) {
      pos.lerpVectors(r.edge, r.spot, ease(t / CANNON_MS.rollIn));
    } else if (out < 0) {
      pos.copy(r.spot);
      // swing round to aim at each volley just before it fires (on the clock, so it points where the dice leave from), and
      // kick back as it fires
      const i = r.shots.findIndex((s) => s.at >= t);
      const n = i < 0 ? r.shots.length - 1 : i;
      const from = n === 0 ? yawToward(r.edge, r.spot) : yawToward(r.spot, r.shots[n - 1]!.aim);
      const to = yawToward(r.spot, r.shots[n]!.aim);
      yaw = lerpAngle(from, to, i < 0 ? 1 : ease((t - (r.shots[n]!.at - CANNON_MS.aim)) / CANNON_MS.aim));
      while (this.fired < r.shots.length && t >= r.shots[this.fired]!.at) {
        this.shoot(r.spot, r.shots[this.fired++]!);
      }
      const since = this.fired ? t - r.shots[this.fired - 1]!.at : Infinity;
      const kick = since < 60 ? since / 60 : Math.exp(-(since - 60) / 160);
      this.barrel.position.z = -0.22 * kick;
      pos.add(this.tmp.set(-Math.sin(yaw), 0, -Math.cos(yaw)).multiplyScalar(0.1 * kick));
    } else if (out < CANNON_MS.rollOut) {
      this.barrel.position.z = 0;
      const last = yawToward(r.spot, r.shots[r.shots.length - 1]!.aim);
      yaw = lerpAngle(last, yawToward(r.edge, r.spot), ease(out / (CANNON_MS.rollOut * 0.4)));
      pos.lerpVectors(r.spot, r.edge, easeIn(out / CANNON_MS.rollOut));
    } else {
      this.run = null;
      this.group.visible = false;
      this.clearPuffs();
      return false;
    }
    this.yaw = yaw;
    this.carriage.rotation.y = yaw;
    // the wheels turn as far as it rolled (backwards when it rolls back)
    const step = this.tmp.subVectors(pos, this.last);
    const dir = Math.sign(step.x * Math.sin(yaw) + step.z * Math.cos(yaw)) || 1;
    this.rolled += (dir * step.length()) / WHEEL_R;
    this.last.copy(pos);
    for (const w of this.wheels) w.rotation.x = this.rolled;
    return true;
  }

  /** A volley fired at `at` (show time): the puff of smoke (and its flash) from the muzzle, and the pop. */
  private shoot(spot: THREE.Vector3, shot: CannonShot): void {
    const at = shot.at;
    // from the muzzle aimed as it fires (where the volley's dice leave from), along the barrel
    const base = this.group.worldToLocal(this.muzzle(spot, shot.aim));
    const yaw = yawToward(spot, shot.aim);
    const local = new THREE.Vector3(Math.sin(yaw) * Math.cos(ELEVATION), Math.sin(ELEVATION), Math.cos(yaw) * Math.cos(ELEVATION));
    base.addScaledVector(local, 0.08);
    for (let i = 0; i < 5; i++) {
      const flash = i === 0;
      const m = new THREE.SpriteMaterial({
        map: smokeTexture(), transparent: true, depthWrite: false, color: flash ? "#ffb24a" : "#e9e4dc",
        blending: flash ? THREE.AdditiveBlending : THREE.NormalBlending, opacity: 0,
      });
      const sprite = new THREE.Sprite(m);
      sprite.position.copy(base);
      sprite.renderOrder = 3;
      this.group.add(sprite);
      const spread = new THREE.Vector3((i % 2 ? 1 : -1) * 0.12 * i, 0.08 * i, 0.1 * i);
      this.puffs.push({ sprite, at: at + i * 25, dir: local.clone().multiplyScalar(0.5 + i * 0.22).add(spread), base: base.clone(), flash });
    }
    if (diceClock.frozen === null) cannonBoom();
  }

  private stepPuffs(t: number): void {
    for (const p of [...this.puffs]) {
      const age = t - p.at;
      const life = p.flash ? 140 : 1100;
      const k = age / life;
      const m = p.sprite.material;
      if (k >= 1) {
        this.group.remove(p.sprite);
        m.dispose();
        this.puffs = this.puffs.filter((x) => x !== p);
        continue;
      }
      if (age < 0) continue;
      const grow = ease(k);
      p.sprite.position.copy(p.base).addScaledVector(p.dir, grow).add(this.tmp.set(0, 0.35 * k, 0));
      p.sprite.scale.setScalar(p.flash ? 0.55 + 0.4 * k : 0.25 + 1.05 * grow);
      m.opacity = p.flash ? 0.9 * (1 - k) : 0.75 * Math.min(1, age / 60) * (1 - k);
    }
  }

  private clearPuffs(): void {
    for (const p of this.puffs) {
      this.group.remove(p.sprite);
      p.sprite.material.dispose();
    }
    this.puffs = [];
  }

  dispose(): void {
    this.clearPuffs();
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.group.clear();
  }
}

/** The cannon's place on this table: the end of the aisle (off every mat), and the table's edge beyond it (world). */
export function cannonSpot(tableWidth: number): { spot: THREE.Vector3; edge: THREE.Vector3 } {
  return { spot: new THREE.Vector3(tableWidth / 2 - 1.5, 0, 0), edge: new THREE.Vector3(tableWidth / 2 + 1.6, 0, 0) };
}

/**
 * Fire a cannon show on a table (the 3D table; the 2D table's overlay has its own frames: game/DiceLayer.tsx): each volley's
 * dice thrown in front of their players (table3d/diceThrow.ts cannonEnv), the re-fires of a tie after the dice before them
 * land, and the cannon rolled in to fire them (`rig`; null: reduced motion or low graphics, only the results). `still`: no
 * physics (low graphics). Returns when each volley fires (ms of show time; tests and diagnostics).
 */
export function fireCannon(o: {
  show: DiceShow; tray: DiceTray; rig: CannonRig | null; seats: Seat[]; view: GameView | null; tableWidth: number; still: boolean; now: number;
}): number[] {
  const { show, tray, rig, seats: all, view } = o;
  const vols = volleys(show);
  if (!vols.length) return [];
  const mode = show.cannon?.mode ?? "volley";
  const player = (pid: string | null) => view?.players.find((p) => p.id === pid);
  for (const v of vols) tray.clear(v.player); // (their last dice make way, as when they roll again)
  const { spot, edge } = cannonSpot(o.tableWidth);
  const shots: CannonShot[] = [];
  const times = fireTimes(volleyCount(show), (round, firedAt) => {
    const group = vols.filter((v) => v.round === round);
    const seats = group.map((v) => all.find((s) => s.player === v.player)).filter((s): s is Seat => !!s);
    const aim = seats.reduce((a, s) => a.add(new THREE.Vector3(s.x, 0, s.z)), new THREE.Vector3()).divideScalar(Math.max(1, seats.length));
    const from = rig ? rig.muzzle(spot, aim) : null;
    let landed = firedAt;
    for (const v of group) {
      const seat = all.find((s) => s.player === v.player);
      if (!seat) continue;
      const who = player(v.player);
      const color = (mode === "first" ? who?.color : player(show.actor)?.color) ?? "#d7ae63";
      const { settles } = tray.throw(v.show, color, who?.name ?? "", { x: seat.x, z: seat.z, rotY: seat.rot }, cannonEnv(rollerEnv(view, v.player).obstacles, round), o.now, {
        launcher: cannonLaunch, from, delay: rig ? firedAt : 0, tag: tagLabel(v.tag), still: o.still,
      });
      landed = Math.max(landed, settles);
    }
    shots.push({ at: firedAt, aim });
    return landed;
  });
  rig?.fire({ spot, edge, shots, leave: times[times.length - 1]! + CANNON_MS.linger, started: o.now });
  return times;
}
