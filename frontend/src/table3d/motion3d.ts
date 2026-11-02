/**
 * TABLE MOTION on the 3D table, played (the plan is table3d/flights3d.ts): card flights between zones, stand-in cards
 * for what the table doesn't show (draws, a mill's lower cards, a bounce into a hidden hand), a riffle on a shuffled
 * library, strike lunges when combat damage lands, and rising damage and life numbers.
 *
 * Display only: the table already shows the new state; this only moves things there. The game never waits on it,
 * input is never locked, and any click or key press finishes the flights at once (timing.ts onMotionSkip; the
 * numbers stay, they are feedback). It is stepped from the table's one frame loop (TableScene.loop), and does
 * nothing while idle (``active``). Stand-ins, numbers and their materials are pooled; nothing is allocated per frame.
 */
import * as THREE from "three";
import type { GameView } from "../types/game";
import { isVisible } from "../types/game";
import { MOTION, motionMs, motionOn, motionPrefs } from "../game/motion/timing";
import { zoneName, zoneOwner, type TableEvent } from "../game/motion/tableEvents";
import { CARD_W, MAT_D, PILES, toWorld, type PileZone, type Seat } from "./layout";
import {
  arcHeight, arcLift, easeOut, flightMs, floaterAt, lungeAt, planMotion, riffleAt, standInOpacity, turnAt,
  type FlightPlan, type FloaterPlan, type Look, type Place, type StrikePlan,
} from "./flights3d";

/** What motion needs of a card on the table (TableScene's card object). */
export interface MotionCard {
  id: string;
  group: THREE.Group;
  face: THREE.Mesh;
  overlay: THREE.Mesh | null;
  target: THREE.Vector3;
  rot: number;
  tilt: number;
  scale: number;
  /** Just made by the table and not yet placed: it starts at its source (a flight) or, unclaimed, right where it belongs. */
  fresh?: boolean;
  /** A flight drives it (the table's glide leaves it alone). */
  flying?: boolean;
  /** A strike lunge is on it (an offset over its glide). */
  struck?: boolean;
}

/** What motion needs of the table. */
export interface MotionHost {
  world: THREE.Group;
  faceGeo: THREE.BufferGeometry;
  /** Card thickness (the face sits on top). */
  thick: number;
  me(): string;
  view(): GameView | null;
  card(id: string): MotionCard | undefined;
  seat(player: string): Seat | undefined;
  /** The height of a pile's top ("p2:library"). */
  pileY(zone: string): number;
  /** A player's card back. */
  back(owner: string): THREE.MeshStandardMaterial;
  /** The face the table would show for a card of the current view (a back when this viewer may not see it). */
  face(id: string): THREE.MeshStandardMaterial;
  /** A seat's life heart (world). */
  heart(player: string): THREE.Vector3 | null;
}

interface Xform { pos: THREE.Vector3; rot: number; tilt: number; scale: number }
const xform = (): Xform => ({ pos: new THREE.Vector3(), rot: 0, tilt: 0, scale: 1 });
const copyX = (out: Xform, a: Xform): Xform => {
  out.pos.copy(a.pos);
  out.rot = a.rot;
  out.tilt = a.tilt;
  out.scale = a.scale;
  return out;
};

/** A pooled stand-in card: a face on its own material (so it can fade), its body drawn with the table's cards. */
interface StandIn {
  group: THREE.Group;
  mesh: THREE.Mesh;
  mat: THREE.MeshStandardMaterial;
  opacity: number;
}

interface Flight {
  card: MotionCard | null;
  standIn: StandIn | null;
  from: Xform;
  to: Xform;
  t0: number;
  delay: number;
  dur: number;
  arc: number;
  vanish: boolean;
  /** Turning over: the look before and after (a real card turns from its back to its face). */
  turn: "up" | "down" | null;
  /** It visibly turns over (reduced motion: the side just changes halfway, no spin). */
  spin: boolean;
  over: boolean;
  before: THREE.Texture | null;
  after: THREE.Texture | null;
  back: THREE.MeshStandardMaterial | null;
  skipped: boolean;
}

interface Riffle { zone: string; cards: StandIn[]; base: Xform; t0: number; dur: number; skipped: boolean }
interface Lunge { card: MotionCard; dir: THREE.Vector3; reach: number; t0: number; dur: number; applied: THREE.Vector3; skipped: boolean }
interface Floater { sprite: THREE.Sprite; canvas: HTMLCanvasElement; tex: THREE.CanvasTexture; at: THREE.Vector3; key: string; size: number; t0: number; dur: number; busy: boolean }

