/**
 * The public choice wheel (docs/TABLETOP_QOL_MILESTONE.md): a radial picker for a pending decision that is one choice among a few
 * public values (a color, a creature or card type, a player, a number, heads or tails, a public option). The pure part lives here: which
 * decisions get it, how an option looks, the ring's layout and the keys. ChoiceWheel.tsx draws it.
 *
 * The server says what is public (`public_choice`, app/rules/view.py: from the rules step, never for a target, a cost, a secret choice
 * or hidden cards); the client only checks the wheel fits. The decision stays a server-authoritative Decision: the wheel sends exactly
 * the list's own `choose` answer.
 */
import type { DecisionOptionView, DecisionView } from "../../types/game";

export const WHEEL_MIN = 2;
export const WHEEL_MAX = 12;
/** Longer option texts (a mode, a long card name) read better in the list. A player's name always fits (the hub shows it whole). */
export const WHEEL_LABEL_MAX = 24;

/**
 * Does this decision get the wheel? Conservative: the chooser's own view of a single `choose_one` the server marked public, 2–12 distinct
 * options, none naming a card (a target on the table, a card looked at) or typed (a card name, a secret number), nothing to remember or
 * cancel and no presentation of its own (a payment). Anything else keeps the existing list.
 */
export function wheelEligible(d: DecisionView | null | undefined, playerIds: readonly string[] = []): boolean {
  if (!d || d.kind !== "choose_one" || d.public_choice !== true || !d.options) return false;
  if ((d.min_choices ?? 1) !== 1 || (d.max_choices ?? 1) !== 1) return false;
  if (d.display || d.rememberable || d.cancelable) return false;
  const options = d.options;
  if (options.length < WHEEL_MIN || options.length > WHEEL_MAX) return false;
  if (new Set(options.map((o) => o.id)).size !== options.length) return false;
  return options.every((o) => !o.card_id && !o.group && !o.id.startsWith("__")
    && (playerIds.includes(o.id) || (o.label.trim() !== "" && o.label.length <= WHEEL_LABEL_MAX)));
}

/** How an option is drawn: a player's seat chip, a color's mana symbol, mana symbols, a number, or its words. */
export type WheelFace =
  | { kind: "player"; initial: string; color: string }
  | { kind: "color"; symbol: string }
  | { kind: "mana" }
  | { kind: "number" }
  | { kind: "text" };

const COLOR_SYMBOL: Record<string, string> = { white: "W", blue: "U", black: "B", red: "R", green: "G", colorless: "C" };
const MANA_ONLY = /^(\{[^{}]+\})+$/;
const NUMBER = /^\d{1,4}$/;

export function faceOf(o: DecisionOptionView, players: readonly { id: string; name: string; color: string }[]): WheelFace {
  const p = players.find((x) => x.id === o.id);
  if (p) return { kind: "player", initial: (p.name.trim()[0] ?? "?").toUpperCase(), color: p.color };
  const label = o.label.trim();
  const symbol = COLOR_SYMBOL[label.toLowerCase()];
  if (symbol) return { kind: "color", symbol };
  if (MANA_ONLY.test(label)) return { kind: "mana" };
  if (NUMBER.test(label)) return { kind: "number" };
  return { kind: "text" };
}

/** A wheel of numbers: typed digits pick the number itself ("1", "0" → 10), not the option's position. */
export function isNumberWheel(labels: readonly string[]): boolean {
  return labels.length > 0 && labels.every((l) => NUMBER.test(l.trim()));
}

/** A token's size on the ring: a round disc for a number or mana symbols, a pill with a chip / symbol, the words and a key otherwise. */
export interface Box { w: number; h: number; disc: boolean }

export const DISC = 52;
const PILL_H = 38;

