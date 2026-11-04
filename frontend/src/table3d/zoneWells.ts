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
  const r = 14;
  // printed on the zone strip's limed oak (TableScene stripMaterial), as on Tabletop Simulator's Commander tables: a
  // frame in dark ink, the zone's glyph large inside it, its name printed under the glyph; light on the felt side
  roundRect(g, wx + 3, 3, ww - 6, wh - 6, r);
  g.fillStyle = command ? hexA(a.color, 0.16) : "rgba(70, 48, 24, 0.08)";
  g.fill();
  g.strokeStyle = INK;
  g.lineWidth = 5;
  g.stroke();
  roundRect(g, wx + 13, 13, ww - 26, wh - 26, r - 6);
  g.strokeStyle = "rgba(43, 29, 16, 0.55)";
  g.lineWidth = 1.6;
  g.stroke();
  // the glyph, large in the frame (the name is printed under the frame, where the pile's cards never cover it)
  const gw = ww * (command ? 0.56 : 0.52);
  const glyph = glyphPath(a.zone, wx + ww / 2, wh / 2, gw, Math.min(stretch, (wh * 0.66) / gw));
  g.fillStyle = "rgba(43, 29, 16, 0.72)";
  g.fill(glyph);
  drawPlate(g, a, (a.plateDx - a.plateW / 2 - lo) * WELL_PX, wh + NAMEPLATE.gap * WELL_PX, a.plateW * WELL_PX, a.plateH * WELL_PX, stretch);
}

/** The strip's printing ink: a warm near-black brown. */
const INK = "#2b1d10";

/** A #rrggbb colour at alpha `k`. */
function hexA(hex: string, k: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  const n = m ? parseInt(m[1]!, 16) : 0x888888;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${k})`;
}

/**
 * Under the frame (x, y, w × h canvas px), printed on the oak: the zone's name in Cinzel capitals, and its card count in
 * an ink badge beside it (the command zone: its name alone; its tax is struck on its top coin). At three or more seats,
 * where the strip is narrow, the badge alone, centred.
 */
function drawPlate(g: CanvasRenderingContext2D, a: WellArt, x: number, y: number, w: number, h: number, stretch: number): void {
  const n = a.count !== null ? String(a.count) : null;
  const bh = h - 10;
  let badgeW = 0;
  if (n !== null) {
    const px = Math.min(bh / (stretch * 0.8), 200);
    g.font = `800 ${px}px "Inter Variable", Inter, Arial, sans-serif`;
    badgeW = Math.max(bh * 1.1 / Math.max(1, stretch * 0.6), g.measureText(n).width + 34);
  }
  const showName = a.duel || n === null;
  const name = a.label.toUpperCase();
  const font = (px: number) => `700 ${px}px Cinzel, "Trajan Pro", Georgia, serif`;
  g.font = font(100);
  const per100 = Math.max(1, g.measureText(name).width);
  const gap = n !== null && showName ? 14 : 0;
  const nameRoom = showName ? w - 12 - badgeW - gap : 0;
  // every name at one height (its capitals about 0.6 of the plate), a long one narrowed to fit rather than made smaller
  const npx = showName ? Math.min((h * 0.62) / (stretch * 0.7), (nameRoom * 100) / (per100 * 0.62)) : 0;
  g.font = font(npx);
  const cond = showName ? Math.min(1, nameRoom / Math.max(1, g.measureText(name).width)) : 1;
  const nameW = showName ? g.measureText(name).width * cond : 0;
  const total = nameW + gap + badgeW;
  let left = x + (w - total) / 2;
  g.textBaseline = "middle";
  if (showName) {
    g.textAlign = "left";
    g.save();
    g.translate(left, y + h / 2 + 2);
    g.scale(cond, stretch);
    g.fillStyle = INK;
    g.fillText(name, 0, 0);
    g.restore();
    left += nameW + gap;
  }
  if (n === null) return;
  roundRect(g, left, y + 5, badgeW, bh, Math.min(bh / 2, 20));
  g.fillStyle = a.count === 0 ? "rgba(43, 29, 16, 0.45)" : INK;
  g.fill();
  g.font = `800 ${Math.min(bh / (stretch * 0.8), 200)}px "Inter Variable", Inter, Arial, sans-serif`;
  g.textAlign = "center";
  g.save();
  g.translate(left + badgeW / 2, y + 5 + bh / 2 + 1);
  g.scale(1, stretch);
  g.fillStyle = "#f4ead2";
  g.fillText(n, 0, 0);
  g.restore();
}