/** Where a card that just left the table was, and what it looked like (kept until the next layout). */
interface Gone { at: Xform; map: THREE.Texture | null }

const RIFFLE_CARDS = 6;
const STAND_INS = 32;
const FLOATERS = 12;
/** How far a striking creature lunges (world units: a third of a card's length). */
const STRIKE_REACH = 0.4;
const LOSS = "#ff8a7a";
// scratch for the per-frame curves (nothing is allocated per frame)
const turnS = { angle: 0, over: false };
const floatS = { rise: 0, opacity: 0, scale: 1 };
const riffleS = { dx: 0, dy: 0, turn: 0 };
const GAIN = "#9ee68a";

function angleLerp(a: number, b: number, t: number): number {
  let d = (b - a) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

/** The table's reduced-motion flag (the setting, or the low graphics preset). */
function reducedNow(): boolean {
  return typeof document !== "undefined" && document.body.classList.contains("reduced-motion");
}

/** A travel duration at the player's speed; reduced motion (or low graphics) shortens it. */
function travelMs(ms: number): number {
  const d = motionMs(ms);
  return reducedNow() && !motionPrefs().reduced ? Math.round(d * 0.4) : d;
}

export class TableMotion {
  private host: MotionHost;
  private flights: Flight[] = [];
  private riffles: Riffle[] = [];
  private lunges: Lunge[] = [];
  private floaters: Floater[] = [];
  private floating = 0;
  private free: StandIn[] = [];
  private made = 0;
  private gone = new Map<string, Gone>();
  /** Tests and screenshots: every motion shown at this many ms after it started (null: live). */
  private frozen: number | null = null;

  constructor(host: MotionHost) {
    this.host = host;
  }

  /** Anything to step this frame (the frame loop does nothing else for motion while this is false). */
  get active(): boolean {
    return this.flights.length > 0 || this.riffles.length > 0 || this.lunges.length > 0 || this.floating > 0;
  }

  /** What is running (tests and diagnostics). */
  state(): { busy: boolean; flights: number; floaters: number; riffles: number; lunges: number } {
    return { busy: this.active, flights: this.flights.length, floaters: this.floating, riffles: this.riffles.length, lunges: this.lunges.length };
  }

  freeze(ms: number | null): void {
    this.frozen = ms;
  }

  private elapsed(t0: number, now: number): number {
    return this.frozen ?? now - t0;
  }

  // ------------------------------------------------------------------ the table's hooks

  /** The table is about to lay out a new view: forget where departed cards were. */
  layout(): void {
    this.gone.clear();
  }

  /** The table is taking this card off (its zone isn't shown): remember where it was and how it looked, for a moment. */
  forget(c: MotionCard): void {
    const at = xform();
    at.pos.copy(c.group.position);
    at.rot = c.group.rotation.y;
    at.tilt = c.group.rotation.x;
    at.scale = c.group.scale.x;
    this.gone.set(c.id, { at, map: (c.face.material as THREE.MeshStandardMaterial).map ?? null });
  }

  /** Any click or key press: the flights, riffles and lunges finish now (the numbers stay: they're feedback). */
  finish(): void {
    for (const f of this.flights) f.skipped = true;
    for (const r of this.riffles) r.skipped = true;
    for (const l of this.lunges) l.skipped = true;
  }

  /** A new view of the same game: play what happened. */
  play(events: TableEvent[], next: GameView, prev: GameView): void {
    if (!motionOn()) return;
    const me = this.host.me();
    const plan = planMotion(events, next, prev, {
      me,
      shows: (id) => !!this.host.card(id),
      fresh: (id) => !!this.host.card(id)?.fresh,
      had: (id) => this.gone.has(id),
    });
    const now = performance.now();
    const reduced = reducedNow();
    for (const f of plan.flights) this.fly(f, now);
    for (const zone of plan.shuffles) this.riffle(zone, now);
    if (!reduced) for (const s of plan.strikes) this.strike(s, now);
    for (const n of plan.floaters) this.float(n, now);
  }

  // ------------------------------------------------------------------ places

  /** Resolve a place to a transform (false: the table can't say where it is). */
  private spot(place: Place, out: Xform, card: MotionCard | null): boolean {
    out.tilt = 0;
    out.scale = 1;
    if ("gone" in place) {
      const g = this.gone.get(place.gone);
      if (!g) return false;
      copyX(out, g.at);
      return true;
    }
    if ("drop" in place) {
      if (!card) return false;
      out.pos.copy(card.target);
      out.pos.y += 0.7;
      out.rot = card.rot;
      out.tilt = card.tilt;
      out.scale = card.scale * 0.96;
      return true;
    }
    if ("card" in place) {
      const c = this.host.card(place.card);
      if (c) {
        out.pos.copy(c.group.position);
        out.rot = c.group.rotation.y;
        out.tilt = c.group.rotation.x;
        out.scale = c.group.scale.x;
        return true;
      }
      const zone = this.host.view()?.cards[place.card]?.zone;
      return zone ? this.zoneSpot(zone, out) : false;
    }
    return this.zoneSpot(place.zone, out);
  }

  private zoneSpot(zone: string, out: Xform): boolean {
    const me = this.host.me();
    if (zone === "stack") {
      // where the top of the stack stands, toward my side of the centre (TableScene.syncCards)
      const rot = this.host.seat(me)?.rot ?? 0;
      out.pos.set(1.75 * Math.sin(rot), 1.45, 1.75 * Math.cos(rot));
      out.rot = rot;
      out.tilt = 0.75;
      out.scale = 2.25;
      return true;
    }
    const owner = zoneOwner(zone);
    const seat = owner ? this.host.seat(owner) : undefined;
    if (!seat) return false;
    const name = zoneName(zone);
    let lx = 0, lz = 0, y = 0.08;
    out.rot = seat.rot;
    if (name === "library" || name === "graveyard" || name === "exile" || name === "command") {
      [lx, lz] = PILES[name as PileZone];
      y = this.host.pileY(zone) + 0.02;
    } else if (name === "hand" && owner === me) {
      // my hand: the near edge of my mat, held a little up (the hand itself is drawn over the table's foot)
      lz = MAT_D / 2 + 1.5;
      y = 0.7;
    } else if (name === "hand") {
      // another player's hand: the fan of backs past their mat's edge (TableScene.syncHandFan)
      lz = MAT_D / 2 + 1.25;
      y = 0.3;
      out.rot = seat.rot + Math.PI;
    }
    const [wx, wz] = toWorld(seat, lx, lz);
    out.pos.set(wx, y, wz);
    return true;
  }

  // ------------------------------------------------------------------ flights

  private texOf(look: Look, owner: string): THREE.Texture | null {
    if ("back" in look) return this.host.back(look.back).map;
    if ("seen" in look) return this.gone.get(look.seen)?.map ?? this.host.back(owner).map;
    const card = this.host.view()?.cards[look.face];
    // only a face this viewer sees face up (host.face is a back otherwise)
    return isVisible(card) && !card.face_down ? this.host.face(look.face).map : this.host.back(owner).map;
  }

  private fly(plan: FlightPlan, now: number): void {
    const card = plan.card ? this.host.card(plan.card) ?? null : null;
    if (plan.card && !card) return;
    const from = xform();
    if (!this.spot(plan.from, from, card)) return;
    const to = xform();
    let standIn: StandIn | null = null;
    let before: THREE.Texture | null = null;
    let after: THREE.Texture | null = null;
    let back: THREE.MeshStandardMaterial | null = null;
    if (card) {
      // the card itself, from its source to its own place (a newer flight takes over from an older one, where it is)
      for (let i = this.flights.length - 1; i >= 0; i--) {
        const old = this.flights[i]!;
        if (old.card !== card) continue;
        this.flights.splice(i, 1);
        if (old.back && card.face.material === old.back) card.face.material = this.host.face(card.id);
      }
      card.fresh = false;
      card.flying = true;
      if (plan.turn === "up") {
        back = this.host.back(plan.owner);
        card.face.material = back;
      }
      if (card.overlay) card.overlay.visible = plan.turn !== "up";
      copyX(to, { pos: card.target, rot: card.rot, tilt: card.tilt, scale: card.scale });
    } else {
      if (plan.vanish) copyX(to, from);
      else if (!plan.to || !this.spot(plan.to, to, null)) return;
      standIn = this.take();
      if (!standIn) return;
      const look = plan.look ?? { back: plan.owner };
      const seen = this.texOf(look, plan.owner);
      const backMap = this.host.back(plan.owner).map;
      before = plan.turn === "up" ? backMap : seen;
      after = plan.turn === "down" ? backMap : seen;
      this.dress(standIn, before);
    }
    const dist = from.pos.distanceTo(to.pos);
    const f: Flight = {
      card, standIn, from, to, t0: now, delay: travelMs(plan.delay), dur: Math.max(1, travelMs(plan.vanish ? plan.ms : flightMs(plan.ms, dist))),
      arc: plan.vanish || "drop" in plan.from ? 0 : arcHeight(dist) * (reducedNow() ? 0.5 : 1), vanish: !!plan.vanish, turn: plan.turn ?? null, spin: !reducedNow(), over: false, before, after, back, skipped: false,
    };
    this.flights.push(f);
    this.pose(f, 0);
  }

  /** Place a flight at progress p. */
  private pose(f: Flight, p: number): void {
    const obj = f.card?.group ?? f.standIn!.group;
    const c = f.card;
    if (c) {
      // a card flying itself goes to where the table wants it now (its place can change while it flies)
      f.to.pos.copy(c.target);
      f.to.rot = c.rot;
      f.to.tilt = c.tilt;
      f.to.scale = c.scale;
    }
    const e = easeOut(p);
    obj.position.lerpVectors(f.from.pos, f.to.pos, e);
    obj.position.y += arcLift(e, f.arc); // (the arc and the turn follow the way it has come, not the clock)
    obj.rotation.y = angleLerp(f.from.rot, f.to.rot, e);
    obj.rotation.x = f.from.tilt + (f.to.tilt - f.from.tilt) * e;
    obj.scale.setScalar(f.from.scale + (f.to.scale - f.from.scale) * e);
    if (f.turn) {
      const t = turnAt(e, turnS);
      obj.rotation.z = !f.spin ? 0 : t.over ? t.angle - Math.PI : t.angle;
      if (t.over !== f.over) {
        f.over = t.over;
        if (f.standIn) this.dress(f.standIn, t.over ? f.after : f.before);
        else if (c && t.over && f.turn === "up") c.face.material = this.host.face(c.id);
      }
      // until it turns, a card turning face up keeps its back (the table may relayout it meanwhile)
      if (c && !f.over && f.back) {
        c.face.material = f.back;
        if (c.overlay) c.overlay.visible = false;
      }
      if (c?.overlay && f.over) c.overlay.visible = true;
    }
    if (f.standIn) f.standIn.opacity = f.standIn.mat.opacity = standInOpacity(p, f.vanish);
  }

  private land(f: Flight): void {
    const c = f.card;
    if (c) {
      c.flying = false;
      c.group.position.copy(c.target);
      c.group.rotation.set(c.tilt, c.rot, 0);
      c.group.scale.setScalar(c.scale);
      if (f.back && c.face.material === f.back) c.face.material = this.host.face(c.id);
      if (c.overlay) c.overlay.visible = true;
    }
    if (f.standIn) this.give(f.standIn);
  }

  // ------------------------------------------------------------------ stand-ins

  private take(): StandIn | null {
    let s = this.free.pop();
    if (!s) {
      if (this.made >= STAND_INS) return null;
      this.made++;
      const mat = new THREE.MeshStandardMaterial({ roughness: 0.8, metalness: 0, envMapIntensity: 0.12, transparent: true });
      const mesh = new THREE.Mesh(this.host.faceGeo, mat);
      mesh.position.y = this.host.thick + 0.0008;
      const group = new THREE.Group();
      group.add(mesh);
      s = { group, mesh, mat, opacity: 1 };
    }
    s.opacity = s.mat.opacity = 1;
    s.group.rotation.set(0, 0, 0);
    this.host.world.add(s.group);
    return s;
  }

  private give(s: StandIn): void {
    this.host.world.remove(s.group);
    this.free.push(s);
  }

  private dress(s: StandIn, map: THREE.Texture | null): void {
    if (s.mat.map === map) return;
    const hadMap = !!s.mat.map;
    s.mat.map = map;
    if (hadMap !== !!map) s.mat.needsUpdate = true; // (switching between two textures needs no new program)
  }

  /** Each stand-in's body and shadow are drawn with the table's cards (TableScene's instanced bodies). */
  standIns(each: (obj: THREE.Object3D, opacity: number) => void): void {
    for (const f of this.flights) if (f.standIn) each(f.standIn.group, f.standIn.opacity);
    for (const r of this.riffles) for (const s of r.cards) each(s.group, 1);
  }

  // ------------------------------------------------------------------ shuffles

  private riffle(zone: string, now: number): void {
    const z = this.host.view()?.zones[zone];
    const count = z && !Array.isArray(z) ? z.count : 0;
    if (count < 2 || this.riffles.some((r) => r.zone === zone)) return;
    const base = xform();
    if (!this.zoneSpot(zone, base)) return;
    base.pos.y -= 0.02;
    const owner = zoneOwner(zone) ?? this.host.me();
    const map = this.host.back(owner).map;
    const cards: StandIn[] = [];
    for (let i = 0; i < Math.min(RIFFLE_CARDS, count); i++) {
      const s = this.take();
      if (!s) break;
      this.dress(s, map);
      cards.push(s);
    }
    if (cards.length < 2) {
      for (const s of cards) this.give(s);
      return;
    }
    const r: Riffle = { zone, cards, base, t0: now, dur: Math.max(1, travelMs(MOTION.shuffle)), skipped: false };
    this.riffles.push(r);
    this.poseRiffle(r, 0);
  }

  private poseRiffle(r: Riffle, p: number): void {
    const cos = Math.cos(r.base.rot);
    const sin = Math.sin(r.base.rot);
    for (let i = 0; i < r.cards.length; i++) {
      const s = r.cards[i]!;
      const o = riffleAt(i, r.cards.length, p, CARD_W, this.host.thick, riffleS);
      s.group.position.set(r.base.pos.x + o.dx * cos, r.base.pos.y + o.dy, r.base.pos.z - o.dx * sin);
      s.group.rotation.set(0, r.base.rot + o.turn, 0);
    }
  }

  // ------------------------------------------------------------------ strikes

  private strike(s: StrikePlan, now: number): void {
    const c = this.host.card(s.id);
    if (!c || c.flying || c.struck) return;
    let toward: THREE.Vector3 | null = null;
    if ("card" in s.toward) toward = this.host.card(s.toward.card)?.target ?? null;
    else toward = this.host.heart(s.toward.player);
    if (!toward) return;
    const dir = new THREE.Vector3(toward.x - c.target.x, 0, toward.z - c.target.z);
    if (dir.lengthSq() < 1e-4) return;
    dir.normalize();
    c.struck = true;
    this.lunges.push({ card: c, dir, reach: STRIKE_REACH, t0: now, dur: Math.max(1, motionMs(MOTION.lunge)), applied: new THREE.Vector3(), skipped: false });
  }

  /** Before the table glides a struck card: take off last frame's lunge. */
  unstrike(c: MotionCard): void {
    const l = this.lungeOf(c);
    if (l >= 0) c.group.position.sub(this.lunges[l]!.applied);
  }

  private lungeOf(c: MotionCard): number {
    for (let i = 0; i < this.lunges.length; i++) if (this.lunges[i]!.card === c) return i;
    return -1;
  }

  /** After the glide: put this frame's lunge on (and end it when it's done). */
  restrike(c: MotionCard, now: number): void {
    const i = this.lungeOf(c);
    const l = this.lunges[i];
    if (!l) {
      c.struck = false;
      return;
    }
    const p = l.skipped ? 1 : Math.min(1, this.elapsed(l.t0, now) / l.dur);
    if (p >= 1) {
      l.applied.set(0, 0, 0);
      c.struck = false;
      this.lunges.splice(i, 1);
      return;
    }
    l.applied.copy(l.dir).multiplyScalar(l.reach * lungeAt(p));
    l.applied.y = 0.12 * lungeAt(p);
    c.group.position.add(l.applied);
  }

  // ------------------------------------------------------------------ numbers

  private float(n: FloaterPlan, now: number): void {
    const at = new THREE.Vector3();
    let size: number;
    let key: string;
    if ("card" in n.at) {
      const c = this.host.card(n.at.card);
      if (!c) return;
      at.copy(c.target).setY(c.target.y + 0.45);
      size = 0.62;
      key = n.at.card;
    } else {
      const h = this.host.heart(n.at.player);
      if (!h) return;
      at.copy(h).setY(h.y + 1.15); // (just over the heart's top: the total stays readable)
      size = 0.8;
      key = `life:${n.at.player}`;
    }
    // a second number at the same place starts above the one still rising
    const stacked = this.floaters.filter((f) => f.busy && f.key === key && this.elapsed(f.t0, now) < 500).length;
    at.y += stacked * size * 0.9;
    let f = this.floaters.find((x) => !x.busy);
    if (!f) {
      if (this.floaters.length >= FLOATERS) return;
      const canvas = document.createElement("canvas");
      canvas.width = 256;
      canvas.height = 128;
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false, toneMapped: false }));
      sprite.renderOrder = 20;
      f = { sprite, canvas, tex, at: new THREE.Vector3(), key: "", size: 1, t0: 0, dur: 1, busy: false };
      this.floaters.push(f);
    }
    drawNumber(f.canvas, n.text, n.gain ? GAIN : LOSS);
    f.tex.needsUpdate = true;
    f.at.copy(at);
    f.key = key;
    f.size = size;
    f.t0 = now;
    f.dur = Math.max(1, motionMs(MOTION.floater, false)); // (reduced motion keeps numbers whole)
    f.busy = true;
    this.floating++;
    this.host.world.add(f.sprite);
    this.poseFloater(f, 0, reducedNow());
  }

  private poseFloater(f: Floater, p: number, reduced: boolean): void {
    const s = floaterAt(p, reduced, floatS);
    f.sprite.position.set(f.at.x, f.at.y + s.rise * 0.8, f.at.z);
    f.sprite.scale.set(f.size * 2 * s.scale, f.size * s.scale, 1);
    (f.sprite.material as THREE.SpriteMaterial).opacity = s.opacity;
  }

  // ------------------------------------------------------------------ the frame

  /** Step everything one frame (only called while ``active``). */
  update(now: number, reduced: boolean): void {
    for (let i = this.flights.length - 1; i >= 0; i--) {
      const f = this.flights[i]!;
      const t = this.elapsed(f.t0, now) - f.delay;
      const p = f.skipped ? 1 : Math.max(0, Math.min(1, t / f.dur));
      if (p >= 1) {
        this.flights.splice(i, 1);
        this.land(f);
        continue;
      }
      this.pose(f, p);
    }
    for (let i = this.riffles.length - 1; i >= 0; i--) {
      const r = this.riffles[i]!;
      const p = r.skipped ? 1 : Math.min(1, this.elapsed(r.t0, now) / r.dur);
      if (p >= 1) {
        this.riffles.splice(i, 1);
        for (const s of r.cards) this.give(s);
        continue;
      }
      this.poseRiffle(r, p);
    }
    for (const f of this.floaters) {
      if (!f.busy) continue;
      const p = Math.min(1, this.elapsed(f.t0, now) / f.dur);
      if (p >= 1) {
        f.busy = false;
        this.floating--;
        this.host.world.remove(f.sprite);
        continue;
      }
      this.poseFloater(f, p, reduced);
    }
  }

  dispose(): void {
    for (const f of this.flights) this.land(f);
    this.flights = [];
    for (const r of this.riffles) for (const s of r.cards) this.give(s);
    this.riffles = [];
    for (const l of this.lunges) l.card.struck = false;
    this.lunges = [];
    for (const s of this.free) s.mat.dispose();
    this.free = [];
    this.made = 0;
    for (const f of this.floaters) {
      this.host.world.remove(f.sprite);
      f.tex.dispose();
      (f.sprite.material as THREE.SpriteMaterial).dispose();
    }
    this.floaters = [];
    this.floating = 0;
    this.gone.clear();
  }
}

/** A damage or life number: Cinzel, its sign as text, with a dark edge so it reads over pale cards. */
function drawNumber(canvas: HTMLCanvasElement, text: string, color: string): void {
  const g = canvas.getContext("2d");
  if (!g) return;
  g.clearRect(0, 0, canvas.width, canvas.height);
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = "700 92px Cinzel, Georgia, serif";
  g.lineJoin = "round";
  g.lineWidth = 12;
  g.strokeStyle = "rgba(14, 9, 6, 0.92)";
  g.strokeText(text, canvas.width / 2, canvas.height / 2 + 4);
  g.fillStyle = color;
  g.fillText(text, canvas.width / 2, canvas.height / 2 + 4);
}
