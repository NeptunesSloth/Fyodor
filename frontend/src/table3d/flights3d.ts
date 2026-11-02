/**
 * TABLE MOTION on the 3D table, the pure half (unit-tested; table3d/motion3d.ts plays it): what each table event
 * (game/motion/tableEvents.ts) becomes on the 3D table, and the curves the motion follows.
 *
 * - A card the table shows in its new place flies there itself, from where it really was: its old spot, the
 *   owner's hand, the top of a library, the stack, or the permanent an ability comes from. Out of a hidden zone
 *   (a library, another player's hand) it leaves as a card back and turns face up on the way.
 * - A card the table doesn't show where it went (a hand, a library, under a pile's top card) is played by a
 *   stand-in that flies there and goes: a draw, another player's draw, the cards of a mill under the top one,
 *   a bounce. Going into a hidden zone it turns face down on the way.
 * - A shuffle riffles a few card backs on the library; damage and life changes rise as numbers; combat damage
 *   makes the fighters strike.
 *
 * Privacy: a stand-in shows a face only for a card this viewer sees face up in one of the two views (or the face
 * the table itself was showing), otherwise it is a card back. Nothing here reads more than the views hold.
 */
import type { GameCard, GameView } from "../types/game";
import { isVisible } from "../types/game";
import { MOTION } from "../game/motion/timing";
import { zoneName, zoneOwner, type TableEvent } from "../game/motion/tableEvents";

/** Where a flight starts or ends. */
export type Place =
  /** A zone's spot: a pile's top, a hand (another player's fan; the viewer's own: the near edge of their mat), the stack, a mat. */
  | { zone: string }
  /** A card on the table now, where it is. */
  | { card: string }
  /** Where a card that just left the table was (the table remembers it for a moment). */
  | { gone: string }
  /** Just above the card's own place: it was made there (a token, a copy). */
  | { drop: true };

/** What a stand-in looks like: a card back of its owner, the face the table showed ("seen"), or a card's face this viewer sees. */
export type Look = { back: string } | { seen: string } | { face: string };

export interface FlightPlan {
  /** The card the table shows at the end, flying itself; absent: a stand-in flies and goes. */
  card?: string;
  /** A stand-in's look (absent for a card flying itself). */
  look?: Look;
  /** The card's owner (its back, when it travels face down). */
  owner: string;
  from: Place;
  /** A stand-in's destination (a card flying itself goes to its own place). */
  to?: Place;
  /** Turns face up or face down on the way. */
  turn?: "up" | "down";
  /** The stand-in fades where it is instead of flying (a token or an ability that left the game). */
  vanish?: boolean;
  /** Start after this many ms (a group staggers). */
  delay: number;
  /** Base duration (a motion token; the player's speed applies on top). */
  ms: number;
}

export interface FloaterPlan {
  /** A creature, or a player's life heart. */
  at: { card: string } | { player: string };
  text: string;
  gain: boolean;
}

export interface StrikePlan {
  id: string;
  /** What it strikes toward: the creature it fights, or the player it hits. */
  toward: { card: string } | { player: string };
}

export interface MotionPlan {
  flights: FlightPlan[];
  /** Library zones to riffle. */
  shuffles: string[];
  floaters: FloaterPlan[];
  strikes: StrikePlan[];
}

/** What the table knows about its cards right now (just after it laid out the new view). */
export interface SceneFacts {
  me: string;
  /** The table shows this card now (a battlefield, the stack, a command zone, a pile's top card). */
  shows(id: string): boolean;
  /** ...and it is new there (it wasn't on the table a moment ago). */
  fresh(id: string): boolean;
  /** The table showed this card a moment ago and remembers where. */
  had(id: string): boolean;
}

/** A zone this viewer can't look into: a library, or another player's hand. */
export function hiddenZone(zone: string, me: string): boolean {
  const name = zoneName(zone);
  return name === "library" || (name === "hand" && zoneOwner(zone) !== me);
}

/** The minus sign, as typeset (not a hyphen). */
export const MINUS = "−";

