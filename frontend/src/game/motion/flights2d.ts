/**
 * TABLE MOTION on the 2D table: what to show for the events between two views (tableEvents.ts), as plain data the DOM layer
 * (Motion2D.tsx) measures and plays. Pure: no DOM here, so it is all tested.
 *
 * Privacy: a face is only ever a card view that this viewer's own view shows face up (isVisible); everything else is a card back in
 * its owner's sleeve. A card that leaves a hidden zone starts as a back and turns face up as it lands; a card going into one turns
 * face down on the way.
 */
import { isVisible, type GameCard, type GameView, type VisibleCard } from "../../types/game";
import { MOTION } from "./timing";
import { zoneName, zoneOwner, type TableEvent } from "./tableEvents";

/** Where a flight starts or lands: a card's element if there is one, else its zone's (a pile, a hand, a seat). */
export interface Spot {
  zone: string;
  card?: string;
}

export type FlightKind = "card" | "draw" | "mill";

export interface FlightPlan {
  key: string;
  /** The real card (its element is hidden at the destination until the flight lands); null: hidden traffic (card backs). */
  id: string | null;
  from: Spot;
  to: Spot;
  /** The face shown when it leaves and when it lands; null: a card back. */
  start: GameCard | null;
  end: GameCard | null;
  /** Whose sleeve a back wears. */
  owner: string | null;
  kind: FlightKind;
  /** For hidden traffic into a hand: this is the nth newest card back there (0 = the last one). */
  nth?: number;
  /** It comes out of a permanent (an ability): it grows in from that card instead of being a copy of it. */
  emerge?: boolean;
  /** ms after the batch starts (the stagger of a group). */
  delay: number;
}

export interface MotionPlan {
  flights: FlightPlan[];
  /** Cards made here (a token, a copy): they settle in where they are. */
  appear: string[];
  /** Cards gone from the game (a token): they fade where they were. */
  vanish: { id: string; zone: string; card: GameCard }[];
  shuffles: string[];
  lunges: { id: string; toward: { player: string } | { card: string } }[];
  floaters: Floater[];
  lives: { player: string; from: number; to: number }[];
}

export type Floater = ({ card: string } | { player: string }) & { text: string; tone: "loss" | "gain" };

/** A signed number as text, with a real minus sign ("−3", "+5"): the sign is always there, never colour alone. */
export function signed(n: number): string {
  return n < 0 ? `\u2212${Math.abs(n)}` : `+${n}`;
}

/** What this viewer may see of a card in a view: the card when it is face up to them, else null (a back). */
export function faceIn(view: GameView, id: string): VisibleCard | null {
  const card = view.cards[id];
  return isVisible(card) ? card : null;
}

function kindOf(from: string | null, to: string): FlightKind {
  if (from && zoneName(from) === "library") return zoneName(to) === "hand" ? "draw" : "mill";
  return "card";
}

/** The stagger between cards of one moment: a group never staggers past ``MOTION.groupMax`` in all. */
export function staggerMs(n: number): number {
  return n <= 1 ? 0 : Math.min(MOTION.millStagger, MOTION.groupMax / (n - 1));
}

/** The plan for one batch of events. Cards past ``MOTION.maxFlights`` don't fly: they are just there (a board wipe, a library reset). */
export function planMotion(events: TableEvent[], next: GameView, prev: GameView): MotionPlan {
  const flights: Omit<FlightPlan, "delay">[] = [];
  const plan: MotionPlan = { flights: [], appear: [], vanish: [], shuffles: [], lunges: [], floaters: [], lives: [] };
  const owner = (view: GameView, id: string) => view.cards[id]?.owner ?? null;
  for (const e of events) {
    switch (e.kind) {
      case "move": {
        const was = faceIn(prev, e.id);
        const now = faceIn(next, e.id);
        flights.push({ key: `m:${e.id}`, id: e.id, from: { zone: e.from, card: e.id }, to: { zone: e.to, card: e.id },
          start: was ? now ?? was : null, end: now, owner: owner(next, e.id), kind: kindOf(e.from, e.to) });
        break;
      }
      case "arrive": {
        const now = faceIn(next, e.id);
        if (e.source) {
          // an ability: out of the permanent it comes from (wherever that is now), already face up
          const zone = next.cards[e.source]?.zone ?? prev.cards[e.source]?.zone;
          if (zone) {
            flights.push({ key: `a:${e.id}`, id: e.id, from: { zone, card: e.source }, to: { zone: e.to, card: e.id }, start: now, end: now,
              owner: owner(next, e.id), kind: "card", emerge: true });
          }
        } else if (e.from) {
          // out of a hidden zone (a draw, a mill, another player's cast): it leaves as a back and turns face up as it lands
          flights.push({ key: `a:${e.id}`, id: e.id, from: { zone: e.from }, to: { zone: e.to, card: e.id }, start: null, end: now,
            owner: owner(next, e.id), kind: kindOf(e.from, e.to) });
        } else if (zoneName(e.to) === "battlefield") {
          plan.appear.push(e.id);
        }
        break;
      }
      case "leave": {
        const was = faceIn(prev, e.id);
        if (e.to) {
          flights.push({ key: `l:${e.id}`, id: null, from: { zone: e.from, card: e.id }, to: { zone: e.to }, start: was, end: null,
            owner: owner(prev, e.id), kind: "card" });
        } else if (was && !was.ability && zoneName(e.from) === "battlefield") {
          plan.vanish.push({ id: e.id, zone: e.from, card: was });
        }
        break;
      }
      case "hidden": {
        for (let i = 0; i < e.n; i++) {
          flights.push({ key: `h:${e.from}>${e.to}:${i}`, id: null, from: { zone: e.from }, to: { zone: e.to }, start: null, end: null,
            owner: zoneOwner(e.from), kind: kindOf(e.from, e.to), nth: e.n - 1 - i });
        }
        break;
      }
      case "shuffle":
        if (!plan.shuffles.includes(e.zone)) plan.shuffles.push(e.zone);
        break;
      case "attack":
        if (e.target) plan.lunges.push({ id: e.id, toward: e.target.kind === "player" ? { player: e.target.id } : { card: e.target.id } });
        break;
      case "block":
        plan.lunges.push({ id: e.id, toward: { card: e.attacker } });
        break;
      case "damage":
        plan.floaters.push({ card: e.id, text: signed(-e.amount), tone: "loss" });
        break;
      case "life": {
        plan.floaters.push({ player: e.player, text: signed(e.delta), tone: e.delta < 0 ? "loss" : "gain" });
        const now = next.players.find((p) => p.id === e.player)?.life;
        if (now != null) plan.lives.push({ player: e.player, from: now - e.delta, to: now });
        break;
      }
    }
  }
  const flying = flights.slice(0, MOTION.maxFlights);
  const gap = staggerMs(flying.length);
  plan.flights = flying.map((f, i) => ({ ...f, delay: Math.round(i * gap) }));
  return plan;
}

