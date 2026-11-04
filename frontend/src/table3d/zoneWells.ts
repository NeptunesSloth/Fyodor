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
import { rng } from "./textures";

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

const GOLD = { hi: "#f6dc9a", mid: "#c9a056", low: "#8a6a30" };
const BRASS = { hi: "#ead197", light: "#cba664", mid: "#a47c40", dark: "#6c4c22" };

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

/** A colour, darkened toward black by `k` (0..1). */
function shade(hex: string, k: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  const n = m ? parseInt(m[1]!, 16) : 0x888888;
  const ch = (s: number) => Math.round(((n >> s) & 255) * (1 - k));
  return `rgb(${ch(16)}, ${ch(8)}, ${ch(0)})`;
}

/** Leather (or velvet) grain: fine speckle and a few creases, deterministic. */
function grain(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, seed: number, velvet: boolean): void {
  const rand = rng(seed);
  g.save();
  for (let i = 0; i < (w * h) / 22; i++) {
    const px = x + rand() * w;
    const py = y + rand() * h;
    const light = rand() > 0.5;
    g.fillStyle = light ? `rgba(255, 225, 180, ${velvet ? 0.035 : 0.05})` : "rgba(0, 0, 0, 0.18)";
    g.fillRect(px, py, velvet ? 1 : 1.6, velvet ? 2.2 : 1.6);
  }
  if (!velvet) {
    g.strokeStyle = "rgba(0, 0, 0, 0.16)";
    g.lineWidth = 1;
    for (let i = 0; i < 14; i++) {
      const px = x + rand() * w;
      const py = y + rand() * h;
      g.beginPath();
      g.moveTo(px, py);
      g.quadraticCurveTo(px + (rand() - 0.5) * 30, py + (rand() - 0.5) * 30, px + (rand() - 0.5) * 50, py + (rand() - 0.5) * 50);
      g.stroke();
    }
  }
  g.restore();
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
  const r = 16;
  // -- the cut in the wood: a dark edge, light caught on the lip's far (lower-right) wall
  roundRect(g, wx, 0, ww, wh, r);
  g.fillStyle = "#0b0705";
  g.fill();
  // -- the lining: tooled leather, or velvet in the seat's colour for the command zone
  const inset = 5;
  g.save();
  roundRect(g, wx + inset, inset, ww - inset * 2, wh - inset * 2, r - 4);
  g.clip();
  const lining = g.createRadialGradient(wx + ww * 0.45, wh * 0.42, 4, wx + ww / 2, wh / 2, Math.max(ww, wh) * 0.7);
  if (command) {
    lining.addColorStop(0, shade(a.color, 0.62));
    lining.addColorStop(1, shade(a.color, 0.86));
  } else {
    lining.addColorStop(0, "#3a2a1e");
    lining.addColorStop(1, "#1a110b");
  }
  g.fillStyle = lining;
  g.fillRect(wx, 0, ww, wh);
  grain(g, wx, 0, ww, wh, a.zone.length * 97 + (command ? 11 : 3), command);
  // the glyph, pressed in (blind tooling): darker than the leather, with light caught on its lower edges
  const gw = ww * (command ? 0.62 : 0.56);
  const glyph = glyphPath(a.zone, wx + ww / 2, wh / 2, gw, Math.min(stretch, (wh * 0.62) / gw));
  g.save();
  g.translate(1.5, 2);
  g.fillStyle = command ? "rgba(255, 230, 170, 0.1)" : "rgba(255, 220, 160, 0.075)";
  g.fill(glyph);
  g.restore();
  g.fillStyle = command ? "rgba(0, 0, 0, 0.34)" : "rgba(0, 0, 0, 0.42)";
  g.fill(glyph);
  if (command) {
    // the crown's outline in gold leaf, faint
    g.strokeStyle = "rgba(214, 176, 100, 0.35)";
    g.lineWidth = 1.4;
    g.stroke(glyph);
  }
  // the gold tooling: a fillet inside the edge and a roll of dots inside that
  const t = 14;
  roundRect(g, wx + t, t, ww - t * 2, wh - t * 2, r - 8);
  g.strokeStyle = "rgba(0, 0, 0, 0.55)";
  g.lineWidth = 3.2;
  g.stroke();
  const fillet = g.createLinearGradient(wx, 0, wx + ww, wh);
  fillet.addColorStop(0, GOLD.hi);
  fillet.addColorStop(0.5, GOLD.mid);
  fillet.addColorStop(1, GOLD.low);
  g.strokeStyle = fillet;
  g.lineWidth = 3.4;
  g.stroke();
  const d = t + 11;
  roundRect(g, wx + d, d, ww - d * 2, wh - d * 2, r - 12);
  g.setLineDash([0.1, 10]);
  g.lineCap = "round";
  g.lineWidth = 4.4;
  g.strokeStyle = command ? "rgba(214, 176, 100, 0.55)" : "rgba(214, 176, 100, 0.7)";
  g.stroke();
  g.setLineDash([]);
  // the sink: the lip's shadow falls in from the top and left, soft, and the far walls catch a little light
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.85)";
  g.shadowBlur = 22;
  g.shadowOffsetX = 7;
  g.shadowOffsetY = 9;
  g.beginPath();
  g.rect(wx - 200, -200, ww + 400, wh + 400);
  g.roundRect(wx + inset, inset, ww - inset * 2, wh - inset * 2, r - 4);
  g.fillStyle = "#000";
  g.fill("evenodd");
  g.restore();
  g.restore();
  g.strokeStyle = "rgba(255, 214, 150, 0.16)";
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(wx + ww - r + 2, wh - 3);
  g.lineTo(wx + r, wh - 3);
  g.moveTo(wx + ww - 3, r);
  g.lineTo(wx + ww - 3, wh - r);
  g.stroke();
  drawPlate(g, a, (a.plateDx - a.plateW / 2 - lo) * WELL_PX, wh + NAMEPLATE.gap * WELL_PX, a.plateW * WELL_PX, a.plateH * WELL_PX, stretch);
}

