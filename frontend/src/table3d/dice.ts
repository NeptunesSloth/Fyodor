/**
 * The thrown dice (game/dice.ts feeds them): real dice (table3d/diceGeometry.ts) with engraved, inked numbers
 * (diceArt.ts) in the roller's seat colour and the player's chosen look (diceLook.ts), thrown for real by cannon-es
 * (diceThrow.ts, physics.ts) from the roller's seat across their mat. The server's number is what lands on top: each
 * die is drawn turned by the symmetry of its solid that brings that number's face onto the face the physics landed.
 *
 * A tray holds any number of throws, each in its own frame (the roller's mat on the 3D table, a mat on the 2D table's
 * overlay, the toy tray). Dice cast real shadows where the renderer has them, plus a soft contact shadow; a d20's
 * natural 20 or 1 gets a thin ring on the table; the ignored dice of a "roll one more and ignore the lowest" are
 * greyed. Impacts make their sound as the throw reaches them. Landed dice stay until cleared (`dismiss`, `clear`).
 * Geometry, atlases and materials are cached and disposed with the last tray.
 */
import * as THREE from "three";
import { diceClock, natural, rollLine, type DiceShow } from "../game/dice";
import { diceClack, diceSettle } from "../game/diceSound";
import { coinAtlas, coinGeometry, dieAtlas, disposeDiceArt } from "./diceArt";
import { COIN_RADIUS, COIN_THICK, dieSolid, disposeSolids, type DieKind } from "./diceGeometry";
import { coinMaterial, diceMaterial, type DiceLook } from "./diceLook";
import type { HudThrow } from "./diceHud";
import { placeRoll, prefixTrack, throwRoll, type Launcher, type ThrowEnv, type ThrownDie } from "./diceThrow";
import { FRAMES_PER_SECOND, poseLerp } from "./physics";
import { flightSeconds } from "../game/cannon";

export type { ThrowEnv } from "./diceThrow";

/** Where a throw's mat frame sits in the world: x to the roller's right, z toward them (see diceThrow.ts). */
export interface ThrowFrame { x: number; z: number; rotY: number; scale?: number }

/**
 * -- table toys -- a throw that doesn't leave the roller's hand (game/cannon.ts): dice fired from the dice cannon fly from
 * `from` (the muzzle, world coordinates) and drop in (`launcher`), fired `delay` ms after the throw is made; or, on low
 * graphics, lie `still` with no physics. `line` and `tag` say what the throw was for ("Goes first").
 */
export interface ThrowOptions {
  launcher?: Launcher;
  from?: THREE.Vector3 | null;
  delay?: number;
  line?: string;
  tag?: string | null;
  still?: boolean;
}

export interface TrayOptions {
  look: DiceLook;
  /** Reflections for the glossy looks (the scene's environment). */
  envMap: THREE.Texture | null;
  shadows: boolean;
  /** Edge segments of the rounded dice. */
  segments?: number;
  /** Play impact sounds (the live table and the overlay; the toy tray too). */
  sound?: boolean;
  /** Reflection strength (a brighter environment wants less). */
  envIntensity?: number;
}

interface LiveDie { spec: ThrownDie; mesh: THREE.Mesh; blob: THREE.Mesh; ring: THREE.Mesh | null; radius: number; height: number }
interface LiveThrow {
  key: string;
  actor: string | null;
  color: string;
  name: string;
  show: DiceShow;
  root: THREE.Group;
  dice: LiveDie[];
  impacts: ReturnType<typeof throwRoll>["impacts"];
  heard: number;
  started: number;
  /** When the last die came to rest (ms of throw time). */
  settles: number;
  cleared: number | null;
  /** Throw time at the last update (ms). */
  age: number;
  /** How long the throw took to simulate and build (diagnostics). */
  ms: number;
  /** -- table toys -- fired this long after it was made (ms of throw time), its own line and tag. */
  delay: number;
  line: string | null;
  tag: string | null;
}

const CLEAR_MS = 260;
let trays = 0;

