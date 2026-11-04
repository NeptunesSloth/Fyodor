/**
 * The zone wells beside each mat (the candlelit card room): every pile lies in a shallow well set into the walnut, a
 * little larger than a card, lined in dark tooled leather with a gold fillet and a roll of gold dots inside its edge, a
 * soft shadow under its lip so it reads as sunk. Empty, its zone's glyph is pressed faintly into the leather (blind
 * tooling: game/zoneGlyphs.ts, game-icons.net). The command zone's well is lined in dark velvet in the seat's colour.
 *
 * Under each well, as I see it, its brass nameplate: the zone's name in engraved Cinzel capitals (on a duel's table; a
 * table of three or more seats is seen from farther off, so the plate carries the zone's glyph instead), and for the
 * library, graveyard and exile how many cards are in it, in Inter numerals on a blackened inset. Counts are public.
 *
 * Drawn on one canvas per pile (the well and its plate one plane, one draw call), redrawn only when its count changes.
 */
import type { PileZone } from "./layout";
import { NAMEPLATE } from "./layout";
import { ZONE_GLYPH_PATHS } from "../game/zoneGlyphs";

/** The wells' fonts (Cinzel for the names, Inter for the numbers), once loaded: a well drawn before is drawn again. */
export function whenWellFontsReady(): Promise<void> {
  if (typeof document === "undefined" || !document.fonts?.load) return Promise.resolve();
  return Promise.all([document.fonts.load("700 40px Cinzel"), document.fonts.load('700 40px "Inter Variable"')]).then(() => undefined, () => undefined);
}

/** Canvas pixels per world unit. */
export const WELL_PX = 256;

/**
 * How much taller than wide a well's glyph and its plate's letters are drawn: a duel is seen low (DUEL_VIEW), so they
 * are drawn tall to read upright; a table of three or more seats is seen from well above.
 */
export function wellStretch(duel: boolean, far = false): number {
  // (the far row, seen lower still, more)
  return duel ? (far ? 2.2 : 1.7) : 1.1;
}


export interface WellArt {
  zone: PileZone;
  /** The name on the plate ("Library", "Partner"…). */
  label: string;
  /** Cards in the pile (null: no count, as the command zone). */
  count: number | null;
  /**
   * The command zone at a table of three or more seats: its commander's tax to pay, on the plate where a pile's count is
   * ("+4"; seen from that far off, the coin column's own tag is too small to read). Nothing at 0.
   */
  tax?: number;
  /** A duel's table: the name in words; more seats: the glyph. */
  duel: boolean;
  /** The seat's colour (the command zone's velvet). */
  color: string;
  /** The well's size and the plate's width and depth (world units: layout.ts plateWidth, plateDepth). */
  well: { w: number; h: number };
  plateW: number;
  plateH: number;
  /** The plate's middle right of the well's, as I see it (world units; the command zone's runs under its tax coins too). */
  plateDx: number;
  /** How much taller than wide its glyph and letters are drawn (wellStretch). */
  stretch: number;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}

/** The canvas size for a well piece. */
export function wellCanvasSize(a: Pick<WellArt, "well" | "plateW" | "plateH" | "plateDx">): [number, number] {
  const [lo, hi] = span(a);
  return [Math.round((hi - lo) * WELL_PX), Math.round((a.well.h + NAMEPLATE.gap + a.plateH) * WELL_PX)];
}

/** The piece's left and right ends from the well's middle (world units, as I see it). */
function span(a: Pick<WellArt, "well" | "plateW" | "plateDx">): [number, number] {
  return [Math.min(-a.well.w / 2, a.plateDx - a.plateW / 2), Math.max(a.well.w / 2, a.plateDx + a.plateW / 2)];
}



/** The zone's glyph (512-unit path) fitted into a box w wide, centred on (cx, cy), drawn `stretch` times taller than wide. */
function glyphPath(zone: PileZone, cx: number, cy: number, w: number, stretch: number): Path2D {
  const k = w / 512;
  const p = new Path2D();
  p.addPath(new Path2D(ZONE_GLYPH_PATHS[zone].d), new DOMMatrix([k, 0, 0, k * stretch, cx - 256 * k, cy - 256 * k * stretch]));
  return p;
}

/**
 * Draw a zone's well and nameplate (`a`) on `canvas` (sized by wellCanvasSize): the well at the top, centred, its plate
 * under it. `a.stretch`: how much taller than wide the glyph and the plate's letters are drawn (the table is seen at a
 * slant, so they read upright, as road markings do).
 */
export function drawWell(canvas: HTMLCanvasElement, a: WellArt): void {
  const stretch = a.stretch;
  const [W, H] = wellCanvasSize(a);
  if (canvas.width !== W || canvas.height !== H) {
    canvas.width = W;
    canvas.height = H;
  }
  const g = canvas.getContext("2d")!;
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.clearRect(0, 0, W, H);
  const ww = a.well.w * WELL_PX;
  const wh = a.well.h * WELL_PX;
  const [lo] = span(a);
  const wx = (-a.well.w / 2 - lo) * WELL_PX;
  const command = a.zone === "command";
  const r = 18;
  // as on the Oops I Baked a Pie table: the zone a rounded frame in the seat's colour on the panel's dark surface, its
  // glyph in that colour (seen when it's empty); no count (the user's call)
  roundRect(g, wx + 4, 4, ww - 8, wh - 8, r);
  g.fillStyle = "rgba(0, 0, 0, 0.22)";
  g.fill();
  g.strokeStyle = a.color;
  g.lineWidth = 6;
  g.stroke();
  const gw = ww * (command ? 0.5 : 0.46);
  const glyph = glyphPath(a.zone, wx + ww / 2, wh / 2, gw, Math.min(stretch, (wh * 0.6) / gw));
  g.fillStyle = a.color;
  g.fill(glyph);
}