/** A face this viewer may see: a card they see face up. */
function faceUp(card: GameCard | undefined): boolean {
  return isVisible(card) && !card.face_down;
}

/**
 * The 3D table's plan for one batch of table events between ``prev`` and ``next``: flights (staggered, capped at
 * ``MOTION.maxFlights``: the rest just appear), riffles, numbers and combat strikes.
 */
export function planMotion(events: TableEvent[], next: GameView, prev: GameView, facts: SceneFacts): MotionPlan {
  const me = facts.me;
  const flights: Omit<FlightPlan, "delay">[] = [];
  const shuffles: string[] = [];
  const floaters: FloaterPlan[] = [];
  const travel = (from: string | null) => (from && zoneName(from) === "library" ? MOTION.drawTravel : MOTION.cardTravel);
  // what a stand-in for this card looks like, setting out from ``from``
  const lookOf = (id: string, owner: string, card: GameCard | undefined): Look => (facts.had(id) ? { seen: id } : faceUp(card) ? { face: id } : { back: owner });

  for (const e of events) {
    if (e.kind === "move") {
      const card = next.cards[e.id];
      const owner = card?.owner ?? zoneOwner(e.from) ?? me;
      if (facts.shows(e.id)) {
        // it flies itself: a card new to the table from its old zone, one already on it from where it is
        const fresh = facts.fresh(e.id);
        flights.push({ card: e.id, owner, from: fresh ? { zone: e.from } : { card: e.id }, ...(fresh && hiddenZone(e.from, me) ? { turn: "up" as const } : {}), ms: travel(e.from) });
      } else {
        // a stand-in: into a hand, a library or under a pile's top card
        const was = prev.cards[e.id];
        const look = facts.had(e.id) ? { seen: e.id } : faceUp(card) && !hiddenZone(e.to, me) ? { face: e.id } : faceUp(was) && !hiddenZone(e.from, me) ? { face: e.id } : { back: owner };
        const down = !("back" in look) && hiddenZone(e.to, me);
        flights.push({ look, owner, from: facts.had(e.id) ? { gone: e.id } : { zone: e.from }, to: { zone: e.to }, ...(down ? { turn: "down" as const } : {}), ms: travel(e.from) });
      }
    } else if (e.kind === "arrive") {
      const card = next.cards[e.id];
      const owner = card?.owner ?? zoneOwner(e.to) ?? me;
      const from: Place | null = e.source ? { card: e.source } : e.from ? { zone: e.from } : null;
      const out = !!e.from && hiddenZone(e.from, me); // out of a hidden zone: a back that turns face up
      if (facts.shows(e.id)) {
        if (!facts.fresh(e.id)) continue;
        flights.push({ card: e.id, owner, from: from ?? { drop: true }, ...(out ? { turn: "up" as const } : {}), ms: from ? travel(e.from) : MOTION.cardTravel * 0.7 });
      } else if (from) {
        // a draw into the viewer's own hand travels face down (the hand shows it); a mill's lower cards turn face up
        const intoHidden = zoneName(e.to) === "hand" || hiddenZone(e.to, me);
        const look: Look = !intoHidden && faceUp(card) ? { face: e.id } : { back: owner };
        flights.push({ look, owner, from, to: { zone: e.to }, ...("face" in look && out ? { turn: "up" as const } : {}), ms: travel(e.from) });
      }
    } else if (e.kind === "leave") {
      const was = prev.cards[e.id];
      const owner = was?.owner ?? zoneOwner(e.from) ?? me;
      if (e.to === null) {
        // a token or an ability gone from the game: it fades where it was
        if (facts.had(e.id)) flights.push({ look: { seen: e.id }, owner, from: { gone: e.id }, vanish: true, ms: MOTION.cardTravel * 0.6 });
        continue;
      }
      const look = lookOf(e.id, owner, undefined); // (never a face it didn't show: the card is out of sight now)
      flights.push({ look, owner, from: facts.had(e.id) ? { gone: e.id } : { zone: e.from }, to: { zone: e.to }, ...(!("back" in look) && hiddenZone(e.to, me) ? { turn: "down" as const } : {}), ms: travel(e.from) });
    } else if (e.kind === "hidden") {
      const owner = zoneOwner(e.from) ?? me;
      for (let i = 0; i < e.n; i++) flights.push({ look: { back: owner }, owner, from: { zone: e.from }, to: { zone: e.to }, ms: travel(e.from) });
    } else if (e.kind === "shuffle") {
      if (zoneName(e.zone) === "library" && !shuffles.includes(e.zone)) shuffles.push(e.zone);
    } else if (e.kind === "damage") {
      if (facts.shows(e.id)) floaters.push({ at: { card: e.id }, text: `${MINUS}${e.amount}`, gain: false });
    } else if (e.kind === "life") {
      floaters.push({ at: { player: e.player }, text: e.delta < 0 ? `${MINUS}${-e.delta}` : `+${e.delta}`, gain: e.delta > 0 });
    }
  }
  return { flights: stagger(flights), shuffles, floaters, strikes: combatStrikes(events, next) };
}