export function boxOf(face: WheelFace, label: string): Box {
  if (face.kind === "number") return { w: DISC, h: DISC, disc: true };
  if (face.kind === "mana") return { w: Math.max(DISC, 16 + (label.match(/\{/g) ?? []).length * 22), h: DISC, disc: true };
  const lead = face.kind === "text" ? 0 : 29; // the seat chip or mana symbol, and its gap
  const words = Math.min(label.trim().length, WHEEL_LABEL_MAX) * 7.8; // (generous: a label is never cut short; a long name is, the hub shows it)
  return { w: Math.round(Math.min(230, Math.max(76, 53 + lead + words))), h: PILL_H, disc: false }; // padding, the key, gaps
}

/** The hub (the dial's centre, which shows the aimed option) and the space kept around each token. */
export const HUB = 46;
const GAP = 8;
const DIAL_PAD = 34;

/** Each option's direction from the centre (radians, clockwise from the right, y down): the first at the top, then clockwise; two sit left and right. */
export function ringAngles(n: number): number[] {
  if (n === 2) return [Math.PI, 0];
  return Array.from({ length: n }, (_, i) => -Math.PI / 2 + (i * 2 * Math.PI) / n);
}

export interface WheelLayout {
  /** The ring's radius: token centres sit on it. */
  radius: number;
  /** The dial behind the tokens (the pointer's aiming area). */
  dial: number;
  points: { x: number; y: number }[];
  boxes: Box[];
  /** The extent of the dial and tokens around the centre. */
  bounds: { left: number; top: number; right: number; bottom: number };
}

function overlaps(a: { x: number; y: number }, ab: Box, b: { x: number; y: number }, bb: Box): boolean {
  return Math.abs(a.x - b.x) < (ab.w + bb.w) / 2 + GAP && Math.abs(a.y - b.y) < (ab.h + bb.h) / 2 + GAP;
}

function clearOfHub(p: { x: number; y: number }, b: Box): boolean {
  return Math.hypot(Math.max(Math.abs(p.x) - b.w / 2, 0), Math.max(Math.abs(p.y) - b.h / 2, 0)) >= HUB + GAP;
}

/** The smallest ring on which no two tokens touch and none covers the hub. */
export function wheelLayout(boxes: Box[]): WheelLayout {
  const angles = ringAngles(boxes.length);
  const place = (r: number) => angles.map((a) => ({ x: Math.round(r * Math.cos(a)), y: Math.round(r * Math.sin(a)) }));
  let radius = 72;
  let points = place(radius);
  const fits = () => points.every((p, i) => clearOfHub(p, boxes[i]!) && points.every((q, j) => j <= i || !overlaps(p, boxes[i]!, q, boxes[j]!)));
  while (radius < 480 && !fits()) {
    radius += 4;
    points = place(radius);
  }
  const dial = radius + DIAL_PAD;
  const bounds = { left: -dial, top: -dial, right: dial, bottom: dial };
  points.forEach((p, i) => {
    const b = boxes[i]!;
    bounds.left = Math.min(bounds.left, p.x - b.w / 2);
    bounds.right = Math.max(bounds.right, p.x + b.w / 2);
    bounds.top = Math.min(bounds.top, p.y - b.h / 2);
    bounds.bottom = Math.max(bounds.bottom, p.y + b.h / 2);
  });
  return { radius, dial, points, boxes, bounds };
}

/** Space for the prompt plaque above the dial (two lines and the "List" key). */
export const CAPTION = { h: 58, halfW: 210 };
/** A wheel bigger than this is no longer quick to aim at (many long options): the list is better. */
export const WHEEL_MAX_SIZE = { w: 760, h: 620 };

/** Does the wheel, with its prompt above, fit this screen (and stay small enough to be quick)? If not, the list is shown. */
export function wheelFits(layout: WheelLayout, view: { w: number; h: number }, margin = 12): boolean {
  const { left, top, right, bottom } = layout.bounds;
  const w = Math.max(right, CAPTION.halfW) - Math.min(left, -CAPTION.halfW);
  const h = bottom - top + CAPTION.h;
  return w <= Math.min(view.w - 2 * margin, WHEEL_MAX_SIZE.w) && h <= Math.min(view.h - 2 * margin, WHEEL_MAX_SIZE.h);
}

/**
 * Where the wheel's centre goes: at the pointer (or the middle of the screen when the player was using the keyboard: `anchor` null),
 * moved just enough that the dial, every token and the prompt above it stay on screen.
 */
export function placeWheel(anchor: { x: number; y: number } | null, layout: WheelLayout, view: { w: number; h: number }, margin = 12): { x: number; y: number } {
  const { left, top, right, bottom } = layout.bounds;
  const fit = (v: number, lo: number, hi: number) => (lo > hi ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, v)));
  const x = fit(anchor?.x ?? view.w / 2, margin - Math.min(left, -CAPTION.halfW), view.w - margin - Math.max(right, CAPTION.halfW));
  const y = fit(anchor?.y ?? view.h / 2, margin + CAPTION.h - top, view.h - margin - bottom);
  return { x: Math.round(x), y: Math.round(y) };
}

