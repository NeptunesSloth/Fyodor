/**
 * How my hand is laid out along the bottom of the screen (2D and 3D tables alike), whatever its size.
 *
 * - **fan**: up to STRIP_AT cards, all of them on screen at once. The more cards, the more they overlap, but the whole
 *   hand always fits the width it has, and every card keeps at least a sliver (its name corner) showing.
 * - **strip**: a bigger hand (a Grimoire draw loop: 77 cards) is a flat row that scrolls sideways (wheel, the arrow
 *   keys, the ‹ › buttons), each card a readable sliver; "Hand (N)" opens the whole hand as a grid (the zone browser).
 *
 * Pure math in CSS pixels, so it is unit-tested; Hand.tsx measures the width and sets the CSS variables.
 */

/** More cards than this and the hand becomes a scrolling strip (unless the fan still leaves every card a wide sliver). */
export const STRIP_AT = 20;
/** The thinnest sliver a fanned card may show (px), whatever its width: enough for the start of its name. */
export const MIN_SLIVER_PX = 24;
/** The thinnest sliver as a share of the card's width (its name corner). */
export const MIN_SLIVER = 0.22;
/** In the strip each card shows this share of its width: the name reads, the strip scrolls. */
export const STRIP_SLIVER = 0.3;
/** A card's height for its width (63 × 88 mm). */
export const CARD_RATIO = 88 / 63;

export type HandStyle = "arc" | "row";

export interface HandLayout {
  mode: "fan" | "strip";
  /** Card width (px). */
  cardW: number;
  /** Distance from one card's left edge to the next one's (px). */
  step: number;
  /** Width of the box the cards sit in (px): the fan's own width, or the strip's visible width. */
  boxW: number;
  /** Width of all the cards side by side (px): equal to boxW for a fan, wider than boxW for a strip (it scrolls). */
  contentW: number;
  /** Turn between neighbouring cards of the arc (degrees; 0 for a row or a strip). */
  spread: number;
}

/** The thinnest sliver a card of width `cardW` may show (px). */
export function minSliver(cardW: number): number {
  return Math.max(MIN_SLIVER_PX, cardW * MIN_SLIVER);
}

/** How far apart a few cards sit when there's room (px): the 3D arc overlaps them a little, the 2D row hardly. */
export function naturalStep(count: number, cardW: number, style: HandStyle): number {
  const overlap = style === "arc"
    ? Math.min(0.6, Math.max(0.12, (count - 3) * 0.07))
    : Math.min(0.75, Math.max(0, ((count - 8) * 9) / 104));
  return cardW * (1 - overlap);
}

/** The width of `count` cards `step` apart. */
export function rowWidth(count: number, cardW: number, step: number): number {
  return count > 0 ? cardW + (count - 1) * step : 0;
}

/**
 * The layout for `count` cards of width `cardW` in `avail` px of screen width.
 * A fan always fits `avail`; a strip is `avail` wide and scrolls (its content is always wider than that).
 */
export function handLayout(count: number, avail: number, cardW: number, style: HandStyle = "arc"): HandLayout {
  const n = Math.max(0, Math.floor(count));
  const room = Math.max(cardW, avail);
  const natural = naturalStep(n, cardW, style);
  const fit = n > 1 ? (room - cardW) / (n - 1) : cardW;
  const sliver = minSliver(cardW);
  const stripStep = Math.max(sliver, cardW * STRIP_SLIVER);
  // a fan while every card keeps its sliver; past STRIP_AT cards only while the slivers are as wide as the strip's
  const fan = n <= 1 || (fit >= sliver && (n <= STRIP_AT || fit >= stripStep));
  if (fan) {
    const step = Math.min(natural, fit);
    const w = rowWidth(n, cardW, step);
    const spread = style === "arc" && n > 1 ? Math.min(4.5, 34 / n) : 0;
    return { mode: "fan", cardW, step, boxW: w, contentW: w, spread };
  }
  return { mode: "strip", cardW, step: stripStep, boxW: room, contentW: rowWidth(n, cardW, stripStep), spread: 0 };
}

/** The cards a strip shows scrolled `scrollLeft` px along (1-based, inclusive): "1–23 of 77". */
export function stripRange(count: number, layout: HandLayout, scrollLeft: number): { first: number; last: number } {
  if (count <= 0) return { first: 0, last: 0 };
  const first = Math.min(count, Math.max(1, Math.floor(scrollLeft / layout.step + 0.5) + 1));
  const last = Math.min(count, Math.max(first, Math.floor((scrollLeft + layout.boxW - layout.cardW) / layout.step + 0.5) + 1));
  return { first, last };
}

/**
 * Where my hand may spread on the screen: the screen width less a margin each side (kept equal, so a fan stays centred).
 * On the 3D table the turn dial sits over the bottom right corner, so the hand keeps clear of it on both sides.
 */
export function handRoom(width: number, three: boolean): number {
  const margin = three ? (width >= 1100 ? 340 : 150) : 150;
  return Math.max(0, width - 2 * margin);
}

/** A card's width on the screen: the 3D table sizes it to the window (as its CSS used to: clamp(112px, 8.4vw, 184px)). */
export function handCardWidth(viewportW: number, three: boolean): number {
  return three ? Math.min(184, Math.max(112, viewportW * 0.084)) : 104;
}