let blobTex: THREE.Texture | null = null;
function blobTexture(): THREE.Texture {
  if (blobTex) return blobTex;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(0,0,0,0.62)");
  grad.addColorStop(0.45, "rgba(0,0,0,0.32)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  return (blobTex = new THREE.CanvasTexture(c));
}

let ringTex: THREE.Texture | null = null;
function ringTexture(): THREE.Texture {
  if (ringTex) return ringTex;
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 34, 64, 64, 62);
  grad.addColorStop(0, "rgba(255,255,255,0)");
  grad.addColorStop(0.55, "rgba(255,255,255,0.9)");
  grad.addColorStop(0.7, "rgba(255,255,255,0.35)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  ringTex = new THREE.CanvasTexture(c);
  ringTex.colorSpace = THREE.SRGBColorSpace;
  return ringTex;
}

let plane: THREE.PlaneGeometry | null = null;
const flat = () => (plane ??= new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2));
const tmpQ = new THREE.Quaternion();
const tmpV = new THREE.Vector3();

/**
 * Build the commonest dice's meshes and engraving ahead, while the page is idle, so the first roll of a d20 or a d6
 * doesn't pay for them.
 */
export function prewarmDice(): () => void {
  const ric = (globalThis as { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
  // idle time, or within two seconds at the latest (a busy table may never be idle)
  const idle = ric ? (f: () => void) => ric(f, { timeout: 2000 }) : (f: () => void) => setTimeout(f, 400);
  const cancel = (globalThis as { cancelIdleCallback?: (n: number) => void }).cancelIdleCallback ?? ((n: number) => clearTimeout(n));
  const jobs: (() => void)[] = [() => dieAtlas("d20"), () => dieAtlas("d6"), () => dieSolid("d20"), () => dieSolid("d6"), () => coinAtlas()];
  let handle = 0;
  const next = () => {
    const job = jobs.shift();
    if (!job) return;
    job();
    handle = idle(next) as number;
  };
  handle = idle(next) as number;
  return () => cancel(handle);
}

export class DiceTray {
  readonly group = new THREE.Group();
  private throws: LiveThrow[] = [];
  private materials = new Map<string, THREE.Material>();
  private opts: TrayOptions;
  /** A throw just landed or was cleared: callers that render on demand draw again. */
  changed = true;

  constructor(opts: TrayOptions) {
    this.opts = { segments: 4, sound: true, ...opts };
    trays++;
  }

  /**
   * Throw a roll in `frame` (the roller's mat). `env` is the throw's world in that frame (diceThrow.ts tableEnv
   * for the live table), `now` the clock the tray is updated with.
   */
  throw(show: DiceShow, color: string, name: string, frame: ThrowFrame, env: ThrowEnv, now: number, opts: ThrowOptions = {}): { settles: number } {
    const t0 = performance.now();
    const thrown = opts.still ? placeRoll(show, env) : throwRoll(show, env, opts.launcher);
    const root = new THREE.Group();
    this.place(root, frame);
    let impacts = thrown.impacts;
    if (opts.from && !opts.still) {
      // fired from the cannon: each die flies from the muzzle (in this throw's own frame) into the throw (diceThrow.ts)
      const from = root.worldToLocal(opts.from.clone());
      const p = new THREE.Vector3();
      const q = new THREE.Quaternion();
      // a volley's dice leave the muzzle together and reach the mat together, as the throw has them (the farthest sets the time)
      const longest = Math.max(...thrown.dice.map((d) => {
        poseLerp(d.track, 0, p, q);
        return flightSeconds(from.distanceTo(p));
      }));
      for (const d of thrown.dice) {
        d.track = prefixTrack(d.track, from, longest);
        d.rest = Math.min(d.track.count - 1, d.track.rest) / FRAMES_PER_SECOND;
      }
      impacts = impacts.map((x) => ({ ...x, t: x.t + longest }));
    }
    root.visible = !(opts.delay && opts.delay > 0);
    const dice = thrown.dice.map((spec) => this.makeDie(spec, color, root));
    this.group.add(root);
    const delay = Math.max(0, opts.delay ?? 0);
    const settles = Math.max(...thrown.dice.map((d) => d.rest)) * 1000;
    this.throws.push({
      key: show.key, actor: show.actor, color, name, show, root, dice, impacts, heard: 0, started: now,
      settles, cleared: null, age: -1, ms: performance.now() - t0, delay, line: opts.line ?? null, tag: opts.tag ?? null,
    });
    this.changed = true;
    return { settles: delay + settles };
  }

  private place(root: THREE.Group, f: ThrowFrame): void {
    root.position.set(f.x, 0, f.z);
    root.rotation.set(0, f.rotY, 0);
    root.scale.setScalar(f.scale ?? 1);
    root.updateMatrixWorld(true);
  }

  /** Move a throw's frame (the 2D table's mats move as the layout changes). */
  setFrame(key: string, f: ThrowFrame): void {
    const t = this.throws.find((x) => x.key === key);
    if (!t) return;
    this.place(t.root, f);
    this.changed = true;
  }

  private material(kind: DieKind, color: string, ignored: boolean): THREE.Material {
    const { look, envMap } = this.opts;
    const key = `${kind === "coin" ? "coin" : look}|${color}|${kind}|${ignored ? 1 : 0}`;
    let m = this.materials.get(key);
    if (!m) {
      m = kind === "coin"
        ? coinMaterial(color, coinAtlas(), envMap, ignored)
        : diceMaterial({ look, seat: color, ignored, atlas: dieAtlas(kind), envMap, seed: (color.charCodeAt(1) % 7) * 3.1 });
      (m as THREE.MeshPhysicalMaterial).envMapIntensity *= this.opts.envIntensity ?? 1;
      this.materials.set(key, m);
    }
    return m;
  }

  private makeDie(spec: ThrownDie, color: string, root: THREE.Group): LiveDie {
    const kind = spec.kind;
    const solid = kind === "coin" ? null : dieSolid(kind, this.opts.segments);
    const geo = solid ? solid.geometry : coinGeometry(COIN_RADIUS, COIN_THICK);
    const mesh = new THREE.Mesh(geo, this.material(kind, color, spec.ignored));
    mesh.castShadow = this.opts.shadows;
    const radius = solid ? solid.radius : COIN_RADIUS;
    const height = solid ? solid.inradius : COIN_THICK / 2;
    const blob = new THREE.Mesh(flat(), new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false, opacity: 0.8 }));
    blob.renderOrder = 1; // over the (transparent) mats
    let ring: THREE.Mesh | null = null;
    if (spec.crit) {
      ring = new THREE.Mesh(flat(), new THREE.MeshBasicMaterial({
        map: ringTexture(), transparent: true, depthWrite: false, opacity: 0, color: spec.crit === "high" ? "#f2c96c" : "#b8463d",
        blending: spec.crit === "high" ? THREE.AdditiveBlending : THREE.NormalBlending,
      }));
      ring.renderOrder = 2;
      root.add(ring);
    }
    root.add(blob, mesh);
    const d: LiveDie = { spec, mesh, blob, ring, radius, height };
    this.pose(d, 0);
    return d;
  }

  private pose(d: LiveDie, frame: number): void {
    poseLerp(d.spec.track, frame, d.mesh.position, tmpQ);
    d.mesh.quaternion.copy(tmpQ).multiply(d.spec.turn);
    const lift = Math.max(0, d.mesh.position.y - d.height);
    // the contact shadow: under the die, a touch away from the key light, spreading and fading as it rises
    d.blob.position.set(d.mesh.position.x + 0.03, 0.006, d.mesh.position.z + 0.05);
    d.blob.scale.setScalar(d.radius * (2.3 + lift * 1.2));
    (d.blob.material as THREE.MeshBasicMaterial).opacity = 0.85 / (1 + lift * 2.2);
    if (d.ring) d.ring.position.set(d.mesh.position.x, 0.008, d.mesh.position.z);
  }

  /** Advance every throw (ms clock); returns whether anything moved (on-demand renderers draw while it does). */
  update(now: number, reduced: boolean, speed: number): boolean {
    const rate = Math.max(0.25, speed);
    let moving = this.changed;
    this.changed = false;
    const frozen = diceClock.frozen;
    for (const t of [...this.throws]) {
      // (a cannon's throw waits `delay` before it leaves the muzzle: hidden until then; reduced motion shows only the result)
      const age = reduced && frozen === null ? t.settles + 1000 : (frozen ?? (now - t.started) * rate) - t.delay;
      const waiting = age < 0;
      if (t.root.visible === waiting) {
        t.root.visible = !waiting;
        moving = true;
      }
      if (waiting) {
        if (t.cleared !== null) this.remove(t); // cleared before it was even fired (a new turn): it never shows
        moving = true;
        t.age = age;
        continue;
      }
      if (age !== t.age) {
        const frame = (age / 1000) * FRAMES_PER_SECOND;
        // at rest nothing moves: skip the poses once both this frame and the last are past the last landing
        if (!(age > t.settles + 600 && t.age > t.settles + 600)) for (const d of t.dice) this.pose(d, frame);
        if (age < t.settles + 600) moving = true;
      }
      // sounds as the throw reaches each impact (one soft settle when the dice simply appear)
      if (this.opts.sound && frozen === null) {
        if (reduced) {
          if (t.heard === 0) diceSettle(t.dice.every((d) => d.spec.kind === "coin"));
          t.heard = t.impacts.length + 1;
        } else {
          while (t.heard < t.impacts.length && t.impacts[t.heard]!.t * 1000 <= age) {
            const i = t.impacts[t.heard++]!;
            const d = t.dice[i.body];
            if (d && age - i.t * 1000 < 250) diceClack(i.speed, i.with, d.radius, d.spec.kind === "coin");
          }
        }
      }
      // a crit's ring fades in once its die rests
      for (const d of t.dice) {
        if (!d.ring) continue;
        const k = Math.max(0, Math.min(1, (age - d.spec.rest * 1000 - 120) / 380));
        (d.ring.material as THREE.MeshBasicMaterial).opacity = k * 0.5;
        d.ring.scale.setScalar(d.radius * (2.9 + (1 - k) * 0.6));
      }
      t.age = age;
      if (t.cleared !== null) {
        // cleared: the dice sink away
        const k = reduced ? 1 : Math.min(1, (now - t.cleared) / CLEAR_MS);
        for (const d of t.dice) {
          d.mesh.scale.setScalar(Math.max(0.001, 1 - k * k));
          (d.blob.material as THREE.MeshBasicMaterial).opacity *= 1 - k;
          if (d.ring) (d.ring.material as THREE.MeshBasicMaterial).opacity *= 1 - k;
        }
        moving = true;
        if (k >= 1) this.remove(t);
      }
    }
    return moving;
  }

  /** The chips and lines for the DOM labels (diceHud.ts), placed with `project` (world → screen). */
  hud(project: (p: THREE.Vector3) => { x: number; y: number; visible: boolean }, now = performance.now()): HudThrow[] {
    return this.throws.map((t) => {
      const fade = t.cleared === null ? 1 : Math.max(0, 1 - (now - t.cleared) / CLEAR_MS);
      const at = (x: number, y: number, z: number) => project(tmpV.set(x, y, z).applyMatrix4(t.root.matrixWorld));
      let cx = 0, cy = 0;
      const chips = t.dice.map((d) => {
        const p = d.mesh.position;
        const c = at(p.x, p.y, p.z);
        const top = at(p.x, p.y + d.height + 0.25, p.z);
        const side = at(p.x + d.radius, p.y, p.z);
        // the die's size on screen, so a chip clears it whether the camera looks down at an angle or straight down
        const r = Math.max(8, Math.hypot(side.x - c.x, side.y - c.y));
        cx += c.x / t.dice.length;
        cy += c.y / t.dice.length;
        return {
          x: c.x, y: Math.min(top.y, c.y - r * 0.85), cy: c.y, r, visible: c.visible,
          shown: t.age >= d.spec.rest * 1000 + 120, label: d.spec.label, ignored: d.spec.ignored, crit: d.spec.crit,
        };
      });
      // the line goes on the roller's side of the dice (toward local +z), clear of the chips
      const c = t.dice.reduce((a, d) => a.add(d.mesh.position), new THREE.Vector3()).divideScalar(Math.max(1, t.dice.length));
      const toward = at(c.x, 0, c.z + 2);
      const crits = t.show.results.map((_, i) => natural(t.show, i));
      const crit = crits.includes("high") ? "high" : crits.includes("low") ? "low" : null;
      return {
        key: t.key, color: t.color, name: t.name, line: t.line ?? rollLine(t.name, t.show), crit, chips, fade, tag: t.tag,
        x: cx, y: cy, below: toward.y >= cy, visible: chips.some((ch) => ch.visible), shown: t.age >= t.settles + 150,
      };
    });
  }

  /** Clear a throw away (it sinks, then is gone). */
  dismiss(key: string, now = performance.now()): void {
    const t = this.throws.find((x) => x.key === key);
    if (t && t.cleared === null) t.cleared = now;
    this.changed = true;
  }

  /** Clear a player's dice (they rolled again), or everyone's. */
  clear(actor?: string | null, now = performance.now()): void {
    for (const t of this.throws) if (actor === undefined || t.actor === actor) this.dismiss(t.key, now);
  }

  /** The throw whose die is under this ray, if any (a click clears it). */
  pick(ray: THREE.Raycaster): string | null {
    const live = this.throws.filter((t) => t.cleared === null);
    const hit = ray.intersectObjects(live.flatMap((t) => t.dice.map((d) => d.mesh)), false)[0];
    if (!hit) return null;
    return live.find((t) => t.dice.some((d) => d.mesh === hit.object))?.key ?? null;
  }

  /** Another look (Settings): the dice on the table change material in place. */
  setLook(look: DiceLook): void {
    if (look === this.opts.look) return;
    this.opts.look = look;
    const old = [...this.materials.values()];
    this.materials.clear();
    for (const t of this.throws) for (const d of t.dice) d.mesh.material = this.material(d.spec.kind, t.color, d.spec.ignored);
    for (const m of old) m.dispose();
    this.changed = true;
  }

  private remove(t: LiveThrow): void {
    this.group.remove(t.root);
    for (const d of t.dice) {
      (d.blob.material as THREE.Material).dispose();
      if (d.ring) (d.ring.material as THREE.Material).dispose();
    }
    this.throws = this.throws.filter((x) => x !== t);
    this.changed = true;
  }

  /** Where the dice are now, in world coordinates (tests and diagnostics). */
  positions(): THREE.Vector3[] {
    return this.throws.filter((t) => t.cleared === null).flatMap((t) => t.dice.map((d) => d.mesh.getWorldPosition(new THREE.Vector3())));
  }

  /** Where a throw's dice come to rest, in world coordinates. */
  restPositions(key: string): THREE.Vector3[] {
    const t = this.throws.find((x) => x.key === key);
    if (!t) return [];
    const q = new THREE.Quaternion();
    return t.dice.map((d) => {
      const p = new THREE.Vector3();
      poseLerp(d.spec.track, d.spec.track.count, p, q);
      return p.applyMatrix4(t.root.matrixWorld);
    });
  }

  /** What each throw shows (tests and diagnostics): each die's label, kind, whether ignored and whether at rest. */
  describe(): { key: string; ms: number; dice: { label: string; kind: DieKind; ignored: boolean; resting: boolean }[] }[] {
    return this.throws.filter((t) => t.cleared === null).map((t) => ({
      key: t.key, ms: Math.round(t.ms * 10) / 10, dice: t.dice.map((d) => ({ label: d.spec.label, kind: d.spec.kind, ignored: d.spec.ignored, resting: t.age >= d.spec.rest * 1000 })),
    }));
  }

  /** Throws on the table (cleared ones excluded). */
  get count(): number {
    return this.throws.filter((t) => t.cleared === null).length;
  }

  dispose(): void {
    for (const t of [...this.throws]) this.remove(t);
    for (const m of this.materials.values()) m.dispose();
    this.materials.clear();
    if (--trays <= 0) {
      trays = 0;
      // the last tray: the shared meshes, atlases and textures go too
      disposeDiceArt();
      disposeSolids();
      blobTex?.dispose();
      ringTex?.dispose();
      plane?.dispose();
      blobTex = ringTex = plane = null;
    }
  }
}
