/**
 * -- flip the table -- (╯°□°)╯︵ ┻━┻ on the 3D table: one player's battlefield cards jolt up away from them, tumble a little and drop back
 * where they were. Cosmetic only: no state changes, every card ends exactly where the table had it (``target``), and the glide takes over
 * again. Stepped from the table's one frame loop through TableMotion (motion3d.ts: ``active``, ``update``, ``finish``); a click or a key
 * press snaps it to the end (timing.ts onMotionSkip); the player's animation speed scales it; reduced motion never starts it (the shout
 * is enough). Cheap: one pose per card per frame for under a second, no allocation per frame, at most MAX_CARDS cards.
 */
import type { MotionCard } from "./motion3d";

export const FLIP_MS = 950;
export const MAX_CARDS = 80;
const STAGGER = 9; // ms per card, at most STAGGER_MAX in all
const STAGGER_MAX = 140;

interface Flying {
  card: MotionCard;
  delay: number;
  lift: number; // world units at the top of the arc
  push: number; // how far it is thrown away from the flipper
  rx: number; // tumble (radians at the top)
  ry: number;
  rz: number;
}

/** A small stable random number in [0, 1) from a card id and a salt (the same toss every time the same card flies). */
export function toss(id: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10007) / 10007;
}

/** How far through its arc a card is: up and out, then back down where it was (0 at both ends). */
export function arc(p: number): number {
  if (p <= 0 || p >= 1) return 0;
  // a quick throw up (the first 35%), a slower fall back with a small bounce as it lands
  if (p < 0.35) return Math.sin((p / 0.35) * (Math.PI / 2));
  const q = (p - 0.35) / 0.65;
  const fall = Math.cos(q * (Math.PI / 2));
  const bounce = q > 0.82 ? Math.sin(((q - 0.82) / 0.18) * Math.PI) * 0.06 : 0;
  return fall + bounce;
}

export class TableFlip {
  private cards: Flying[] = [];
  private t0 = 0;
  private dur = FLIP_MS;
  private skipped = false;
  /** Away from the flipper, in world x / z. */
  private dx = 0;
  private dz = -1;

  get active(): boolean {
    return this.cards.length > 0;
  }

  get count(): number {
    return this.cards.length;
  }

  /** Throw these cards (one seat's battlefield). ``seatRot``: the seat's rotation about Y (its local +z points at its owner). */
  start(cards: MotionCard[], seatRot: number, now: number, dur: number): void {
    this.end();
    this.dx = -Math.sin(seatRot);
    this.dz = -Math.cos(seatRot);
    this.t0 = now;
    this.dur = Math.max(1, dur);
    this.skipped = false;
    const n = Math.min(cards.length, MAX_CARDS);
    const step = n > 1 ? Math.min(STAGGER, STAGGER_MAX / (n - 1)) : 0;
    for (let i = 0; i < n; i++) {
      const c = cards[i]!;
      if (c.flying || c.struck) continue; // (a real flight or a lunge has it)
      c.flying = true;
      const a = toss(c.id, 1), b = toss(c.id, 2), d = toss(c.id, 3);
      this.cards.push({
        card: c, delay: i * step,
        lift: 0.9 + 0.8 * a, push: 0.5 + 0.7 * b,
        rx: (d - 0.5) * 1.1 - 0.35, ry: (a - 0.5) * 0.9, rz: (b - 0.5) * 1.0,
      });
    }
  }

  /** One frame: pose every card in the air (after the table's glide skipped them: they are ``flying``). ``frozen``: shown this many ms
   * after it started (tests and screenshots: TableMotion.freeze). */
  update(now: number, frozen: number | null = null): void {
    if (!this.cards.length) return;
    const elapsed = frozen ?? now - this.t0;
    let done = true;
    for (const f of this.cards) {
      const p = this.skipped ? 1 : Math.max(0, Math.min(1, (elapsed - f.delay) / this.dur));
      if (p < 1) done = false;
      const k = arc(p);
      const c = f.card;
      c.group.position.set(c.target.x + this.dx * f.push * k, c.target.y + f.lift * k, c.target.z + this.dz * f.push * k);
      c.group.rotation.set(c.tilt + f.rx * k, c.rot + f.ry * k, f.rz * k);
    }
    if (done) this.end();
  }

  /** A click or a key press: everything lands now (next frame). */
  finish(): void {
    this.skipped = true;
  }

  /** Every card back where the table has it, and the glide's again. */
  end(): void {
    for (const f of this.cards) {
      const c = f.card;
      c.group.position.copy(c.target);
      c.group.rotation.set(c.tilt, c.rot, 0);
      c.flying = false;
    }
    this.cards = [];
  }
}