/** The option the pointer aims at from the centre (the nearest by direction), or null inside the hub. */
export function indexAt(dx: number, dy: number, n: number): number | null {
  if (n < 1 || Math.hypot(dx, dy) < HUB) return null;
  const a = Math.atan2(dy, dx);
  const off = (b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));
  const angles = ringAngles(n);
  return angles.reduce((best, b, i) => (off(b) < off(angles[best]!) ? i : best), 0);
}

/** The keyboard: the aimed option (-1: none yet) and the digits typed so far (several make one number: "1", "2" → 12). */
export interface WheelKeys { index: number; typed: string; at: number }
export const NO_KEYS: WheelKeys = { index: -1, typed: "", at: 0 };
/** Digits typed within this long of each other make one number. */
export const TYPE_MS = 900;

/**
 * One key press on the wheel. Digits aim at an option — its number on a wheel of numbers, otherwise its position (1–9, 0 for the tenth,
 * two digits for 10–12); arrows go round the ring (Right/Down clockwise; with two options Left and Right pick that side); Home/End the
 * first/last; Enter chooses the aimed option; Esc falls back to the list. Returns null for a key the wheel doesn't use: Enter with nothing
 * aimed yet (a held key never answers) and Space, which stays the table's (skip, pass) unless a focused token takes it as a button.
 */
export function wheelKey(keys: WheelKeys, key: string, labels: readonly string[], now: number): { keys: WheelKeys; act: "choose" | "list" | null } | null {
  const n = labels.length;
  const aim = (index: number): { keys: WheelKeys; act: null } => ({ keys: { index, typed: "", at: 0 }, act: null });
  const step = (dir: 1 | -1) => (n === 2 ? (dir > 0 ? 1 : 0) : keys.index < 0 ? (dir > 0 ? 0 : n - 1) : (keys.index + dir + n) % n);
  switch (key) {
    case "Escape":
      return { keys, act: "list" };
    case "Enter":
      return keys.index >= 0 && keys.index < n ? { keys, act: "choose" } : null;
    case "ArrowRight":
    case "ArrowDown":
      return aim(step(1));
    case "ArrowLeft":
    case "ArrowUp":
      return aim(step(-1));
    case "Home":
      return aim(0);
    case "End":
      return aim(n - 1);
  }
  if (!/^\d$/.test(key)) return null;
  const numbers = isNumberWheel(labels);
  const find = (typed: string): number => {
    if (numbers) return labels.findIndex((l) => Number(l.trim()) === Number(typed));
    const pos = typed === "0" ? 10 : Number(typed);
    return pos >= 1 && pos <= n ? pos - 1 : -1;
  };
  const joined = keys.typed && now - keys.at < TYPE_MS ? keys.typed + key : "";
  for (const typed of joined ? [joined, key] : [key]) {
    const index = find(typed);
    if (index >= 0) return { keys: { index, typed, at: now }, act: null };
  }
  return { keys: { ...keys, typed: "", at: 0 }, act: null }; // no such option: the digit is still the wheel's (not a camera key)
}