/** Group motion: each flight a little after the one before (never past ``groupMax``); past ``maxFlights`` the rest just appear. */
function stagger(flights: Omit<FlightPlan, "delay">[]): FlightPlan[] {
  return flights.slice(0, MOTION.maxFlights).map((f, i) => ({ ...f, delay: Math.min(i * MOTION.millStagger, MOTION.groupMax) }));
}

/**
 * Who strikes when combat damage lands (only in the combat damage step): an attacker and the creature it fights
 * strike at each other when either takes damage; an unblocked attacker strikes at the player who loses life.
 */
export function combatStrikes(events: TableEvent[], next: GameView): StrikePlan[] {
  if (next.turn?.phase !== "combat_damage") return [];
  const out: StrikePlan[] = [];
  const done = new Set<string>();
  const strike = (id: string, toward: StrikePlan["toward"]) => {
    if (done.has(id) || !next.cards[id]?.zone.endsWith(":battlefield")) return;
    done.add(id);
    out.push({ id, toward });
  };
  const blockersOf = (attacker: string) => Object.values(next.cards).filter((c) => c.blocking === attacker || c.blocking_more?.includes(attacker));
  for (const e of events) {
    if (e.kind === "damage") {
      const hurt = next.cards[e.id];
      if (!hurt) continue;
      for (const a of [hurt.blocking, ...(hurt.blocking_more ?? [])]) {
        if (!a || !next.cards[a]?.attacking) continue;
        strike(a, { card: e.id });
        strike(e.id, { card: a });
      }
      if (hurt.attacking) for (const b of blockersOf(e.id)) {
        strike(b.id, { card: e.id });
        strike(e.id, { card: b.id });
      }
    } else if (e.kind === "life" && e.delta < 0) {
      for (const c of Object.values(next.cards)) {
        if (c.attacking?.kind === "player" && c.attacking.id === e.player && !blockersOf(c.id).length) strike(c.id, { player: e.player });
      }
    }
  }
  return out;
}

// ------------------------------------------------------------------ curves

/** A CSS cubic-bezier timing function (x1, y1, x2, y2), solved for y at x (Newton steps, then bisection). */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number): (t: number) => number {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const x = (s: number) => ((ax * s + bx) * s + cx) * s;
  const y = (s: number) => ((ay * s + by) * s + cy) * s;
  const dx = (s: number) => (3 * ax * s + 2 * bx) * s + cx;
  return (t: number) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let s = t;
    for (let i = 0; i < 6; i++) {
      const err = x(s) - t;
      if (Math.abs(err) < 1e-5) return y(s);
      const d = dx(s);
      if (Math.abs(d) < 1e-6) break;
      s -= err / d;
    }
    let lo = 0, hi = 1;
    s = t;
    for (let i = 0; i < 20; i++) {
      if (x(s) < t) lo = s;
      else hi = s;
      s = (lo + hi) / 2;
    }
    return y(s);
  };
}