/** The brass nameplate at (x, y), w × h canvas px: the name engraved (or the glyph), and the count on a blackened inset. */
function drawPlate(g: CanvasRenderingContext2D, a: WellArt, x: number, y: number, w: number, h: number, stretch: number): void {
  // its shadow on the wood, then the plate: bevelled, brushed, two small pins
  g.save();
  g.shadowColor = "rgba(0, 0, 0, 0.7)";
  g.shadowBlur = 6;
  g.shadowOffsetX = 2;
  g.shadowOffsetY = 3;
  roundRect(g, x + 2, y + 2, w - 4, h - 4, 7);
  g.fillStyle = "#24170a";
  g.fill();
  g.restore();
  const face = g.createLinearGradient(x, y, x + w * 0.35, y + h * 1.6);
  face.addColorStop(0, BRASS.hi);
  face.addColorStop(0.35, BRASS.light);
  face.addColorStop(0.8, BRASS.mid);
  face.addColorStop(1, BRASS.dark);
  roundRect(g, x + 4, y + 4, w - 8, h - 8, 5);
  g.fillStyle = face;
  g.fill();
  g.save();
  g.clip();
  const rand = rng(Math.round(w + h));
  for (let i = 0; i < 40; i++) {
    g.fillStyle = rand() > 0.5 ? "rgba(255, 248, 225, 0.08)" : "rgba(70, 45, 15, 0.08)";
    g.fillRect(x, y + rand() * h, w, 1);
  }
  g.restore();
  // the bevel: a lit top edge, a shaded bottom one
  g.strokeStyle = "rgba(255, 246, 215, 0.55)";
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(x + 9, y + 5);
  g.lineTo(x + w - 9, y + 5);
  g.stroke();
  g.strokeStyle = "rgba(60, 38, 12, 0.6)";
  g.beginPath();
  g.moveTo(x + 9, y + h - 5);
  g.lineTo(x + w - 9, y + h - 5);
  g.stroke();
  const pin = (px: number) => {
    const py = y + h / 2;
    g.fillStyle = "rgba(50, 32, 10, 0.75)";
    g.beginPath();
    g.ellipse(px + 0.6, py + 1, 3.6, 3.6 * Math.min(1.6, stretch * 0.8), 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = BRASS.hi;
    g.beginPath();
    g.ellipse(px, py, 2.6, 2.6 * Math.min(1.6, stretch * 0.8), 0, 0, Math.PI * 2);
    g.fill();
  };
  const number = a.count !== null ? String(a.count) : a.tax ? `+${a.tax}` : null;
  const counted = number !== null;
  // the count: Inter numerals, warm ivory on a blackened inset at the plate's right end
  let right = x + w - 26;
  if (counted) {
    const n = number!;
    const cw = Math.max(92, 34 + n.length * 28);
    const cx = x + w - 8 - cw;
    roundRect(g, cx, y + 8, cw, h - 16, 4);
    const inset = g.createLinearGradient(0, y + 8, 0, y + h - 8);
    inset.addColorStop(0, "#0c0907");
    inset.addColorStop(1, "#231a12");
    g.fillStyle = inset;
    g.fill();
    g.strokeStyle = "rgba(255, 240, 200, 0.35)";
    g.lineWidth = 1;
    g.stroke();
    const px = Math.min((h - 22) / stretch, (cw - 10) / (n.length * 0.62));
    g.font = `700 ${px}px "Inter Variable", Inter, Arial, sans-serif`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.save();
    g.translate(cx + cw / 2, y + h / 2 + 1);
    g.scale(1, stretch);
    g.fillStyle = a.count === null ? "#ecc67c" : a.count === 0 ? "#a89a80" : "#f4e6c4"; // (the tax in brass)
    g.fillText(n, 0, 0);
    g.restore();
    right = cx - 10;
  } else pin(x + w - 14);
  const left = x + (counted ? 22 : 26);
  if (!counted) pin(x + 14);
  const engrave = (draw: (dx: number, dy: number, style: string) => void) => {
    draw(0.8, 1.4, "rgba(255, 244, 214, 0.55)"); // the lit lower edge of the cut
    draw(0, 0, "#2a1a08");
  };
  if (a.duel) {
    // the name, engraved in Cinzel capitals, condensed a little to fit
    const text = a.label.toUpperCase();
    const span = right - left - (counted ? 8 : 0);
    // as tall as the plate allows (its capitals about 0.6 of it), narrowed to at most 0.8 of their width, else smaller
    const font = (px: number) => `700 ${px}px Cinzel, "Trajan Pro", Georgia, serif`;
    g.font = font(100);
    const per100 = Math.max(1, g.measureText(text).width);
    const px = Math.min((h * 0.6) / (stretch * 0.7), (span * 100) / (per100 * 0.8));
    g.font = font(px);
    const cond = Math.min(1, span / Math.max(1, g.measureText(text).width));
    g.textAlign = "center";
    g.textBaseline = "middle";
    const cx = counted ? (left + right) / 2 : x + w / 2;
    engrave((dx, dy, style) => {
      g.save();
      g.translate(cx + dx, y + h / 2 + 2 + dy);
      g.scale(cond, stretch);
      g.fillStyle = style;
      g.fillText(text, 0, 0);
      g.restore();
    });
  } else {
    // the glyph, engraved, in the plate's free span
    const gh = (h - 20) / stretch;
    const cx = counted ? (left + right) / 2 : x + w / 2;
    engrave((dx, dy, style) => {
      g.fillStyle = style;
      g.fill(glyphPath(a.zone, cx + dx, y + h / 2 + dy, gh * 1.15, stretch));
    });
  }
}