// -- the DOM side's arithmetic (pure, so it is tested) --

export interface Box {
  /** Centre, in the layer's CSS pixels. */
  cx: number;
  cy: number;
  /** Untransformed size. */
  w: number;
  h: number;
  /** Rotation in degrees (a tapped card: 90). */
  rot: number;
}

export const CARD_ASPECT = 88 / 63;

/** A card-shaped box at an anchor that isn't a card (a hand strip, a seat's hand count): the card stands in its middle. */
export function cardIn(box: Box, height?: number): Box {
  const h = Math.max(28, Math.min(height ?? box.h, 140));
  return { cx: box.cx, cy: box.cy, w: h / CARD_ASPECT, h, rot: 0 };
}

/** How long a card travels: longer for a longer way, never past the per-card budget (research doc §4: ≤ 450 ms with the settle). */
export function travelMs(base: number, distance: number, settle: number): number {
  const scaled = base * Math.max(0.75, Math.min(1.3, 0.75 + distance / 1800));
  return Math.round(Math.min(scaled, 450 - settle));
}

/** The transform that puts a box drawn at ``to`` over ``from`` (FLIP: the ghost is laid out where it lands). */
export function transformFrom(from: Box, to: Box, scaleBy = 1): string {
  const s = (to.w > 0 ? from.w / to.w : 1) * scaleBy;
  return `translate(${round(from.cx - to.cx)}px, ${round(from.cy - to.cy)}px) rotate(${round(from.rot)}deg) scale(${round(s, 3)})`;
}

/** An attacker's or blocker's step toward what it fights: a short way along the line between them, never into it. */
export function lungeOffset(from: { x: number; y: number }, to: { x: number; y: number }, cardH: number): { dx: number; dy: number } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 1) return { dx: 0, dy: 0 };
  const reach = Math.max(10, Math.min(dist * 0.2, cardH * 0.36, 42));
  return { dx: round((dx / dist) * reach), dy: round((dy / dist) * reach) };
}

/** A life total rolling from one number to another: the number shown at ``t`` (0–1, already eased). */
export function rollValue(from: number, to: number, t: number): number {
  if (t >= 1) return to;
  return Math.round(from + (to - from) * Math.max(0, t));
}

/** How long the life total rolls: 300–600 ms, longer for a bigger change. */
export function rollMs(delta: number): number {
  return Math.round(300 + Math.min(300, Math.abs(delta) * 30));
}

function round(n: number, digits = 1): number {
  const k = 10 ** digits;
  return Math.round(n * k) / k;
}

/**
 * The elements a spot may be drawn by, best first. A card: its own element (battlefield, hand, stack row, command zone, an open zone
 * browser); then its zone: a pile, a hand (the newest card back in it, the strip, the seat's hand count), the stack, a battlefield.
 */
export function spotSelectors(spot: Spot): string[] {
  const zone = spot.zone;
  const name = zoneName(zone);
  const owner = zoneOwner(zone);
  const z = attr(zone);
  const out: string[] = [];
  if (spot.card) {
    const id = attr(spot.card);
    if (name === "battlefield") out.push(`.battlefield [data-card-id=${id}]`);
    else if (zone === "stack") out.push(`.chain-list [data-card-id=${id}] .chain-thumb`, `.chain-list [data-card-id=${id}]`);
    else if (name === "hand") out.push(`.hand [data-card-id=${id}]`);
    else if (name === "command") out.push(`.command-zone [data-card-id=${id}]`);
    out.push(`.zone-browser [data-card-id=${id}]`);
  }
  if (name === "library" || name === "graveyard" || name === "exile") out.push(`[data-drop=${z}] .pile-card`);
  else if (name === "hand") out.push(`[data-drop=${z}] .hand-card:last-child`, `[data-drop=${z}]`);
  else if (zone === "stack") out.push(".chain-list .chain-row.top .chain-thumb", "[data-drop=\"stack\"]", "[data-testid=\"rules-stack\"]");
  else out.push(`[data-drop=${z}]`);
  if (owner && name === "hand") out.push(`.t3d-seat[data-player-id=${attr(owner)}] .seat-hand`);
  if (owner) out.push(`.t3d-seat[data-player-id=${attr(owner)}]`);
  return out;
}

/** A quoted CSS attribute value. */
function attr(value: string): string {
  return `"${value.replace(/["\\]/g, "\\$&")}"`;
}