/** The theme's motion curves (theme.css --ease-out, --ease-in-out; docs/GAME_UI_MOTION_RESEARCH.md §3). */
export const easeOut = cubicBezier(0.23, 1, 0.32, 1);
export const easeInOut = cubicBezier(0.77, 0, 0.175, 1);

/** How high a flying card rides over the straight line between its ends, e of the way along (a low arc, highest halfway). */
export function arcLift(e: number, height: number): number {
  return 4 * e * (1 - e) * height;
}

/** How high a flight arcs for its length (world units): a short hop for a short move, never a lob. */
export function arcHeight(distance: number): number {
  return Math.min(1.4, 0.25 + distance * 0.09);
}

/** A flight's duration for its length (ms, before the player's speed): longer trips take a little longer, never past 450 ms. */
export function flightMs(base: number, distance: number): number {
  return Math.min(450, Math.round(base * (0.85 + Math.min(distance, 20) * 0.025)));
}

/**
 * A card turning over on the way, at e (how far along its way it is, 0 → 1): the angle it has turned (0 → π, over the
 * middle of the way) and whether it shows its new side yet (past edge-on).
 */
export function turnAt(e: number, out = { angle: 0, over: false }): { angle: number; over: boolean } {
  const q = Math.min(1, Math.max(0, (e - 0.1) / 0.8));
  out.angle = easeInOut(q) * Math.PI;
  out.over = out.angle >= Math.PI / 2;
  return out;
}

/** A stand-in's opacity at progress p: whole until the last fifth of its flight, where it merges into its destination. */
export function standInOpacity(p: number, vanish = false): number {
  if (vanish) return 1 - easeOut(p);
  return p < 0.8 ? 1 : Math.max(0, 1 - (p - 0.8) / 0.2);
}

/** A strike lunge (0 → 1 → 0 of its reach): out fast, back more slowly. */
export function lungeAt(p: number): number {
  if (p <= 0 || p >= 1) return 0;
  return p < 0.35 ? easeOut(p / 0.35) : 1 - easeInOut((p - 0.35) / 0.65);
}

/** A rising number at progress p: how far it has risen (0 → 1), its opacity, and its size (a small punch as it appears). */
export function floaterAt(p: number, reduced: boolean, out = { rise: 0, opacity: 0, scale: 1 }): { rise: number; opacity: number; scale: number } {
  out.opacity = p < 0.1 ? p / 0.1 : p > 0.6 ? Math.max(0, 1 - (p - 0.6) / 0.4) : 1;
  out.scale = reduced ? 1 : p < 0.2 ? 1.15 - 0.15 * easeOut(p / 0.2) : 1;
  out.rise = easeOut(p);
  return out;
}

/**
 * A riffle shuffle of ``n`` cards on a library, at progress p: card i's offset from the pile's top, in the pile's own
 * frame (dx across the pile, dy up, and a small turn). The lower half splits to one side and the upper half to the
 * other, then they fall back in, interleaved, one by one.
 */
export function riffleAt(i: number, n: number, p: number, width: number, thick: number, out = { dx: 0, dy: 0, turn: 0 }): { dx: number; dy: number; turn: number } {
  const half = Math.ceil(n / 2);
  const side = i < half ? -1 : 1;
  const k = i < half ? i : i - half; // place within its half
  const order = k * 2 + (i < half ? 0 : 1); // where it lands in the interleaved pile
  const split = 0.42;
  if (p <= split) {
    const s = easeOut(p / split);
    out.dx = side * width * 0.62 * s;
    out.dy = k * thick + 0.14 * s;
    out.turn = side * -0.1 * s;
    return out;
  }
  // the halves fall back in turn, bottom first, each card a little after the last
  const q = (p - split) / (1 - split);
  const start = (order / n) * 0.5;
  const s = q <= start ? 0 : easeOut(Math.min(1, (q - start) / 0.5));
  out.dx = side * width * 0.62 * (1 - s);
  out.dy = (k * thick + 0.14) * (1 - s) + order * thick * s;
  out.turn = side * -0.1 * (1 - s);
  return out;
}
